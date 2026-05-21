import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os
from datetime import datetime, timedelta
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
TIMEZONE = os.getenv("TIMEZONE", "Europe/Madrid")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
scheduler = AsyncIOScheduler(timezone=TIMEZONE)

responded_yes = set()
active_embeds = {}


def create_embed(is_morning: bool) -> discord.Embed:
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)

    if is_morning:
        color = discord.Color.from_rgb(255, 180, 0)
        title = "☀️ ¡Buenos días!"
        description = (
            "**¿Estás disponible y listo para hoy?**\n\n"
            "Pulsa **✅ Sí** si estás aquí y disponible.\n"
            "Pulsa **❌ No** si no puedes ahora mismo.\n\n"
            "*Si no respondes en 5 minutos, te volvemos a preguntar en 30 min.*"
        )
        footer = f"☀️ Turno de mañana  •  {now.strftime('%d/%m/%Y %H:%M')}"
    else:
        color = discord.Color.from_rgb(60, 60, 120)
        title = "🌙 ¡Buenas noches!"
        description = (
            "**¿Estás disponible para el turno de noche?**\n\n"
            "Pulsa **✅ Sí** si estás aquí y disponible.\n"
            "Pulsa **❌ No** si no puedes ahora mismo.\n\n"
            "*Si no respondes en 5 minutos, te volvemos a preguntar en 30 min.*"
        )
        footer = f"🌙 Turno de noche  •  {now.strftime('%d/%m/%Y %H:%M')}"

    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text=footer)
    embed.timestamp = now
    return embed


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
        responded_yes.add(interaction.user.id)
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)
        await interaction.response.send_message(
            f"✅ **{interaction.user.display_name}** ha confirmado disponibilidad a las **{now.strftime('%H:%M:%S')}** del {now.strftime('%d/%m/%Y')} 🎉",
            allowed_mentions=discord.AllowedMentions.none()
        )

    @discord.ui.button(label="❌ No", style=discord.ButtonStyle.danger)
    async def no_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            f"❌ **{interaction.user.display_name}** no está disponible ahora. Se volverá a preguntar en **30 minutos**.",
            ephemeral=True
        )
        scheduler.add_job(
            send_embed, "date",
            run_date=datetime.now(pytz.timezone(TIMEZONE)) + timedelta(minutes=30),
            args=[self.is_morning],
            id=f"retry_{datetime.now().timestamp()}",
        )


async def send_embed(is_morning: bool):
    channel = bot.get_channel(CHANNEL_ID)
    if channel is None:
        print(f"❌ No se encontró el canal con ID {CHANNEL_ID}")
        return
    embed = create_embed(is_morning)
    view = ConfirmButtons(is_morning=is_morning, timeout=300)
    msg = await channel.send(
        content="@everyone", embed=embed, view=view,
        allowed_mentions=discord.AllowedMentions(everyone=True)
    )
    view.message = msg
    active_embeds[msg.id] = view
    print(f"✅ Embed enviado a las {datetime.now()}")


@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")
    print(f"📡 Canal objetivo: {CHANNEL_ID}")
    scheduler.add_job(send_embed, "cron", hour=10, minute=0, args=[True], id="morning")
    scheduler.add_job(send_embed, "cron", hour=0, minute=0, args=[False], id="night")
    scheduler.start()
    print("⏰ Scheduler iniciado: 10:00 AM y 00:00 cada día")
    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} comandos slash sincronizados")
    except Exception as e:
        print(f"❌ Error sincronizando: {e}")


@bot.tree.command(name="test_morning", description="Prueba el embed de mañana")
async def test_morning(interaction: discord.Interaction):
    await interaction.response.send_message("Enviando embed de prueba...", ephemeral=True)
    await send_embed(is_morning=True)


@bot.tree.command(name="test_night", description="Prueba el embed de noche")
async def test_night(interaction: discord.Interaction):
    await interaction.response.send_message("Enviando embed de prueba...", ephemeral=True)
    await send_embed(is_morning=False)


bot.run(TOKEN)