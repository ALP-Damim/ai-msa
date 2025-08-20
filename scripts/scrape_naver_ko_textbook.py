from __future__ import annotations
import argparse
import json
import re
import time
from pathlib import Path
from typing import Dict, Iterable, List, Tuple
from urllib.parse import urljoin, urlparse, parse_qs, urlencode

import requests
from bs4 import BeautifulSoup

BASE = "https://terms.naver.com"
CID = 58583  # 초중등 교육 카테고리

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)

# categoryId → (원래 grade, semester)
CID_TO_GRADE_SEM = {
    59180: (1, 1), 59181: (1, 2),
    59182: (2, 1), 59183: (2, 2),
    59184: (3, 1), 59185: (3, 2),
    59186: (4, 1), 59187: (4, 2),
    59188: (5, 1), 59189: (5, 2),
    59190: (6, 1), 59191: (6, 2),
}

def list_url(category_id: int, page: int) -> str:
    return f"{BASE}/list.naver?cid={CID}&categoryId={category_id}&page={page}"


def normalize_grade(g: int) -> int:
    if g in (1, 2):
        return 3
    if g in (5, 6):
        return 4
    return g  # 3,4


def clean(text: str | None) -> str:
    text = text or ""
    return re.sub(r"\s+", " ", text).strip()


def ensure_entry_url(href: str, category_id: int) -> str:
    url = urljoin(BASE, href)
    if "entry.naver" not in url:
        return ""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    params = {k: v[0] for k, v in qs.items()}
    if "cid" not in params:
        params["cid"] = str(CID)
    if "categoryId" not in params:
        params["categoryId"] = str(category_id)
    new_query = urlencode(params)
    return parsed._replace(query=new_query).geturl()


def dump_html(path: Path, html: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def get_list_entry_urls(
    category_id: int, pages: int, headers: dict, delay: float, debug: bool, dumpdir: Path
) -> Iterable[str]:
    session = requests.Session()
    for p in range(1, pages + 1):
        url = list_url(category_id, p)
        r = session.get(url, headers=headers, timeout=12)
        if debug:
            dump_html(dumpdir / f"list_{category_id}_p{p}.html", r.text)
        if r.status_code != 200:
            time.sleep(delay)
            continue

        soup = BeautifulSoup(r.text, "html.parser")
        anchors = soup.select("a[href*='entry.naver?docId=']")
        if not anchors:
            anchors = [a for a in soup.find_all("a", href=True) if "entry.naver" in a["href"]]

        for a in anchors:
            href = a.get("href")
            if not href:
                continue
            entry = ensure_entry_url(href, category_id)
            if entry:
                yield entry
        time.sleep(delay)


def fetch_entry(
    url: str, headers: dict, delay: float, debug: bool, dumpdir: Path
) -> Tuple[str, str]:
    r = requests.get(url, headers=headers, timeout=12)
    if debug:
        m = re.search(r"docId=(\d+)", url)
        doc_id = m.group(1) if m else "unknown"
        dump_html(dumpdir / f"entry_{doc_id}.html", r.text)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    title_node = (
        soup.select_one(".headword")
        or soup.select_one("h1.headword, h2.headword, h3.headword")
        or soup.select_one("h1, h2")
    )
    title = clean(title_node.get_text() if title_node else (soup.title.get_text() if soup.title else ""))

    candidates = soup.select(
        ".article_view, .size2, .txt, .subject, .content, #size_ct, "
        ".entry_end_section, .sc, .ct_box, .content_bx"
    )
    texts: List[Tuple[int, str]] = []
    for c in candidates:
        t = clean(c.get_text(" "))
        if t:
            texts.append((len(t), t))
    text = max(texts, key=lambda x: x[0])[1] if texts else clean(soup.get_text(" "))

    time.sleep(delay)
    return title, text


def scrape_and_build_docs(
    start_cid: int, end_cid: int, pages: int, headers: dict, delay: float, debug: bool, dumpdir: Path
) -> Tuple[List[dict], List[dict]]:
    g3_docs: List[dict] = []
    g4_docs: List[dict] = []

    seq3 = 1
    seq4 = 1

    for category_id in range(start_cid, end_cid + 1):
        if category_id not in CID_TO_GRADE_SEM:
            continue
        raw_grade, _sem = CID_TO_GRADE_SEM[category_id]
        g_norm = normalize_grade(raw_grade)

        seen_urls = set()
        for entry_url in get_list_entry_urls(category_id, pages, headers, delay, debug, dumpdir):
            if entry_url in seen_urls:
                continue
            seen_urls.add(entry_url)
            try:
                title, content = fetch_entry(entry_url, headers, delay, debug, dumpdir)
                if not content:
                    continue
                if g_norm == 3:
                    doc = {
                        "material_id": f"korean-g3-{seq3:05d}",
                        "subject": "korean",
                        "grade": "3",
                        "title": title or f"국어 G3 {seq3}",
                        "content": content,
                    }
                    g3_docs.append(doc)
                    seq3 += 1
                else:
                    doc = {
                        "material_id": f"korean-g4-{seq4:05d}",
                        "subject": "korean",
                        "grade": "4",
                        "title": title or f"국어 G4 {seq4}",
                        "content": content,
                    }
                    g4_docs.append(doc)
            except Exception:
                continue
    return g3_docs, g4_docs


def main():
    ap = argparse.ArgumentParser(description="Scrape Naver Terms (국어) -> system JSON arrays for grade 3/4")
    ap.add_argument("--start-cid", type=int, default=59180)
    ap.add_argument("--end-cid", type=int, default=59191)
    ap.add_argument("--pages", type=int, default=1)
    ap.add_argument("--delay", type=float, default=1.2)
    ap.add_argument("--outdir", type=str, default="materials/korean")
    ap.add_argument("--user-agent", type=str, default=DEFAULT_UA)
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    out_root = Path(args.outdir)
    out_root.mkdir(parents=True, exist_ok=True)
    dumpdir = Path("debug_html") if args.debug else Path(".")
    headers = {
        "User-Agent": args.user_agent,
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": f"{BASE}/",
        "Connection": "keep-alive",
    }

    g3_docs, g4_docs = scrape_and_build_docs(
        args.start_cid, args.end_cid, args.pages, headers, args.delay, args.debug, dumpdir
    )

    g3_path = out_root / "ko_g3.json"
    g4_path = out_root / "ko_g4.json"
    g3_path.write_text(json.dumps(g3_docs, ensure_ascii=False, indent=2), encoding="utf-8")
    g4_path.write_text(json.dumps(g4_docs, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✅ saved g3: {len(g3_docs)} -> {g3_path.as_posix()}")
    print(f"✅ saved g4: {len(g4_docs)} -> {g4_path.as_posix()}")


if __name__ == "__main__":
    main()


