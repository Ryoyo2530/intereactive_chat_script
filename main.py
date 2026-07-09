import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from game.middleware import RateLimitMiddleware, StaticCacheMiddleware
from game.settings import get_settings
from routers import dev_drafts, dev_prompts, dev_scripts, dev_simulate, player

load_dotenv(Path(__file__).resolve().parent / ".env")
settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(title="入戏")

app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(StaticCacheMiddleware)
app.add_middleware(RateLimitMiddleware, requests_per_minute=settings.rate_limit_per_minute)

app.include_router(player.router)
app.include_router(dev_scripts.router)
app.include_router(dev_drafts.router)
app.include_router(dev_prompts.router)
app.include_router(dev_simulate.router)

static_dir = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=str(static_dir)), name="static")
