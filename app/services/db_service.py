from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, String, Integer, DateTime, Text, ForeignKey, Boolean, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session, relationship
from sqlalchemy.dialects.postgresql import JSONB
from pymongo import MongoClient

from .config import load_pg_settings, load_mongo_settings


class Base(DeclarativeBase):
	pass


class AIAdvice(Base):
	__tablename__ = "ai_advices"
	id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
	student_id: Mapped[str] = mapped_column(String(64), index=True)
	subject: Mapped[str] = mapped_column(String(64))
	grade: Mapped[str] = mapped_column(String(16))
	score: Mapped[int] = mapped_column(Integer)
	advice_text: Mapped[str] = mapped_column(Text)
	created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AIFeedback(Base):
	__tablename__ = "ai_feedbacks"
	id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
	submission_id: Mapped[str] = mapped_column(String(64), index=True)
	student_id: Mapped[str] = mapped_column(String(64), index=True)
	feedback_text: Mapped[str] = mapped_column(Text)
	evidence_json: Mapped[Any] = mapped_column(JSONB)
	created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


# Read-only external tables (minimal columns)
class Class(Base):
	__tablename__ = "classes"
	id: Mapped[int] = mapped_column(Integer, primary_key=True)
	name: Mapped[Optional[str]] = mapped_column(String(255))
	# subject: 코드(0:과학,1:수학,2:영어,3:국어)
	subject: Mapped[Optional[int]] = mapped_column(Integer)
	# grade: 문자열("3","4")
	grade: Mapped[Optional[str]] = mapped_column(String(16))
	tags: Mapped[Optional[Any]] = mapped_column(JSONB)


class Exam(Base):
	__tablename__ = "exams"
	id: Mapped[int] = mapped_column(Integer, primary_key=True)
	class_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("classes.id"))
	clazz: Mapped[Optional[Class]] = relationship("Class", primaryjoin="Exam.class_id==Class.id", viewonly=True)


class Test(Base):
	__tablename__ = "tests"
	id: Mapped[int] = mapped_column(Integer, primary_key=True)
	class_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("classes.id"))
	level: Mapped[Optional[String]] = mapped_column(String(32))
	clazz: Mapped[Optional[Class]] = relationship("Class", primaryjoin="Test.class_id==Class.id", viewonly=True)


class Question(Base):
	__tablename__ = "questions"
	id: Mapped[int] = mapped_column(Integer, primary_key=True)
	# 신규 스키마: exam_id, 구 스키마: test_id
	exam_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("exams.id"))
	test_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("tests.id"))
	# 신 스키마 컬럼
	qtype: Mapped[Optional[str]] = mapped_column(String(16))  # MCQ | SHORT
	body: Mapped[Optional[str]] = mapped_column(Text)  # 문제 본문
	choices: Mapped[Optional[Any]] = mapped_column(JSONB)  # 객관식 선지 배열
	# 구 스키마 호환 컬럼
	type: Mapped[Optional[str]] = mapped_column(String(8))  # MC|SA
	stem: Mapped[Optional[str]] = mapped_column(Text)
	options: Mapped[Optional[Any]] = mapped_column(JSONB)
	answer_key: Mapped[Optional[Any]] = mapped_column(JSONB)


class Submission(Base):
	__tablename__ = "submissions"
	id: Mapped[int] = mapped_column(Integer, primary_key=True)
	# 신/구 스키마 병행 지원
	submission_id: Mapped[Optional[str]] = mapped_column(String(64))
	exam_id: Mapped[Optional[int]] = mapped_column(Integer)
	user_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
	test_id: Mapped[Optional[int]] = mapped_column(Integer)
	student_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
	answers: Mapped[Optional[Any]] = mapped_column(JSONB)
	score: Mapped[Optional[int]] = mapped_column(Integer)
	status: Mapped[Optional[str]] = mapped_column(String(32))
	created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
	submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
	total_score: Mapped[Optional[int]] = mapped_column(Integer)
	feedback: Mapped[Optional[str]] = mapped_column(Text)


class SubmissionAnswer(Base):
	__tablename__ = "submission_answers"
	exam_id: Mapped[int] = mapped_column(Integer, primary_key=True)
	user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
	question_id: Mapped[int] = mapped_column(Integer, primary_key=True)
	answer_text: Mapped[Optional[str]] = mapped_column(Text)
	is_correct: Mapped[Optional[bool]] = mapped_column(Boolean)
	score: Mapped[Optional[int]] = mapped_column(Integer)
	elapsed_time_seconds: Mapped[Optional[int]] = mapped_column(Integer)


