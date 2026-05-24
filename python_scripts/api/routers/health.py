from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def api_info():
    return {
        "name": "Brain MRI Processing API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }


@router.get("/health")
def health_check():
    return {"status": "ok"}
