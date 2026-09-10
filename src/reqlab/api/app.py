from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .dependencies import get_client, get_settings
from .routers import artifacts, definition, exports, generation, projects, sources


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="ReqLab API",
        description="API local para generación trazable de requisitos desde fuentes heterogéneas.",
        version="0.2.0",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )
    application.include_router(projects.router, prefix="/api")
    application.include_router(sources.router, prefix="/api")
    application.include_router(definition.router, prefix="/api")
    application.include_router(generation.router, prefix="/api")
    application.include_router(artifacts.router, prefix="/api")
    application.include_router(exports.router, prefix="/api")

    @application.get("/api/health", tags=["system"])
    def health() -> dict:
        return {
            "status": "ok",
            "llm_configured": get_client().configured,
            "storage": "sqlite+chromadb",
        }

    return application


app = create_app()
