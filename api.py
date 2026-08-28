import json
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

# Use Render's persistent disk if available, otherwise use temp directory
BASE_DIR = Path(os.getenv("RENDER_MOUNT_PATH", "/tmp"))
DATABASE_PATH = Path(os.getenv("EGG_DATABASE", BASE_DIR / "eggs.db"))
COLLECTOR_KEY = os.getenv("COLLECTOR_KEY", "change-me")

app = FastAPI(title="Egg Predictor API", version="1.0.0")


class EggRecord(BaseModel):
    uid: str | None = None
    egg_type: str = Field(min_length=1, max_length=100)
    area: str | None = Field(default=None, max_length=100)
    spawned_at: float | None = None


class EggSnapshot(BaseModel):
    server_time: float | None = None
    cycle_seconds: int = Field(default=0, ge=0, le=86400)
    next_reset_at: float | None = None
    eggs: list[EggRecord] = Field(default_factory=list, max_length=500)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connection() -> sqlite3.Connection:
    db = sqlite3.connect(DATABASE_PATH)
    db.row_factory = sqlite3.Row
    return db


def init_db() -> None:
    with connection() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                received_at TEXT NOT NULL,
                server_time REAL,
                cycle_seconds INTEGER NOT NULL,
                next_reset_at REAL,
                eggs_json TEXT NOT NULL
            )
        """)
        db.commit()


def require_collector_key(x_collector_key: str | None = Header(default=None)) -> None:
    if not x_collector_key or not secrets.compare_digest(x_collector_key, COLLECTOR_KEY):
        raise HTTPException(status_code=401, detail="Invalid collector key")


def latest_snapshot() -> dict[str, Any] | None:
    with connection() as db:
        row = db.execute("SELECT * FROM snapshots ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        return None
    result = dict(row)
    result["eggs"] = json.loads(result.pop("eggs_json"))
    return result


def predictions(limit: int = 100) -> list[dict[str, Any]]:
    with connection() as db:
        rows = db.execute(
            "SELECT eggs_json FROM snapshots ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    counts: dict[str, int] = {}
    total = 0
    for row in rows:
        seen_in_cycle: set[str] = set()
        for egg in json.loads(row["eggs_json"]):
            egg_type = egg["egg_type"]
            if egg_type not in seen_in_cycle:
                counts[egg_type] = counts.get(egg_type, 0) + 1
                seen_in_cycle.add(egg_type)
                total += 1
    if not total:
        return []
    return [
        {"egg_type": egg_type, "observations": count, "probability": round(count / total, 4)}
        for egg_type, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


@app.on_event("startup")
def startup() -> None:
    init_db()
    print(f"Database initialized at {DATABASE_PATH}")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ingest", dependencies=[Depends(require_collector_key)])
def ingest(snapshot: EggSnapshot) -> dict[str, Any]:
    received_at = utc_now()
    with connection() as db:
        cursor = db.execute(
            "INSERT INTO snapshots (received_at, server_time, cycle_seconds, next_reset_at, eggs_json) VALUES (?, ?, ?, ?, ?)",
            (received_at, snapshot.server_time, snapshot.cycle_seconds, snapshot.next_reset_at,
             json.dumps([egg.model_dump() for egg in snapshot.eggs])),
        )
        db.commit()
    return {"id": cursor.lastrowid, "received_at": received_at, "eggs": len(snapshot.eggs)}


@app.get("/eggs")
def eggs() -> dict[str, Any]:
    snapshot = latest_snapshot()
    if snapshot is None:
        return {"snapshot": None, "seconds_until_reset": None}
    reset_at = snapshot["next_reset_at"]
    now = snapshot["server_time"] or datetime.now(timezone.utc).timestamp()
    seconds_until_reset = max(0, round(reset_at - now)) if reset_at is not None else None
    return {"snapshot": snapshot, "seconds_until_reset": seconds_until_reset}


@app.get("/next")
def next_cycle() -> dict[str, Any]:
    snapshot = latest_snapshot()
    return {
        "seconds_until_reset": None if not snapshot or snapshot["next_reset_at"] is None
        else max(0, round(snapshot["next_reset_at"] - (snapshot["server_time"] or datetime.now(timezone.utc).timestamp()))),
        "predictions": predictions(),
    }


@app.get("/history")
def history(limit: int = 20) -> dict[str, Any]:
    limit = min(max(limit, 1), 100)
    with connection() as db:
        rows = db.execute(
            "SELECT id, received_at, server_time, cycle_seconds, next_reset_at, eggs_json FROM snapshots ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return {"cycles": [{**dict(row), "eggs": json.loads(row["eggs_json"])} for row in rows]}
