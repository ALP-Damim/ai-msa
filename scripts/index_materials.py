import sys
import json
import os
import glob
from typing import List, Dict, Any

from pymongo import MongoClient
from dotenv import load_dotenv

sys.path.append(".")

from app.services.config import load_mongo_settings
from app.services.rag_service import embed_text


def load_json(path: str) -> List[Dict[str, Any]]:
	with open(path, "r", encoding="utf-8") as f:
		return json.load(f)


def load_path(path: str) -> List[Dict[str, Any]]:
	"""Load a single JSON file or merge all JSON files in a directory."""
	if os.path.isdir(path):
		docs: List[Dict[str, Any]] = []
		for p in sorted(glob.glob(os.path.join(path, "*.json"))):
			print(f"Loading {p}...")
			docs.extend(load_json(p))
		return docs
	else:
		return load_json(path)


def ensure_indexes(coll):
	coll.create_index("material_id", unique=True)
	coll.create_index([("parent_id", 1)])
	coll.create_index([("subject", 1)])
	coll.create_index([("grade", 1)])


def chunk_text(text: str, max_chars: int) -> List[str]:
	text = text or ""
	if len(text) <= max_chars:
		return [text]
	chunks: List[str] = []
	start = 0
	while start < len(text):
		end = min(start + max_chars, len(text))
		# Prefer split at newline if present and not too early
		split_pos = text.rfind("\n", start, end)
		if split_pos == -1 or split_pos < start + int(max_chars * 0.5):
			split_pos = end
		chunk = text[start:split_pos].strip()
		if chunk:
			chunks.append(chunk)
		start = split_pos
	return chunks


def main():
	load_dotenv()
	if len(sys.argv) < 2:
		print("Usage: python scripts/index_materials.py <data.json or directory>")
		return
	path = sys.argv[1]

	mongo = load_mongo_settings()
	if not mongo.uri:
		raise RuntimeError("MONGODB_URI must be set")
	client = MongoClient(mongo.uri)
	coll = client[mongo.database][mongo.materials_collection]

	rows = load_path(path)
	max_chars = int(os.getenv("EMBED_MAX_CHARS", "3500"))

	docs = []
	for row in rows:
		content = row.get("content", "")
		if not content:
			continue
		parent_id = str(row.get("material_id"))
		subject = row.get("subject")
		grade = str(row.get("grade"))
		title = row.get("title", "")

		parts = chunk_text(content, max_chars=max_chars)
		for idx, part in enumerate(parts, start=1):
			chunk_id = f"{parent_id}-c{idx:03d}"
			vec = embed_text(part)
			docs.append({
				"material_id": chunk_id,
				"parent_id": parent_id,
				"subject": subject,
				"grade": grade,
				"title": f"{title} (part {idx})".strip(),
				"content": part,
				"vector": vec,
			})

	ensure_indexes(coll)
	for d in docs:
		coll.replace_one({"material_id": d["material_id"]}, d, upsert=True)
	print(f"Indexed {len(docs)} materials into {mongo.database}.{mongo.materials_collection}")


if __name__ == "__main__":
	main()
