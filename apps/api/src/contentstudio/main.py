from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from .browser_security import browser_write_guard
from .config import get_settings
from .db import Base, engine, session_factory
from .internal_api import router as internal_router
from .public_api import router as public_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.mode == "demo":
        Base.metadata.create_all(engine())
        from .seed import seed_demo

        with session_factory()() as db:
            seed_demo(db)
    yield


app = FastAPI(title="ContentStudio API", version="0.1.0", lifespan=lifespan)
app.middleware("http")(browser_write_guard)
app.include_router(public_router)
app.include_router(internal_router)


@app.get("/healthz")
def healthz():
    try:
        with engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "mode": get_settings().mode}
    except Exception:
        return {"status": "unhealthy", "mode": get_settings().mode}
