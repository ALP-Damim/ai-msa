from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import create_engine, String, Integer, DateTime, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session
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


_engine = None
_session_factory = None
_mongo_client: MongoClient | None = None


def init_databases() -> None:
	global _engine, _session_factory, _mongo_client
	pg = load_pg_settings()
	if not pg.url:
		raise RuntimeError("POSTGRESQL_URL must be set")
	_engine = create_engine(pg.url, pool_pre_ping=True)
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


