import os

import aiohttp
import discord
from discord import app_commands


API_URL = os.getenv("PREDICTOR_API_URL", "http://127.0.0.1:8000").rstrip("/")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")


class EggBot(discord.Client):
    def __init__(self) -> None:
        super().__init__(intents=discord.Intents.default())
        self.commands = app_commands.CommandTree(self)

    async def on_ready(self) -> None:
        await self.commands.sync()
        print(f"{self.user} online; slash commands synced")


client = EggBot()


async def api_json(path: str) -> dict:
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(f"{API_URL}{path}") as response:
            if response.status != 200:
                raise RuntimeError(f"API returned HTTP {response.status}")
            return await response.json()


@client.commands.command(name="eggs", description="Show the latest observed field eggs")
async def eggs(interaction: discord.Interaction) -> None:
    try:
        data = await api_json("/eggs")
        snapshot = data.get("snapshot")
        if not snapshot:
            await interaction.response.send_message("No egg snapshot has been received yet.")
            return
        lines = [f"{egg['egg_type']}" + (f" ({egg['area']})" if egg.get("area") else "") for egg in snapshot["eggs"]]
        countdown = data.get("seconds_until_reset")
        reset_text = f"Next reset: {countdown}s" if countdown is not None else "Reset time unavailable"
        await interaction.response.send_message(f"**Current eggs**\n{chr(10).join(lines) or 'None'}\n\n{reset_text}")
    except Exception as error:
        await interaction.response.send_message(f"Could not read predictor API: {error}", ephemeral=True)


@client.commands.command(name="next", description="Show historical probabilities for the next cycle")
async def next_cycle(interaction: discord.Interaction) -> None:
    try:
        data = await api_json("/next")
        rows = data.get("predictions", [])
        lines = [f"{row['egg_type']}: {row['probability']:.1%} ({row['observations']} cycles)" for row in rows]
        countdown = data.get("seconds_until_reset")
        await interaction.response.send_message(
            f"**Next cycle estimate**\nReset in: {countdown if countdown is not None else 'unknown'}s\n" +
            ("\n".join(lines) or "Not enough history yet.")
        )
    except Exception as error:
        await interaction.response.send_message(f"Could not read predictor API: {error}", ephemeral=True)


@client.commands.command(name="history", description="Show recent observed cycles")
async def history(interaction: discord.Interaction) -> None:
    try:
        data = await api_json("/history?limit=5")
        lines = [f"Cycle {cycle['id']}: {len(cycle['eggs'])} eggs" for cycle in data["cycles"]]
        await interaction.response.send_message("**Recent cycles**\n" + ("\n".join(lines) or "No history yet."))
    except Exception as error:
        await interaction.response.send_message(f"Could not read predictor API: {error}", ephemeral=True)


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise SystemExit("DISCORD_TOKEN is required")
    client.run(DISCORD_TOKEN)