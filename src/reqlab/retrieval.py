from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter

from .models import Fragment

STOPWORDS = {
    "a", "al", "ante", "bajo", "con", "contra", "de", "del", "el", "en", "es", "la", "las",
    "lo", "los", "para", "por", "que", "se", "su", "sus", "un", "una", "y", "o", "como",
}


def tokenize(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    return [term for term in re.findall(r"[a-z0-9]+", normalized) if len(term) > 2 and term not in STOPWORDS]


class TfidfRetrievalAgent:
    """Recuperación contextual reproducible basada en similitud TF-IDF coseno."""

    def __init__(self, fragments: list[Fragment]):
        self.fragments = fragments
        self._terms = [Counter(tokenize(fragment.text)) for fragment in fragments]
        document_count = len(fragments)
        document_frequency: Counter[str] = Counter()
        for terms in self._terms:
            document_frequency.update(terms.keys())
        self._idf = {
            term: math.log((document_count + 1) / (frequency + 1)) + 1
            for term, frequency in document_frequency.items()
        }
        self._vectors = [self._vector(terms) for terms in self._terms]

    def retrieve(self, query: str, top_k: int = 12) -> list[tuple[Fragment, float]]:
        query_vector = self._vector(Counter(tokenize(query)))
        if not query_vector:
            return []
        scored = [
            (fragment, self._cosine(query_vector, vector))
            for fragment, vector in zip(self.fragments, self._vectors, strict=True)
        ]
        return [(fragment, score) for fragment, score in sorted(scored, key=lambda item: item[1], reverse=True)[:top_k] if score > 0]

    def _vector(self, counts: Counter[str]) -> dict[str, float]:
        if not counts:
            return {}
        total = sum(counts.values())
        return {term: (count / total) * self._idf.get(term, 0.0) for term, count in counts.items() if term in self._idf}

    @staticmethod
    def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
        numerator = sum(value * right.get(term, 0.0) for term, value in left.items())
        if not numerator:
            return 0.0
        left_norm = math.sqrt(sum(value * value for value in left.values()))
        right_norm = math.sqrt(sum(value * value for value in right.values()))
        return numerator / (left_norm * right_norm)

