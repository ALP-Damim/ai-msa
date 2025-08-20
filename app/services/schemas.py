from __future__ import annotations
from pydantic import BaseModel, Field, conint, model_validator
from typing import List, Optional, Any


class SearchRequest(BaseModel):
	query: str
	materialIds: List[str] = Field(default_factory=list)
	k: conint(gt=0, le=50) = 5
	subject: Optional[str] = Field(default=None, pattern=r"^(korean|english|math|science)$")
	grade: Optional[str] = Field(default=None, pattern=r"^(3|4)$")


class AdviceRequest(BaseModel):
	studentId: Optional[str] = None
	subject: Optional[str] = None
	grade: Optional[str] = None
	score: conint(ge=0, le=100)


class FeedbackRequest(BaseModel):
	studentId: Optional[str] = None
	submissionId: Optional[str] = None
	answer: str
	materialIds: List[str] = Field(default_factory=list)


class EvaluateRequest(BaseModel):
	studentId: Optional[str] = None
	examId: Optional[str] = None
	subject: str = Field(pattern=r"^(korean|english|math|science)$")
	grade: str = Field(pattern=r"^(3|4)$")
	question: str
	answer: str
	studentAnswer: str
	score: conint(ge=0, le=100)
	materialIds: List[str] = Field(default_factory=list)


class EvaluateBatchRequest(BaseModel):
	studentId: Optional[str] = None
	examId: Optional[str] = None
	subject: str = Field(pattern=r"^(korean|english|math|science)$")
	grade: str = Field(pattern=r"^(3|4)$")
	questions: List[str]
	answers: List[str]
	studentAnswers: List[str]
	scores: List[conint(ge=0, le=100)]
	materialIds: List[str] = Field(default_factory=list)
	count: Optional[conint(gt=0)] = None

	@model_validator(mode="after")
	def lengths_match(self):
		lengths = {len(self.questions), len(self.answers), len(self.studentAnswers), len(self.scores)}
		if len(lengths) != 1:
			raise ValueError("questions, answers, studentAnswers, scores must have the same length")
		if self.count is not None and self.count != len(self.questions):
			raise ValueError("count must equal the length of questions/answers/studentAnswers/scores")
		return self

