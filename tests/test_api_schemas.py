import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from reqlab.api.schemas import DefinitionAnswer


class DefinitionAnswerSchemaTests(unittest.TestCase):
    def test_accepts_detailed_provisional_profile_from_large_corpus(self):
        answer = DefinitionAnswer(question_key="DEF-SCOPE", answer="x" * 12_000)

        self.assertEqual(len(answer.answer), 12_000)

    def test_rejects_unbounded_definition_answer(self):
        with self.assertRaises(ValidationError):
            DefinitionAnswer(question_key="DEF-SCOPE", answer="x" * 20_001)


if __name__ == "__main__":
    unittest.main()
