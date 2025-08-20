from __future__ import annotations
import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Tuple

from pdfminer.high_level import extract_text

# Silence pdfminer noisy logs if any external logging configured
import logging
logging.getLogger("pdfminer").setLevel(logging.ERROR)
logging.getLogger("pdfminer.layout").setLevel(logging.ERROR)
logging.getLogger("pdfminer.pdfinterp").setLevel(logging.ERROR)

# JIHAKSA_과목_초_4-2_*.pdf (handle NFD/NFC by normalizing to NFC first)
FNAME_RE = re.compile(
    r"""^JIHAKSA[_\-](?P<subject>수학|과학)[_\-](?:초|초)[_\-](?P<grade>\d)[\-_](?P<sem>[12])[_\-].*\.pdf$""",
    re.IGNORECASE,
)

# Map to system subject codes
SUBJECT_MAP = {"수학": "math", "과학": "science"}


def clean(s: str) -> str:
    s = s.replace("\u0000", " ").replace("\u200b", "")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def normalize_grade(g: int) -> int:
    # 1,2→3 / 5,6→4 / 3,4는 그대로
    if g in (1, 2):
        return 3
    if g in (5, 6):
        return 4
    return g


UNIT_HEADER_RE = re.compile(
    r"""(?P<header>^\s*(?:[0-9]+)\s*단원[^\n]*$|^\s*단원\s*평가[^\n]*$|^\s*학습\s*목표[^\n]*$|^\s*(?:[0-9]+)\s*차시[^\n]*$)""",
    re.MULTILINE,
)


def split_by_unit_text(full_text: str) -> List[Tuple[str, str]]:
    t = clean(full_text)
    ms = list(UNIT_HEADER_RE.finditer(t))
    if len(ms) < 2:
        return []
    parts: List[Tuple[str, str]] = []
    for i, m in enumerate(ms):
        start = m.start()
        end = ms[i + 1].start() if i + 1 < len(ms) else len(t)
        title = clean(m.group("header"))
        body = clean(t[start:end])
        if len(body) >= 300:
            parts.append((title, body))
    return parts if len(parts) > 1 else []


def split_by_pages(pdf: Path, pages_per_unit: int) -> List[Tuple[str, str]]:
    raw = extract_text(pdf.as_posix())
    chunks = [clean(c) for c in raw.split("\x0c") if clean(c)]
    parts: List[Tuple[str, str]] = []
    for i in range(0, len(chunks), pages_per_unit):
        body = clean("\n\n".join(chunks[i : i + pages_per_unit]))
        if len(body) >= 200:
            idx = i // pages_per_unit + 1
            parts.append((f"{idx}단원(페이지블록)", body))
    return parts


def process_pdf(pdf: Path, split: str, pages_per_unit: int) -> tuple[str, int, List[Dict[str, str]]]:
    # Normalize filename to NFC before matching
    base = unicodedata.normalize("NFC", pdf.name)
    m = FNAME_RE.match(base)
    if not m:
        print(f"[skip-name] {pdf.name} (pattern mismatch)")
        return "", 0, []

    subj_ko = m.group("subject")
    g = int(m.group("grade"))
    # sem = int(m.group("sem"))  # 학기 미사용
    subject_code = SUBJECT_MAP.get(subj_ko, "")
    if not subject_code:
        print(f"[skip-subject] {pdf.name} (unknown subject)")
        return "", 0, []

    g_norm = normalize_grade(g)

    if split == "unit":
        text = extract_text(pdf.as_posix())
        parts = split_by_unit_text(text) or split_by_pages(pdf, pages_per_unit)
    else:
        parts = split_by_pages(pdf, pages_per_unit)

    docs: List[Dict[str, str]] = []
    seq = 1
    for title_like, content in parts:
        title = f"[{g_norm}] {title_like}" if title_like else f"[{g_norm}] 단원 {seq}"
        docs.append(
            {
                "material_id": f"{subject_code}-g{g_norm}-{seq:05d}",
                "subject": subject_code,
                "grade": str(g_norm),
                "title": title,
                "content": content,
            }
        )
        seq += 1
    return subject_code, g_norm, docs


def main():
    ap = argparse.ArgumentParser(description="Ingest JIHAKSA PDFs into system materials schema (arrays)")
    ap.add_argument("--src", required=True, help="PDF directory path")
    ap.add_argument("--outdir", default="materials", help="Output materials root")
    ap.add_argument("--split", choices=["unit", "page"], default="unit", help="Split by headers or page blocks")
    ap.add_argument("--pages-per-unit", type=int, default=8, help="Pages per unit when split=page")
    args = ap.parse_args()

    src = Path(args.src)
    out_root = Path(args.outdir)
    pdfs = sorted(src.glob("*.pdf"))
    if not pdfs:
        print("⚠️ no PDF files.")
        return

    buckets: Dict[tuple[str, int], List[Dict[str, str]]] = {}
    total = 0

    for pdf in pdfs:
        subject_code, g_norm, docs = process_pdf(pdf, args.split, args.pages_per_unit)
        if not docs:
            continue
        key = (subject_code, g_norm)
        buckets.setdefault(key, []).extend(docs)
        total += len(docs)

    for (subject_code, g_norm), items in buckets.items():
        subdir = subject_code
        out_dir = out_root / subdir
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{subject_code}_g{g_norm}.json"
        out_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✅ saved {len(items)} -> {out_path.as_posix()}")

    print(f"🎉 done. total items: {total}")


if __name__ == "__main__":
    main()
