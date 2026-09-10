from __future__ import annotations

import io
from typing import Any


def build_docx(payload: dict[str, Any]) -> bytes:
    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Pt
    except ImportError as error:
        raise RuntimeError("La dependencia python-docx no está instalada.") from error

    document = Document()
    styles = document.styles
    styles["Normal"].font.name = "Arial"
    styles["Normal"].font.size = Pt(10)
    title = document.add_heading(payload["project"]["name"], level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    document.add_paragraph(f"Dominio: {payload['project'].get('domain') or 'No especificado'}")
    if payload["project"].get("description"):
        document.add_paragraph(payload["project"]["description"])

    profile = payload.get("profile") or {}
    if profile:
        document.add_heading("Definición confirmada", level=1)
        labels = {
            "project_goal": "Objetivo",
            "problem": "Problema",
            "actors": "Actores",
            "scope": "Alcance",
            "out_of_scope": "Fuera de alcance",
            "business_and_legal_constraints": "Reglas y restricciones",
            "quality_expectations": "Expectativas de calidad",
            "known_conflicts": "Conflictos conocidos",
        }
        for key, label in labels.items():
            if profile.get(key):
                paragraph = document.add_paragraph()
                paragraph.add_run(f"{label}: ").bold = True
                paragraph.add_run(str(profile[key]))

    for artifact_type, heading in (("RF", "Requisitos funcionales"), ("RNF", "Requisitos no funcionales"), ("HU", "Historias de usuario")):
        artifacts = [item for item in payload.get("artifacts", []) if item["artifact_type"] == artifact_type]
        document.add_heading(heading, level=1)
        if not artifacts:
            document.add_paragraph("No se generaron artefactos de este tipo.")
            continue
        for item in artifacts:
            document.add_heading(f"{item['artifact_key']}. {item['title']}", level=2)
            document.add_paragraph(item["description"])
            metadata = document.add_paragraph()
            metadata.add_run("Prioridad: ").bold = True
            metadata.add_run(f"{item['priority']}   ")
            metadata.add_run("Estado: ").bold = True
            metadata.add_run(f"{item['status']}   ")
            metadata.add_run("Versión: ").bold = True
            metadata.add_run(str(item["version"]))
            trace = document.add_paragraph()
            trace.add_run("Fuentes: ").bold = True
            trace.add_run(", ".join(item["source_fragments"]) or "Sin evidencia asociada")
            if item.get("acceptance_criteria"):
                document.add_paragraph("Criterios de aceptación:")
                for criterion in item["acceptance_criteria"]:
                    document.add_paragraph(str(criterion), style="List Bullet")

    document.add_heading("Resumen de validación automática", level=1)
    validation = payload.get("validation") or {}
    if validation:
        document.add_paragraph(f"Artefactos analizados: {validation.get('artifact_count', 0)}")
        document.add_paragraph(f"Estado de trazabilidad: {validation.get('traceability_status', 'no disponible')}")
        document.add_paragraph(f"Estado de calidad básica: {validation.get('quality_status', 'no disponible')}")
    else:
        document.add_paragraph("No existe un reporte de validación almacenado.")

    output = io.BytesIO()
    document.save(output)
    return output.getvalue()

