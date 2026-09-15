"""
Structured API errors (spec Section 10).

Every error response has one shape, with the same request_id in the
X-Request-ID header:

    {"error": {"code": "...", "message": "...", "details": ..., "request_id": "..."}}

Messages are fixed texts chosen by the API. Exception text from connectors,
the database or the framework is never echoed, and validation details carry
the failing location, message and type only, never the submitted value.

Unhandled exceptions become a generic INTERNAL_ERROR response. Starlette
re-raises them after the response is sent, so the server still logs the
failure; this module logs only the exception class name.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from enum import StrEnum
from http import HTTPStatus

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import Response

from app.api.request_id import REQUEST_ID_HEADER, request_id_of

logger = logging.getLogger(__name__)

ErrorDetails = list[dict[str, object]] | dict[str, object] | None


class ErrorCode(StrEnum):
    """Stable API error codes."""

    INVALID_REQUEST = "INVALID_REQUEST"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    HTTP_ERROR = "HTTP_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SOURCE_NOT_FOUND = "SOURCE_NOT_FOUND"
    SOURCE_MISCONFIGURED = "SOURCE_MISCONFIGURED"
    RUN_NOT_FOUND = "RUN_NOT_FOUND"
    UNSUPPORTED_OPTION = "UNSUPPORTED_OPTION"
    INVALID_INGESTION_REQUEST = "INVALID_INGESTION_REQUEST"
    ENTITY_NOT_FOUND = "ENTITY_NOT_FOUND"


class ErrorBody(BaseModel):
    code: str
    message: str
    details: ErrorDetails = None
    request_id: str


class ErrorResponse(BaseModel):
    """The body of every API error response."""

    error: ErrorBody


class ApiError(Exception):
    """An expected failure that routes raise to produce a structured error."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: ErrorDetails = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: ErrorDetails = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    request_id = request_id_of(request)
    body = ErrorResponse(error=ErrorBody(code=code, message=message, details=details,
                                         request_id=request_id))
    return JSONResponse(body.model_dump(mode="json"), status_code=status_code,
                        headers={**(headers or {}), REQUEST_ID_HEADER: request_id})


def _validation_details(exc: RequestValidationError) -> list[dict[str, object]]:
    return [
        {"loc": list(error["loc"]), "message": error["msg"], "type": error["type"]}
        for error in exc.errors()
    ]


async def _handle_api_error(request: Request, exc: ApiError) -> Response:
    return error_response(request, exc.status_code, exc.code, exc.message, exc.details)


async def _handle_validation_error(request: Request, exc: RequestValidationError) -> Response:
    return error_response(request, HTTPStatus.UNPROCESSABLE_ENTITY, ErrorCode.INVALID_REQUEST,
                          "request validation failed", _validation_details(exc))


_HTTP_ERROR_CODES: dict[int, ErrorCode] = {
    HTTPStatus.NOT_FOUND: ErrorCode.NOT_FOUND,
    HTTPStatus.METHOD_NOT_ALLOWED: ErrorCode.METHOD_NOT_ALLOWED,
}


async def _handle_http_error(request: Request, exc: StarletteHTTPException) -> Response:
    code =_HTTP_ERROR_CODES.get(exc.status_code, ErrorCode.HTTP_ERROR)
    return error_response(request, exc.status_code, code, HTTPStatus(exc.status_code).phrase,
                          headers=exc.headers)


async def _handle_unhandled_error(request: Request, exc: Exception) -> Response:
    logger.error("request_failed request_id=%s method=%s path=%s failure=%s",
                 request_id_of(request), request.method, request.url.path, type(exc).__name__)
    return error_response(request, HTTPStatus.INTERNAL_SERVER_ERROR, ErrorCode.INTERNAL_ERROR,
                          "internal server error")


def install_error_handlers(app: FastAPI) -> None:
    app.exception_handler(ApiError)(_handle_api_error)
    app.exception_handler(RequestValidationError)(_handle_validation_error)
    app.exception_handler(StarletteHTTPException)(_handle_http_error)
    app.exception_handler(Exception)(_handle_unhandled_error)
