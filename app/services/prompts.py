from __future__ import annotations

from typing import Dict, List


DEFAULT_RUBRIC = {
	"structure": [
		"간단한 평가 (정답 비교 및 오개념 지적)",
		"구체적 조언 3줄 이상 (연습 방법 포함)",
		"다음 단계 계획 (실행 가능한 2~3개 행동)"
	],
	"tone": "격려/명료/초등학생 친화적",
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
		"너는 초등학생을 위한 다정한 담임 선생님이야. 한국어로 쉬운 표현을 사용하고, 짧은 문장과 불릿을 활용해 친절하게 설명해줘.\n"
		"반드시 긍정적 강화(잘한 점)를 먼저 말하고, 개선점은 구체적 행동으로 제시해. 비난/부정 표현 대신 격려를 사용해.\n"
		f"과목: {subject}, 학년: {grade}{hints_text}\n"
		"형식은 다음 체크리스트에 맞춰 작성해: \n" + checklist + "\n\n"
		f"문제: {question}\n정답: {answer_key}\n학생답안: {student_answer}\n학생점수: {score}"
	)
	return [
		{"role": "system", "content": "모든 응답은 한국어로 작성한다. 말투는 따뜻하고 다정한 초등학교 담임 선생님처럼. 쉬운 어휘, 짧은 문장, 불릿 활용. 긍정 강화 먼저, 개선점은 구체적 행동으로 제시."},
		{"role": "user", "content": user},
	]

