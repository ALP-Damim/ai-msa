from __future__ import annotations
import argparse
import json
import os
import re
from pathlib import Path
from typing import List, Dict

from pdfminer.high_level import extract_text

try:
	import fitz  # PyMuPDF
	HAS_FITZ = True
except Exception:
	HAS_FITZ = False

try:
	from pdf2image import convert_from_path
	import pytesseract
	HAS_OCR = True
except Exception:
	HAS_OCR = False


def normalize_spaces(text: str) -> str:
	return re.sub(r"\s+", " ", text).strip()


def extract_with_pdfminer(path: str, max_pages: int | None = None) -> str:
	try:
		text = extract_text(path, maxpages=max_pages)
		return normalize_spaces(text or "")
	except Exception:
		return ""


def extract_with_pymupdf(path: str, max_pages: int | None = None) -> str:
	if not HAS_FITZ:
		return ""
	try:
		doc = fitz.open(path)
		texts: List[str] = []
		limit = min(len(doc), max_pages) if max_pages else len(doc)
		for i in range(limit):
			page = doc.load_page(i)
			texts.append(page.get_text("text"))
		doc.close()
		return normalize_spaces("\n".join(texts))
	except Exception:
		return ""


def extract_with_ocr(path: str, max_pages: int | None = None, dpi: int = 200) -> str:
	if not HAS_OCR:
		return ""
	try:
		pages = convert_from_path(path, dpi=dpi, first_page=1, last_page=(max_pages or None))
		texts: List[str] = []
		for img in pages:
			texts.append(pytesseract.image_to_string(img, lang="kor+eng"))
		return normalize_spaces("\n".join(texts))
	except Exception:
		return ""


def read_pdf_text(path: str, max_pages: int | None = None, use_ocr: bool = False) -> str:
	text = extract_with_pdfminer(path, max_pages=max_pages)
	if text:
		return text
	text = extract_with_pymupdf(path, max_pages=max_pages)
	if text:
		return text
	if use_ocr:
		return extract_with_ocr(path, max_pages=max_pages)
	return ""


def detect_grade_from_filename(fname: str) -> str:
	s = fname
	return "3" if ("_3-" in s or "_3_" in s or "초_3" in s) else "4"


def scan_pdfs(pattern: str) -> List[str]:
	pdf_dir = os.path.join(os.path.dirname(__file__), "..", "pdf")
	pdf_dir = os.path.abspath(pdf_dir)
	return sorted([str(p) for p in Path(pdf_dir).glob(pattern)])


def build_docs(subject: str, paths: List[str], max_pages: int | None, use_ocr: bool) -> Dict[str, List[Dict[str, str]]]:
	g3, g4 = [], []
	seq3, seq4 = 1, 1
	for p in paths:
		text = read_pdf_text(p, max_pages=max_pages, use_ocr=use_ocr)
		if not text:
			print(f"[skip] empty text: {os.path.basename(p)}")
			continue
		fname = os.path.basename(p)
		grade = detect_grade_from_filename(fname)
		if grade == "3":
			doc = {
				"material_id": f"{subject}-g3-{seq3:05d}",
				"subject": subject,
				"grade": "3",
				"title": fname[:120],
				"content": text,
			}
			g3.append(doc)
			seq3 += 1
		else:
			doc = {
				"material_id": f"{subject}-g4-{seq4:05d}",
				"subject": subject,
				"grade": "4",
				"title": fname[:120],
				"content": text,
			}
			g4.append(doc)
			seq4 += 1
	return {"3": g3, "4": g4}


def save_array(docs: List[Dict[str, str]], path: Path):
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(docs, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
	ap = argparse.ArgumentParser(description="Parse PDFs to JSON arrays by grade (3/4)")
	ap.add_argument("--subject", required=True, choices=["math", "science"])
	ap.add_argument("--pattern", required=True, help='Glob pattern, e.g. "JIHAKSA_수학_*.pdf"')
	ap.add_argument("--outdir", default="materials/math")
	ap.add_argument("--max-pages", type=int, default=None, help="Max pages to extract per PDF (for speed)")
	ap.add_argument("--ocr", action="store_true", help="Enable OCR fallback for scanned PDFs")
	args = ap.parse_args()

	if args.outdir == "materials/math" and args.subject == "science":
		outdir = Path("materials/science")
	else:
		outdir = Path(args.outdir)

	paths = scan_pdfs(args.pattern)
	print(f"Found {len(paths)} PDFs for subject={args.subject}")
	docs = build_docs(args.subject, paths, max_pages=args.max_pages, use_ocr=args.ocr)

	if args.subject == "math":
		save_array(docs["3"], outdir / "math_g3.json")
		save_array(docs["4"], outdir / "math_g4.json")
		print(f"✅ saved math g3: {len(docs['3'])}, g4: {len(docs['4'])} -> {outdir}")
	else:
		save_array(docs["3"], outdir / "science_g3.json")
		save_array(docs["4"], outdir / "science_g4.json")
		print(f"✅ saved science g3: {len(docs['3'])}, g4: {len(docs['4'])} -> {outdir}")


if __name__ == "__main__":
	main()