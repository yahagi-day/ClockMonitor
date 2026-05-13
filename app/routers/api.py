import asyncio
import json

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from app import config

router = APIRouter(prefix="/api")

HISTORY_SOURCES = {
    "chrony_offset",
    "ptp_offset_from_master",
    "gps_sat_used",
    "gps_sat_visible",
    "pps0_seq",
}


@router.get("/health")
async def health():
    return {"ok": True}


@router.get("/status")
async def status(request: Request):
    return JSONResponse(request.app.state.storage.get_status())


@router.get("/history")
async def history(request: Request, source: str, minutes: int = 10):
    if source not in HISTORY_SOURCES:
        raise HTTPException(status_code=400, detail=f"Unknown source: {source}")
    if not 1 <= minutes <= 60:
        raise HTTPException(status_code=400, detail="minutes must be 1-60")
    return JSONResponse(request.app.state.storage.get_history(source, minutes))


@router.get("/stream")
async def stream(request: Request):
    storage = request.app.state.storage

    async def generator():
        while True:
            if await request.is_disconnected():
                break
            data = json.dumps(storage.get_status())
            yield {"event": "snapshot", "data": data}
            await asyncio.sleep(config.SSE_PUSH_INTERVAL)

    return EventSourceResponse(generator())
