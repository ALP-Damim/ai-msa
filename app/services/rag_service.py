from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from openai import AzureOpenAI

from .config import load_mongo_settings, load_azure_settings, resolve_azure_openai_credentials
from .db_service import get_mongo


def _get_index_name() -> str:
	return os.getenv("MONGODB_SEARCH_INDEX", "default")


def _materials_collection() -> Collection:
	client: MongoClient = get_mongo()
	mongo = load_mongo_settings()
	return client[mongo.database][mongo.materials_collection]


def _embedding_client() -> AzureOpenAI:
	settings = load_azure_settings()
	endpoint, api_key = resolve_azure_openai_credentials(settings)
	return AzureOpenAI(api_key=api_key, api_version=settings.api_version, azure_endpoint=endpoint)


def embed_text(text: str) -> List[float]:
	settings = load_azure_settings()
	client = _embedding_client()
	resp = client.embeddings.create(
		model=settings.embedding_deployment,
		input=text,
	)
	return resp.data[0].embedding


def search_with_evidence(query: str, material_ids: List[str], k: int = 5, subject: Optional[str] = None, grade: Optional[str] = None) -> List[Dict[str, Any]]:
	vec = embed_text(query)
	coll = _materials_collection()
	index_name = _get_index_name()

	def _subject_candidates(s: str) -> List[str]:
		s0 = (s or "").strip()
		s_l = s0.lower()
		eng_to_kor = {
			"korean": "국어",
			"english": "영어",
			"math": "수학",
			"science": "과학",
		}
		kor_to_eng = {v: k for k, v in eng_to_kor.items()}
		aliases = {
			"ko": "korean",
			"kor": "korean",
			"en": "english",
			"eng": "english",
			"mat": "math",
			"sci": "science",
		}
		cands = {s0, s_l}
		canon_eng = aliases.get(s_l, s_l)
		if canon_eng in eng_to_kor:
			cands.add(canon_eng)
			cands.add(eng_to_kor[canon_eng])
		if s0 in kor_to_eng:
			cands.add(kor_to_eng[s0])
		return list(cands)

	# Build search pipeline
	pipeline: List[Dict[str, Any]] = [
		{"$search": {"index": index_name, "knnBeta": {"vector": vec, "path": "vector", "k": max(int(k), 1)}}},
	]

	conditions: List[Dict[str, Any]] = []
	if material_ids:
		conditions.append({
			"$or": [
				{"material_id": {"$in": material_ids}},
				{"parent_id": {"$in": material_ids}},
			]
		})
	if subject:
		conditions.append({"subject": {"$in": _subject_candidates(subject)}})
	if grade:
		# Documents may store grade as int or string; match both safely
		try:
			g_int = int(str(grade).strip())
		except Exception:
			g_int = None
		g_str = str(grade).strip()
		grade_or = [{"grade": g_str}]
		if g_int is not None:
			grade_or.append({"grade": g_int})
		conditions.append({"$or": grade_or})

	if conditions:
		pipeline.append({"$match": {"$and": conditions}})

	pipeline.extend([
		{"$limit": k},
		{"$project": {"material_id": 1, "parent_id": 1, "title": 1, "content": 1, "score": {"$meta": "searchScore"}}},
	])

	results: List[Dict[str, Any]] = []
	try:
		for doc in coll.aggregate(pipeline):
			snippet = doc.get("content", "")
			if len(snippet) > 480:
				snippet = snippet[:480] + "..."
			results.append({
				"material_id": doc.get("material_id"),
				"parent_id": doc.get("parent_id"),
				"title": doc.get("title"),
				"snippet": snippet,
				"score": float(doc.get("score", 0.0)),
			})
		return results
	except PyMongoError:
		return []
