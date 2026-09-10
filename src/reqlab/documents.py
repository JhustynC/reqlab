from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from pathlib import Path

from .models import Fragment


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


@dataclass(frozen=True)
class ExtractedDocument:
    filename: str
    text: str
    sha256: str


class DocumentExtractionService:
    """Extrae texto de los formatos delimitados para el MVP."""

    def extract(self, filename: str, content: bytes) -> ExtractedDocument:
        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"Formato no soportado: {suffix or 'sin extensión'}")
        if not content:
            raise ValueError("El archivo está vacío.")
        if suffix in {".txt", ".md"}:
            text = self._decode_text(content)
        elif suffix == ".pdf":
            text = self._extract_pdf(content)
        else:
            text = self._extract_docx(content)
        normalized = self._normalize(text)
        if len(normalized) < 20:
            raise ValueError("No se pudo extraer suficiente texto del archivo.")
        return ExtractedDocument(filename, normalized, hashlib.sha256(content).hexdigest())

    @staticmethod
    def _decode_text(content: bytes) -> str:
        for encoding in ("utf-8-sig", "utf-8", "cp1252"):
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise ValueError("No se pudo determinar la codificación del archivo de texto.")

    @staticmethod
    def _extract_pdf(content: bytes) -> str:
        try:
            from pypdf import PdfReader
        except ImportError as error:
            raise RuntimeError("La dependencia pypdf no está instalada.") from error
        reader = PdfReader(io.BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages)

    @staticmethod
    def _extract_docx(content: bytes) -> str:
        try:
            from docx import Document
        except ImportError as error:
            raise RuntimeError("La dependencia python-docx no está instalada.") from error
        document = Document(io.BytesIO(content))
        blocks = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
        for table in document.tables:
            for row in table.rows:
                values = [cell.text.strip() for cell in row.cells]
                if any(values):
                    blocks.append(" | ".join(values))
        return "\n\n".join(blocks)

    @staticmethod
    def _normalize(text: str) -> str:
        text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


class TextSegmentationService:
    """Segmenta por párrafos con tamaño y solapamiento configurables."""

    def __init__(self, chunk_size: int = 1200, overlap: int = 180):
        if chunk_size < 300:
            raise ValueError("chunk_size debe ser al menos 300 caracteres.")
        if overlap < 0 or overlap >= chunk_size:
            raise ValueError("overlap debe ser positivo y menor que chunk_size.")
        self.chunk_size = chunk_size
        self.overlap = overlap

    def segment(self, text: str, source_code: str, source_file: str) -> list[Fragment]:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            if len(paragraph) > self.chunk_size:
                if current:
                    chunks.append(current.strip())
                    current = ""
                chunks.extend(self._split_long_text(paragraph))
                continue
            candidate = f"{current}\n\n{paragraph}".strip()
            if current and len(candidate) > self.chunk_size:
                chunks.append(current.strip())
                prefix = current[-self.overlap :].strip() if self.overlap else ""
                current = f"{prefix}\n\n{paragraph}".strip()
            else:
                current = candidate
        if current:
            chunks.append(current.strip())
        return [
            Fragment(
                fragment_id=f"{source_code}-F{index:03d}",
                source_id=source_code,
                source_file=source_file,
                heading=self._heading(chunk, index),
                text=chunk,
            )
            for index, chunk in enumerate(chunks, start=1)
        ]

    def _split_long_text(self, text: str) -> list[str]:
        step = self.chunk_size - self.overlap
        return [text[start : start + self.chunk_size].strip() for start in range(0, len(text), step) if text[start : start + self.chunk_size].strip()]

    @staticmethod
    def _heading(chunk: str, index: int) -> str:
        first_line = chunk.splitlines()[0].strip().lstrip("# ")
        if len(first_line) <= 100:
            return first_line
        return f"Fragmento {index}"


def safe_filename(filename: str) -> str:
    """Conserva una extensión válida y elimina componentes de ruta."""
    name = Path(filename).name
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).stem).strip("._") or "fuente"
    suffix = Path(name).suffix.lower()
    return f"{stem}{suffix}"

