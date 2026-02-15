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
ADMIN_CHANNEL_ID = 1439934427852443688
AFK_CHANNEL_ID = 1425159320001056919
ACTIVE_VC_IDS = {
    1469625366477013198,  # VC 1
    1462365089305985055,
    1459676906244014171,
    1459677374911352852,
    1472587015324434444,
    1459677406204923934,
    1459677452769956075,
    1459677833403170877,
    1459678015540695175,
    1439938056613265551,
}

# Put VC IDs where rewards should NOT work
DISABLED_VC_IDS = {
    1463833480885440617,
    1460372096998707421,
    1425159313152016525,
}
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

# ---------- DATABASE FUNCTIONS ----------
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
    return Redemption.objects.create(user_id=user_id, item_name=item_name, price=price, status="PENDING")

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

# ---------- MESSAGE → POINT SYSTEM ----------
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

# ---------- CHANNEL ENABLE / DISABLE ----------
async def send_embed(ctx, title, description, color=0x00ff00):
    embed = discord.Embed(title=title, description=description, color=color, timestamp=timezone.now())
    await ctx.send(embed=embed)

@bot.command()
async def enable_channel(ctx, channel_name):
    if ctx.author.id != OWNER_ID:
        return
    enabled_text_channels.add(channel_name)
    disabled_text_channels.discard(channel_name)
    await send_embed(ctx, "✅ Channel Enabled", f"Message points enabled in **{channel_name}**", 0x00ff00)

@bot.command()
async def disable_channel(ctx, channel_name):
    if ctx.author.id != OWNER_ID:
        return
    disabled_text_channels.add(channel_name)
    enabled_text_channels.discard(channel_name)
    await send_embed(ctx, "❌ Channel Disabled", f"Message points disabled in **{channel_name}**", 0xff0000)

@bot.command()
async def enable_vc(ctx, vc_name):
    if ctx.author.id != OWNER_ID:
        return
    enabled_vc_channels.add(vc_name)
    disabled_vc_channels.discard(vc_name)
    await send_embed(ctx, "✅ VC Enabled", f"VC points enabled in **{vc_name}**", 0x00ff00)

@bot.command()
async def disable_vc(ctx, vc_name):
    if ctx.author.id != OWNER_ID:
        return
    disabled_vc_channels.add(vc_name)
    enabled_vc_channels.discard(vc_name)
    await send_embed(ctx, "❌ VC Disabled", f"VC points disabled in **{vc_name}**", 0xff0000)

# ---------- POINT MANAGEMENT ----------
@bot.command()
async def add_points(ctx, member: discord.Member, amount: int):
    if ctx.author.id != OWNER_ID and ctx.author.id not in ADMIN_IDS:
        return
    user = await get_user(member.id)
    user.balance += amount
    await sync_to_async(user.save)()
    await save_transaction(member.id, "ADMIN_ADD", amount)
    await send_embed(ctx, "✅ Points Added", f"{amount} points added to {member.mention}", 0x00ff00)

@bot.command()
async def remove_points(ctx, member: discord.Member, amount: int):
    if ctx.author.id != OWNER_ID and ctx.author.id not in ADMIN_IDS:
        return
    user = await get_user(member.id)
    user.balance = max(0, user.balance - amount)
    await sync_to_async(user.save)()
    await save_transaction(member.id, "ADMIN_REMOVE", amount)
    await send_embed(ctx, "❌ Points Removed", f"{amount} points removed from {member.mention}", 0xff0000)

@bot.command()
async def reset_points(ctx, member: discord.Member):
    if ctx.author.id != OWNER_ID and ctx.author.id not in ADMIN_IDS:
        return
    user = await get_user(member.id)
    user.balance = 0
    await sync_to_async(user.save)()
    await save_transaction(member.id, "ADMIN_RESET", 0)
    await send_embed(ctx, "♻ Points Reset", f"Points reset for {member.mention}", 0xffff00)

# ---------- HELP COMMAND ----------
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

# ---------- ECONOMY ----------
@bot.command()
async def balance(ctx, member: discord.Member = None):
    member = member or ctx.author
    u = await get_user(member.id)
    embed = discord.Embed(title="💰 Balance", color=0x00ff00, timestamp=timezone.now())
    embed.description = f"**{member.display_name}** has **{u.balance} points**"
    await ctx.send(embed=embed)

# ---------- SHOP ----------
@bot.command()
async def shop(ctx):
    items = await get_shop_items()
    embed = discord.Embed(title="🛒 Shop", color=0xffff00, timestamp=timezone.now())
    if not items:
        embed.description = "Shop is empty"
    else:
        for i in items:
            embed.add_field(name=f"{i.name} - {i.price}", value=i.description, inline=False)
    await ctx.send(embed=embed)

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
        description=f"**User:** {ctx.author.mention}\n**Item:** {item.name}\n**Price:** {item.price} points\n**Redemption ID:** {redemption.id}",
        color=0x00ff00,
        timestamp=timezone.now()
    )
    admin_embed.set_footer(text="Use .accept <ID> or .deny <ID> to process")
    await admin_channel.send(embed=admin_embed)
    
    embed.title = "✅ Success"
    embed.description = "Redemption request sent to admins"
    embed.color = 0x00ff00
    await ctx.send(embed=embed)

# ---------- VC STATS ----------
@bot.command()
async def vc_stats(ctx):
    u = await get_user(ctx.author.id)
    embed = discord.Embed(title="🎧 VC Stats", description=f"VC Time: **{u.vc_minutes} minutes**", color=0x00ff00, timestamp=timezone.now())
    await ctx.send(embed=embed)

# ---------- ON READY ----------
@bot.event
async def on_ready():
    vc_task.start()
    print("Bot Online")

# ---------- VC LOOP ----------
afk_tracker = {}

@tasks.loop(minutes=1)
async def vc_task():
    for guild in bot.guilds:

        afk_channel = guild.get_channel(AFK_CHANNEL_ID)
        if not afk_channel:
            continue

        for vc in guild.voice_channels:

            # Skip AFK channel itself
            if vc.id == AFK_CHANNEL_ID:
                continue

            # Only allow active VC IDs
            if vc.id not in ACTIVE_VC_IDS:
                continue

            # Skip disabled VC IDs
            if vc.id in DISABLED_VC_IDS:
                continue

            for member in vc.members:

                if member.bot:
                    continue

                if member.id not in afk_tracker:
                    afk_tracker[member.id] = 0

                user = await get_user(member.id)

                # ---------------- AFK CHECK ----------------
                if member.voice.self_mute or member.voice.self_deaf:
                    afk_tracker[member.id] += 1

                    # Move after 1 minute (change number if needed)
                    if afk_tracker[member.id] >= 5:
                        if member.voice.channel.id != AFK_CHANNEL_ID:
                            try:
                                await member.move_to(afk_channel)
                            except:
                                pass
                    continue

                # ---------------- ACTIVE USER ----------------
                else:
                    afk_tracker[member.id] = 0

                    user.vc_minutes = user.vc_minutes or 0
                    user.vc_minutes += 1

                    await sync_to_async(user.save)()
                    await save_transaction(member.id, "VC_REWARD", 1)


bot.run(TOKEN)
