import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os
import random
from datetime import datetime, timedelta
import pytz
import aiohttp
from aiohttp import web
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

# Historial de mensajes recientes para evitar repeticiones
_recent_messages: list[str] = []

# ── Health check para Viirless ───────────────────────────────────────────────
async def health_check(request):
    return web.Response(text="OK")

async def start_health_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    print("🌐 Health server escuchando en puerto 8080")
# ─────────────────────────────────────────────────────────────────────────────

# Mensajes de fallback variados estilo coreano, mañana y noche por separado
FALLBACK_MORNING = [
    "☀️ Yah~ ¡buenos días mi vida! ¿Ya te tomaste la pastillita? No me hagas preguntar dos veces 🥺",
    "☀️ Oye oye oye… antes de hacer nada, pastilla primero. ¡Venga! 💊✨",
    "☀️ Buenos días preciosa~ El bot te quiere mucho pero si no tomas la pastilla se va a enfadar un poquito 😤💕",
    "☀️ Yah! ¡Ni se te ocurra olvidarla hoy! La pastilla primero, el resto después~ 🌸",
    "☀️ Annyeong~~ ¡Levanta esa cabeza bonita y tómate la pastilla! ¡Hwaiting! 💪🌼",
    "☀️ Eh eh eh, para para para… ¿pastilla tomada? No, ¿verdad? Sabía yo~ 😏💊",
    "☀️ Buenos días mi amor~ El universo entero está esperando a que te tomes la pastilla, incluido yo 🥹",
    "☀️ Yah~ no me mires con esa carita, ya sé que acabas de despertar. ¡Pastilla igualmente! 😤🌸",
]

FALLBACK_NIGHT = [
    "🌙 Yah~ antes de dormirte, ¡pastilla! No te escapes sin tomártela 😤💕",
    "🌙 Oye dormilona del futuro~ tómate la pastilla ahora o te voy a recordar en sueños 👻💊",
    "🌙 Última llamada del día~ pastilla o el bot se queda triste toda la noche 🥺🌙",
    "🌙 Yah! ¿Ya? ¿Segura? No me falles ahora que vamos tan bien~ 💊✨",
    "🌙 Buenas noches mi vida~ pero primero: pastilla. Después ya duermes todo lo que quieras 😴🌸",
    "🌙 Eh eh, no te duermas todavía~ pastilla primero y luego te dejo en paz, lo prometo 🤙💕",
    "🌙 Annyeong~ el bot nocturno ha llegado a recordarte que eres preciosa y que necesitas tomar la pastilla 🌙💊",
    "🌙 Yah~ si ya la tomaste, eres mi persona favorita. Si no… tenemos que hablar 😒💕",
]

