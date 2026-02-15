import discord
from discord.ext import commands, tasks
import os, django
from asgiref.sync import sync_to_async
from django.utils import timezone
from dotenv import load_dotenv
from pathlib import Path

# ---------- LOAD ENV ----------
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)

# ---------- DJANGO SETUP ----------
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "staffbot.settings")
django.setup()

from economy.models import UserProfile, Transaction
from shop.models import ShopItem, Redemption

# ---------- CONFIG ----------
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("DISCORD_TOKEN not found in environment variables")

OWNER_ID = 716982756017569813
ADMIN_IDS = []
ADMIN_CHANNEL_ID = 1466724559595114709
AFK_CHANNEL_ID = 1466754970299797687

# ---------- ENABLED / DISABLED CHANNELS ----------
enabled_text_channels = set()
disabled_text_channels = set()
enabled_vc_channels = set()
disabled_vc_channels = set()

# ---------- INTENTS ----------
intents = discord.Intents.all()
intents.message_content = True

bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

vc_tracker = {}
message_count_tracker = {}
afk_tracker = {}

# ---------- DATABASE ----------
@sync_to_async
def get_user(uid):
    obj, _ = UserProfile.objects.get_or_create(user_id=uid)
    if obj.balance is None:
        obj.balance = 0
    if obj.vc_minutes is None:
        obj.vc_minutes = 0
    obj.save()
    return obj

@sync_to_async
def save_transaction(user_id, action, amount):
    Transaction.objects.create(user_id=user_id, action=action, amount=amount)

@sync_to_async
def get_shop_items():
    return list(ShopItem.objects.all())

@sync_to_async
def get_shop_item_by_name(name):
    return ShopItem.objects.filter(name__iexact=name).first()

@sync_to_async
def create_redemption(user_id, item_name, price):
    return Redemption.objects.create(
        user_id=user_id,
        item_name=item_name,
        price=price,
        status="PENDING"
    )

@sync_to_async
def get_redemption(rid):
    return Redemption.objects.filter(id=rid).first()

@sync_to_async
def update_redemption_status(rid, status):
    r = Redemption.objects.filter(id=rid).first()
    if r:
        r.status = status
        r.save()
    return r

@sync_to_async
def add_shop_item(name, price, description):
    return ShopItem.objects.create(name=name, price=price, description=description)

@sync_to_async
def remove_shop_item(name):
    item = ShopItem.objects.filter(name__iexact=name).first()
    if item:
        item.delete()
        return True
    return False

@sync_to_async
def reset_shop_items():
    ShopItem.objects.all().delete()

