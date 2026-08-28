import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import aiohttp
import requests
import uvicorn
import discord

from discord import app_commands
from fastapi import FastAPI


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("EggService")


# ============================================================
# ENVIRONMENT VARIABLES
# ============================================================

API_URL = os.getenv(
    "PREDICTOR_API_URL",
    ""
).rstrip("/")

DISCORD_TOKEN = os.getenv(
    "DISCORD_TOKEN",
    ""
)

COLLECTOR_KEY = os.getenv(
    "COLLECTOR_KEY",
    ""
)

PORT = int(
    os.getenv(
        "PORT",
        "10000"
    )
)

COLLECTION_INTERVAL = int(
    os.getenv(
        "COLLECTION_INTERVAL",
        "60"
    )
)


# ============================================================
# CONFIG VALIDATION
# ============================================================

if not API_URL:
    raise SystemExit(
        "ERROR: PREDICTOR_API_URL is not configured."
    )

if not DISCORD_TOKEN:
    raise SystemExit(
        "ERROR: DISCORD_TOKEN is not configured."
    )

if not COLLECTOR_KEY:
    raise SystemExit(
        "ERROR: COLLECTOR_KEY is not configured."
    )


# ============================================================
# SMALL HTTP SERVER
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):

    logger.info("HTTP service starting")

    yield

    logger.info("HTTP service shutting down")


web_app = FastAPI(
    title="Egg Bot Service",
    version="1.0.0",
    lifespan=lifespan,
)


@web_app.get("/")
async def root():

    return {
        "status": "online",
        "service": "Egg Bot + Collector",
    }


@web_app.get("/health")
async def health():

    return {
        "status": "ok",
        "discord": client.is_ready(),
    }


# ============================================================
# DISCORD BOT
# ============================================================

class EggBot(discord.Client):

    def __init__(self):

        intents = discord.Intents.default()

        super().__init__(
            intents=intents
        )

        self.tree = app_commands.CommandTree(
            self
        )


    async def setup_hook(self):

        logger.info(
            "Syncing Discord slash commands..."
        )

        try:

            synced = await self.tree.sync()

            logger.info(
                "Synced %s slash commands",
                len(synced)
            )

        except Exception:

            logger.exception(
                "Failed to sync slash commands"
            )


    async def on_ready(self):

        logger.info(
            "Discord logged in as %s",
            self.user
        )


client = EggBot()


# ============================================================
# API REQUEST
# ============================================================

async def api_json(
    path: str
) -> dict:

    url = f"{API_URL}{path}"

    timeout = aiohttp.ClientTimeout(
        total=30
    )

    try:

        async with aiohttp.ClientSession(
            timeout=timeout
        ) as session:

            async with session.get(
                url
            ) as response:

                text = await response.text()

                if response.status != 200:

                    raise RuntimeError(
                        f"API returned HTTP "
                        f"{response.status}: "
                        f"{text[:300]}"
                    )

                try:

                    import json

                    return json.loads(text)

                except Exception:

                    raise RuntimeError(
                        "API returned invalid JSON"
                    )

    except asyncio.TimeoutError:

        raise RuntimeError(
            "API request timed out"
        )

    except aiohttp.ClientError as error:

        raise RuntimeError(
            f"API connection failed: {error}"
        )


# ============================================================
# /eggs
# ============================================================

@client.tree.command(
    name="eggs",
    description="Show the latest observed field eggs",
)
async def eggs(
    interaction: discord.Interaction
):

    await interaction.response.defer()

    try:

        data = await api_json(
            "/eggs"
        )

        snapshot = data.get(
            "snapshot"
        )

        if not snapshot:

            await interaction.followup.send(
                "🥚 No egg snapshot has been received yet."
            )

            return

        eggs_list = snapshot.get(
            "eggs",
            []
        )

        if not eggs_list:

            egg_text = "None"

        else:

            lines = []

            for egg in eggs_list:

                egg_type = egg.get(
                    "egg_type",
                    "Unknown"
                )

                area = egg.get(
                    "area"
                )

                if area:

                    lines.append(
                        f"🥚 {egg_type} — {area}"
                    )

                else:

                    lines.append(
                        f"🥚 {egg_type}"
                    )

            egg_text = "\n".join(
                lines
            )

        countdown = data.get(
            "seconds_until_reset"
        )

        if countdown is None:

            reset_text = (
                "Reset time unavailable"
            )

        else:

            reset_text = (
                f"⏱️ Next reset in "
                f"{countdown}s"
            )

        message = (
            "**🥚 Current Eggs**\n\n"
            f"{egg_text}\n\n"
            f"{reset_text}"
        )

        await interaction.followup.send(
            message
        )

    except Exception as error:

        logger.exception(
            "Error in /eggs"
        )

        await interaction.followup.send(
            f"❌ Could not read predictor API:\n"
            f"`{error}`",
            ephemeral=True
        )


