"""AutoRFQ web app: the JSON API under /api and the built React UI (web/dist) everywhere else.

    uvicorn app.main:app --port 8000
"""
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import settings
from contextlib import asynccontextmanager

from app.routes import admin, health, review, runs, upload
from app.services import inbox


@asynccontextmanager
async def lifespan(_app):
    inbox.start()  # answers RFQ emails while the app runs (when mail is set up)
    yield
    inbox.stop()


app = FastAPI(title="AutoRFQ", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan)
app.include_router(runs.router)
app.include_router(review.router)
app.include_router(health.router)
app.include_router(upload.router)
app.include_router(admin.router)

if (settings.WEB_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=settings.WEB_DIST / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    """The React app for every non-API path (client-side routing)."""
    if path == "api" or path.startswith("api/"):
        return JSONResponse({"detail": "Not found"}, status_code=404)
    candidate = (settings.WEB_DIST / path).resolve()
    if path and candidate.is_file() and settings.WEB_DIST in candidate.parents:
        return FileResponse(candidate)
    index = settings.WEB_DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"detail": "The web UI is not built yet: run `npm ci && npm run build` in web/."},
                        status_code=503)
