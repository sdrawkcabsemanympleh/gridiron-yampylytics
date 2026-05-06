"""YampGM FastAPI application.

Run with::

    uv run uvicorn gridiron_yampylytics.ffb.api.main:app --reload

The React frontend (``frontend/``) is served separately during development
via Vite's dev server (``npm run dev``).  In production both can be served
from the same host with Vite's build output served as static files.
"""
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from gridiron_yampylytics.ffb.api.routers.sessions import router as sessions_router
from gridiron_yampylytics.ffb.api.session_store import all_draft_ids, get_context


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Cancel all active listener tasks on server shutdown.

    :param app: The FastAPI application instance.
    :yields: Nothing — just handles startup/shutdown lifecycle.
    """
    yield
    for draft_id in all_draft_ids():
        ctx = get_context(draft_id)
        if ctx is not None:
            ctx.shutdown = True
            if ctx.listener_task is not None:
                ctx.listener_task.cancel()
                try:
                    await asyncio.wait_for(ctx.listener_task, timeout=2.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass


app = FastAPI(
    title="YampGM Draft Assistant",
    description="Monte Carlo draft recommendation engine backed by gridiron-yampylytics data.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],  # Vite default ports
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions_router)
