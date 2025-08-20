from flask import Flask, request, jsonify, g
import os
import uuid
from dotenv import load_dotenv
from flask_cors import CORS
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from pydantic import ValidationError
from .services import llm_service, rag_service, grading_service, db_service
from .services.schemas import SearchRequest, AdviceRequest, FeedbackRequest, EvaluateRequest


load_dotenv()

def create_app() -> Flask:
	app = Flask(__name__)
	# Ensure UTF-8 JSON (no ASCII escaping) for Korean
	app.config["JSON_AS_ASCII"] = False
	CORS(app, resources={r"/api/*": {"origins": "*"}})

	REQUESTS = Counter("ai_requests_total", "Total API requests", ["path", "status"])
	LATENCY = Histogram("ai_request_latency_seconds", "Request latency", ["path"])
	LLM_TOKENS = Histogram("ai_llm_tokens", "LLM tokens used", ["path"])
	READY = Gauge("ai_ready", "Readiness state")
	LIVE = Gauge("ai_live", "Liveness state")
	READY.set(1)
	LIVE.set(1)

	@app.errorhandler(ValidationError)
	def _handle_validation_error(err: ValidationError):
		return jsonify({"error": "validation_error", "details": err.errors()}), 400

	@app.before_request
	def _inject_correlation_id():
		g.corr_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))

	@app.after_request
	def _add_common_headers(resp):
		resp.headers["X-Correlation-ID"] = g.get("corr_id", "")
		return resp

	@app.get("/healthz")
	def healthz():
		return jsonify({"status": "ok"})

	@app.get("/readyz")
	def readyz():
		return jsonify({"status": "ready"})

	@app.get("/metrics")
	def metrics():
		return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}

	# ----- v1 JSON APIs (internal) -----
	@app.post("/api/v1/advice")
	def advice():
		payload = AdviceRequest.model_validate(request.get_json(force=True) or {})
		with LATENCY.labels("/api/v1/advice").time():
			result = llm_service.generate_advice(student_id=payload.studentId, subject=payload.subject, grade=payload.grade, score=payload.score)
			REQUESTS.labels("/api/v1/advice", result.get("status", "OK")).inc()
			return jsonify(result), (200 if result.get("status") == "OK" else 202)

	@app.post("/api/v1/feedback")
	def feedback():
		payload = FeedbackRequest.model_validate(request.get_json(force=True) or {})
		with LATENCY.labels("/api/v1/feedback").time():
			result = llm_service.generate_feedback(student_id=payload.studentId, submission_id=payload.submissionId, answer=payload.answer, material_ids=payload.materialIds)
			REQUESTS.labels("/api/v1/feedback", result.get("status", "OK")).inc()
			return jsonify(result), (200 if result.get("status") == "OK" else 202)

	@app.post("/api/v1/search")
	def search():
		payload = SearchRequest.model_validate(request.get_json(force=True) or {})
		with LATENCY.labels("/api/v1/search").time():
			hits = rag_service.search_with_evidence(query=payload.query, material_ids=payload.materialIds, k=payload.k, subject=payload.subject, grade=payload.grade)
			REQUESTS.labels("/api/v1/search", "OK").inc()
			return jsonify({"status": "OK", "hits": hits})

	@app.post("/api/v1/grade")
	def grade():
		payload = request.get_json(force=True) or {}
		with LATENCY.labels("/api/v1/grade").time():
			test = payload.get("test")
			answers = payload.get("answers")
			student_answers = payload.get("studentAnswers")
			if test is None or answers is None or student_answers is None:
				REQUESTS.labels("/api/v1/grade", "BAD_REQUEST").inc()
				return jsonify({"error": "test, answers, studentAnswers required"}), 400
			score_detail = grading_service.grade_submission(test=test, answers=answers, student_answers=student_answers)
			REQUESTS.labels("/api/v1/grade", "OK").inc()
			return jsonify({"status": "OK", **score_detail})

	@app.post("/api/v1/evaluate")
	def evaluate():
		payload = EvaluateRequest.model_validate(request.get_json(force=True) or {})
		with LATENCY.labels("/api/v1/evaluate").time():
			result = llm_service.generate_evaluation_and_advice(
				student_id=payload.studentId or "",
				exam_id=payload.examId or "",
				subject=payload.subject,
				grade=str(payload.grade),
				question=payload.question,
				answer_key=str(payload.answer),
				student_answer=str(payload.studentAnswer),
				score=int(payload.score),
				material_ids=payload.materialIds,
			)
			if result.get("tokens"):
				LLM_TOKENS.labels("/api/v1/evaluate").observe(result["tokens"]) 
			REQUESTS.labels("/api/v1/evaluate", result.get("status", "OK")).inc()
			return jsonify(result), (200 if result.get("status") == "OK" else 202)

	@app.post("/api/v1/evaluate/batch")
	def evaluate_batch():
		from .services.schemas import EvaluateBatchRequest
		payload = EvaluateBatchRequest.model_validate(request.get_json(force=True) or {})
		replies = []
		n = min(len(payload.questions), len(payload.answers), len(payload.studentAnswers), len(payload.scores))
		for i in range(n):
			res = llm_service.generate_evaluation_and_advice(
				student_id=payload.studentId or "",
				exam_id=payload.examId or "",
				subject=payload.subject,
				grade=str(payload.grade),
				question=payload.questions[i],
				answer_key=str(payload.answers[i]),
				student_answer=str(payload.studentAnswers[i]),
				score=int(payload.scores[i]),
				material_ids=payload.materialIds,
			)
			replies.append(res)
		return jsonify({"status": "OK", "items": replies}), 200

	# ----- External agreed URLs mapping -----
	# AI 학습 조언
	@app.post("/api/exams/<string:exam_id>/ai/advice")
	def advice_for_exam(exam_id: str):
		payload = AdviceRequest.model_validate(request.get_json(force=True) or {})
		with LATENCY.labels("/api/exams/:id/ai/advice").time():
			result = llm_service.generate_advice(student_id=payload.studentId, subject=payload.subject, grade=payload.grade, score=payload.score)
			REQUESTS.labels("/api/exams/:id/ai/advice", result.get("status", "OK")).inc()
			# 표준 응답 형태: [{title, body}]
			if result.get("status") == "OK":
				return jsonify([{"title": "학습 조언", "body": result.get("advice", "")}]), 200
			return jsonify([]), 202

	# 문항 단위 피드백
	@app.post("/api/exams/<string:exam_id>/answers/<string:answer_id>/ai/feedback")
	def feedback_for_answer(exam_id: str, answer_id: str):
		payload = FeedbackRequest.model_validate(request.get_json(force=True) or {})
		with LATENCY.labels("/api/exams/:id/answers/:aid/ai/feedback").time():
			result = llm_service.generate_feedback(student_id=payload.studentId, submission_id=answer_id, answer=payload.answer, material_ids=payload.materialIds)
			REQUESTS.labels("/api/exams/:id/answers/:aid/ai/feedback", result.get("status", "OK")).inc()
			return jsonify(result), (200 if result.get("status") == "OK" else 202)

	# RAG 검색 (GET)
	@app.get("/api/ai/rag")
	def rag_get():
		query = request.args.get("query")
		if not query:
			return jsonify([]), 200
		topk = int(request.args.get("topK", 5))
		subject = request.args.get("subject")
		grade = request.args.get("grade")
		material_ids_param = request.args.get("materialIds") or ""
		material_ids = [x for x in material_ids_param.split(",") if x]
		with LATENCY.labels("/api/ai/rag").time():
			hits = rag_service.search_with_evidence(query=query, material_ids=material_ids, k=topk, subject=subject, grade=grade)
			REQUESTS.labels("/api/ai/rag", "OK").inc()
			resp = [{"docId": h.get("material_id"), "title": h.get("title"), "snippets": [h.get("snippet")]} for h in hits]
			return jsonify(resp), 200

	with app.app_context():
		db_service.init_databases()

	return app


app = create_app()
