from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .errors import error_payload, normalize_error_detail
from .routers import artifacts, auth, cases, health, jobs, processing, public, subjects


LOCAL_DEV_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "http://localhost:3002",
    "http://127.0.0.1:3002",
    "http://localhost:3003",
    "http://127.0.0.1:3003",
    "http://localhost:3004",
    "http://127.0.0.1:3004",
    "http://localhost:3005",
    "http://127.0.0.1:3005",
]


def create_app() -> FastAPI:
    app = FastAPI(
        title="Brain MRI Processing API",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=LOCAL_DEV_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(auth.router, prefix="/auth", tags=["auth"])
    app.include_router(subjects.router, prefix="/subjects", tags=["subjects"])
    app.include_router(artifacts.router, prefix="/cases", tags=["artifacts"])
    app.include_router(cases.router, prefix="/cases", tags=["cases"])
    app.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
    app.include_router(processing.router, prefix="/processing", tags=["processing"])
    app.include_router(public.router, prefix="/public", tags=["public"])

    return app


app = create_app()
