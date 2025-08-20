from __future__ import annotations

from typing import TypedDict, List, Any, Dict

from langgraph.graph import StateGraph, END

from .rag_service import search_with_evidence
from .llm_service import _feedback_prompt, _call_llm  # reuse prompt and retrying call


class FeedbackState(TypedDict, total=False):
	answer: str
	material_ids: List[str]
	evidences: List[Dict[str, Any]]
	feedback_text: str


def _node_retrieve(state: FeedbackState) -> FeedbackState:
	answer = state["answer"]
	material_ids = state.get("material_ids", [])
	evidences = search_with_evidence(query=answer, material_ids=material_ids, k=3)
	return {**state, "evidences": evidences}


def _node_llm(state: FeedbackState) -> FeedbackState:
	answer = state["answer"]
	evidences = state.get("evidences", [])
	resp = _call_llm(_feedback_prompt(answer, evidences))
	text = getattr(resp, "content", str(resp))
	return {**state, "feedback_text": text}


def build_feedback_graph():
	graph = StateGraph(FeedbackState)
	graph.add_node("retrieve", _node_retrieve)
	graph.add_node("llm", _node_llm)
	graph.set_entry_point("retrieve")
	graph.add_edge("retrieve", "llm")
	graph.add_edge("llm", END)
	return graph.compile()