# ============================================================
# /next
# ============================================================

@client.tree.command(
    name="next",
    description="Show historical probabilities for the next cycle",
)
async def next_cycle(
    interaction: discord.Interaction
):

    await interaction.response.defer()

    try:

        data = await api_json(
            "/next"
        )

        predictions = data.get(
            "predictions",
            []
        )

        if predictions:

            lines = []

            for row in predictions:

                egg_type = row.get(
                    "egg_type",
                    "Unknown"
                )

                probability = float(
                    row.get(
                        "probability",
                        0
                    )
                )

                observations = row.get(
                    "observations",
                    0
                )

                lines.append(
                    f"🥚 **{egg_type}** — "
                    f"{probability:.1%} "
                    f"({observations} cycles)"
                )

            prediction_text = "\n".join(
                lines
            )

        else:

            prediction_text = (
                "Not enough history yet."
            )

        countdown = data.get(
            "seconds_until_reset"
        )

        if countdown is None:

            reset_text = "unknown"

        else:

            reset_text = f"{countdown}s"

        message = (
            "**🔮 Next Cycle Estimate**\n\n"
            f"⏱️ Reset in: {reset_text}\n\n"
            f"{prediction_text}"
        )

        await interaction.followup.send(
            message
        )

    except Exception as error:

        logger.exception(
            "Error in /next"
        )

        await interaction.followup.send(
            f"❌ Could not read predictor API:\n"
            f"`{error}`",
            ephemeral=True
        )


# ============================================================
# /history
# ============================================================

@client.tree.command(
    name="history",
    description="Show recent observed cycles",
)
async def history(
    interaction: discord.Interaction
):

    await interaction.response.defer()

    try:

        data = await api_json(
            "/history?limit=5"
        )

        cycles = data.get(
            "cycles",
            []
        )

        if not cycles:

            message = (
                "**📚 Recent Cycles**\n\n"
                "No history yet."
            )

        else:

            lines = []

            for cycle in cycles:

                cycle_id = cycle.get(
                    "id",
                    "?"
                )

                egg_count = len(
                    cycle.get(
                        "eggs",
                        []
                    )
                )

                lines.append(
                    f"Cycle **{cycle_id}** — "
                    f"{egg_count} eggs"
                )

            message = (
                "**📚 Recent Cycles**\n\n"
                + "\n".join(lines)
            )

        await interaction.followup.send(
            message
        )

    except Exception as error:

        logger.exception(
            "Error in /history"
        )

        await interaction.followup.send(
            f"❌ Could not read predictor API:\n"
            f"`{error}`",
            ephemeral=True
        )


# ============================================================
# /status
# ============================================================

@client.tree.command(
    name="status",
    description="Check API connectivity",
)
async def status(
    interaction: discord.Interaction
):

    await interaction.response.defer(
        ephemeral=True
    )

    try:

        data = await api_json(
            "/health"
        )

        api_status = data.get(
            "status",
            "unknown"
        )

        await interaction.followup.send(
            f"✅ Predictor API is **{api_status}**",
            ephemeral=True
        )

    except Exception as error:

        logger.exception(
            "Error in /status"
        )

        await interaction.followup.send(
            f"❌ Predictor API is offline:\n"
            f"`{error}`",
            ephemeral=True
        )


# ============================================================
# COLLECTOR
# ============================================================

