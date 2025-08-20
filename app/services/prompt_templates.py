from __future__ import annotations

from typing import Dict, Tuple

# Simple rubric per subject/grade; can be expanded
RUBRICS: Dict[Tuple[str, str], Dict[str, str]] = {
    ("korean", "3"): {
        "tone": "친절하고 간결하게",
        "focus": "받침, 문장부호, 기본 맞춤법",
    },
    ("korean", "4"): {
        "tone": "격려하되 구체적으로",
        "focus": "맞춤법, 문장 표현, 문단 구성",
    },
    ("math", "3"): {
        "tone": "단계별 설명",
        "focus": "사칙연산, 분수의 기초",
    },
    ("math", "4"): {
        "tone": "절차와 검산 강조",
        "focus": "분수, 소수, 도형 기초",
    },
}


def get_rubric(subject: str, grade: str) -> Dict[str, str]:
    return RUBRICS.get((subject, grade), {"tone": "친절하게", "focus": "핵심 개념"})


def build_evaluation_template(subject: str, grade: str) -> str:
    r = get_rubric(subject, grade)
    return (
        f"너는 초등학생을 위한 {subject} 과목 {grade}학년 선생님이야. "
        f"평가는 {r['tone']} 어조로, {r['focus']}에 초점을 맞춰.\n"
        "출력 형식:\n"
        "- 평가: (정답과 비교해 학생의 이해도를 한 문단으로)\n"
        "- 체크리스트: (핵심 개념 3가지, 불릿)\n"
        "- 조언: (3줄 이상, 구체적 연습 방법)\n"
        "- 다음 단계: (2~3개의 실행 가능한 액션)\n"
    )
