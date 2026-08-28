import json
import os
import secrets
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


# --------------------------------------------------
# CONFIG
# --------------------------------------------------

BASE_DIR = Path(os.getenv("RENDER_MOUNT_PATH", "/tmp"))

DATABASE_PATH = Path(
    os.getenv(
        "EGG_DATABASE",
        str(BASE_DIR / "eggs.db")
    )
)

COLLECTOR_KEY = os.getenv("COLLECTOR_KEY", "change-me")


# Make sure the database directory exists.
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------
# MODELS
# --------------------------------------------------

class EggRecord(BaseModel):
    uid: str | None = None
    egg_type: str = Field(min_length=1, max_length=100)
    area: str | None = Field(default=None, max_length=100)
    spawned_at: float | None = None


class EggSnapshot(BaseModel):
    server_time: float | None = None
    cycle_seconds: int = Field(default=0, ge=0, le=86400)
    next_reset_at: float | None = None
    eggs: list[EggRecord] = Field(
        default_factory=list,
        max_length=500
    )


# --------------------------------------------------
# DATABASE
# --------------------------------------------------

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connection() -> sqlite3.Connection:
    db = sqlite3.connect(
        str(DATABASE_PATH),
        timeout=30
    )

    db.row_factory = sqlite3.Row

    return db


def init_db() -> None:
    with connection() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                received_at TEXT NOT NULL,
                server_time REAL,
                cycle_seconds INTEGER NOT NULL,
                next_reset_at REAL,
                eggs_json TEXT NOT NULL
            )
            """
        )

        db.commit()


# --------------------------------------------------
# AUTH
# --------------------------------------------------

def require_collector_key(
    x_collector_key: str | None = Header(default=None)
) -> None:

    if not x_collector_key:
        raise HTTPException(
            status_code=401,
            detail="Missing collector key"
        )

    if not secrets.compare_digest(
        x_collector_key,
        COLLECTOR_KEY
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid collector key"
        )


# --------------------------------------------------
# DATA
# --------------------------------------------------

def latest_snapshot() -> dict[str, Any] | None:

    with connection() as db:
        row = db.execute(
            """
            SELECT *
            FROM snapshots
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    if row is None:
        return None

    result = dict(row)

    result["eggs"] = json.loads(
        result.pop("eggs_json")
    )

    return result


def predictions(
    limit: int = 100
) -> list[dict[str, Any]]:

    with connection() as db:
        rows = db.execute(
            """
            SELECT eggs_json
            FROM snapshots
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()

    counts: dict[str, int] = {}

    total = 0

    for row in rows:

        seen_in_cycle: set[str] = set()

        try:
            eggs = json.loads(
                row["eggs_json"]
            )
        except (json.JSONDecodeError, TypeError):
            continue

        for egg in eggs:

            egg_type = egg.get("egg_type")

            if not egg_type:
                continue

            if egg_type not in seen_in_cycle:

                counts[egg_type] = (
                    counts.get(egg_type, 0) + 1
                )

                seen_in_cycle.add(egg_type)

                total += 1

    if total == 0:
        return []

    return [
        {
            "egg_type": egg_type,
            "observations": count,
            "probability": round(
                count / total,
                4
            )
        }
        for egg_type, count in sorted(
            counts.items(),
            key=lambda item: (
                -item[1],
                item[0]
            )
        )
    ]


# --------------------------------------------------
# FASTAPI
# --------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):

    init_db()

    print(
        f"Database initialized at {DATABASE_PATH}"
    )

    yield


app = FastAPI(
    title="Egg Predictor API",
    version="1.0.0",
    lifespan=lifespan
)


# --------------------------------------------------
# ROUTES
# --------------------------------------------------

@app.get("/")
def root() -> dict[str, str]:

    return {
        "name": "Egg Predictor API",
        "status": "online"
    }


@app.get("/health")
def health() -> dict[str, str]:

    return {
        "status": "ok"
    }


@app.post(
    "/ingest",
    dependencies=[
        Depends(require_collector_key)
    ]
)
def ingest(
    snapshot: EggSnapshot
) -> dict[str, Any]:

    received_at = utc_now()

    eggs_json = json.dumps(
        [
            egg.model_dump()
            for egg in snapshot.eggs
        ]
    )

    with connection() as db:

        cursor = db.execute(
            """
            INSERT INTO snapshots (
                received_at,
                server_time,
                cycle_seconds,
                next_reset_at,
                eggs_json
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                received_at,
                snapshot.server_time,
                snapshot.cycle_seconds,
                snapshot.next_reset_at,
                eggs_json
            )
        )

        db.commit()

        snapshot_id = cursor.lastrowid

    return {
        "id": snapshot_id,
        "received_at": received_at,
        "eggs": len(snapshot.eggs)
    }


@app.get("/eggs")
def eggs() -> dict[str, Any]:

    snapshot = latest_snapshot()

    if snapshot is None:

        return {
            "snapshot": None,
            "seconds_until_reset": None
        }

    reset_at = snapshot["next_reset_at"]

    now = (
        snapshot["server_time"]
        or datetime.now(
            timezone.utc
        ).timestamp()
    )

    seconds_until_reset = None

    if reset_at is not None:

        seconds_until_reset = max(
            0,
            round(reset_at - now)
        )

    return {
        "snapshot": snapshot,
        "seconds_until_reset": seconds_until_reset
    }


@app.get("/next")
def next_cycle() -> dict[str, Any]:

    snapshot = latest_snapshot()

    seconds_until_reset = None

    if (
        snapshot
        and snapshot["next_reset_at"] is not None
    ):

        now = (
            snapshot["server_time"]
            or datetime.now(
                timezone.utc
            ).timestamp()
        )

        seconds_until_reset = max(
            0,
            round(
                snapshot["next_reset_at"]
                - now
            )
        )

    return {
        "seconds_until_reset":
            seconds_until_reset,

        "predictions":
            predictions()
    }


@app.get("/history")
def history(
    limit: int = 20
) -> dict[str, Any]:

    limit = min(
        max(limit, 1),
        100
    )

    with connection() as db:

        rows = db.execute(
            """
            SELECT
                id,
                received_at,
                server_time,
                cycle_seconds,
                next_reset_at,
                eggs_json
            FROM snapshots
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()

    cycles = []

    for row in rows:

        cycle = dict(row)

        try:
            cycle["eggs"] = json.loads(
                cycle.pop("eggs_json")
            )
        except (json.JSONDecodeError, TypeError):

            cycle["eggs"] = []

            cycle.pop(
                "eggs_json",
                None
            )

        cycles.append(cycle)

    return {
        "cycles": cycles
    }


# --------------------------------------------------
# LOCAL START
# --------------------------------------------------

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=int(
            os.getenv("PORT", "8000")
        )
    )