def get_current_time() -> float:

    return datetime.now(
        timezone.utc
    ).timestamp()


def collect_eggs() -> dict:

    current_time = get_current_time()

    # ========================================================
    # IMPORTANT
    #
    # THESE ARE STILL EXAMPLE EGGS.
    #
    # Replace this section with your REAL egg collection
    # source when you have it.
    # ========================================================

    eggs = [
        {
            "uid": "egg_001",
            "egg_type": "grass",
            "area": "Route 1",
            "spawned_at": current_time,
        },
        {
            "uid": "egg_002",
            "egg_type": "water",
            "area": "Lake",
            "spawned_at": current_time,
        },
        {
            "uid": "egg_003",
            "egg_type": "fire",
            "area": "Volcano",
            "spawned_at": current_time,
        },
    ]

    cycle_seconds = 3600

    return {
        "server_time": current_time,
        "cycle_seconds": cycle_seconds,
        "next_reset_at": (
            current_time
            + cycle_seconds
        ),
        "eggs": eggs,
    }


def send_snapshot(
    snapshot: dict
) -> bool:

    headers = {
        "X-Collector-Key": COLLECTOR_KEY,
        "Content-Type": "application/json",
    }

    try:

        response = requests.post(
            f"{API_URL}/ingest",
            json=snapshot,
            headers=headers,
            timeout=30,
        )

        if response.status_code == 200:

            result = response.json()

            logger.info(
                "Snapshot sent successfully "
                "(ID: %s, %s eggs)",
                result.get("id"),
                result.get("eggs"),
            )

            return True

        logger.error(
            "API error HTTP %s: %s",
            response.status_code,
            response.text[:500],
        )

        return False

    except requests.exceptions.ConnectionError:

        logger.error(
            "Could not connect to %s",
            API_URL,
        )

        return False

    except requests.exceptions.Timeout:

        logger.error(
            "Snapshot request timed out"
        )

        return False

    except Exception:

        logger.exception(
            "Unexpected collector error"
        )

        return False


async def collector_loop():

    logger.info(
        "Egg collector started"
    )

    logger.info(
        "Collection interval: %ss",
        COLLECTION_INTERVAL,
    )

    await asyncio.sleep(
        10
    )

    while True:

        try:

            logger.info(
                "Collecting eggs..."
            )

            snapshot = collect_eggs()

            logger.info(
                "Found %s eggs",
                len(snapshot["eggs"]),
            )

            # requests is synchronous, so run it
            # outside the Discord event loop.
            success = await asyncio.to_thread(
                send_snapshot,
                snapshot
            )

            if success:

                logger.info(
                    "Waiting %ss...",
                    COLLECTION_INTERVAL,
                )

            else:

                logger.warning(
                    "Snapshot failed; "
                    "will retry next cycle."
                )

            await asyncio.sleep(
                COLLECTION_INTERVAL
            )

        except asyncio.CancelledError:

            logger.info(
                "Collector task stopped"
            )

            raise

        except Exception:

            logger.exception(
                "Collector loop error"
            )

            await asyncio.sleep(
                30
            )


# ============================================================
# START BOTH SERVICES
# ============================================================

async def discord_runner():

    try:

        await client.start(
            DISCORD_TOKEN
        )

    except Exception:

        logger.exception(
            "Discord bot stopped"
        )

        raise


async def run_all():

    collector_task = asyncio.create_task(
        collector_loop()
    )

    discord_task = asyncio.create_task(
        discord_runner()
    )

    try:

        await asyncio.gather(
            collector_task,
            discord_task
        )

    finally:

        collector_task.cancel()

        if not client.is_closed():

            await client.close()


def start_background_services():

    asyncio.run(
        run_all()
    )


# ============================================================
# UVICORN + BACKGROUND THREAD
# ============================================================

if __name__ == "__main__":

    import threading

    bot_thread = threading.Thread(
        target=start_background_services,
        daemon=True,
        name="DiscordCollector"
    )

    bot_thread.start()

    logger.info(
        "Starting HTTP server on port %s",
        PORT
    )

    uvicorn.run(
        web_app,
        host="0.0.0.0",
        port=PORT,
        log_level="info",
    )
