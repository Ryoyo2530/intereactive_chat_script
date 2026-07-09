import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from routers import dev_drafts, dev_prompts, dev_scripts, dev_simulate, player

load_dotenv(Path(__file__).resolve().parent / ".env")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = FastAPI(title="入戏")

app.include_router(player.router)
app.include_router(dev_scripts.router)
app.include_router(dev_drafts.router)
app.include_router(dev_prompts.router)
app.include_router(dev_simulate.router)

static_dir = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=str(static_dir)), name="static")
