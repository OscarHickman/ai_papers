"""PDF Metadata Scanner for AURA paper management system."""

import io
import logging
import re
from typing import Any, Dict

logger = logging.getLogger(__name__)


def scan_pdf_metadata(content_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Scan and extract key details (Title, Authors, Abstract, ArXiv ID, DOI) from PDF bytes."""
    extracted_text = ""
    pdf_meta_title = None
    pdf_meta_author = None

    # 1. Extract text and metadata using pypdf
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content_bytes))

        if reader.metadata:
            if reader.metadata.title and len(reader.metadata.title.strip()) > 3:
                pdf_meta_title = reader.metadata.title.strip()
            if reader.metadata.author and len(reader.metadata.author.strip()) > 2:
                pdf_meta_author = reader.metadata.author.strip()

        pages_text = []
        for page in reader.pages[:3]:
            txt = page.extract_text() or ""
            if txt.strip():
                pages_text.append(txt)
        extracted_text = "\n".join(pages_text)
    except Exception as e:
        logger.warning(f"pypdf extraction warning for {filename}: {e}")

    # Fallback decode if pypdf extracted minimal text
    if len(extracted_text) < 50:
        extracted_text = content_bytes[:8192].decode("latin1", errors="ignore")

    # 2. Extract ArXiv ID
    arxiv_match = re.search(r"arXiv:\s*([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)", extracted_text, re.IGNORECASE)
    if not arxiv_match:
        arxiv_match = re.search(r"\b([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)\b", filename)
    arxiv_id = arxiv_match.group(1) if arxiv_match else None

    # 3. Extract DOI
    doi_match = re.search(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", extracted_text)
    doi = doi_match.group(0).rstrip(".,;") if doi_match else None

    # 4. Extract Title
    title = pdf_meta_title
    clean_filename_title = filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ")

    if not title or title.lower() in ["untitled", "microsoft word", "latex", filename.lower()]:
        lines = [line.strip() for line in extracted_text.split("\n") if line.strip()]
        candidate_lines = []
        for line in lines[:15]:
            if re.match(r"^(abstract|introduction|arxiv:|1\s+intro)", line, re.IGNORECASE):
                break
            if len(line) > 5 and not line.startswith("http") and not line.isdigit() and not re.match(r"^[%<>\/]|^\d+\s+\d+\s+obj|^endobj|^stream", line):
                candidate_lines.append(line)
        if candidate_lines:
            title = " ".join(candidate_lines[:2])
        else:
            title = clean_filename_title.title()

    title = re.sub(r"\s+", " ", title).strip()
    if not title:
        title = clean_filename_title.title()

    # 5. Extract Authors
    authors = []
    if pdf_meta_author and not pdf_meta_author.lower().startswith("latex"):
        authors = [a.strip() for a in re.split(r"[,;]| and ", pdf_meta_author) if a.strip()]

    if not authors:
        lines = [line.strip() for line in extracted_text.split("\n") if line.strip()]
        for line in lines[1:12]:
            if "abstract" in line.lower() or "introduction" in line.lower():
                break
            if re.search(r"^[A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+", line):
                found = re.split(r"[,;]|\band\b|\d+", line)
                for f in found:
                    cleaned = re.sub(r"[0-9*†‡§#]", "", f).strip()
                    if len(cleaned) > 2 and "university" not in cleaned.lower() and "department" not in cleaned.lower():
                        authors.append(cleaned)
    if not authors:
        authors = ["Scanned PDF Author"]

    # 6. Extract Abstract
    abstract = "Scanned and saved PDF paper document."
    abs_match = re.search(
        r"abstract[\s\:\-\—\.\n]+(.*?)(?=\n\s*(?:1\.?\s+|1\s+intro|introduction|keywords|contents|\Z))",
        extracted_text,
        re.IGNORECASE | re.DOTALL,
    )
    if abs_match:
        raw_abs = abs_match.group(1).strip()
        if len(raw_abs) > 30:
            abstract = re.sub(r"\s+", " ", raw_abs[:1500])
    elif len(extracted_text) > 150:
        abstract = re.sub(r"\s+", " ", extracted_text[:500]) + "..."

    return {
        "arxiv_id": arxiv_id,
        "doi": doi,
        "title": title,
        "authors": authors,
        "abstract": abstract,
        "scanned_text": extracted_text[:2000],
    }
