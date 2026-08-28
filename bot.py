import os
import logging
import aiohttp
import discord
from discord import app_commands

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("EggBot")

API_URL = os.getenv("PREDICTOR_API_URL", "").rstrip("/")
if not API_URL:
    raise SystemExit("PREDICTOR_API_URL environment variable is required")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    raise SystemExit("DISCORD_TOKEN is required")


class EggBot(discord.Client):
    def __init__(self) -> None:
        super().__init__(intents=discord.Intents.default())
        self.commands = app_commands.CommandTree(self)

    async def on_ready(self) -> None:
        await self.commands.sync()
        logger.info(f"{self.user} online; slash commands synced")


client = EggBot()


async def api_json(path: str) -> dict:
    """Fetch JSON from API with extended timeout for Render cold starts"""
    timeout = aiohttp.ClientTimeout(total=30)  # 30 seconds for Render cold starts
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.get(f"{API_URL}{path}") as response:
                if response.status != 200:
                    raise RuntimeError(f"API returned HTTP {response.status}")
                return await response.json()
        except asyncio.TimeoutError:
            raise RuntimeError("API request timed out (Render service may be starting)")
        except aiohttp.ClientError as e:
            raise RuntimeError(f"Connection failed: {e}")


import asyncio


@client.commands.command(name="eggs", description="Show the latest observed field eggs")
async def eggs(interaction: discord.Interaction) -> None:
    await interaction.response.defer()
    try:
        data = await api_json("/eggs")
        snapshot = data.get("snapshot")
        if not snapshot:
            await interaction.followup.send("No egg snapshot has been received yet.")
            return
        lines = [
            f"{egg['egg_type']}" + (f" ({egg['area']})" if egg.get("area") else "")
            for egg in snapshot["eggs"]
        ]
        countdown = data.get("seconds_until_reset")
        reset_text = (
            f"Next reset: {countdown}s"
            if countdown is not None
            else "Reset time unavailable"
        )
        await interaction.followup.send(
            f"**Current eggs**\n{chr(10).join(lines) or 'None'}\n\n{reset_text}"
        )
    except Exception as error:
        logger.error(f"Error in eggs command: {error}")
        await interaction.followup.send(
            f"Could not read predictor API: {error}", ephemeral=True
        )


@client.commands.command(
    name="next", description="Show historical probabilities for the next cycle"
)
async def next_cycle(interaction: discord.Interaction) -> None:
    await interaction.response.defer()
    try:
        data = await api_json("/next")
        rows = data.get("predictions", [])
        lines = [
            f"{row['egg_type']}: {row['probability']:.1%} ({row['observations']} cycles)"
            for row in rows
        ]
        countdown = data.get("seconds_until_reset")
        await interaction.followup.send(
            f"**Next cycle estimate**\nReset in: {countdown if countdown is not None else 'unknown'}s\n"
            + ("\n".join(lines) or "Not enough history yet.")
        )
    except Exception as error:
        logger.error(f"Error in next_cycle command: {error}")
        await interaction.followup.send(
            f"Could not read predictor API: {error}", ephemeral=True
        )


@client.commands.command(name="history", description="Show recent observed cycles")
async def history(interaction: discord.Interaction) -> None:
    await interaction.response.defer()
    try:
        data = await api_json("/history?limit=5")
        lines = [f"Cycle {cycle['id']}: {len(cycle['eggs'])} eggs" for cycle in data["cycles"]]
        await interaction.followup.send(
            "**Recent cycles**\n" + ("\n".join(lines) or "No history yet.")
        )
    except Exception as error:
        logger.error(f"Error in history command: {error}")
        await interaction.followup.send(
            f"Could not read predictor API: {error}", ephemeral=True
        )


@client.commands.command(name="status", description="Check API connectivity")
async def status(interaction: discord.Interaction) -> None:
    await interaction.response.defer()
    try:
        data = await api_json("/health")
        await interaction.followup.send(f"✅ API is online: {data}", ephemeral=True)
    except Exception as error:
        logger.error(f"Error in status command: {error}")
        await interaction.followup.send(f"❌ API is offline: {error}", ephemeral=True)


if __name__ == "__main__":
    client.run(DISCORD_TOKEN)
