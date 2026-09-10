from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .corpus import CorpusIngestionAgent
from .generation import DeepSeekGenerationAgent, load_local_env
from .models import Artifact
from .retrieval import TfidfRetrievalAgent
from .validation import TraceabilityConsistencyAgent


def parser() -> argparse.ArgumentParser:
    app = argparse.ArgumentParser(description="Prototipo de generación trazable de requisitos desde corpus textuales")
    subcommands = app.add_subparsers(dest="command", required=True)
    for name in ("inspect", "generate"):
        command = subcommands.add_parser(name)
        command.add_argument("--corpus", required=True, help="Directorio del corpus con corpus_manifest.json")
        if name == "generate":
            command.add_argument("--output", required=True, help="Directorio para las salidas")
            command.add_argument("--model", default=None, help="Modelo DeepSeek (por defecto: deepseek-chat)")
    validate = subcommands.add_parser("validate")
    validate.add_argument("--artifacts", required=True)
    validate.add_argument("--corpus", required=True)
    validate.add_argument("--output", required=True)
    return app


def main() -> int:
    args = parser().parse_args()
    project_dir = Path(__file__).resolve().parents[2]
    load_local_env(project_dir)
    manifest = json.loads((Path(args.corpus) / "corpus_manifest.json").read_text(encoding="utf-8"))
    fragments = CorpusIngestionAgent().load(args.corpus)
    retriever = TfidfRetrievalAgent(fragments)
    system_name = manifest.get("system_name") or manifest.get("name") or manifest["corpus_id"]
    domain = manifest.get("domain", "dominio no especificado")
    ambiguity_registry = manifest.get("ambiguity_registry", [])
    if args.command == "inspect":
        results = retriever.retrieve(f"{system_name} {domain} requisitos funcionales no funcionales historias de usuario trazabilidad", top_k=8)
        print(f"Fragmentos indexados: {len(fragments)}")
        for fragment, score in results:
            print(f"{fragment.fragment_id}  puntuación={score:.3f}  {fragment.heading}")
        return 0
    if args.command == "generate":
        generator = DeepSeekGenerationAgent(retriever, model=args.model, system_name=system_name, domain=domain)
        artifacts: list[Artifact] = []
        retrieval_runs: dict[str, list[dict]] = {}
        for artifact_type in ("RF", "RNF", "HU"):
            generated, evidence = generator.generate(artifact_type)
            artifacts.extend(generated)
            retrieval_runs[artifact_type] = [
                {"fragment_id": fragment.fragment_id, "score": round(score, 6)}
                for fragment, score in evidence
            ]
        metadata = {
            "corpus_id": manifest["corpus_id"],
            "corpus_version": manifest["version"],
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "model": generator.model,
            "retrieval_method": "tfidf_cosine",
            "top_k": 16,
            "temperature": 0.1,
        }
        write_outputs(artifacts, fragments, args.output, metadata=metadata, retrieval_runs=retrieval_runs, ambiguity_registry=ambiguity_registry)
        print(f"Generación completada: {len(artifacts)} artefactos en {args.output}")
        return 0
    payload = json.loads(Path(args.artifacts).read_text(encoding="utf-8"))
    artifacts = [Artifact.from_dict(item, item["artifact_type"], index + 1) for index, item in enumerate(payload["artifacts"])]
    write_outputs(artifacts, fragments, args.output, write_artifacts=False, ambiguity_registry=ambiguity_registry)
    print(f"Validación completada: {args.output}")
    return 0


def write_outputs(
    artifacts: list[Artifact],
    fragments,
    output_dir: str,
    write_artifacts: bool = True,
    metadata: dict | None = None,
    retrieval_runs: dict | None = None,
    ambiguity_registry: list[dict] | None = None,
) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    validator = TraceabilityConsistencyAgent()
    if write_artifacts:
        (output / "artefactos.json").write_text(
            json.dumps({"metadata": metadata or {}, "artifacts": [artifact.to_dict() for artifact in artifacts]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    if retrieval_runs is not None:
        (output / "recuperacion.json").write_text(json.dumps(retrieval_runs, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "trazabilidad.md").write_text(validator.traceability_markdown(artifacts), encoding="utf-8")
    (output / "validacion.json").write_text(
        json.dumps(validator.validate(artifacts, fragments, ambiguity_registry), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"Error de ejecución: {error}")
        raise SystemExit(2) from None
