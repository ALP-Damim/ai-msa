import os
import re
import sys
import json
import glob
import time
import random
import argparse
from typing import List, Dict, Any, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from pdfminer.high_level import extract_text
from dotenv import load_dotenv
from pymongo import MongoClient

sys.path.append(".")
from app.services.config import load_mongo_settings
from app.services.rag_service import embed_text


def normalize_spaces(text: str) -> str:
	return re.sub(r"\s+", " ", text).strip()


def _make_session() -> requests.Session:
	retries = Retry(
		total=5,
		connect=5,
		read=5,
		backoff_factor=0.6,
		status_forcelist=[429, 500, 502, 503, 504],
		allowed_methods={"GET"},
	)
	sess = requests.Session()
	sess.mount("https://", HTTPAdapter(max_retries=retries))
	sess.mount("http://", HTTPAdapter(max_retries=retries))
	return sess


SESSION = _make_session()
DEFAULT_HEADERS = {
	"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
	"Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
	"Referer": "https://terms.naver.com/",
}


def fetch_html(url: str) -> str:
	# polite delay with jitter
	time.sleep(random.uniform(0.5, 1.4))
	r = SESSION.get(url, timeout=30, headers=DEFAULT_HEADERS)
	r.raise_for_status()
	return r.text


def scrape_naver_list(url: str, limit: int | None = None) -> List[Tuple[str, str]]:
	"""Return list of (title, content_url) from terms.naver list page."""
	html = fetch_html(url)
	soup = BeautifulSoup(html, "lxml")
	items: List[Tuple[str, str]] = []
	# Try several common list selectors used across terms.naver
	candidates = [
		"ul.lst a",  # generic list
		"ul.list_wrap a",
		"div.list_wrap a",
		"a.title",
	]
	seen = set()
	for sel in candidates:
		for a in soup.select(sel):
			href = a.get("href")
			title = a.get_text(strip=True)
			if not href or not title:
				continue
			if href.startswith("/"):
				href = "https://terms.naver.com" + href
			key = (title, href)
			if key in seen:
				continue
			seen.add(key)
			items.append(key)
			if limit and len(items) >= limit:
				return items
	return items


def scrape_naver_content(url: str) -> str:
	html = fetch_html(url)
	soup = BeautifulSoup(html, "lxml")
	# Try common article content containers
	texts = []
	for selector in ["div.size_ct_v1", "div#content", "div#size_ct", "div.end_body", "div#article"]:
		ct = soup.select_one(selector)
		if ct:
			texts.append(ct.get_text(" ", strip=True))
	text = max(texts, key=len) if texts else soup.get_text(" ", strip=True)
	return normalize_spaces(text)


def ingest_korean(limit_per_list: int | None = None) -> List[Dict[str, Any]]:
	"""국어: 1~3학년은 3학년으로, 4~6학년은 4학년으로 라벨링."""
	urls = [
		"https://terms.naver.com/list.naver?cid=58583&categoryId=59180",
		"https://terms.naver.com/list.naver?cid=58583&categoryId=59191",
	]
	all_items: List[Tuple[str, str]] = []
	for u in urls:
		try:
			all_items.extend(scrape_naver_list(u, limit=limit_per_list))
		except Exception:
			continue

	materials: List[Dict[str, Any]] = []
	if not all_items:
		return materials
	mid = len(all_items) // 2
	for idx, (title, href) in enumerate(all_items):
		try:
			content = scrape_naver_content(href)
			grade = "3" if idx < mid else "4"
			materials.append({
				"material_id": f"kor-{idx:05d}",
				"subject": "korean",
				"grade": grade,
				"title": title[:120],
				"content": content,
			})
		except Exception:
			continue
	return materials


