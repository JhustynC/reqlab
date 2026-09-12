from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from reqlab.api.routers import exports


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


if __name__ == "__main__":
    unittest.main()
