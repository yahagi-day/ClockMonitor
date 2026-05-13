import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.storage import Storage
from app.collectors.chrony import ChronyCollector
from app.collectors.gpsd import GpsdCollector
from app.collectors.ptp4l import Ptp4lCollector
from app.collectors.pps import PpsCollector
from app.collectors.systemd import SystemdCollector
from app.routers import pages, api


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage = Storage()
    app.state.storage = storage

    collectors = [
        ChronyCollector(),
        GpsdCollector(),
        Ptp4lCollector(),
        PpsCollector(),
        SystemdCollector(),
    ]
    tasks = [asyncio.create_task(c.run(storage)) for c in collectors]

    yield

    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


def create_app() -> FastAPI:
    app = FastAPI(title="ClockMonitor", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory="static"), name="static")
    app.state.templates = Jinja2Templates(directory="templates")
    app.include_router(pages.router)
    app.include_router(api.router)
    return app