class User(Base):
	__tablename__ = "users"
	user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
	email: Mapped[Optional[str]] = mapped_column(String(255))
	name: Mapped[Optional[str]] = mapped_column(String(255))


_engine = None
_session_factory = None
_mongo_client: MongoClient | None = None


def init_databases() -> None:
	global _engine, _session_factory, _mongo_client
	pg = load_pg_settings()
	if not pg.url:
		raise RuntimeError("POSTGRESQL_URL must be set")
	_engine = create_engine(pg.url, pool_pre_ping=True)
	# Ensure submissions.feedback exists (safe migration)
	with _engine.connect() as conn:
		try:
			conn.execute(text("ALTER TABLE submissions ADD COLUMN feedback text"))
		except Exception:
			pass
		# Best-effort: add columns if missing (ignore errors if already exist or types differ)
		for stmt in [
			"ALTER TABLE classes ADD COLUMN subject int",
			"ALTER TABLE classes ADD COLUMN grade text",
			"ALTER TABLE submissions ADD COLUMN exam_id int",
			"ALTER TABLE submissions ADD COLUMN user_id text",
			"ALTER TABLE submissions ADD COLUMN submitted_at timestamptz",
			"ALTER TABLE submissions ADD COLUMN total_score int",
			"CREATE TABLE IF NOT EXISTS submission_answers (exam_id int, user_id text, question_id int, answer_text text, is_correct boolean, score int, elapsed_time_seconds int, PRIMARY KEY (exam_id, user_id, question_id))",
		]:
			try:
				conn.execute(text(stmt))
			except Exception:
				pass
	Base.metadata.create_all(_engine)
	_session_factory = Session

	mongo = load_mongo_settings()
	if not mongo.uri:
		raise RuntimeError("MONGODB_URI must be set")
	_mongo_client = MongoClient(mongo.uri)


def get_session() -> Session:
	if _engine is None:
		raise RuntimeError("Database is not initialized")
	return _session_factory(bind=_engine)


def get_mongo() -> MongoClient:
	if _mongo_client is None:
		raise RuntimeError("MongoDB is not initialized")
	return _mongo_client


def _map_subject_code(code: Any) -> Optional[str]:
	try:
		val = int(str(code))
		mapping = {0: "science", 1: "math", 2: "english", 3: "korean"}
		return mapping.get(val)
	except Exception:
		return None


def _infer_subject_grade(clazz: Optional[Class]) -> tuple[Optional[str], Optional[str]]:
	if not clazz:
		return None, None
	# subject may be numeric code(0..3) or string label; grade may be int/str
	subject = None
	if clazz.subject is not None:
		if isinstance(clazz.subject, (int, float)) or (isinstance(clazz.subject, str) and clazz.subject.isdigit()):
			subject = _map_subject_code(clazz.subject)
		elif isinstance(clazz.subject, str):
			subject = clazz.subject.lower()
	grade = None
	if clazz.grade is not None:
		grade = str(clazz.grade)
	try:
		# If subject/grade are not explicitly set on columns, fallback to tags/name heuristics
		if (not subject or not grade) and isinstance(clazz.tags, list):
			for t in clazz.tags:
				if isinstance(t, str):
					t = t.lower()
					if (not subject) and t in ("korean", "english", "math", "science"):
						subject = t
					if (not grade) and "3" in t:
						grade = "3"
					if (not grade) and "4" in t:
						grade = "4"
		elif (not subject or not grade) and isinstance(clazz.tags, dict):
			subject = subject or clazz.tags.get("subject")
			grade = grade or clazz.tags.get("grade")
	except Exception:
		pass
	if (not subject) and clazz.name:
		name = clazz.name.lower()
		for s in ("korean", "english", "math", "science"):
			if s in name:
				subject = s
				break
		if ("3" in name) and not grade:
			grade = "3"
		if ("4" in name) and not grade:
			grade = "4"
	return subject, grade


