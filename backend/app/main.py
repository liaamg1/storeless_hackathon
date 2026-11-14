import logging
import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.transcription_worker import manage_transcription_worker

from app.api.presentations import router as presentations_router
from app.api.uploads import router as uploads_router
from app.api.duplicates import router as duplicates_router
from app.api.files import router
from app.api.search import router as search_router
from app.api.transcription import router as transcription_router

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    from app.services.duplicate_cleanup import recover_staging

    await asyncio.to_thread(recover_staging)
    # The API owns a separate worker process; model inference never runs on its event loop.
    async with manage_transcription_worker():
        try:
            yield
        finally:
            from app.services.legacy_pdf import shutdown

            await asyncio.to_thread(shutdown)


app = FastAPI(title="ReStore", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(search_router)
app.include_router(duplicates_router)
app.include_router(transcription_router)
app.include_router(presentations_router)
app.include_router(uploads_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
