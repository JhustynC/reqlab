from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    cors_origins: tuple[str, ...]
    max_upload_bytes: int

    @classmethod
    def from_environment(cls) -> "Settings":
        data_dir = Path(os.getenv("DATA_DIR", Path.cwd() / "data"))
        origins = tuple(
            value.strip()
            for value in os.getenv("CORS_ORIGINS", "http://localhost:4200,http://localhost:8080").split(",")
            if value.strip()
        )
        return cls(
            data_dir=data_dir,
            cors_origins=origins,
            max_upload_bytes=int(os.getenv("MAX_UPLOAD_BYTES", str(20 * 1024 * 1024))),
        )

