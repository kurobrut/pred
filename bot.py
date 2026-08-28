import asyncio
import logging
import os

import aiohttp
import discord
from discord import app_commands


# --------------------------------------------------
# CONFIG
# --------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)

logger = logging.getLogger("EggBot")


API_URL = os.getenv(
    "PREDICTOR_API_URL",
    ""
).rstrip("/")

DISCORD_TOKEN = os.getenv(
    "DISCORD_TOKEN"
)


if not API_URL:

    raise SystemExit(
        "PREDICTOR_API_URL environment variable is required"
    )


if not DISCORD_TOKEN:

    raise SystemExit(
        "DISCORD_TOKEN environment variable is required"
    )


# --------------------------------------------------
# DISCORD BOT
# --------------------------------------------------

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

        await self.tree.sync()

        logger.info(
            "Slash commands synced"
        )

    async def on_ready(self):

        logger.info(
            "Logged in as %s",
            self.user
        )


client = EggBot()


# --------------------------------------------------
# API HELPER
# --------------------------------------------------

async def api_json(
    path: str
) -> dict:

    timeout = aiohttp.ClientTimeout(
        total=30
    )

    url = f"{API_URL}{path}"

    try:

        async with aiohttp.ClientSession(
            timeout=timeout
        ) as session:

            async with session.get(
                url
            ) as response:

                if response.status != 200:

                    text = await response.text()

                    raise RuntimeError(
                        f"API returned HTTP "
                        f"{response.status}: {text[:300]}"
                    )

                return await response.json()

    except asyncio.TimeoutError:

        raise RuntimeError(
            "API request timed out"
        )

    except aiohttp.ClientError as error:

        raise RuntimeError(
            f"Connection failed: {error}"
        )


# --------------------------------------------------
# /eggs
# --------------------------------------------------

@client.tree.command(
    name="eggs",
    description="Show the latest observed field eggs"
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
                "No egg snapshot has been received yet."
            )

            return

        lines = []

        for egg in snapshot.get(
            "eggs",
            []
        ):

            egg_type = egg.get(
                "egg_type",
                "Unknown"
            )

            area = egg.get(
                "area"
            )

            if area:

                lines.append(
                    f"{egg_type} ({area})"
                )

            else:

                lines.append(
                    egg_type
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
                f"Next reset in: "
                f"{countdown}s"
            )

        message = (
            "**Current eggs**\n"
            + (
                "\n".join(lines)
                if lines
                else "None"
            )
            + "\n\n"
            + reset_text
        )

        await interaction.followup.send(
            message
        )

    except Exception as error:

        logger.exception(
            "Error in /eggs"
        )

        await interaction.followup.send(
            f"Could not read predictor API: "
            f"{error}",
            ephemeral=True
        )


# --------------------------------------------------
# /next
# --------------------------------------------------

@client.tree.command(
    name="next",
    description="Show historical probabilities for the next cycle"
)
async def next_cycle(
    interaction: discord.Interaction
):

    await interaction.response.defer()

    try:

        data = await api_json(
            "/next"
        )

        rows = data.get(
            "predictions",
            []
        )

        lines = []

        for row in rows:

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
                f"{egg_type}: "
                f"{probability:.1%} "
                f"({observations} cycles)"
            )

        countdown = data.get(
            "seconds_until_reset"
        )

        reset_text = (
            str(countdown)
            if countdown is not None
            else "unknown"
        )

        message = (
            "**Next cycle estimate**\n"
            f"Reset in: {reset_text}s\n\n"
            + (
                "\n".join(lines)
                if lines
                else "Not enough history yet."
            )
        )

        await interaction.followup.send(
            message
        )

    except Exception as error:

        logger.exception(
            "Error in /next"
        )

        await interaction.followup.send(
            f"Could not read predictor API: "
            f"{error}",
            ephemeral=True
        )


# --------------------------------------------------
# /history
# --------------------------------------------------

@client.tree.command(
    name="history",
    description="Show recent observed cycles"
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

        lines = [
            (
                f"Cycle {cycle.get('id', '?')}: "
                f"{len(cycle.get('eggs', []))} eggs"
            )
            for cycle in cycles
        ]

        await interaction.followup.send(
            "**Recent cycles**\n"
            + (
                "\n".join(lines)
                if lines
                else "No history yet."
            )
        )

    except Exception as error:

        logger.exception(
            "Error in /history"
        )

        await interaction.followup.send(
            f"Could not read predictor API: "
            f"{error}",
            ephemeral=True
        )


# --------------------------------------------------
# /status
# --------------------------------------------------

@client.tree.command(
    name="status",
    description="Check API connectivity"
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

        await interaction.followup.send(
            f"✅ API is online: "
            f"{data.get('status', 'unknown')}",
            ephemeral=True
        )

    except Exception as error:

        logger.exception(
            "Error in /status"
        )

        await interaction.followup.send(
            f"❌ API is offline: {error}",
            ephemeral=True
        )


# --------------------------------------------------
# START
# --------------------------------------------------

if __name__ == "__main__":

    client.run(
        DISCORD_TOKEN
    )
