"""
네이버 지식백과 (초등 영어 문법) entry.naver 페이지를 docId 범위로 스크랩해서
우리 시스템 스키마(JSON 배열)로 저장합니다.

- 출력 스키마 (배열의 각 요소):
  {
    "material_id": str,           # unique e.g., english-g3-00001
    "subject": "english",
    "grade": "3" | "4",        # string
    "title": str,
    "content": str
  }
"""

from __future__ import annotations
import argparse
import json
import re
import time
from pathlib import Path
from typing import Optional, Tuple, List, Dict

import requests
from bs4 import BeautifulSoup

# 네이버 영어 문법 카테고리 고정
CID = 59150
CATEGORY_ID = 59151
ENTRY_TMPL = (
    "https://terms.naver.com/entry.naver?docId={doc}"
    f"&categoryId={CATEGORY_ID}&cid={CID}"
)
DEFAULT_UA = "Mozilla/5.0 (RAG-edu bot; contact: you@example.com)"


def clean(text: Optional[str]) -> str:
    text = text or ""
    return re.sub(r"\s+", " ", text).strip()


def fetch_entry(doc_id: int, headers: dict, delay: float, debug: bool = False) -> Tuple[str, str]:
    """단일 entry 페이지에서 제목/본문 텍스트 추출"""
    url = ENTRY_TMPL.format(doc=doc_id)
    r = requests.get(url, headers=headers, timeout=12)
    if r.status_code == 404:
        if debug:
            print(f"[{doc_id}] 404 Not Found")
        time.sleep(delay)
        return "", ""
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    # 제목
    title_node = (
        soup.select_one(".headword")
        or soup.select_one("h2.headword")
        or soup.select_one("h3.headword")
    )
    title = clean(title_node.get_text()) if title_node else clean(soup.title.get_text() if soup.title else "")

    # 본문 후보
    candidates = soup.select(".size2, .txt, .subject, .content, #size_ct, .article_view")
    text = clean(" ".join(n.get_text(" ") for n in candidates)) if candidates else clean(soup.get_text(" "))

    if debug:
        print(f"[{doc_id}] title='{title[:30]}' len(content)={len(text)}")

    time.sleep(delay)
    return title, text


def save_json_array(data: List[Dict[str, str]], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser(description="Scrape Naver Terms (초등 영어 문법, 시스템 스키마로 3/4학년 파일 출력)")
    ap.add_argument("--start-id", type=int, default=3581701, help="시작 docId")
    ap.add_argument("--end-id", type=int, default=3581745, help="끝 docId (inclusive)")
    ap.add_argument("--split-id", type=int, default=3581723, help="3학년과 4학년을 나누는 기준 docId")
    ap.add_argument("--delay", type=float, default=1.5, help="요청 간 딜레이(초)")
    ap.add_argument("--user-agent", type=str, default=DEFAULT_UA)
    ap.add_argument("--outdir", type=str, default="materials/english", help="출력 디렉토리")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    headers = {"User-Agent": args.user_agent}
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    g3_docs: List[Dict[str, str]] = []
    g4_docs: List[Dict[str, str]] = []
    seq3, seq4 = 1, 1

    for doc_id in range(args.start_id, args.end_id + 1):
        try:
            title, content = fetch_entry(doc_id, headers, args.delay, debug=args.debug)
            if not content:
                continue

            grade = "3" if doc_id <= args.split_id else "4"
            if grade == "3":
                doc = {
                    "material_id": f"english-g3-{seq3:05d}",
                    "subject": "english",
                    "grade": "3",
                    "title": title or f"en_{doc_id}",
                    "content": content,
                }
                g3_docs.append(doc)
                seq3 += 1
            else:
                doc = {
                    "material_id": f"english-g4-{seq4:05d}",
                    "subject": "english",
                    "grade": "4",
                    "title": title or f"en_{doc_id}",
                    "content": content,
                }
                g4_docs.append(doc)
                seq4 += 1

        except Exception as e:
            print(f"[skip] docId={doc_id} -> {e}")

    save_json_array(g3_docs, outdir / "en_g3.json")
    save_json_array(g4_docs, outdir / "en_g4.json")
    print(f"✅ saved g3: {len(g3_docs)} -> {(outdir / 'en_g3.json').as_posix()}")
    print(f"✅ saved g4: {len(g4_docs)} -> {(outdir / 'en_g4.json').as_posix()}")


if __name__ == "__main__":
    main()


