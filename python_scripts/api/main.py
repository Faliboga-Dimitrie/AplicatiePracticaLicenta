from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .routers import health, auth, users, subjects, cases, processing, artifacts


def create_app() -> FastAPI:
    app = FastAPI(
        title="Brain MRI Processing API",
        version="0.1.0",
    )

    app.include_router(health.router)
    app.include_router(auth.router, prefix="/auth", tags=["auth"])

    # Temporary admin/test CRUD routers.
    app.include_router(users.router, prefix="/users", tags=["users"])
    app.include_router(subjects.router, prefix="/subjects", tags=["subjects"])
    app.include_router(cases.router, prefix="/cases", tags=["cases"])

    app.include_router(processing.router, prefix="/processing", tags=["processing"])
    # app.include_router(artifacts.router, prefix="/artifacts", tags=["artifacts"])

    app.mount("/static", StaticFiles(directory="processed_mri"), name="static")

    return app


app = create_app()