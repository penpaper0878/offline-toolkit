"""Application errors and the single JSON error envelope every endpoint returns.

    {"error": {"code": "not_found", "message": "...", "details": [...]}}
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    status = 400
    code = "bad_request"

    def __init__(self, message: str, details: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or []


class Unauthorized(AppError):
    status, code = 401, "unauthorized"


class Forbidden(AppError):
    status, code = 403, "forbidden"


class NotFound(AppError):
    status, code = 404, "not_found"


class Conflict(AppError):
    status, code = 409, "conflict"


class Invalid(AppError):
    status, code = 422, "validation_error"


class Locked(AppError):
    status, code = 423, "locked"


def envelope(code: str, message: str, details: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or []}}


def validation_details(errors: list[Any]) -> list[dict[str, Any]]:
    out = []
    for e in errors:
        loc = [str(p) for p in e.get("loc", ()) if p not in ("body", "query", "path")]
        msg = str(e.get("msg", "")).removeprefix("Value error, ")
        out.append({"field": ".".join(loc), "message": msg})
    return out


def from_pydantic(exc: ValidationError) -> Invalid:
    details = validation_details(exc.errors())
    first = details[0] if details else {"field": "", "message": "Invalid input."}
    label = f"{first['field']}: " if first["field"] else ""
    return Invalid(f"{label}{first['message']}", details)


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status == 401 else None
        return JSONResponse(envelope(exc.code, exc.message, exc.details), status_code=exc.status, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def _request_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = validation_details(list(exc.errors()))
        first = details[0] if details else {"field": "", "message": "Invalid request."}
        label = f"{first['field']}: " if first["field"] else ""
        return JSONResponse(envelope("validation_error", f"{label}{first['message']}", details), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return JSONResponse(envelope(code, str(exc.detail)), status_code=exc.status_code, headers=getattr(exc, "headers", None))