async def get_ai_message(is_morning: bool) -> str:
    turno = "mañana" if is_morning else "noche"
    emoji = "☀️" if is_morning else "🌙"

    # Construir lista de mensajes recientes para que Gemini no los repita
    recientes_str = ""
    if _recent_messages:
        recientes_str = (
            "IMPORTANTE: NO repitas ni parafrasees ninguno de estos mensajes anteriores:\n"
            + "\n".join(f"- {m}" for m in _recent_messages[-5:])
            + "\n\n"
        )

    prompt = (
        f"{recientes_str}"
        f"Eres un bot de Discord cariñoso con un estilo muy coreano (k-drama/k-pop), "
        f"como esos chicos cariñosos pero regañones de los doramas. "
        f"Le recuerdas a tu novia que se tome la pastilla anticonceptiva. "
        f"Es por la {turno}. "
        f"Escribe UN mensaje corto (máximo 3 líneas) con el emoji {emoji}. "
        f"Usa 'Yah~', 'Annyeong', 'Hwaiting', apodos cariñosos, emojis kawaii. "
        f"Tono: cariñoso + un poco regañón + gracioso. "
        f"No uses asteriscos ni markdown. Solo texto plano con emojis. "
        f"Cada mensaje debe ser completamente diferente al anterior."
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    body = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()

                # Guardar en historial anti-repetición (máximo 10)
                _recent_messages.append(text)
                if len(_recent_messages) > 10:
                    _recent_messages.pop(0)

                return text
    except Exception as e:
        print(f"⚠️ Gemini falló: {e} — usando fallback")
        pool = FALLBACK_MORNING if is_morning else FALLBACK_NIGHT
        # Elegir uno que no esté en los recientes
        opciones = [m for m in pool if m not in _recent_messages]
        if not opciones:
            opciones = pool  # si todos ya se usaron, resetear
        elegido = random.choice(opciones)
        _recent_messages.append(elegido)
        if len(_recent_messages) > 10:
            _recent_messages.pop(0)
        return elegido


async def send_embed(is_morning: bool, test_mode: bool = False):
    channel = bot.get_channel(CHANNEL_ID)
    if channel is None:
        print(f"❌ Canal no encontrado: {CHANNEL_ID}")
        return

    ai_text = await get_ai_message(is_morning)

    color = discord.Color.from_rgb(255, 180, 0) if is_morning else discord.Color.from_rgb(80, 60, 140)
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)

    embed = discord.Embed(description=ai_text, color=color)

    if test_mode:
        embed.add_field(
            name="🧪 MODO TEST",
            value="Botones con tiempos cortos para probar\n**1 min** · **5 min** · **10 min**",
            inline=False
        )
        embed.set_footer(text=f"🧪 Test mode • {now.strftime('%d/%m/%Y %H:%M')}")
        view = ConfirmButtons(is_morning=is_morning, test_mode=True, timeout=120)
    else:
        embed.add_field(
            name="",
            value="Pulsa **✅ Sí** si ya te la has tomado~\nPulsa **❌ No** si aún no, vaga 😤",
            inline=False
        )
        embed.set_footer(text=f"💊 Pastilla time~ • {now.strftime('%d/%m/%Y %H:%M')}")
        view = ConfirmButtons(is_morning=is_morning, test_mode=False, timeout=1800)

    embed.timestamp = now

    msg = await channel.send(
        content="@everyone" if not test_mode else None,
        embed=embed,
        view=view,
        allowed_mentions=discord.AllowedMentions(everyone=True) if not test_mode else discord.AllowedMentions.none()
    )
    view.message = msg


class ConfirmButtons(discord.ui.View):
    def __init__(self, is_morning: bool, test_mode: bool = False, timeout=1800):
        super().__init__(timeout=timeout)
        self.is_morning = is_morning
        self.test_mode = test_mode
        self.message = None
        self.responded = False

        # Añadir botones de "No" dinámicamente según el modo
        if test_mode:
            self.add_item(NoButton(label="❌ 1 min",   minutes=1,  test_mode=True))
            self.add_item(NoButton(label="❌ 5 min",   minutes=5,  test_mode=True))
            self.add_item(NoButton(label="❌ 10 min",  minutes=10, test_mode=True))
        else:
            self.add_item(NoButton(label="❌ En 10 min", minutes=10,  test_mode=False))
            self.add_item(NoButton(label="❌ En 30 min", minutes=30,  test_mode=False))
            self.add_item(NoButton(label="❌ En 1 hora", minutes=60,  test_mode=False))

    async def on_timeout(self):
        if self.responded:
            return

        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

        if not self.test_mode:
            scheduler.add_job(
                send_embed, "date",
                run_date=datetime.now(pytz.timezone(TIMEZONE)) + timedelta(minutes=30),
                args=[self.is_morning],
                kwargs={"test_mode": False},
                id=f"retry_{datetime.now().timestamp()}",
                replace_existing=True,
            )
            print("⏰ Sin respuesta en 30 min — enviando retry automático")

    @discord.ui.button(label="✅ Sí, ya la tomé~", style=discord.ButtonStyle.success, row=0)
    async def yes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.responded:
            await interaction.response.send_message("Ya estaba marcado~ 💕", ephemeral=True)
            return

        self.responded = True
        tz = pytz.timezone(TIMEZONE)
        now = datetime.now(tz)

        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)

        if self.test_mode:
            await interaction.response.send_message(
                f"🧪 Test ✅ — botón Sí funcionando a las **{now.strftime('%H:%M:%S')}**",
                ephemeral=True
            )
        else:
            respuestas = [
                f"✅ ¡Bien hecha! 💊 Anotado a las **{now.strftime('%H:%M')}** ~ ¡Hwaiting! 🎉",
                f"✅ ¡Eso es! 🌸 Pastilla tomada a las **{now.strftime('%H:%M')}** — eres la mejor 💕",
                f"✅ Yah~ sabía que no me fallarías 🥹 Anotado: **{now.strftime('%H:%M')}** 💊✨",
                f"✅ ¡Mi chica más responsable del mundo! 💪 Tomada a las **{now.strftime('%H:%M')}** 🌸",
                f"✅ Annyeong pastilla~ 💊 Confirmado a las **{now.strftime('%H:%M')}**, ¡te quiero mucho! 💕",
            ]
            await interaction.response.send_message(
                random.choice(respuestas),
                allowed_mentions=discord.AllowedMentions.none()
            )


