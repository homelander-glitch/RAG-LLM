import hashlib
import os
from pathlib import Path
from typing import List, Dict, Tuple, Any

from pypdf import PdfReader
from docx import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}


def compute_sha256(content: bytes) -> str:
    """Calculate the SHA-256 hash of file bytes to prevent duplicates."""
    return hashlib.sha256(content).hexdigest()


def extract_chunks_from_file(
    file_path: str,
    filename: str,
    doc_id: str,
    user_id: str = "default",
    chunk_size: int = 800,
    chunk_overlap: int = 100
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Extracts text preserving page numbers where applicable,
    and splits into chunks with RecursiveCharacterTextSplitter.
    Includes user_id in metadata for strict multi-user privacy isolation.
    Returns (chunks, total_pages).
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file format: {ext}. Supported formats: PDF, DOCX, TXT.")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", " ", ""]
    )

    chunks: List[Dict[str, Any]] = []
    total_pages = 1

    if ext == ".pdf":
        try:
            reader = PdfReader(file_path)
            total_pages = max(len(reader.pages), 1)

            for page_idx, page in enumerate(reader.pages):
                page_num = page_idx + 1
                page_text = page.extract_text() or ""
                if not page_text.strip():
                    continue

                split_pieces = splitter.split_text(page_text)
                for chunk_idx, piece in enumerate(split_pieces):
                    chunk_id = f"{doc_id}_p{page_num}_c{chunk_idx + 1}"
                    chunks.append({
                        "chunk_id": chunk_id,
                        "text": piece.strip(),
                        "metadata": {
                            "user_id": user_id,
                            "doc_id": doc_id,
                            "filename": filename,
                            "page": page_num,
                            "chunk_id": chunk_id
                        }
                    })
        except Exception as e:
            raise ValueError(f"Failed to read PDF document: {str(e)}")

    elif ext == ".docx":
        try:
            doc = Document(file_path)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            full_text = "\n\n".join(paragraphs)
            total_pages = 1

            if full_text.strip():
                split_pieces = splitter.split_text(full_text)
                for chunk_idx, piece in enumerate(split_pieces):
                    chunk_id = f"{doc_id}_p1_c{chunk_idx + 1}"
                    chunks.append({
                        "chunk_id": chunk_id,
                        "text": piece.strip(),
                        "metadata": {
                            "user_id": user_id,
                            "doc_id": doc_id,
                            "filename": filename,
                            "page": 1,
                            "chunk_id": chunk_id
                        }
                    })
        except Exception as e:
            raise ValueError(f"Failed to read DOCX document: {str(e)}")

    elif ext == ".txt":
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                full_text = f.read()
            total_pages = 1

            if full_text.strip():
                split_pieces = splitter.split_text(full_text)
                for chunk_idx, piece in enumerate(split_pieces):
                    chunk_id = f"{doc_id}_p1_c{chunk_idx + 1}"
                    chunks.append({
                        "chunk_id": chunk_id,
                        "text": piece.strip(),
                        "metadata": {
                            "user_id": user_id,
                            "doc_id": doc_id,
                            "filename": filename,
                            "page": 1,
                            "chunk_id": chunk_id
                        }
                    })
        except Exception as e:
            raise ValueError(f"Failed to read TXT document: {str(e)}")

    if not chunks:
        raise ValueError("Document contains no readable text.")

    return chunks, total_pages
