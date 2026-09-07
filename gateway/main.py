from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_FILE = Path(os.getenv("STREAM_REGISTRY_FILE", PROJECT_ROOT / "config" / "streams.json"))
PLAYER_FILE = PROJECT_ROOT / "gateway" / "static" / "index.html"
MEDIAMTX_API_URL = os.getenv("MEDIAMTX_API_URL", "http://127.0.0.1:9997").rstrip("/")

app = FastAPI(
    title="Local Video API Gateway",
    version="0.1.0",
    description="Discovery, health, and playback URL generation for local MediaMTX streams.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def load_registry() -> list[dict[str, Any]]:
    with REGISTRY_FILE.open(encoding="utf-8") as stream_file:
        entries = json.load(stream_file)
    if not isinstance(entries, list):
        raise RuntimeError("stream registry must contain a JSON array")
    return entries


def get_registry_entry(stream_id: str) -> dict[str, Any]:
    entry = next((item for item in load_registry() if item.get("stream_id") == stream_id), None)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"unknown stream: {stream_id}")
    return entry


def fetch_mediamtx_paths_sync() -> list[dict[str, Any]]:
    request = urllib.request.Request(
        f"{MEDIAMTX_API_URL}/v3/paths/list",
        headers={"Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise RuntimeError(f"MediaMTX API unavailable: {error}") from error
    return payload.get("items", [])


async def fetch_mediamtx_paths() -> list[dict[str, Any]]:
    return await asyncio.to_thread(fetch_mediamtx_paths_sync)


def path_health(entry: dict[str, Any], paths: list[dict[str, Any]]) -> dict[str, Any]:
    path_name = entry["mediamtx_path"]
    path = next((item for item in paths if item.get("name") == path_name), None)
    if path is None:
        return {
            "stream_id": entry["stream_id"],
            "status": "offline",
            "ready": False,
            "readers": 0,
            "tracks": [],
        }

    ready = bool(path.get("ready"))
    readers = path.get("readers") or []
    return {
        "stream_id": entry["stream_id"],
        "status": "online" if ready else "offline",
        "ready": ready,
        "ready_since": path.get("readyTime"),
        "source_type": entry.get("source_type"),
        "readers": len(readers),
        "tracks": path.get("tracks") or [],
        "bytes_received": path.get("bytesReceived", 0),
        "bytes_sent": path.get("bytesSent", 0),
    }


def public_host(request: Request) -> str:
    configured = os.getenv("PUBLIC_HOST")
    if configured:
        return configured
    host = request.url.hostname or "127.0.0.1"
    return f"[{host}]" if ":" in host else host


def playback_payload(entry: dict[str, Any], request: Request, online: bool) -> dict[str, Any]:
    host = public_host(request)
    path = entry["mediamtx_path"]
    return {
        "stream_id": entry["stream_id"],
        "display_name": entry["display_name"],
        "status": "online" if online else "offline",
        "primary_protocol": entry.get("primary_protocol", "webrtc"),
        "fallback_protocol": entry.get("fallback_protocol", "hls"),
        "latency_target_ms": entry.get("latency_target_ms"),
        "protocols": {
            "hls": f"http://{host}:8888/{path}/index.m3u8",
            "hls_player": f"http://{host}:8888/{path}",
            "webrtc": f"http://{host}:8889/{path}",
            "whep": f"http://{host}:8889/{path}/whep",
            "rtsp": f"rtsp://{host}:8554/{path}",
        },
    }


@app.get("/", include_in_schema=False)
async def player() -> FileResponse:
    return FileResponse(PLAYER_FILE)


@app.get("/healthz")
async def gateway_health() -> dict[str, Any]:
    try:
        paths = await fetch_mediamtx_paths()
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {"status": "ok", "mediamtx": "reachable", "path_count": len(paths)}


@app.get("/streams")
@app.get("/api/streams", include_in_schema=False)
async def streams(request: Request) -> list[dict[str, Any]]:
    try:
        paths = await fetch_mediamtx_paths()
    except RuntimeError:
        paths = []
    return [
        playback_payload(entry, request, path_health(entry, paths)["ready"])
        for entry in load_registry()
    ]


@app.get("/streams/{stream_id}")
@app.get("/api/streams/{stream_id}", include_in_schema=False)
async def stream(stream_id: str, request: Request) -> dict[str, Any]:
    entry = get_registry_entry(stream_id)
    try:
        paths = await fetch_mediamtx_paths()
    except RuntimeError:
        paths = []
    result = dict(entry)
    result["health"] = path_health(entry, paths)
    result["playback"] = playback_payload(entry, request, result["health"]["ready"])["protocols"]
    return result


@app.get("/streams/{stream_id}/playback")
@app.get("/api/streams/{stream_id}/playback", include_in_schema=False)
async def playback(stream_id: str, request: Request) -> dict[str, Any]:
    entry = get_registry_entry(stream_id)
    try:
        paths = await fetch_mediamtx_paths()
    except RuntimeError:
        paths = []
    return playback_payload(entry, request, path_health(entry, paths)["ready"])


@app.get("/streams/{stream_id}/health")
@app.get("/api/streams/{stream_id}/health", include_in_schema=False)
async def stream_health(stream_id: str) -> dict[str, Any]:
    entry = get_registry_entry(stream_id)
    try:
        paths = await fetch_mediamtx_paths()
    except RuntimeError as error:
        return {
            "stream_id": stream_id,
            "status": "unknown",
            "ready": False,
            "error": str(error),
        }
    return path_health(entry, paths)
