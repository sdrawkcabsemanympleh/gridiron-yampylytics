"""YampGM FastAPI application.

Run with::

    uv run uvicorn gridiron_yampylytics.ffb.api.main:app --reload

The React frontend (``frontend/``) is served separately during development
via Vite's dev server (``npm run dev``).  In production both can be served
from the same host with Vite's build output served as static files.
"""
import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from fastapi.responses import JSONResponse
from gridiron_yampylytics.ffb.api.routers.sessions import router as sessions_router
from gridiron_yampylytics.ffb.api.session_store import all_draft_ids, get_context
from gridiron_yampylytics.ffb.data.player_loader import load_player_pool

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logging.getLogger("gridiron_yampylytics").setLevel(logging.INFO)


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
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions_router)


@app.get("/api/debug/player-pool")
async def debug_player_pool() -> JSONResponse:
    """Temporary diagnostic: returns player pool stats as seen by the API process."""
    players = load_player_pool(season=2026)
    with_proj = [p for p in players if p.projected_points > 0]
    top5 = players[:5]
    return JSONResponse({
        "cwd": str(Path.cwd()),
        "total_players": len(players),
        "with_projected_points": len(with_proj),
        "top5": [
            {"name": p.name, "position": str(p.position), "adp": p.adp, "projected_points": p.projected_points}
            for p in top5
        ],
    })
