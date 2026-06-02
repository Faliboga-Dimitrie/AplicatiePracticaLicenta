from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .errors import error_payload, normalize_error_detail
from .routers import artifacts, auth, cases, health, jobs, processing, public, subjects


def create_app() -> FastAPI:
    app = FastAPI(
        title="Brain MRI Processing API",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=normalize_error_detail(exc.detail, status_code=exc.status_code),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content=error_payload(
                "Request validation failed.",
                code="VALIDATION_ERROR",
                details=exc.errors(),
            ),
        )

    app.include_router(health.router)
    app.include_router(auth.router, prefix="/auth", tags=["auth"])
    app.include_router(subjects.router, prefix="/subjects", tags=["subjects"])
    app.include_router(cases.router, prefix="/cases", tags=["cases"])
    app.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
    app.include_router(processing.router, prefix="/processing", tags=["processing"])
    app.include_router(public.router, prefix="/public", tags=["public"])
    app.include_router(artifacts.router, prefix="/cases", tags=["artifacts"])

    return app


app = create_app()
