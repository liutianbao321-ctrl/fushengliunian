from __future__ import annotations

import asyncio
import signal

from app.config import get_settings
from app.database import check_database_ready, engine
from app.services.generation import generation_coordinator
from app.services.import_worker import import_analysis_worker
from app.services.indexing import index_worker
from app.services.outbox import outbox_dispatcher


async def run_workers() -> None:
    settings = get_settings()
    await check_database_ready()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop.set)

    if settings.generation_worker_enabled:
        await generation_coordinator.start_worker()
    if settings.index_worker_enabled:
        await index_worker.start()
    if settings.import_worker_enabled:
        await import_analysis_worker.start()
    if settings.outbox_worker_enabled:
        await outbox_dispatcher.start()
    try:
        await stop.wait()
    finally:
        await generation_coordinator.stop_worker()
        await index_worker.stop()
        await import_analysis_worker.stop()
        await outbox_dispatcher.stop()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_workers())