def get_exam_context(student_id: str, exam_id: str) -> Dict[str, Any]:
	"""Assemble exam context from relational DB.
	Returns: { subject, grade, score, studentName, items:[{stem, answer, studentAnswer, correct, timeSpent}] }
	"""
	with get_session() as s:
		exam: Optional[Exam] = s.get(Exam, int(exam_id)) if exam_id.isdigit() else None
		clazz: Optional[Class] = exam.clazz if exam else None
		subject, grade = _infer_subject_grade(clazz)

		questions: List[Question] = []
		if exam:
			# Prefer new schema
			questions = list(s.query(Question).filter(Question.exam_id == exam.id).order_by(Question.id.asc()))
			if not questions:
				# Fallback to legacy linkage
				questions = list(s.query(Question).filter(Question.test_id == exam.id).order_by(Question.id.asc()))

		# Latest submission (new schema first)
		sub: Optional[Submission] = None
		if exam:
			sub = (
				s.query(Submission)
				.filter(Submission.exam_id == exam.id, Submission.user_id == student_id)
				.order_by(Submission.submitted_at.desc())
				.first()
			)
			if not sub:
				sub = (
					s.query(Submission)
					.filter(Submission.test_id == exam.id, Submission.student_id == student_id)
					.order_by(Submission.created_at.desc())
					.first()
				)
		score = 0
		if sub:
			score = sub.total_score if (sub.total_score is not None) else (sub.score or 0)

		# Per-question answers (new schema)
		answers_map: Dict[int, Dict[str, Any]] = {}
		if exam:
			rows = (
				s.query(SubmissionAnswer)
				.filter(SubmissionAnswer.exam_id == exam.id, SubmissionAnswer.user_id == student_id)
				.all()
			)
			for r in rows:
				answers_map[r.question_id] = {
					"studentAnswer": r.answer_text,
					"correct": bool(r.is_correct) if r.is_correct is not None else None,
					"timeSpent": r.elapsed_time_seconds,
				}

		# Legacy JSON answers fallback
		legacy_answers = []
		legacy_times = []
		if sub and sub.answers:
			legacy_answers = sub.answers.get("answers") or sub.answers.get("studentAnswers") or []
			legacy_times = sub.answers.get("timeSpent") or sub.answers.get("times") or []

		student_name: Optional[str] = None
		if student_id.isdigit():
			u = s.get(User, int(student_id))
			if u:
				student_name = u.name or (u.email.split("@")[0] if u.email else None)

		items: List[Dict[str, Any]] = []
		for idx, q in enumerate(questions):
			ak = q.answer_key if q and q.answer_key is not None else None
			# qtype 우선 사용, 없으면 구 스키마 type 사용
			qt = (q.qtype or "").upper() if hasattr(q, "qtype") and q.qtype else ((q.type or "").upper() if hasattr(q, "type") and q.type else "")
			is_mcq = (qt == "MCQ" or qt == "MC")
			is_short = (qt == "SHORT" or qt == "SA")
			# body/stem 통합
			q_text = q.body if hasattr(q, "body") and q.body else (q.stem or "")
			# 객관식 선택지
			q_choices = q.choices if hasattr(q, "choices") and q.choices else (q.options or None)
			ans = answers_map.get(q.id) if q else None
			student_ans = None
			is_correct = None
			time_spent = None
			if ans:
				student_ans = ans.get("studentAnswer")
				is_correct = ans.get("correct")
				time_spent = ans.get("timeSpent")
			elif legacy_answers:
				student_ans = legacy_answers[idx] if idx < len(legacy_answers) else None
				time_spent = legacy_times[idx] if idx < len(legacy_times) else None
				# derive correctness from qtype/answer_key when possible
				if q and is_mcq:
					is_correct = (student_ans == ak)
				elif q and is_short:
					allowed = ak if isinstance(ak, list) else [ak]
					try:
						st_norm = (str(student_ans or "").strip().lower().replace(" ", ""))
						allowed_norm = {str(x).strip().lower().replace(" ", "") for x in allowed if x is not None}
						is_correct = st_norm in allowed_norm
					except Exception:
						is_correct = False
			item = {
				"stem": q_text or "",
				"answer": ak[0] if isinstance(ak, list) and ak else ak,
				"studentAnswer": student_ans,
				"correct": bool(is_correct) if is_correct is not None else None,
				"timeSpent": time_spent,
				"qtype": qt,
				"choices": q_choices,
			}
			items.append(item)

		return {
			"subject": subject,
			"grade": grade,
			"score": int(score),
			"studentName": student_name,
			"items": items,
		}


def set_submission_feedback_if_null(student_id: str, exam_id: str, feedback_text: str) -> bool:
	"""Set feedback for latest submission of (student_id, exam_id) only if currently NULL.
	Returns True if updated, False if not found or already set.
	"""
	with get_session() as s:
		row: Optional[Submission] = (
			s.query(Submission)
			.filter(Submission.exam_id == int(exam_id), Submission.user_id == student_id)
			.order_by(Submission.submitted_at.desc())
			.first()
		)
		if not row:
			row = (
				s.query(Submission)
				.filter(Submission.test_id == int(exam_id), Submission.student_id == student_id)
				.order_by(Submission.created_at.desc())
				.first()
			)
		if not row:
			return False
		if row.feedback is not None:
			return False
		row.feedback = feedback_text
		s.add(row)
		s.commit()
		return True


