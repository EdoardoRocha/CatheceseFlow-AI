import hashlib
from io import BytesIO
import re
from pypdf import PdfReader


def compute_file_hash(raw_bytes: bytes) -> str:
    """Calcula hash SHA-256 para evitar duplicidade de PDFs na mesma paróquia."""
    return hashlib.sha256(raw_bytes).hexdigest()


def _normalize_page_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def extract_pdf_pages(raw_bytes: bytes) -> list[tuple[int, str]]:
    """Extrai texto página a página de um PDF ignorando páginas em branco."""
    reader = PdfReader(BytesIO(raw_bytes))
    pages: list[tuple[int, str]] = []

    for idx, page in enumerate(reader.pages, start=1):
        raw_text = page.extract_text() or ""
        cleaned = _normalize_page_text(raw_text)
        if cleaned:
            pages.append((idx, cleaned))

    return pages


def _split_text_with_overlap(
    text: str,
    chunk_size: int = 900,
    chunk_overlap: int = 150,
) -> list[str]:
    if len(text) <= chunk_size:
        return [text]

    safe_size = max(100, chunk_size)
    safe_overlap = max(0, min(chunk_overlap, safe_size - 20))
    chunks: list[str] = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + safe_size, text_len)

        if end < text_len:
            search_from = start + int(safe_size * 0.5)
            cut = -1
            for sep in ("\n\n", "\n", ". ", " "):
                pos = text.rfind(sep, search_from, end)
                if pos > start:
                    cut = pos + len(sep)
                    break
            if cut > start:
                end = cut

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= text_len:
            break

        next_start = end - safe_overlap
        start = next_start if next_start > start else end

    return chunks


def chunk_pdf_pages(
    pages: list[tuple[int, str]],
    chunk_size: int = 900,
    chunk_overlap: int = 150,
) -> list[dict]:
    """Divide o conteúdo das páginas em chunks sequenciais preservando página e índice."""
    all_chunks: list[dict] = []
    chunk_index = 0

    for page_number, page_text in pages:
        for piece in _split_text_with_overlap(
            page_text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        ):
            all_chunks.append(
                {
                    "page_number": page_number,
                    "chunk_index": chunk_index,
                    "content": piece,
                }
            )
            chunk_index += 1

    return all_chunks
