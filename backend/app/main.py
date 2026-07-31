from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.ai_assist import router as ai_assist_router
from app.api.auth import router as auth_router
from app.api.bible import router as bible_router
from app.api.blueprint import router as blueprint_router
from app.api.chapters import router as chapters_router
from app.api.charter import router as charter_router
from app.api.generate import router as generate_router
from app.api.immersive import router as immersive_router
from app.api.imports import router as imports_router
from app.api.knowledge import router as knowledge_router
from app.api.market import router as market_router
from app.api.memory import router as memory_router
from app.api.projects import router as projects_router
from app.api.reader import router as reader_router
from app.api.volumes import router as volumes_router
from app.config import get_settings
from app.database import check_database_ready, engine

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    from app.services.blueprint_worker import blueprint_job_runner
    from app.services.generation import generation_coordinator
    from app.services.import_worker import import_analysis_worker
    from app.services.indexing import index_worker
    from app.services.outbox import outbox_dispatcher

    await check_database_ready()
    if settings.generation_worker_enabled:
        await generation_coordinator.start_worker()
    if settings.index_worker_enabled:
        await index_worker.start()
    if settings.import_worker_enabled:
        await import_analysis_worker.start()
    if settings.outbox_worker_enabled:
        await outbox_dispatcher.start()
    if settings.generation_worker_enabled:
        await blueprint_job_runner.start_worker()
    try:
        yield
    finally:
        await generation_coordinator.stop_worker()
        await index_worker.stop()
        await import_analysis_worker.stop()
        await outbox_dispatcher.stop()
        await blueprint_job_runner.stop_worker()
        await engine.dispose()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(projects_router, prefix=settings.api_prefix)
app.include_router(blueprint_router, prefix=settings.api_prefix)
app.include_router(bible_router, prefix=settings.api_prefix)
app.include_router(charter_router, prefix=settings.api_prefix)
app.include_router(chapters_router, prefix=settings.api_prefix)
app.include_router(generate_router, prefix=settings.api_prefix)
app.include_router(memory_router, prefix=settings.api_prefix)
app.include_router(ai_assist_router, prefix=settings.api_prefix)
app.include_router(imports_router, prefix=settings.api_prefix)
app.include_router(knowledge_router, prefix=settings.api_prefix)
app.include_router(market_router, prefix=settings.api_prefix)
app.include_router(immersive_router, prefix=settings.api_prefix)
app.include_router(reader_router, prefix=settings.api_prefix)
app.include_router(volumes_router, prefix=settings.api_prefix)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    await check_database_ready()
    return {"status": "ok", "database": "ready"}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    from app.services.web_search import web_search_configured

    await check_database_ready()
    return {
        "status": "ready",
        "database": "ready",
        "llm_backend": settings.llm_backend,
        "web_search": "ready" if web_search_configured(settings) else "disabled",
    }
