from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .models import Artifact, Fragment


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SQLiteRepository:
    """Persistencia transaccional del prototipo web.

    SQLite almacena proyectos, fuentes, preguntas, artefactos, versiones y
    ejecuciones. Los documentos originales y los vectores se conservan fuera de
    la base relacional.
    """

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    domain TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'created',
                    definition_confirmed INTEGER NOT NULL DEFAULT 0,
                    archived_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sources (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    source_code TEXT NOT NULL,
                    original_name TEXT NOT NULL,
                    stored_path TEXT NOT NULL,
                    content_type TEXT NOT NULL DEFAULT '',
                    source_kind TEXT NOT NULL DEFAULT 'document',
                    sha256 TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'uploaded',
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(project_id, source_code),
                    UNIQUE(project_id, sha256)
                );

                CREATE TABLE IF NOT EXISTS fragments (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    source_id TEXT,
                    fragment_key TEXT NOT NULL,
                    heading TEXT NOT NULL DEFAULT '',
                    text TEXT NOT NULL,
                    position INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    UNIQUE(project_id, fragment_key),
                    FOREIGN KEY(source_id) REFERENCES sources(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS definition_questions (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    question_key TEXT NOT NULL,
                    question TEXT NOT NULL,
                    rationale TEXT NOT NULL DEFAULT '',
                    required INTEGER NOT NULL DEFAULT 0,
                    origin TEXT NOT NULL DEFAULT 'core',
                    dimension TEXT NOT NULL DEFAULT '',
                    suggested_answer TEXT NOT NULL DEFAULT '',
                    evidence_json TEXT NOT NULL DEFAULT '[]',
                    confidence TEXT NOT NULL DEFAULT '',
                    answer TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(project_id, question_key)
                );

                CREATE TABLE IF NOT EXISTS project_profiles (
                    project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
                    profile_json TEXT NOT NULL,
                    confirmed_at TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    phase TEXT NOT NULL,
                    status TEXT NOT NULL,
                    agent_id TEXT NOT NULL DEFAULT '',
                    parameters_json TEXT NOT NULL DEFAULT '{}',
                    error_message TEXT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT
                );

                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS artifacts (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    artifact_key TEXT NOT NULL,
                    artifact_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    source_fragments_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    acceptance_criteria_json TEXT NOT NULL,
                    related_artifacts_json TEXT NOT NULL DEFAULT '[]',
                    version INTEGER NOT NULL DEFAULT 1,
                    validation_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(project_id, artifact_key)
                );

                CREATE TABLE IF NOT EXISTS artifact_versions (
                    id TEXT PRIMARY KEY,
                    artifact_id TEXT NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
                    version INTEGER NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    change_origin TEXT NOT NULL,
                    change_instruction TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    UNIQUE(artifact_id, version)
                );

                CREATE TABLE IF NOT EXISTS validation_reports (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    report_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS semantic_validation_reports (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    run_id TEXT REFERENCES runs(id) ON DELETE SET NULL,
                    input_snapshot_hash TEXT NOT NULL,
                    report_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS revision_proposals (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    artifact_id TEXT NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
                    proposal_json TEXT NOT NULL,
                    instruction TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    decided_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_sources_project_id
                    ON sources(project_id);
                CREATE INDEX IF NOT EXISTS idx_fragments_project_id
                    ON fragments(project_id);
                CREATE INDEX IF NOT EXISTS idx_questions_project_id
                    ON definition_questions(project_id);
                CREATE INDEX IF NOT EXISTS idx_runs_project_phase
                    ON runs(project_id, phase);
                CREATE INDEX IF NOT EXISTS idx_artifacts_project_type
                    ON artifacts(project_id, artifact_type);
                CREATE INDEX IF NOT EXISTS idx_validation_project_created
                    ON validation_reports(project_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_semantic_validation_project_created
                    ON semantic_validation_reports(project_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_revision_artifact_status
                    ON revision_proposals(artifact_id, status);
                """
            )
            project_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(projects)").fetchall()
            }
            if "archived_at" not in project_columns:
                connection.execute("ALTER TABLE projects ADD COLUMN archived_at TEXT")
            source_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(sources)").fetchall()
            }
            if "source_kind" not in source_columns:
                connection.execute(
                    "ALTER TABLE sources ADD COLUMN source_kind TEXT NOT NULL DEFAULT 'document'"
                )
            question_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(definition_questions)").fetchall()
            }
            for column, declaration in (
                ("dimension", "TEXT NOT NULL DEFAULT ''"),
                ("suggested_answer", "TEXT NOT NULL DEFAULT ''"),
                ("evidence_json", "TEXT NOT NULL DEFAULT '[]'"),
                ("confidence", "TEXT NOT NULL DEFAULT ''"),
            ):
                if column not in question_columns:
                    connection.execute(
                        f"ALTER TABLE definition_questions ADD COLUMN {column} {declaration}"
                    )
            artifact_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(artifacts)").fetchall()
            }
            if "related_artifacts_json" not in artifact_columns:
                connection.execute(
                    "ALTER TABLE artifacts ADD COLUMN related_artifacts_json TEXT NOT NULL DEFAULT '[]'"
                )
            connection.execute("PRAGMA optimize")

    def create_project(self, name: str, description: str = "", domain: str = "") -> dict[str, Any]:
        project_id = str(uuid.uuid4())
        now = utc_now()
        with self.connection() as connection:
            connection.execute(
                "INSERT INTO projects (id, name, description, domain, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (project_id, name.strip(), description.strip(), domain.strip(), now, now),
            )
        return self.get_project(project_id)

    def list_projects(self, archived: bool = False) -> list[dict[str, Any]]:
        with self.connection() as connection:
            condition = "archived_at IS NOT NULL" if archived else "archived_at IS NULL"
            rows = connection.execute(
                f"SELECT * FROM projects WHERE {condition} ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_project(self, project_id: str) -> dict[str, Any]:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise KeyError(f"Proyecto no encontrado: {project_id}")
        return dict(row)

    def update_project_status(self, project_id: str, status: str) -> None:
        with self.connection() as connection:
            connection.execute(
                "UPDATE projects SET status = ?, updated_at = ? WHERE id = ?",
                (status, utc_now(), project_id),
            )

    def archive_project(self, project_id: str, archived: bool) -> dict[str, Any]:
        self.get_project(project_id)
        now = utc_now()
        with self.connection() as connection:
            connection.execute(
                "UPDATE projects SET archived_at = ?, updated_at = ? WHERE id = ?",
                (now if archived else None, now, project_id),
            )
        return self.get_project(project_id)

    def delete_project(self, project_id: str) -> None:
        self.get_project(project_id)
        with self.connection() as connection:
            connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    def next_source_code(self, project_id: str) -> str:
        with self.connection() as connection:
            current = connection.execute(
                """SELECT COALESCE(MAX(CAST(SUBSTR(source_code, 5) AS INTEGER)), 0)
                   FROM sources WHERE project_id = ? AND source_code LIKE 'SRC-%'""",
                (project_id,),
            ).fetchone()[0]
        return f"SRC-{int(current) + 1:03d}"

    def add_source(
        self,
        project_id: str,
        source_code: str,
        original_name: str,
        stored_path: str,
        content_type: str,
        sha256: str,
        source_kind: str = "document",
    ) -> dict[str, Any]:
        source_id = str(uuid.uuid4())
        with self.connection() as connection:
            connection.execute(
                """INSERT INTO sources
                   (id, project_id, source_code, original_name, stored_path, content_type, source_kind, sha256, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (source_id, project_id, source_code, original_name, stored_path, content_type, source_kind, sha256, utc_now()),
            )
            connection.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (utc_now(), project_id))
        return self.get_source(source_id)

    def get_source(self, source_id: str) -> dict[str, Any]:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
        if row is None:
            raise KeyError(f"Fuente no encontrada: {source_id}")
        return dict(row)

    def get_project_source(self, project_id: str, source_id: str) -> dict[str, Any]:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM sources WHERE id = ? AND project_id = ?",
                (source_id, project_id),
            ).fetchone()
        if row is None:
            raise KeyError(f"Fuente no encontrada en el proyecto: {source_id}")
        return dict(row)

    def find_source_by_hash(self, project_id: str, sha256: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM sources WHERE project_id = ? AND sha256 = ?", (project_id, sha256)
            ).fetchone()
        return dict(row) if row else None

    def list_sources(self, project_id: str) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM sources WHERE project_id = ? ORDER BY source_code", (project_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def update_source_status(self, source_id: str, status: str, error_message: str | None = None) -> None:
        with self.connection() as connection:
            connection.execute(
                "UPDATE sources SET status = ?, error_message = ? WHERE id = ?",
                (status, error_message, source_id),
            )

    def mark_project_sources_indexed(self, project_id: str) -> None:
        with self.connection() as connection:
            connection.execute(
                """UPDATE sources SET status = 'indexed', error_message = NULL
                   WHERE project_id = ? AND status IN ('uploaded', 'processed', 'indexed')""",
                (project_id,),
            )

    def delete_source_and_invalidate(self, project_id: str, source_id: str) -> dict[str, Any]:
        source = self.get_project_source(project_id, source_id)
        now = utc_now()
        with self.connection() as connection:
            connection.execute("DELETE FROM sources WHERE id = ? AND project_id = ?", (source_id, project_id))
            connection.execute(
                "DELETE FROM fragments WHERE project_id = ? AND source_id IS NULL AND fragment_key LIKE 'USR-DEF-%'",
                (project_id,),
            )
            connection.execute(
                "DELETE FROM definition_questions WHERE project_id = ? AND origin = 'dynamic'",
                (project_id,),
            )
            connection.execute(
                """UPDATE definition_questions
                   SET answer = '', suggested_answer = '', evidence_json = '[]', confidence = '', updated_at = ?
                   WHERE project_id = ? AND origin = 'core'""",
                (now, project_id),
            )
            connection.execute("DELETE FROM project_profiles WHERE project_id = ?", (project_id,))
            connection.execute("DELETE FROM validation_reports WHERE project_id = ?", (project_id,))
            connection.execute("DELETE FROM artifacts WHERE project_id = ?", (project_id,))
            connection.execute("DELETE FROM runs WHERE project_id = ?", (project_id,))
            remaining = int(
                connection.execute(
                    "SELECT COUNT(*) FROM sources WHERE project_id = ?", (project_id,)
                ).fetchone()[0]
            )
            connection.execute(
                """UPDATE projects SET definition_confirmed = 0, status = ?, updated_at = ?
                   WHERE id = ?""",
                ("sources_ready" if remaining else "created", now, project_id),
            )
        return source

    def invalidate_after_source_change(self, project_id: str) -> None:
        now = utc_now()
        with self.connection() as connection:
            connection.execute(
                "DELETE FROM fragments WHERE project_id = ? AND source_id IS NULL AND fragment_key LIKE 'USR-DEF-%'",
                (project_id,),
            )
            connection.execute(
                "DELETE FROM definition_questions WHERE project_id = ? AND origin = 'dynamic'",
                (project_id,),
            )
            connection.execute(
                """UPDATE definition_questions
                   SET answer = '', suggested_answer = '', evidence_json = '[]', confidence = '', updated_at = ?
                   WHERE project_id = ? AND origin = 'core'""",
                (now, project_id),
            )
            connection.execute("DELETE FROM project_profiles WHERE project_id = ?", (project_id,))
            connection.execute("DELETE FROM validation_reports WHERE project_id = ?", (project_id,))
            connection.execute("DELETE FROM artifacts WHERE project_id = ?", (project_id,))
            connection.execute("DELETE FROM runs WHERE project_id = ?", (project_id,))
            connection.execute(
                """UPDATE projects SET definition_confirmed = 0, status = 'sources_ready', updated_at = ?
                   WHERE id = ?""",
                (now, project_id),
            )

    def reset_generation_results(self, project_id: str) -> None:
        """Elimina salidas derivadas para iniciar una generación nueva con la definición vigente."""
        self.get_project(project_id)
        now = utc_now()
        with self.connection() as connection:
            connection.execute("DELETE FROM validation_reports WHERE project_id = ?", (project_id,))
            # artifact_versions y revision_proposals se eliminan por cascada.
            connection.execute("DELETE FROM artifacts WHERE project_id = ?", (project_id,))
            connection.execute(
                "DELETE FROM runs WHERE project_id = ? AND phase = 'generation'", (project_id,)
            )
            connection.execute(
                """UPDATE projects SET status = 'ready_to_generate', updated_at = ?
                   WHERE id = ?""",
                (now, project_id),
            )

    def replace_source_fragments(self, source: dict[str, Any], fragments: list[Fragment]) -> None:
        now = utc_now()
        with self.connection() as connection:
            connection.execute("DELETE FROM fragments WHERE source_id = ?", (source["id"],))
            connection.executemany(
                """INSERT INTO fragments
                   (id, project_id, source_id, fragment_key, heading, text, position, metadata_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        str(uuid.uuid4()),
                        source["project_id"],
                        source["id"],
                        fragment.fragment_id,
                        fragment.heading,
                        fragment.text,
                        position,
                        json.dumps({"source_file": fragment.source_file}, ensure_ascii=False),
                        now,
                    )
                    for position, fragment in enumerate(fragments, start=1)
                ],
            )

    def upsert_definition_fragments(self, project_id: str, answers: list[dict[str, Any]]) -> list[Fragment]:
        fragments: list[Fragment] = []
        now = utc_now()
        with self.connection() as connection:
            for index, item in enumerate(answers, start=1):
                if not item.get("answer", "").strip():
                    continue
                key = f"USR-DEF-{index:03d}"
                text = f"Pregunta de definición: {item['question']}\nRespuesta confirmada por el usuario: {item['answer'].strip()}"
                fragment = Fragment(key, "USR-DEF", "definicion_usuario", item["question"], text)
                fragments.append(fragment)
                connection.execute(
                    """INSERT INTO fragments
                       (id, project_id, source_id, fragment_key, heading, text, position, metadata_json, created_at)
                       VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(project_id, fragment_key) DO UPDATE SET
                           heading = excluded.heading,
                           text = excluded.text,
                           position = excluded.position,
                           metadata_json = excluded.metadata_json""",
                    (
                        str(uuid.uuid4()),
                        project_id,
                        key,
                        item["question"],
                        text,
                        index,
                        json.dumps(
                            {
                                "origin": "user_definition",
                                "question_key": item["question_key"],
                                "dimension": item.get("dimension", ""),
                            },
                            ensure_ascii=False,
                        ),
                        now,
                    ),
                )
        return fragments

    def list_fragments(self, project_id: str) -> list[Fragment]:
        with self.connection() as connection:
            rows = connection.execute(
                """SELECT f.fragment_key, COALESCE(s.source_code, 'USR-DEF') AS source_code,
                          COALESCE(s.original_name, 'definicion_usuario') AS source_file,
                          f.heading, f.text
                   FROM fragments f
                   LEFT JOIN sources s ON s.id = f.source_id
                   WHERE f.project_id = ?
                   ORDER BY COALESCE(s.source_code, 'ZZZ'), f.position""",
                (project_id,),
            ).fetchall()
        return [
            Fragment(row["fragment_key"], row["source_code"], row["source_file"], row["heading"], row["text"])
            for row in rows
        ]

    def get_fragment(self, project_id: str, fragment_key: str) -> dict[str, Any]:
        with self.connection() as connection:
            row = connection.execute(
                """SELECT f.fragment_key, f.heading, f.text, f.position, f.metadata_json,
                          COALESCE(s.source_code, 'USR-DEF') AS source_code,
                          COALESCE(s.original_name, 'Definición del usuario') AS source_name
                   FROM fragments f
                   LEFT JOIN sources s ON s.id = f.source_id
                   WHERE f.project_id = ? AND f.fragment_key = ?""",
                (project_id, fragment_key),
            ).fetchone()
        if not row:
            raise KeyError(f"Fragmento no encontrado: {fragment_key}")
        item = dict(row)
        item["metadata"] = json.loads(item.pop("metadata_json"))
        return item

    def list_fragment_summaries(self, project_id: str, source_code: str | None = None) -> list[dict[str, Any]]:
        query = """SELECT f.fragment_key, f.heading, f.position,
                          COALESCE(s.source_code, 'USR-DEF') AS source_code,
                          COALESCE(s.original_name, 'Definición del usuario') AS source_name
                   FROM fragments f
                   LEFT JOIN sources s ON s.id = f.source_id
                   WHERE f.project_id = ?"""
        parameters: list[Any] = [project_id]
        if source_code:
            query += " AND COALESCE(s.source_code, 'USR-DEF') = ?"
            parameters.append(source_code)
        query += " ORDER BY source_code, f.position"
        with self.connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]

    def count_fragments(self, project_id: str) -> int:
        with self.connection() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM fragments WHERE project_id = ?", (project_id,)).fetchone()[0])

    def ensure_questions(self, project_id: str, questions: list[dict[str, Any]]) -> None:
        now = utc_now()
        with self.connection() as connection:
            connection.executemany(
                """INSERT INTO definition_questions
                   (id, project_id, question_key, question, rationale, required, origin, dimension,
                    suggested_answer, evidence_json, confidence, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(project_id, question_key) DO UPDATE SET
                       question = excluded.question,
                       rationale = excluded.rationale,
                       required = excluded.required,
                       origin = excluded.origin,
                       dimension = excluded.dimension""",
                [
                    (
                        str(uuid.uuid4()),
                        project_id,
                        item["question_key"],
                        item["question"],
                        item.get("rationale", ""),
                        int(bool(item.get("required"))),
                        item.get("origin", "core"),
                        item.get("dimension", ""),
                        item.get("suggested_answer", ""),
                        json.dumps(item.get("evidence", []), ensure_ascii=False),
                        item.get("confidence", ""),
                        now,
                        now,
                    )
                    for item in questions
                ],
            )

    def replace_definition_analysis(
        self,
        project_id: str,
        core_questions: list[dict[str, Any]],
        analysis: dict[str, Any],
    ) -> None:
        self.ensure_questions(project_id, core_questions)
        profile_by_dimension = {
            item["dimension"]: item for item in analysis.get("profile", [])
        }
        now = utc_now()
        with self.connection() as connection:
            connection.execute(
                "DELETE FROM definition_questions WHERE project_id = ? AND origin = 'dynamic'",
                (project_id,),
            )
            for core in core_questions:
                profile = profile_by_dimension.get(core.get("dimension", ""), {})
                suggestion = str(profile.get("value", "")).strip()
                connection.execute(
                    """UPDATE definition_questions
                       SET answer = ?, suggested_answer = ?, evidence_json = ?, confidence = ?,
                           required = 0, dimension = ?, updated_at = ?
                       WHERE project_id = ? AND question_key = ?""",
                    (
                        suggestion,
                        suggestion,
                        json.dumps(profile.get("source_fragments", []), ensure_ascii=False),
                        profile.get("confidence", "missing"),
                        core.get("dimension", ""),
                        now,
                        project_id,
                        core["question_key"],
                    ),
                )
            dynamic = analysis.get("questions", [])
            connection.executemany(
                """INSERT INTO definition_questions
                   (id, project_id, question_key, question, rationale, required, origin, dimension,
                    suggested_answer, evidence_json, confidence, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 1, 'dynamic', ?, '', ?, 'pending', ?, ?)""",
                [
                    (
                        str(uuid.uuid4()), project_id, item["question_key"], item["question"],
                        item.get("rationale", ""), item.get("dimension", ""),
                        json.dumps(item.get("evidence", []), ensure_ascii=False), now, now,
                    )
                    for item in dynamic
                ],
            )
        self.save_profile(
            project_id,
            {
                "provisional_profile": analysis.get("profile", []),
                "coverage": analysis.get("coverage", {}),
            },
            confirmed=False,
        )

    def list_questions(self, project_id: str) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                """SELECT * FROM definition_questions WHERE project_id = ?
                   ORDER BY CASE origin WHEN 'core' THEN 0 ELSE 1 END,
                            CASE question_key
                                WHEN 'DEF-OBJ' THEN 1
                                WHEN 'DEF-PROBLEM' THEN 2
                                WHEN 'DEF-ACTORS' THEN 3
                                WHEN 'DEF-SCOPE' THEN 4
                                WHEN 'DEF-OUT' THEN 5
                                WHEN 'DEF-RULES' THEN 6
                                WHEN 'DEF-QUALITY' THEN 7
                                WHEN 'DEF-CONFLICTS' THEN 8
                                ELSE 99
                            END,
                            question_key""",
                (project_id,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["evidence"] = json.loads(item.pop("evidence_json"))
            result.append(item)
        return result

    def save_answer(self, project_id: str, question_key: str, answer: str) -> None:
        with self.connection() as connection:
            connection.execute(
                """UPDATE definition_questions SET answer = ?, updated_at = ?
                   WHERE project_id = ? AND question_key = ?""",
                (answer.strip(), utc_now(), project_id, question_key),
            )
            connection.execute(
                "UPDATE projects SET definition_confirmed = 0, status = 'definition', updated_at = ? WHERE id = ?",
                (utc_now(), project_id),
            )

    def save_profile(self, project_id: str, profile: dict[str, Any], confirmed: bool) -> None:
        now = utc_now()
        with self.connection() as connection:
            connection.execute(
                """INSERT INTO project_profiles (project_id, profile_json, confirmed_at, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(project_id) DO UPDATE SET
                       profile_json = excluded.profile_json,
                       confirmed_at = excluded.confirmed_at,
                       updated_at = excluded.updated_at""",
                (project_id, json.dumps(profile, ensure_ascii=False), now if confirmed else None, now),
            )
            connection.execute(
                """UPDATE projects SET definition_confirmed = ?, status = ?, updated_at = ? WHERE id = ?""",
                (int(confirmed), "ready_to_generate" if confirmed else "definition", now, project_id),
            )

    def get_profile(self, project_id: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM project_profiles WHERE project_id = ?", (project_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        result["profile"] = json.loads(result.pop("profile_json"))
        return result

    def start_run(self, project_id: str, phase: str, agent_id: str = "", parameters: dict | None = None) -> str:
        run_id = str(uuid.uuid4())
        with self.connection() as connection:
            connection.execute(
                """INSERT INTO runs
                   (id, project_id, phase, status, agent_id, parameters_json, started_at)
                   VALUES (?, ?, ?, 'running', ?, ?, ?)""",
                (run_id, project_id, phase, agent_id, json.dumps(parameters or {}, ensure_ascii=False), utc_now()),
            )
        return run_id

    def finish_run(
        self,
        run_id: str,
        status: str,
        error_message: str | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> None:
        with self.connection() as connection:
            if metrics:
                row = connection.execute("SELECT parameters_json FROM runs WHERE id = ?", (run_id,)).fetchone()
                if row:
                    try:
                        params = json.loads(row[0] or "{}")
                    except Exception:
                        params = {}
                    params["metrics"] = metrics
                    connection.execute(
                        "UPDATE runs SET status = ?, error_message = ?, finished_at = ?, parameters_json = ? WHERE id = ?",
                        (status, error_message, utc_now(), json.dumps(params, ensure_ascii=False), run_id),
                    )
                    return
            connection.execute(
                "UPDATE runs SET status = ?, error_message = ?, finished_at = ? WHERE id = ?",
                (status, error_message, utc_now(), run_id),
            )

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            raise KeyError(f"Ejecución no encontrada: {run_id}")
        result = dict(row)
        result["parameters"] = json.loads(result.pop("parameters_json"))
        return result

    def latest_run(self, project_id: str, agent_id: str = "orchestrator.main") -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute(
                """SELECT * FROM runs WHERE project_id = ? AND agent_id = ?
                   ORDER BY started_at DESC LIMIT 1""",
                (project_id, agent_id),
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["parameters"] = json.loads(result.pop("parameters_json"))
        return result

    def get_reranking_preference(self) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT value_json FROM app_settings WHERE key = 'reranking'"
            ).fetchone()
        return json.loads(row[0]) if row else None

    def save_reranking_preference(self, enabled: bool, provider: str) -> dict[str, Any]:
        if provider not in {"local", "jev"}:
            raise ValueError("El proveedor de reranking debe ser local o jev.")
        value = {"enabled": bool(enabled), "provider": provider}
        with self.connection() as connection:
            connection.execute(
                "INSERT INTO app_settings (key, value_json) VALUES ('reranking', ?) "
                "ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json",
                (json.dumps(value),),
            )
        return value

    def project_token_usage(self, project_id: str) -> dict[str, Any]:
        """Suma ejecuciones principales sin contar dos veces los agentes hijos."""
        self.get_project(project_id)
        totals = {"sources": 0, "definition": 0, "generation": 0, "revision": 0,
                  "semantic_validation": 0, "jev": 0}
        unreported = 0
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT id, phase, agent_id, parameters_json FROM runs WHERE project_id = ?",
                (project_id,),
            ).fetchall()
        runs = [(row, json.loads(row["parameters_json"] or "{}")) for row in rows]
        children: dict[str, list[dict[str, Any]]] = {}
        for row, parameters in runs:
            parent_id = parameters.get("parent_run_id")
            if parent_id and row["agent_id"].startswith("agent."):
                children.setdefault(parent_id, []).append(parameters.get("metrics") or {})
        for row, parameters in runs:
            if row["agent_id"] in {"revision.main", "semantic.validator"}:
                metrics = parameters.get("metrics") or {}
                phase = "revision" if row["agent_id"] == "revision.main" else "semantic_validation"
                tokens = metrics.get("total_tokens")
                if isinstance(tokens, (int, float)):
                    totals[phase] += max(0, int(tokens))
                else:
                    unreported += 1
                if phase == "revision":
                    jev_tokens = (metrics.get("jev") or {}).get("total_tokens")
                    if isinstance(jev_tokens, (int, float)):
                        totals["jev"] += max(0, int(jev_tokens))
                continue
            if row["agent_id"] not in {"definition.main", "orchestrator.main"}:
                continue
            metrics = parameters.get("metrics") or {}
            if row["agent_id"] == "definition.main":
                phase = "definition"
                tokens = metrics.get("total_tokens")
                if tokens is None:
                    tokens = (metrics.get("llm") or {}).get("total_tokens")
            else:
                phase = "generation"
                tokens = metrics.get("total_tokens")
                jev_tokens = metrics.get("jev_tokens", metrics.get("jev_input_tokens"))
                if tokens is None and row["id"] in children:
                    known = []
                    for child in children[row["id"]]:
                        child_tokens = child.get("total_tokens")
                        if isinstance(child_tokens, (int, float)):
                            known.append(child_tokens)
                        else:
                            unreported += 1
                    if known:
                        tokens = sum(known)
                    jev_tokens = sum(
                        (child.get("jev") or {}).get("total_tokens", 0) or 0
                        for child in children[row["id"]]
                    )
                if isinstance(jev_tokens, (int, float)):
                    totals["jev"] += max(0, int(jev_tokens))
            if isinstance(tokens, (int, float)):
                totals[phase] += max(0, int(tokens))
            else:
                unreported += 1
        if not any(row["agent_id"] == "definition.main" for row, _ in runs):
            with self.connection() as connection:
                legacy_definition = connection.execute(
                    "SELECT 1 FROM project_profiles WHERE project_id = ? LIMIT 1",
                    (project_id,),
                ).fetchone()
            if legacy_definition:
                unreported += 1
        return {
            "total_tokens": sum(totals.values()),
            "by_phase": totals,
            "unreported_runs": unreported,
            "scope": "Todas las ejecuciones registradas del proyecto",
        }

    def update_run_progress(self, run_id: str, progress: int, message: str, step: str) -> None:
        run = self.get_run(run_id)
        parameters = run["parameters"]
        parameters.update({"progress": max(0, min(100, progress)), "message": message, "step": step})
        with self.connection() as connection:
            connection.execute(
                "UPDATE runs SET parameters_json = ? WHERE id = ?",
                (json.dumps(parameters, ensure_ascii=False), run_id),
            )

    def save_artifacts(self, project_id: str, artifacts: list[Artifact], change_origin: str = "generation") -> None:
        for artifact in artifacts:
            existing = self.get_artifact_by_key(project_id, artifact.artifact_id)
            if existing:
                self.update_artifact(existing["id"], artifact, change_origin)
            else:
                self._insert_artifact(project_id, artifact, change_origin)
        self.update_project_status(project_id, "review")

    def _insert_artifact(self, project_id: str, artifact: Artifact, origin: str) -> None:
        artifact_id = str(uuid.uuid4())
        now = utc_now()
        snapshot = artifact.to_dict() | {"version": 1}
        with self.connection() as connection:
            connection.execute(
                """INSERT INTO artifacts
                   (id, project_id, artifact_key, artifact_type, title, description, priority,
                    source_fragments_json, status, acceptance_criteria_json, related_artifacts_json,
                    version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                (
                    artifact_id,
                    project_id,
                    artifact.artifact_id,
                    artifact.artifact_type,
                    artifact.title,
                    artifact.description,
                    artifact.priority,
                    json.dumps(artifact.source_fragments, ensure_ascii=False),
                    artifact.status,
                    json.dumps(artifact.acceptance_criteria or [], ensure_ascii=False),
                    json.dumps(artifact.related_artifacts or [], ensure_ascii=False),
                    now,
                    now,
                ),
            )
            connection.execute(
                """INSERT INTO artifact_versions
                   (id, artifact_id, version, snapshot_json, change_origin, created_at)
                   VALUES (?, ?, 1, ?, ?, ?)""",
                (str(uuid.uuid4()), artifact_id, json.dumps(snapshot, ensure_ascii=False), origin, now),
            )

    def update_artifact(
        self,
        artifact_id: str,
        artifact: Artifact,
        origin: str,
        instruction: str = "",
    ) -> dict[str, Any]:
        current = self.get_artifact(artifact_id)
        version = int(current["version"]) + 1
        now = utc_now()
        previous_key = current["artifact_key"]
        if artifact.artifact_type != current["artifact_type"]:
            artifact.artifact_id = self.next_artifact_key(
                current["project_id"], artifact.artifact_type
            )
        snapshot = artifact.to_dict() | {"version": version}
        with self.connection() as connection:
            connection.execute(
                """UPDATE artifacts SET artifact_key = ?, artifact_type = ?, title = ?, description = ?, priority = ?, source_fragments_json = ?,
                   status = ?, acceptance_criteria_json = ?, related_artifacts_json = ?,
                   validation_json = '{}', version = ?, updated_at = ? WHERE id = ?""",
                (
                    artifact.artifact_id,
                    artifact.artifact_type,
                    artifact.title,
                    artifact.description,
                    artifact.priority,
                    json.dumps(artifact.source_fragments, ensure_ascii=False),
                    artifact.status,
                    json.dumps(artifact.acceptance_criteria or [], ensure_ascii=False),
                    json.dumps(artifact.related_artifacts or [], ensure_ascii=False),
                    version,
                    now,
                    artifact_id,
                ),
            )
            connection.execute(
                """INSERT INTO artifact_versions
                   (id, artifact_id, version, snapshot_json, change_origin, change_instruction, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (str(uuid.uuid4()), artifact_id, version, json.dumps(snapshot, ensure_ascii=False), origin, instruction, now),
            )
            if artifact.artifact_id != previous_key:
                self._replace_artifact_relation_key(
                    connection,
                    current["project_id"],
                    artifact_id,
                    previous_key,
                    artifact.artifact_id,
                    now,
                )
            connection.execute(
                """UPDATE revision_proposals SET status = 'superseded', decided_at = ?
                   WHERE artifact_id = ? AND status = 'pending'""",
                (now, artifact_id),
            )
        return self.get_artifact(artifact_id)

    def approve_all_artifacts(self, project_id: str) -> int:
        """Aprueba atómicamente todos los artefactos pendientes y conserva una versión por cambio."""
        now = utc_now()
        approved_count = 0
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM artifacts WHERE project_id = ? AND status != 'aceptado'",
                (project_id,),
            ).fetchall()
            for row in rows:
                version = int(row["version"]) + 1
                snapshot = {
                    "artifact_id": row["artifact_key"],
                    "artifact_type": row["artifact_type"],
                    "title": row["title"],
                    "description": row["description"],
                    "priority": row["priority"],
                    "source_fragments": json.loads(row["source_fragments_json"] or "[]"),
                    "status": "aceptado",
                    "acceptance_criteria": json.loads(row["acceptance_criteria_json"] or "[]"),
                    "related_artifacts": json.loads(row["related_artifacts_json"] or "[]"),
                    "version": version,
                }
                connection.execute(
                    """UPDATE artifacts SET status = 'aceptado', version = ?, updated_at = ?
                       WHERE id = ?""",
                    (version, now, row["id"]),
                )
                connection.execute(
                    """INSERT INTO artifact_versions
                       (id, artifact_id, version, snapshot_json, change_origin, change_instruction, created_at)
                       VALUES (?, ?, ?, ?, 'bulk_approval', ?, ?)""",
                    (
                        str(uuid.uuid4()),
                        row["id"],
                        version,
                        json.dumps(snapshot, ensure_ascii=False),
                        "Aprobación masiva confirmada por el analista.",
                        now,
                    ),
                )
                connection.execute(
                    """UPDATE revision_proposals SET status = 'superseded', decided_at = ?
                       WHERE artifact_id = ? AND status = 'pending'""",
                    (now, row["id"]),
                )
                approved_count += 1
        return approved_count

    def next_artifact_key(self, project_id: str, artifact_type: str) -> str:
        if artifact_type not in {"RF", "RNF", "HU"}:
            raise ValueError("Tipo de artefacto no permitido.")
        numeric_start = len(artifact_type) + 2
        with self.connection() as connection:
            current = connection.execute(
                """SELECT COALESCE(MAX(CAST(SUBSTR(artifact_key, ?) AS INTEGER)), 0)
                   FROM artifacts WHERE project_id = ? AND artifact_key LIKE ?""",
                (numeric_start, project_id, f"{artifact_type}-%"),
            ).fetchone()[0]
        return f"{artifact_type}-{int(current) + 1:03d}"

    @staticmethod
    def _replace_artifact_relation_key(
        connection: sqlite3.Connection,
        project_id: str,
        changed_artifact_id: str,
        previous_key: str,
        new_key: str,
        now: str,
    ) -> None:
        rows = connection.execute(
            "SELECT * FROM artifacts WHERE project_id = ? AND id != ?",
            (project_id, changed_artifact_id),
        ).fetchall()
        for row in rows:
            relations = json.loads(row["related_artifacts_json"] or "[]")
            if previous_key not in relations:
                continue
            updated_relations = list(
                dict.fromkeys(new_key if item == previous_key else item for item in relations)
            )
            next_version = int(row["version"]) + 1
            snapshot = {
                "artifact_id": row["artifact_key"],
                "artifact_type": row["artifact_type"],
                "title": row["title"],
                "description": row["description"],
                "priority": row["priority"],
                "source_fragments": json.loads(row["source_fragments_json"] or "[]"),
                "status": row["status"],
                "acceptance_criteria": json.loads(row["acceptance_criteria_json"] or "[]"),
                "related_artifacts": updated_relations,
                "version": next_version,
            }
            connection.execute(
                """UPDATE artifacts SET related_artifacts_json = ?, validation_json = '{}',
                   version = ?, updated_at = ? WHERE id = ?""",
                (json.dumps(updated_relations, ensure_ascii=False), next_version, now, row["id"]),
            )
            connection.execute(
                """INSERT INTO artifact_versions
                   (id, artifact_id, version, snapshot_json, change_origin, change_instruction, created_at)
                   VALUES (?, ?, ?, ?, 'reference_rekey', ?, ?)""",
                (
                    str(uuid.uuid4()),
                    row["id"],
                    next_version,
                    json.dumps(snapshot, ensure_ascii=False),
                    f"Referencia actualizada de {previous_key} a {new_key} por reclasificación.",
                    now,
                ),
            )

    def get_artifact_by_key(self, project_id: str, artifact_key: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM artifacts WHERE project_id = ? AND artifact_key = ?", (project_id, artifact_key)
            ).fetchone()
        return self._artifact_row(row) if row else None

    def get_artifact(self, artifact_id: str) -> dict[str, Any]:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,)).fetchone()
        if not row:
            raise KeyError(f"Artefacto no encontrado: {artifact_id}")
        return self._artifact_row(row)

    def list_artifacts(self, project_id: str, artifact_type: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM artifacts WHERE project_id = ?"
        parameters: list[Any] = [project_id]
        if artifact_type:
            query += " AND artifact_type = ?"
            parameters.append(artifact_type)
        query += " ORDER BY artifact_type, artifact_key"
        with self.connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._artifact_row(row) for row in rows]

    def list_versions(self, artifact_id: str) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM artifact_versions WHERE artifact_id = ? ORDER BY version DESC", (artifact_id,)
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["snapshot"] = json.loads(item.pop("snapshot_json"))
            result.append(item)
        return result

    def save_validation_report(self, project_id: str, report: dict[str, Any]) -> None:
        with self.connection() as connection:
            connection.execute(
                "INSERT INTO validation_reports (id, project_id, report_json, created_at) VALUES (?, ?, ?, ?)",
                (str(uuid.uuid4()), project_id, json.dumps(report, ensure_ascii=False), utc_now()),
            )
            validations = report.get("artifact_validations", {})
            for artifact_key, validation in validations.items():
                connection.execute(
                    "UPDATE artifacts SET validation_json = ? WHERE project_id = ? AND artifact_key = ?",
                    (json.dumps(validation, ensure_ascii=False), project_id, artifact_key),
                )

    def latest_validation_report(self, project_id: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute(
                """SELECT report_json, created_at FROM validation_reports
                   WHERE project_id = ? ORDER BY created_at DESC LIMIT 1""",
                (project_id,),
            ).fetchone()
        if not row:
            return None
        return {"report": json.loads(row["report_json"]), "created_at": row["created_at"]}

    def save_semantic_validation_report(
        self,
        project_id: str,
        input_snapshot_hash: str,
        report: dict[str, Any],
        run_id: str | None = None,
    ) -> str:
        report_id = str(uuid.uuid4())
        with self.connection() as connection:
            connection.execute(
                """INSERT INTO semantic_validation_reports
                   (id, project_id, run_id, input_snapshot_hash, report_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    report_id,
                    project_id,
                    run_id,
                    input_snapshot_hash,
                    json.dumps(report, ensure_ascii=False),
                    utc_now(),
                ),
            )
        return report_id

    def latest_semantic_validation_report(self, project_id: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute(
                """SELECT id, run_id, input_snapshot_hash, report_json, created_at
                   FROM semantic_validation_reports
                   WHERE project_id = ? ORDER BY created_at DESC LIMIT 1""",
                (project_id,),
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["report"] = json.loads(item.pop("report_json"))
        return item

    def create_revision_proposal(
        self, project_id: str, artifact_id: str, proposal: Artifact, instruction: str
    ) -> dict[str, Any]:
        proposal_id = str(uuid.uuid4())
        now = utc_now()
        with self.connection() as connection:
            connection.execute(
                """UPDATE revision_proposals SET status = 'superseded', decided_at = ?
                   WHERE artifact_id = ? AND status = 'pending'""",
                (now, artifact_id),
            )
            connection.execute(
                """INSERT INTO revision_proposals
                   (id, project_id, artifact_id, proposal_json, instruction, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (proposal_id, project_id, artifact_id, json.dumps(proposal.to_dict(), ensure_ascii=False), instruction, now),
            )
        return self.get_revision_proposal(proposal_id)

    def get_revision_proposal(self, proposal_id: str) -> dict[str, Any]:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM revision_proposals WHERE id = ?", (proposal_id,)).fetchone()
        if not row:
            raise KeyError(f"Propuesta de revisión no encontrada: {proposal_id}")
        item = dict(row)
        item["proposal"] = json.loads(item.pop("proposal_json"))
        return item

    def decide_revision_proposal(self, proposal_id: str, status: str) -> dict[str, Any]:
        if status not in {"accepted", "rejected"}:
            raise ValueError("El estado de decisión debe ser accepted o rejected.")
        with self.connection() as connection:
            connection.execute(
                """UPDATE revision_proposals SET status = ?, decided_at = ?
                   WHERE id = ? AND status = 'pending'""",
                (status, utc_now(), proposal_id),
            )
        return self.get_revision_proposal(proposal_id)

    @staticmethod
    def _artifact_row(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["source_fragments"] = json.loads(item.pop("source_fragments_json"))
        item["acceptance_criteria"] = json.loads(item.pop("acceptance_criteria_json"))
        item["related_artifacts"] = json.loads(item.pop("related_artifacts_json", "[]"))
        item["validation"] = json.loads(item.pop("validation_json"))
        return item