class NoButton(discord.ui.Button):
    def __init__(self, label: str, minutes: int, test_mode: bool):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.danger,
            row=1
        )
        self.minutes = minutes
        self.test_mode = test_mode

    async def callback(self, interaction: discord.Interaction):
        view: ConfirmButtons = self.view
        if view.responded:
            await interaction.response.send_message("¡Tómatela ya! 😤", ephemeral=True)
            return

        if self.test_mode:
            await interaction.response.send_message(
                f"🧪 Test ❌ — retry programado en **{self.minutes} min** ⏱️",
                ephemeral=True
            )
        else:
            respuestas_no = [
                f"❌ Yah~ vale… te recuerdo en {self.minutes} min 😒💕",
                f"❌ Ayyy… ¡te voy a estar esperando {self.minutes} min! 😤",
                f"❌ No no no… {self.minutes} minutos y vuelvo, ¿eh? 🕐",
                f"❌ Suspiro profundo… en {self.minutes} min volvemos 😮‍💨💊",
            ]
            await interaction.response.send_message(
                random.choice(respuestas_no),
                ephemeral=True
            )

        scheduler.add_job(
            send_embed, "date",
            run_date=datetime.now(pytz.timezone(TIMEZONE)) + timedelta(minutes=self.minutes),
            args=[view.is_morning],
            kwargs={"test_mode": self.test_mode},
            id=f"retry_{datetime.now().timestamp()}",
            replace_existing=True,
        )


@bot.event
async def on_ready():
    await start_health_server()
    print(f"✅ Bot conectado como {bot.user}")

    # Programar recordatorios diarios
    scheduler.add_job(send_embed, "cron", hour=10, minute=0, args=[True], id="morning", replace_existing=True)
    scheduler.add_job(send_embed, "cron", hour=0, minute=0, args=[False], id="night", replace_existing=True)
    scheduler.start()
    print("⏰ Scheduler iniciado — mañana: 10:00 | noche: 00:00")

    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} comandos slash sincronizados")
    except Exception as e:
        print(f"❌ Error sincronizando comandos: {e}")


@bot.tree.command(name="test_morning", description="🧪 Prueba el mensaje de mañana (botones con tiempos cortos)")
async def test_morning(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await send_embed(is_morning=True, test_mode=True)
    await interaction.followup.send("🧪 Test de mañana enviado~ (botones: 1 min / 5 min / 10 min)", ephemeral=True)


@bot.tree.command(name="test_night", description="🧪 Prueba el mensaje de noche (botones con tiempos cortos)")
async def test_night(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await send_embed(is_morning=False, test_mode=True)
    await interaction.followup.send("🧪 Test de noche enviado~ (botones: 1 min / 5 min / 10 min)", ephemeral=True)


@bot.tree.command(name="parar", description="Cancela los recordatorios de hoy")
async def parar(interaction: discord.Interaction):
    cancelados = 0
    for job_id in [j.id for j in scheduler.get_jobs() if j.id.startswith("retry_")]:
        scheduler.remove_job(job_id)
        cancelados += 1
    await interaction.response.send_message(
        f"🛑 Vale, descansamos hoy~ ({cancelados} recordatorio(s) cancelado(s))",
        ephemeral=True
    )


bot.run(TOKEN)