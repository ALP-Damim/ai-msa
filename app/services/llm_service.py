from __future__ import annotations

from typing import Any, Dict, List, Optional
from time import perf_counter
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from openai import AzureOpenAI

from .config import load_azure_settings, resolve_azure_openai_credentials
from .db_service import get_session, AIAdvice, AIFeedback
from .rag_service import search_with_evidence
from .prompts import build_rubric_prompt


def _make_client() -> AzureOpenAI:
	settings = load_azure_settings()
	endpoint, api_key = resolve_azure_openai_credentials(settings)
	client = AzureOpenAI(
		api_key=api_key,
		api_version=settings.api_version,
		azure_endpoint=endpoint,
	)
	return client


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8), reraise=True)
def _chat(messages: List[Dict[str, str]]) -> Dict[str, Any]:
	settings = load_azure_settings()
	client = _make_client()
	t0 = perf_counter()
	resp = client.chat.completions.create(
		model=settings.llm_deployment,
		messages=messages,
		temperature=settings.temperature,
	)
	latency_ms = int((perf_counter() - t0) * 1000)
	used_tokens = getattr(resp.usage, "total_tokens", None)
	return {"text": resp.choices[0].message.content, "latency_ms": latency_ms, "tokens": used_tokens}


def _advice_prompt(student_id: str | None, subject: str | None, grade: str | None, score: int) -> List[Dict[str, str]]:
	user_prompt = (
		"너는 초등학생을 돕는 한국어 학습 코치야. 학생의 점수를 바탕으로 다음 형식으로 간결하게 작성해줘.\n"
		"1) 간단한 평가 한 줄\n2) 구체적 조언 3줄 이상(연습 방법 포함)\n3) 다음 단계 2~3개(불릿)\n"
		"항상 한국어로, 격려하는 어투로.")
	context = f"student_id={student_id or 'NA'}, subject={subject or 'NA'}, grade={grade or 'NA'}, score={score}"
	return [
		{"role": "system", "content": "모든 응답은 한국어로, 초등학생 눈높이에 맞춰 친절하고 간결하게 작성한다."},
		{"role": "user", "content": user_prompt + "\n" + context},
	]


def generate_advice(student_id: str | None, subject: str | None, grade: str | None, score: int) -> Dict[str, Any]:
	try:
		text = _chat(_advice_prompt(student_id, subject, grade, score))["text"]
		with get_session() as s:
			rec = AIAdvice(
				student_id=student_id or "",
				subject=subject or "",
				grade=grade or "",
				score=int(score),
				advice_text=text,
			)
			s.add(rec)
			s.commit()
		return {"status": "OK", "advice": text}
	except Exception:
		return {"status": "PENDING"}


def _feedback_prompt(answer: str, evidences: List[Dict[str, Any]]) -> List[Dict[str, str]]:
	context_lines = [f"- {e['snippet']} (material_id={e['material_id']})" for e in evidences]
	context = "\n".join(context_lines[:5])
	user_prompt = (
		"아래 학생의 답안과 근거를 보고 한국어로 피드백을 작성해줘.\n"
		"형식: 1) 칭찬 한 줄 2) 오류/오개념 한 줄 3) 구체적 개선 방법 2~3줄 4) 다음 연습 과제 한 줄.\n"
		"항상 초등학생 눈높이, 간결한 문장.")
	return [
		{"role": "system", "content": "모든 응답은 한국어로 작성하며, 친절하고 구체적인 학습 피드백을 제공한다."},
		{"role": "user", "content": user_prompt + f"\n학생 답안: {answer}\n근거:\n{context}"},
	]


def generate_feedback(student_id: str | None, submission_id: str | None, answer: str, material_ids: List[str]) -> Dict[str, Any]:
	evidences = search_with_evidence(query=answer, material_ids=material_ids, k=3)
	try:
		text = _chat(_feedback_prompt(answer, evidences))["text"]
		with get_session() as s:
			rec = AIFeedback(
				submission_id=submission_id or "",
				student_id=student_id or "",
				feedback_text=text,
				evidence_json=evidences,
			)
			s.add(rec)
			s.commit()
		return {"status": "OK", "feedback": text, "evidence": evidences}
	except Exception:
		return {"status": "PENDING"}


def generate_evaluation_and_advice(student_id: str, exam_id: str, subject: str, grade: str, question: str, answer_key: str, student_answer: str, score: int, material_ids: Optional[List[str]] = None) -> Dict[str, Any]:
	materials = material_ids or []
	evidences = search_with_evidence(query=question, material_ids=materials, k=3, subject=subject, grade=grade)
	try:
		resp = _chat(build_rubric_prompt(subject, grade, question, answer_key, student_answer, score))
		text = resp["text"]
		with get_session() as s:
			rec = AIAdvice(
				student_id=student_id,
				subject=subject,
				grade=grade,
				score=int(score),
				advice_text=text,
			)
			s.add(rec)
			s.commit()
		return {
			"status": "OK",
			"studentId": student_id,
			"examId": exam_id,
			"evaluation": text,
			"evidence": evidences,
			"latencyMs": resp["latency_ms"],
			"tokens": resp["tokens"],
		}
	except Exception:
		return {"status": "PENDING", "studentId": student_id, "examId": exam_id}
