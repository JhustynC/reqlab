from __future__ import annotations

import io
import importlib.util
import unittest
from unittest.mock import Mock, patch

from reqlab.api.routers import exports
from reqlab.exporters import build_docx


class ExportStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = Mock()
        self.repository.get_project.return_value = {"name": "Proyecto de prueba"}

    def test_json_export_marks_project_as_exported_after_building_content(self) -> None:
        with (
            patch.object(exports, "get_repository", return_value=self.repository),
            patch.object(exports, "project_export_json", return_value=b"{}") as build,
        ):
            response = exports.export_json("project-1")

        build.assert_called_once_with(self.repository, "project-1")
        self.repository.update_project_status.assert_called_once_with("project-1", "exported")
        self.assertEqual(b"{}", response.body)

    def test_docx_export_marks_project_as_exported_after_building_content(self) -> None:
        payload = {"project": {"name": "Proyecto de prueba"}}
        with (
            patch.object(exports, "get_repository", return_value=self.repository),
            patch.object(exports, "project_export_payload", return_value=payload) as export_payload,
            patch.object(exports, "build_docx", return_value=b"docx") as build,
        ):
            response = exports.export_docx("project-1")

        export_payload.assert_called_once_with(self.repository, "project-1")
        build.assert_called_once_with(payload)
        self.repository.update_project_status.assert_called_once_with("project-1", "exported")
        self.assertEqual(b"docx", response.body)

    @unittest.skipUnless(importlib.util.find_spec("docx"), "python-docx no está disponible")
    def test_docx_presents_each_artifact_as_a_table(self) -> None:
        from docx import Document

        artifacts = [
            {
                "artifact_key": "RF-001",
                "artifact_type": "RF",
                "title": "Registrar solicitud",
                "description": "Cuando se reciba una solicitud, el sistema deberá registrarla.",
                "priority": "Alta",
                "priority_source": "usuario",
                "status": "propuesto",
                "version": 1,
                "source_fragments": ["SRC-001-F001"],
                "related_artifacts": [],
                "ears_pattern": "event-driven",
                "verification_criteria": ["La solicitud queda almacenada."],
                "acceptance_criteria": [],
                "validation": {"warnings": []},
            },
            {
                "artifact_key": "HU-001",
                "artifact_type": "HU",
                "title": "Consultar solicitud",
                "description": "Como residente, quiero consultar mi solicitud para conocer su estado.",
                "priority": "Media",
                "priority_source": "corpus",
                "status": "aceptado",
                "version": 2,
                "source_fragments": ["SRC-001-F002"],
                "related_artifacts": ["RF-001"],
                "acceptance_criteria": ["Dado un caso, cuando se consulta, entonces se muestra su estado."],
                "validation": {"warnings": []},
            },
        ]
        payload = {
            "project": {"name": "Proyecto de prueba", "domain": "Pruebas"},
            "artifacts": artifacts,
            "fragments": [],
            "validation": {},
        }

        document = Document(io.BytesIO(build_docx(payload)))
        artifact_tables = [
            table
            for table in document.tables
            if table.rows and table.rows[0].cells[0].text.startswith(("RF-", "RNF-", "HU-"))
        ]

        self.assertEqual(len(artifacts), len(artifact_tables))
        self.assertIn("Redacción", [cell.text for cell in artifact_tables[0].columns[0].cells])
        self.assertIn("Criterios de aceptación", [cell.text for cell in artifact_tables[1].columns[0].cells])


if __name__ == "__main__":
    unittest.main()