# ---------- BUTTON VIEW ----------
class RedemptionView(discord.ui.View):
    def __init__(self, redemption_id):
        super().__init__(timeout=None)
        self.redemption_id = redemption_id

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != OWNER_ID and interaction.user.id not in ADMIN_IDS:
            await interaction.response.send_message("Not allowed.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.success)
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        redemption = await get_redemption(self.redemption_id)
        if not redemption or redemption.status != "PENDING":
            return await interaction.response.send_message("Already processed.", ephemeral=True)

        await update_redemption_status(self.redemption_id, "APPROVED")

        user = bot.get_user(redemption.user_id)
        if user:
            try:
                await user.send(f"✅ Your redemption for **{redemption.item_name}** was approved!")
            except:
                pass

        await interaction.response.edit_message(
            content=f"✅ Redemption {self.redemption_id} Approved",
            view=None
        )

    @discord.ui.button(label="❌ Deny", style=discord.ButtonStyle.danger)
    async def deny_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        redemption = await get_redemption(self.redemption_id)
        if not redemption or redemption.status != "PENDING":
            return await interaction.response.send_message("Already processed.", ephemeral=True)

        user_profile = await get_user(redemption.user_id)
        user_profile.balance += redemption.price
        await sync_to_async(user_profile.save)()

        await update_redemption_status(self.redemption_id, "DENIED")

        user = bot.get_user(redemption.user_id)
        if user:
            try:
                await user.send("❌ Redemption denied. Points refunded.")
            except:
                pass

        await interaction.response.edit_message(
            content=f"❌ Redemption {self.redemption_id} Denied (Refunded)",
            view=None
        )

# ---------- MESSAGE SYSTEM ----------
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    channel_name = message.channel.name
    if channel_name in enabled_text_channels and channel_name not in disabled_text_channels:
        uid = message.author.id
        message_count_tracker[uid] = message_count_tracker.get(uid, 0) + 1

        if message_count_tracker[uid] >= 5:
            user = await get_user(uid)
            user.balance += 1
            await sync_to_async(user.save)()
            await save_transaction(uid, "MESSAGE_REWARD", 1)
            message_count_tracker[uid] = 0

    await bot.process_commands(message)

# ---------- HELP ----------
@bot.command()
async def help(ctx):
    embed = discord.Embed(title="📘 Commands", color=0x00ff00, timestamp=timezone.now())
    if ctx.author.id == OWNER_ID or ctx.author.id in ADMIN_IDS:
        embed.title = "👑 OWNER / ADMIN COMMANDS"
        embed.color = 0xff0000
        embed.add_field(name=".add_points @user <amt>", value="Add points", inline=False)
        embed.add_field(name=".remove_points @user <amt>", value="Remove points", inline=False)
        embed.add_field(name=".reset_points @user", value="Reset points", inline=False)
        embed.add_field(name=".enable_channel <name>", value="Enable msg points", inline=False)
        embed.add_field(name=".disable_channel <name>", value="Disable msg points", inline=False)
        embed.add_field(name=".enable_vc <name>", value="Enable VC points", inline=False)
        embed.add_field(name=".disable_vc <name>", value="Disable VC points", inline=False)
        embed.add_field(name=".add_shop", value="Add shop item", inline=False)
        embed.add_field(name=".remove_shop", value="Remove shop item", inline=False)
        embed.add_field(name=".reset_shop", value="Reset shop", inline=False)
    else:
        embed.add_field(name=".balance", value="Check your balance", inline=False)
        embed.add_field(name=".shop", value="View shop", inline=False)
        embed.add_field(name=".buy <item>", value="Buy item", inline=False)
        embed.add_field(name=".vc_stats", value="VC time", inline=False)
    await ctx.send(embed=embed)

# ---------- ACCEPT / DENY COMMANDS ----------
@bot.command()
async def accept(ctx, redemption_id: int):
    if ctx.author.id != OWNER_ID and ctx.author.id not in ADMIN_IDS:
        return
    redemption = await get_redemption(redemption_id)
    if not redemption or redemption.status != "PENDING":
        return await ctx.send("Invalid redemption.")
    await update_redemption_status(redemption_id, "APPROVED")
    await ctx.send(f"✅ Redemption {redemption_id} approved.")

@bot.command()
async def deny(ctx, redemption_id: int):
    if ctx.author.id != OWNER_ID and ctx.author.id not in ADMIN_IDS:
        return
    redemption = await get_redemption(redemption_id)
    if not redemption or redemption.status != "PENDING":
        return await ctx.send("Invalid redemption.")
    user_profile = await get_user(redemption.user_id)
    user_profile.balance += redemption.price
    await sync_to_async(user_profile.save)()
    await update_redemption_status(redemption_id, "DENIED")
    await ctx.send(f"❌ Redemption {redemption_id} denied and refunded.")

# ---------- BUY ----------
@bot.command()
async def buy(ctx, *, item_name):
    item = await get_shop_item_by_name(item_name)
    embed = discord.Embed(timestamp=timezone.now())

    if not item:
        embed.title = "❌ Error"
        embed.description = "Item not found"
        embed.color = 0xff0000
        return await ctx.send(embed=embed)

    user = await get_user(ctx.author.id)

    if user.balance < item.price:
        embed.title = "❌ Error"
        embed.description = "Not enough points"
        embed.color = 0xff0000
        return await ctx.send(embed=embed)

    user.balance -= item.price
    await sync_to_async(user.save)()

    redemption = await create_redemption(ctx.author.id, item.name, item.price)

    admin_channel = bot.get_channel(ADMIN_CHANNEL_ID)

    admin_embed = discord.Embed(
        title="🛒 Redemption Request",
        description=f"**User:** {ctx.author.mention}\n"
                    f"**Item:** {item.name}\n"
                    f"**Price:** {item.price} points\n"
                    f"**Redemption ID:** {redemption.id}",
        color=0x00ff00,
        timestamp=timezone.now()
    )

    admin_embed.set_footer(text="Use .accept <ID> or .deny <ID> OR use the buttons below")

    await admin_channel.send(embed=admin_embed, view=RedemptionView(redemption.id))

    embed.title = "✅ Success"
    embed.description = "Redemption request sent to admins"
    embed.color = 0x00ff00
    await ctx.send(embed=embed)

bot.run(TOKEN)
