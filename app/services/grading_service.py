from __future__ import annotations

from typing import Any, Dict, List
import re


def _normalize(s: str) -> str:
	return re.sub(r"\s+", "", s.strip().lower())


def grade_submission(test: Dict[str, Any], answers: List[Any], student_answers: List[Any]) -> Dict[str, Any]:
	"""Grade a submission.
	- MC: exact match to answer key
	- SA: normalized match against allowed answers set
	Parameters mimic the ER schema idea but simplified for the API.
	"""
	total = len(answers)
	correct = 0
	details: List[Dict[str, Any]] = []
	for idx, key in enumerate(answers):
		student = student_answers[idx] if idx < len(student_answers) else None
		qtype = (test.get("questions", [{}])[idx].get("type") if test.get("questions") else None) or "MC"
		is_correct = False
		if qtype == "MC":
			is_correct = student == key
		elif qtype == "SA":
			allowed = key if isinstance(key, list) else [key]
			allowed_norm = {_normalize(str(x)) for x in allowed}
			is_correct = _normalize(str(student or "")) in allowed_norm
		else:
			is_correct = False
		if is_correct:
			correct += 1
		details.append({"index": idx, "type": qtype, "correct": is_correct, "student": student, "answer": key})
	return {"score": int(correct), "total": int(total), "details": details}