def ingest_english(limit: int | None = None) -> List[Dict[str, Any]]:
	"""영어: 상위 1/2 → 3학년, 하위 1/2 → 4학년."""
	url = "https://terms.naver.com/list.naver?cid=59150&categoryId=59151"
	try:
		items = scrape_naver_list(url, limit=limit)
	except Exception:
		items = []
	materials: List[Dict[str, Any]] = []
	if not items:
		return materials
	mid = len(items) // 2
	for idx, (title, href) in enumerate(items):
		try:
			content = scrape_naver_content(href)
			grade = "3" if idx < mid else "4"
			materials.append({
				"material_id": f"eng-{idx:05d}",
				"subject": "english",
				"grade": grade,
				"title": title[:120],
				"content": content,
			})
		except Exception:
			continue
	return materials


def read_pdf_text(path: str) -> str:
	try:
		return normalize_spaces(extract_text(path))
	except Exception:
		return ""


def ingest_pdfs(subject: str, pattern: str) -> List[Dict[str, Any]]:
	"""수학/과학: ./pdf 폴더에서 파일 패턴 매칭. 학기 구분 없이 파일명에서 3/4학년 추정."""
	pdf_dir = os.path.join(os.path.dirname(__file__), "..", "pdf")
	pdf_dir = os.path.abspath(pdf_dir)
	paths = sorted(glob.glob(os.path.join(pdf_dir, pattern)))
	materials: List[Dict[str, Any]] = []
	for idx, p in enumerate(paths):
		text = read_pdf_text(p)
		fname = os.path.basename(p)
		grade = "3" if "_3-" in fname or "_3_" in fname or "초_3" in fname else "4"
		materials.append({
			"material_id": f"{subject}-{idx:05d}",
			"subject": subject,
			"grade": grade,
			"title": fname[:120],
			"content": text,
		})
	return materials


def upsert_materials(docs: List[Dict[str, Any]]):
	mongo = load_mongo_settings()
	client = MongoClient(mongo.uri)
	coll = client[mongo.database][mongo.materials_collection]
	coll.create_index("material_id", unique=True)
	cnt = 0
	for d in docs:
		coll.replace_one({"material_id": d["material_id"]}, d, upsert=True)
		cnt += 1
	print(f"Upserted {cnt} docs into {mongo.database}.{mongo.materials_collection}")


def embed_and_upsert(docs: List[Dict[str, Any]]):
	batched: List[Dict[str, Any]] = []
	for d in docs:
		vec = embed_text(d["content"]) if d.get("content") else []
		batched.append({**d, "vector": vec})
		if len(batched) >= 20:
			upsert_materials(batched)
			batched = []
	if batched:
		upsert_materials(batched)


def main():
	load_dotenv()
	parser = argparse.ArgumentParser(description="Ingest subjects and embed into MongoDB")
	parser.add_argument("--subjects", nargs="*", default=["korean", "english", "math", "science"], help="Subjects to ingest")
	parser.add_argument("--limit", type=int, default=int(os.getenv("INGEST_LIMIT_PER_SUBJ", "40")), help="Max items to scrape per subject")
	args = parser.parse_args()

	all_docs: List[Dict[str, Any]] = []
	if "korean" in args.subjects:
		kor = ingest_korean(limit_per_list=args.limit)
		print(f"Korean scraped: {len(kor)}")
		all_docs.extend(kor)
	if "english" in args.subjects:
		eng = ingest_english(limit=args.limit)
		print(f"English scraped: {len(eng)}")
		all_docs.extend(eng)
	if "math" in args.subjects:
		math = ingest_pdfs("math", "JIHAKSA_수학_*.pdf")
		print(f"Math PDFs: {len(math)}")
		all_docs.extend(math)
	if "science" in args.subjects:
		sci = ingest_pdfs("science", "JIHAKSA_과학_*.pdf")
		print(f"Science PDFs: {len(sci)}")
		all_docs.extend(sci)

	# Only keep grades 3 or 4
	all_docs = [d for d in all_docs if d.get("grade") in {"3", "4"}]
	print(f"Total to embed: {len(all_docs)}")

	embed_and_upsert(all_docs)
	print("Done.")


if __name__ == "__main__":
	main()
