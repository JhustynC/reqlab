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
    """Segmenta por estructura del documento con tamaño y solapamiento configurables."""

    def __init__(self, chunk_size: int = 1200, overlap: int = 180):
        if chunk_size < 300:
            raise ValueError("chunk_size debe ser al menos 300 caracteres.")
        if overlap < 0 or overlap >= chunk_size:
            raise ValueError("overlap debe ser positivo y menor que chunk_size.")
        self.chunk_size = chunk_size
        self.overlap = overlap

    def segment(
        self,
        text: str,
        source_code: str,
        source_file: str,
        source_kind: str = "document",
    ) -> list[Fragment]:
        units = self._structural_units(text, source_kind)
        chunks = self._merge_units(units)
        return [
            Fragment(
                fragment_id=f"{source_code}-F{index:03d}",
                source_id=source_code,
                source_file=source_file,
                heading=self._heading(chunk, index, source_kind),
                text=chunk,
            )
            for index, chunk in enumerate(chunks, start=1)
        ]

    def _structural_units(self, text: str, source_kind: str) -> list[str]:
        if source_kind == "email":
            return self._split_email(text)
        if source_kind == "interview":
            return self._split_interview(text)
        if source_kind == "conversation":
            return self._split_conversation(text)
        if source_kind in {"meeting_notes", "note"}:
            return self._split_markdown_sections(text)
        return [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]

    @staticmethod
    def _split_email(text: str) -> list[str]:
        headers = re.split(
            r"(?=^(?:De|Para|Asunto|Subject|From|To|Date|Fecha)\s*:)",
            text,
            flags=re.MULTILINE | re.IGNORECASE,
        )
        return [part.strip() for part in headers if part.strip()]

    @staticmethod
    def _split_interview(text: str) -> list[str]:
        parts = re.split(
            r"(?=^(?:Entrevistador|Entrevistado|Entrevistadora|Pregunta|Respuesta|Q|A)\s*:)",
            text,
            flags=re.MULTILINE | re.IGNORECASE,
        )
        units = [part.strip() for part in parts if part.strip()]
        return units or [text.strip()]

    @staticmethod
    def _split_conversation(text: str) -> list[str]:
        parts = re.split(r"(?=^[A-Za-zÁÉÍÓÚáéíóú0-9 _-]{2,40}:\s)", text, flags=re.MULTILINE)
        units = [part.strip() for part in parts if part.strip()]
        return units or [text.strip()]

    @staticmethod
    def _split_markdown_sections(text: str) -> list[str]:
        parts = re.split(r"(?=^#{1,3}\s+.+$)", text, flags=re.MULTILINE)
        units = [part.strip() for part in parts if part.strip()]
        return units or [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]

    def _merge_units(self, units: list[str]) -> list[str]:
        chunks: list[str] = []
        current = ""
        for unit in units:
            if len(unit) > self.chunk_size:
                if current:
                    chunks.append(current.strip())
                    current = ""
                chunks.extend(self._split_long_text(unit))
                continue
            candidate = f"{current}\n\n{unit}".strip()
            if current and len(candidate) > self.chunk_size:
                chunks.append(current.strip())
                prefix = current[-self.overlap :].strip() if self.overlap else ""
                current = f"{prefix}\n\n{unit}".strip()
            else:
                current = candidate
        if current:
            chunks.append(current.strip())
        return chunks

    def _split_long_text(self, text: str) -> list[str]:
        step = self.chunk_size - self.overlap
        return [
            text[start : start + self.chunk_size].strip()
            for start in range(0, len(text), step)
            if text[start : start + self.chunk_size].strip()
        ]

    @staticmethod
    def _heading(chunk: str, index: int, source_kind: str) -> str:
        first_line = chunk.splitlines()[0].strip().lstrip("# ")
        if source_kind == "email" and re.match(r"^(De|Para|Asunto|Subject)\s*:", first_line, re.IGNORECASE):
            return first_line[:100]
        if len(first_line) <= 100:
            return first_line
        return f"Fragmento {index}"


def safe_filename(filename: str) -> str:
    """Conserva una extensión válida y elimina componentes de ruta."""
    name = Path(filename).name
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).stem).strip("._") or "fuente"
    suffix = Path(name).suffix.lower()
    return f"{stem}{suffix}"


def infer_source_kind(filename: str, text: str) -> str:
    """Infiere una estructura de segmentación sin exigir plantillas al usuario."""
    name = Path(filename).stem.lower()
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")

    filename_rules = (
        (
            "document",
            (
                "procedimiento",
                "catalogo",
                "catálogo",
                "acuerdo",
                "resolucion",
                "resolución",
                "politica",
                "política",
                "norma",
                "exportacion",
                "exportación",
                "export",
            ),
        ),
        ("interview", ("entrevista", "interview", "transcripcion", "transcripción")),
        ("email", ("correo", "email", "e-mail")),
        ("conversation", ("chat", "conversacion", "conversación", "mensajes")),
        ("meeting_notes", ("minuta", "acta", "reunion", "reunión", "meeting")),
        ("note", ("informe", "nota", "resultados", "reporte", "report")),
    )
    for source_kind, markers in filename_rules:
        if any(marker in name for marker in markers):
            return source_kind

    interview_turns = re.findall(
        r"^(?:Entrevistador(?:a)?|Entrevistado(?:a)?|Pregunta|Respuesta|Q|A)\s*:",
        normalized,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    if len(interview_turns) >= 3:
        return "interview"

    email_headers = re.findall(
        r"^(?:De|Para|Asunto|Subject|From|To|Date|Fecha)\s*:",
        normalized,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    if len(email_headers) >= 2:
        return "email"

    conversation_turns = re.findall(
        r"^(?:\[?\d{1,2}:\d{2}\]?\s*)?[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9 _-]{2,40}:\s+",
        normalized,
        flags=re.MULTILINE,
    )
    if len(conversation_turns) >= 5:
        return "conversation"
    return "document"
