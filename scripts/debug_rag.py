import os
import sys
from dotenv import load_dotenv
from pymongo import MongoClient

sys.path.append(".")
from app.services.config import load_mongo_settings
from app.services.rag_service import embed_text


def main():
	load_dotenv()
	query = sys.argv[1] if len(sys.argv) > 1 else "분수"
	subject = sys.argv[2] if len(sys.argv) > 2 else None
	grade = sys.argv[3] if len(sys.argv) > 3 else None
	k = int(sys.argv[4]) if len(sys.argv) > 4 else 5
	index_name = os.getenv("MONGODB_SEARCH_INDEX", "default")

	mongo = load_mongo_settings()
	client = MongoClient(mongo.uri)
	coll = client[mongo.database][mongo.materials_collection]

	total = coll.estimated_document_count()
	with_vec = coll.count_documents({"vector": {"$type": "array"}})
	print(f"materials: total={total}, with_vector={with_vec}")

	sample = coll.find_one({"vector": {"$type": "array"}}, {"vector": {"$slice": 1}, "subject": 1, "grade": 1, "material_id": 1})
	if sample:
		vec_len = len(sample.get("vector", []))
		print(f"sample: material_id={sample.get('material_id')}, subject={sample.get('subject')}, grade={sample.get('grade')}, vector_len={vec_len}")
	else:
		print("sample: none with vector")

	# Build search pipeline
	qvec = embed_text(query)
	match = {}
	if subject:
		match["subject"] = subject
	if grade:
		match["grade"] = grade

	pipeline = [
		{"$search": {"index": index_name, "knnBeta": {"vector": qvec, "path": "vector", "k": k}}},
	]
	if match:
		pipeline.append({"$match": match})
	pipeline.extend([
		{"$limit": k},
		{"$project": {"material_id": 1, "parent_id": 1, "title": 1, "score": {"$meta": "searchScore"}}},
	])

	results = list(coll.aggregate(pipeline))
	print(f"search hits={len(results)} (index={index_name}, subject={subject}, grade={grade})")
	for r in results[:5]:
		print({k: r.get(k) for k in ("material_id", "parent_id", "title", "score")})


if __name__ == "__main__":
	main()


