from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ProblemError(Exception):
    """Error de dominio o de API que se responde como application/problem+json."""

    def __init__(self, status: int, code: str, title: str, detail: str | None = None) -> None:
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail
        super().__init__(title)


def problem_response(
    request: Request,
    status: int,
    code: str,
    title: str,
    detail: str | None = None,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"https://nicheradar.local/problems/{code.lower()}",
        "title": title,
        "status": status,
        "detail": detail,
        "code": code,
        "request_id": getattr(request.state, "request_id", None),
    }
    if extra:
        body.update(extra)
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProblemError)
    async def _problem(request: Request, exc: ProblemError) -> JSONResponse:
        return problem_response(request, exc.status, exc.code, exc.title, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        return problem_response(
            request,
            422,
            "VALIDATION_ERROR",
            "Solicitud inválida",
            "Revise los campos indicados.",
            {"errors": errors},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return problem_response(
            request, exc.status_code, f"HTTP_{exc.status_code}", str(exc.detail)
        )
