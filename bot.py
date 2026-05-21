import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os
import json
import random
from datetime import datetime, timedelta
import pytz
import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
TIMEZONE = os.getenv("TIMEZONE", "Europe/Madrid")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
scheduler = AsyncIOScheduler(timezone=TIMEZONE)

RACHA_FILE = "racha.json"

def load_racha():
    if os.path.exists(RACHA_FILE):
        with open(RACHA_FILE, "r") as f:
            return json.load(f)
    return {"racha": 0, "ultimo_si": None}

def save_racha(data):
    with open(RACHA_FILE, "w") as f:
        json.dump(data, f)

async def get_ai_message(is_morning: bool, racha: int) -> str:
    turno = "mañana" if is_morning else "noche"
    emoji = "☀️" if is_morning else "🌙"
    prompt = (
        f"Eres un bot cariñoso pero gracioso que le recuerda a su novia que se tome la pastilla. "
        f"Es por la {turno}. Lleva una racha de {racha} días tomándosela. "
        f"Escribe un mensaje corto (máximo 3 líneas) con el emoji {emoji}, "
        f"con un tono cariñoso, gracioso y un poco regañón. "
        f"Si la racha es mayor a 0, menciona la racha de forma motivadora. "
        f"No uses asteriscos ni markdown. Solo texto plano con emojis."
    )
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body) as resp:
                data = await resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        fallback = [
            f"{emoji} Ey dormilona, ¿te has tomado la pastilla?",
            f"{emoji} Oye tú, pastilla. Ya sabes.",
            f"{emoji} No me hagas repetirlo... ¿pastilla tomada?",
        ]
        return random.choice(fallback)

async def send_embed(is_morning: bool):
    channel = bot.get_channel(CHANNEL_ID)
    if channel is None:
        print(f"❌ Canal no encontrado: {CHANNEL_ID}")
        return

    racha_data = load_racha()
    racha = racha_data.get("racha", 0)
    ai_text = await get_ai_message(is_morning, racha)

    color = discord.Color.from_rgb(255, 180, 0) if is_morning else discord.Color.from_rgb(60, 60, 120)
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)

    embed = discord.Embed(description=ai_text, color=color)
    embed.add_field(name="", value="Pulsa **✅ Sí** si ya te la has tomado.\nPulsa **❌ No** si aún no, vaga 😤", inline=False)
    if racha > 0:
        embed.set_footer(text=f"🔥 Llevas {racha} día{'s' if racha != 1 else ''} seguido{'s' if racha != 1 else ''} • {now.strftime('%d/%m/%Y %H:%M')}")
    else:
        embed.set_footer(text=f"💊 Recuerda tu pastilla • {now.strftime('%d/%m/%Y %H:%M')}")
    embed.timestamp = now

    view = ConfirmButtons(is_morning=is_morning, timeout=300)
    msg = await channel.send(
        content="@everyone",
        embed=embed,
        view=view,
        allowed_mentions=discord.AllowedMentions(everyone=True)
    )
    view.message = msg

class ConfirmButtons(discord.ui.View):
    def __init__(self, is_morning: bool, timeout=300):
        super().__init__(timeout=timeout)
        self.is_morning = is_morning
        self.message = None

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass
        scheduler.add_job(
            send_embed, "date",
            run_date=datetime.now(pytz.timezone(TIMEZONE)) + timedelta(minutes=30),
            args=[self.is_morning],
            id=f"retry_{datetime.now().timestamp()}",
        )

    @discord.ui.button(label="✅ Sí", style=discord.ButtonStyle.success)
    async def yes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        tz = pytz.timezone(TIMEZONE)
        now = datetime.now(tz)

        racha_data = load_racha()
        ultimo = racha_data.get("ultimo_si")
        hoy = now.strftime("%Y-%m-%d")

        if ultimo != hoy:
            racha_data["racha"] = racha_data.get("racha", 0) + 1
            racha_data["ultimo_si"] = hoy
            save_racha(racha_data)

        racha = racha_data["racha"]

        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)

        if racha == 7:
            msg = f"✅ ¡SEMANA COMPLETA! 🎉🔥 Llevas 7 días seguidos tomándotela, eres una campeona!"
        elif racha >= 3:
            msg = f"✅ ¡Bien hecha! 🔥 Llevas **{racha} días** seguidos. ¡Sigue así!"
        else:
            msg = f"✅ Anotado a las **{now.strftime('%H:%M:%S')}** — pastilla tomada 💊"

        await interaction.response.send_message(msg, allowed_mentions=discord.AllowedMentions.none())

    @discord.ui.button(label="❌ No", style=discord.ButtonStyle.danger)
    async def no_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        racha_data = load_racha()
        if racha_data.get("racha", 0) > 0:
            racha_data["racha"] = 0
            save_racha(racha_data)

        await interaction.response.send_message(
            "❌ Vaga... te recuerdo en 30 minutos 😒",
            ephemeral=True
        )
        scheduler.add_job(
            send_embed, "date",
            run_date=datetime.now(pytz.timezone(TIMEZONE)) + timedelta(minutes=30),
            args=[self.is_morning],
            id=f"retry_{datetime.now().timestamp()}",
        )

@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")
    scheduler.add_job(send_embed, "cron", hour=10, minute=0, args=[True], id="morning")
    scheduler.add_job(send_embed, "cron", hour=0, minute=0, args=[False], id="night")
    scheduler.start()
    print("⏰ Scheduler iniciado")
    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} comandos sincronizados")
    except Exception as e:
        print(f"❌ Error: {e}")

@bot.tree.command(name="test_morning", description="Prueba el mensaje de mañana")
async def test_morning(interaction: discord.Interaction):
    await interaction.response.send_message("Enviando...", ephemeral=True)
    await send_embed(is_morning=True)

@bot.tree.command(name="test_night", description="Prueba el mensaje de noche")
async def test_night(interaction: discord.Interaction):
    await interaction.response.send_message("Enviando...", ephemeral=True)
    await send_embed(is_morning=False)

bot.run(TOKEN)