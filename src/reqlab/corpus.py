from __future__ import annotations

import json
import re
from pathlib import Path

from .models import Fragment

HEADING = re.compile(r"^##\s+(.*)$", re.MULTILINE)
DEFAULT_FRAGMENT_ID_REGEX = r"[A-Za-z][A-Za-z0-9_-]*"


class CorpusIngestionAgent:
    """Lee Markdown y produce fragmentos atómicos con identificadores estables."""

    def load(self, corpus_dir: str | Path) -> list[Fragment]:
        base = Path(corpus_dir)
        manifest_path = base / "corpus_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        fragment_marker = re.compile(rf"\[({manifest.get('fragment_id_regex', DEFAULT_FRAGMENT_ID_REGEX)})\]")
        fragments: list[Fragment] = []
        for document in manifest["documents"]:
            source_file = document["file"]
            path = base / source_file
            fragments.extend(self._split_document(path, document["source_id"], source_file, fragment_marker))
        if not fragments:
            raise ValueError("No se encontraron fragmentos con el patrón de identificador declarado por el corpus.")
        duplicates = self._duplicates(fragments)
        if duplicates:
            raise ValueError(f"Identificadores de fragmento duplicados: {', '.join(duplicates)}")
        return fragments

    @staticmethod
    def _split_document(path: Path, source_id: str, source_file: str, fragment_marker: re.Pattern[str]) -> list[Fragment]:
        text = path.read_text(encoding="utf-8")
        headings = list(HEADING.finditer(text))
        fragments: list[Fragment] = []
        for position, match in enumerate(headings):
            end = headings[position + 1].start() if position + 1 < len(headings) else len(text)
            section = text[match.start() : end].strip()
            id_match = fragment_marker.search(section)
            if not id_match:
                continue
            fragment_id = id_match.group(1)
            fragments.append(
                Fragment(
                    fragment_id=fragment_id,
                    source_id=source_id,
                    source_file=source_file,
                    heading=match.group(1).strip(),
                    text=section,
                )
            )
        return fragments

    @staticmethod
    def _duplicates(fragments: list[Fragment]) -> list[str]:
        ids = [fragment.fragment_id for fragment in fragments]
        return sorted({value for value in ids if ids.count(value) > 1})
