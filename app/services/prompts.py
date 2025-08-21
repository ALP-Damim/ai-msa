from __future__ import annotations

from typing import Dict, List


DEFAULT_RUBRIC = {
	"structure": [
		"간단한 평가 (정답 비교 및 오개념 지적)",
		"구체적 조언 3줄 이상 (연습 방법 포함)",
		"다음 단계 계획 (실행 가능한 2~3개 행동)",
		"오답 문항에 대한 간단한 해설과 개념 정리"
	],
	"tone": "상냥한 담임 선생님 톤의 반말(친근한 구어체)",
}


SUBJECT_GRADE_HINTS: Dict[str, Dict[str, List[str]]] = {
	"korean": {
		"3": ["받침 발음/맞춤법", "문장 부호", "문장 성분 기초"],
		"4": ["띄어쓰기 규칙", "맞춤법 심화", "요약/요지 파악"],
	},
	"math": {
		"3": ["곱셈/나눗셈 기초", "분수 개념"],
		"4": ["분수 사칙", "도형/각도", "소수 기초"],
	},
	"science": {
		"3": ["생물 기초", "물질의 상태"],
		"4": ["힘과 운동", "지구/우주 기초"],
	},
	"english": {
		"3": ["기초 어휘", "기초 문장 패턴"],
		"4": ["시제 기초", "의문문/부정문"],
	},
}


def build_rubric_prompt(subject: str, grade: str, question: str, answer_key: str, student_answer: str, score: int, rubric: Dict | None = None) -> List[Dict[str, str]]:
	r = rubric or DEFAULT_RUBRIC
	hints = SUBJECT_GRADE_HINTS.get(subject, {}).get(grade, [])
	checklist = "\n".join([f"- {item}" for item in r["structure"]])
	hints_text = ("\n도움말: " + ", ".join(hints)) if hints else ""
	user = (
		"너는 초등학생에게 상냥하게 알려주는 담임 선생님이야. 한국어 반말(친근한 구어체)로, 짧은 문장과 불릿으로 또박또박 이야기해줘.\n"
		"학생 이름이 보이면 이름 뒤에 적절하게 '아/야'를 붙여서 자연스럽게 인사로 시작해(예: 민수야, 안녕?).\n"
		"첫 문장은 점수를 칭찬하는 문장으로 시작하되, 같은 표현을 반복하지 말고 자연스럽고 다양한 표현을 사용해.\n"
		"오답 문항이 있으면 간단한 해설과 핵심 개념을 초등 눈높이로 덧붙여줘.\n"
		"친절하지만 모호하게 말하지 말고, 단계별로 명확하게 알려줘(1-2-3 순서, 또는 불릿).\n"
		f"과목: {subject}, 학년: {grade}{hints_text}\n"
		"형식은 다음 체크리스트를 따르되, 말투는 자연스러운 대화체 반말로: \n" + checklist + "\n\n"
		f"문제: {question}\n정답: {answer_key}\n학생답안: {student_answer}\n학생점수: {score}"
	)
	return [
		{"role": "system", "content": "모든 응답은 한국어 반말(친근한 구어체)로 작성한다. 말투는 상냥한 담임 선생님처럼. 첫 문장은 점수를 칭찬하되, 표현을 다양하게 사용하고 반복하지 않는다. 학생 이름이 보이면 이름에 자연스럽게 '아/야'를 붙여 호명하고 인사로 시작한다. 오답은 간단한 해설과 핵심 개념을 추가한다. 친절하면서도 단계별로 명확하게 안내한다(모호한 표현 금지)."},
		{"role": "user", "content": user},
	]


def _shorten(text: str, limit: int = 120) -> str:
	text = text or ""
	return text if len(text) <= limit else (text[:limit] + "...")


def build_exam_advice_prompt(subject: str, grade: str, student_name: str, score: int, items: List[Dict[str, str]], evidences: List[Dict[str, str]] | None = None) -> List[Dict[str, str]]:
	# Build compact per-question lines
	lines: List[str] = []
	for idx, it in enumerate(items[:12], start=1):
		qt = (it.get("qtype") or "").upper()
		qt_h = "객관식" if qt in ("MCQ", "MC") else ("단답형" if qt in ("SHORT", "SA") else "")
		stem = _shorten(str(it.get("stem") or ""))
		stu = str(it.get("studentAnswer") if it.get("studentAnswer") is not None else "")
		ans = it.get("answer")
		corr = it.get("correct")
		spent = it.get("timeSpent")
		choices = it.get("choices")
		choice_hint = ""
		if choices and isinstance(choices, list):
			preview = ", ".join([str(c) for c in choices[:4]])
			choice_hint = f" | 선지: {preview}"
		corr_h = "정답" if corr is True else ("오답" if corr is False else "미평가")
		spent_h = (f", 시간: {spent}s" if spent is not None else "")
		ans_h = (f", 정답: {ans}" if ans is not None else "")
		lines.append(f"{idx}. [{qt_h}] {stem} | 제출: {stu} ({corr_h}{spent_h}){ans_h}{choice_hint}")

	exam_context = "\n".join(lines) if lines else "(문항 정보 없음)"
	# Evidence section (optional)
	ev_lines: List[str] = []
	for e in (evidences or [])[:5]:
		try:
			line = f"- { _shorten(str(e.get('snippet') or ''), 160) } (score={e.get('score', 0):.2f})"
			ev_lines.append(line)
		except Exception:
			continue
	ev_text = ("\n참고 자료(필요 시 참고, 과도하게 의존하지 말 것):\n" + "\n".join(ev_lines)) if ev_lines else ""

	user = (
		f"과목: {subject}, 학년: {grade}, 학생: {student_name}, 점수: {score}\n"
		"아래의 문항별 정보를 검토해서 학생에게 개인화된 조언을 작성해줘.\n"
		"형식: 1) 인사+칭찬(첫 문장: 점수에 대한 칭찬, 표현 다양화) 2) 잘한 점 1~2줄 3) 오답 문항별 간단 해설+개선 방법(각 2~3줄) 4) 다음 학습 계획(불릿 2~3개).\n"
		"규칙: 한국어 반말, 상냥한 담임 선생님 톤. 학생 이름에는 자연스럽게 '아/야'를 붙여서 호명. 모호한 표현 금지, 단계별로 명확하게.\n"
		"문항별 정보:\n" + exam_context + ("\n\n" + ev_text if ev_text else "")
	)
	return [
		{"role": "system", "content": "모든 응답은 한국어 반말(친근한 구어체)로 작성한다. 말투는 상냥한 담임 선생님처럼. 첫 문장은 점수를 칭찬하되, 같은 표현을 반복하지 말고 자연스럽고 다양한 표현을 사용한다. 학생 이름이 보이면 이름에 자연스럽게 '아/야'를 붙여 호명하고 인사로 시작한다. 각 오답 문항에는 간단한 해설과 핵심 개념을 덧붙이고, 구체적인 개선 방법을 제시한다. 친절하면서도 단계별로 명확하게 안내한다(모호한 표현 금지). 참고 자료가 제공되면 필요할 때만 자연스럽게 반영하고, 과도하게 의존하지 않는다."},
		{"role": "user", "content": user},
	]

