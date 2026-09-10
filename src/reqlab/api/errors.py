from __future__ import annotations

from fastapi import HTTPException


def not_found(error: KeyError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(error).strip("'"))


def bad_request(error: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(error))

