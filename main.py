import os, json, discord, asyncio, time
from discord.ext import commands
from datetime import datetime, timezone
from collections import defaultdict

TOKEN = os.getenv("DISCORD_BOT_TOKEN") or os.getenv("TOKEN") or os.getenv("DISCORD_TOKEN")
MY_ID = 1310357536087740450
OWNER_FILE="owners.json"
WHITELIST_FILE="whitelist.json"
BACKUP_DIR="backups"
os.makedirs(BACKUP_DIR, exist_ok=True)

def load_owners():
    if os.path.exists(OWNER_FILE):
        try:
            with open(OWNER_FILE,"r") as f: return set(map(int,json.load(f)))
        except: return {MY_ID}
    return {MY_ID}
def save_owners():
    with open(OWNER_FILE,"w") as f: json.dump(list(OWNER_IDS),f)
def load_whitelist():
    if os.path.exists(WHITELIST_FILE):
        try:
            with open(WHITELIST_FILE,"r") as f: return set(map(int,json.load(f)))
        except: return set()
    return set()
def save_whitelist():
    with open(WHITELIST_FILE,"w") as f: json.dump(list(WHITELIST_IDS),f)

OWNER_IDS=load_owners(); OWNER_IDS.add(MY_ID)
WHITELIST_IDS=load_whitelist()
intents=discord.Intents.default(); intents.message_content=True; intents.members=True; intents.guilds=True
bot=commands.Bot(command_prefix="_",intents=intents,help_command=None)

def bubble(text):
    return discord.Embed(description=text, color=0x2B2D31)
def sync_owners():
    o=load_owners(); o.add(MY_ID); OWNER_IDS.clear(); OWNER_IDS.update(o); return o
def has_perm(ctx): return ctx.author.id in sync_owners()

LIMIT = 3
TIME_WINDOW = 10
cache = defaultdict(list)
def is_safe(uid, guild_owner_id=None):
    return uid == MY_ID or uid in OWNER_IDS or uid in WHITELIST_IDS or uid == guild_owner_id
def is_spam(uid):
    now = time.time()
    cache[uid] = [t for t in cache[uid] if now - t < TIME_WINDOW]
    cache[uid].append(now)
    return len(cache[uid]) > LIMIT
async def nuke_punish(guild, uid, reason):
    if is_safe(uid, guild.owner_id): return
    try:
        m = guild.get_member(uid) or await guild.fetch_member(uid)
        await guild.ban(m, reason=f"ANTINUKE: {reason}")
    except: pass

@bot.event
async def on_ready():
    print(f"Listo {bot.user} - Prefix _")

@bot.event
async def on_member_update(before,after):
    if after.bot or len(before.roles)==len(after.roles): return
    added = [r for r in after.roles if r not in before.roles]
    removed = [r for r in before.roles if r not in after.roles]
    risky = [r for r in added+removed if r.permissions.administrator or r.permissions.ban_members or r.permissions.kick_members or r.permissions.manage_roles or r.permissions.manage_guild or r.permissions.manage_channels]
    if not risky: return
    try:
        async for entry in after.guild.audit_logs(limit=3,action=discord.AuditLogAction.member_role_update):
            if (datetime.now(timezone.utc)-entry.created_at).total_seconds()>10: continue
            if entry.target.id!=after.id: continue
            exe=entry.user
            if exe.bot or is_safe(exe.id, after.guild.owner_id): return
            try: await after.edit(roles=before.roles, reason="AntiRole")
            except: pass
            try: await after.guild.kick(exe, reason=f"AntiRole {risky[0].name}")
            except: pass
            return
    except: pass
@bot.event
async def on_member_ban(guild, user):
    try:
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
            if (datetime.now(timezone.utc)-entry.created_at).total_seconds()>10: continue
            if is_safe(entry.user.id, guild.owner_id): return
            if is_spam(entry.user.id): await nuke_punish(guild, entry.user.id, "Mass Ban")
    except: pass
@bot.event
async def on_member_remove(member):
    try:
        await asyncio.sleep(1)
        async for entry in member.guild.audit_logs(limit=1, action=discord.AuditLogAction.kick):
            if (datetime.now(timezone.utc)-entry.created_at).total_seconds()>10: continue
            if entry.target.id!=member.id: continue
            if is_safe(entry.user.id, member.guild.owner_id): return
            if is_spam(entry.user.id): await nuke_punish(member.guild, entry.user.id, "Mass Kick")
    except: pass
@bot.event
async def on_guild_channel_delete(channel):
    try:
        async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
            if (datetime.now(timezone.utc)-entry.created_at).total_seconds()>10: continue
            if is_safe(entry.user.id, channel.guild.owner_id): return
            if is_spam(entry.user.id): await nuke_punish(channel.guild, entry.user.id, "Mass Channel Delete")
    except: pass
@bot.event
async def on_guild_channel_create(channel):
    try:
        async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_create):
            if (datetime.now(timezone.utc)-entry.created_at).total_seconds()>10: continue
            if is_safe(entry.user.id, channel.guild.owner_id): return
            if is_spam(entry.user.id): await nuke_punish(channel.guild, entry.user.id, "Mass Channel Create")
    except: pass
@bot.event
async def on_guild_role_delete(role):
    try:
        async for entry in role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_delete):
            if (datetime.now(timezone.utc)-entry.created_at).total_seconds()>10: continue
            if is_safe(entry.user.id, role.guild.owner_id): return
            if is_spam(entry.user.id): await nuke_punish(role.guild, entry.user.id, "Mass Role Delete")
    except: pass
@bot.event
async def on_guild_role_create(role):
    try:
        async for entry in role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_create):
            if (datetime.now(timezone.utc)-entry.created_at).total_seconds()>10: continue
            if is_safe(entry.user.id, role.guild.owner_id): return
            if is_spam(entry.user.id): await nuke_punish(role.guild, entry.user.id, "Mass Role Create")
    except: pass
@bot.event
async def on_member_join(member):
    if not member.bot: return
    await asyncio.sleep(1.5)
    try:
        async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.bot_add):
            if (datetime.now(timezone.utc)-entry.created_at).total_seconds()>15: continue
            if entry.target.id!=member.id: continue
            if is_safe(entry.user.id, member.guild.owner_id): return
            try: await member.ban(reason=f"Antibot por {entry.user}")
            except: pass
            await nuke_punish(member.guild, entry.user.id, "Agrego bot")
            return
    except: pass

# --- MODERACION PRIVADA ---
@bot.command(name="ban")
async def ban(ctx,m:discord.Member,*,reason="Sin razón"):
    if not has_perm(ctx): return
    await ctx.guild.ban(m,reason=reason)
    await ctx.send(embed=bubble(f"🔨 {m.mention} baneado\n`{reason}`"))
@bot.command(name="kick")
async def kick(ctx,m:discord.Member,*,reason="Sin razón"):
    if not has_perm(ctx): return
    await m.kick(reason=reason)
    await ctx.send(embed=bubble(f"👢 {m.mention} kickeado\n`{reason}`"))
@bot.command(name="owner_add")
async def owner_add(ctx,user_id:str):
    if ctx.author.id!=MY_ID: return
    OWNER_IDS.add(int(user_id)); save_owners()
    await ctx.send(embed=bubble(f"( {user_id} ) added as owner"))
@bot.command(name="owner_remove")
async def owner_remove(ctx,user_id:str):
    if ctx.author.id!=MY_ID: return
    uid=int(user_id)
    if uid!=MY_ID and uid in OWNER_IDS:
        OWNER_IDS.remove(uid); save_owners()
        await ctx.send(embed=bubble(f"( {uid} )\ndeleted as owner"))
@bot.command(name="owner_list")
async def owner_list(ctx):
    if ctx.author.id!=MY_ID: return
    text = "\n".join(f"<@{u}> - ( {u} )" for u in OWNER_IDS)
    await ctx.send(embed=bubble(f"{text}"))
@bot.command(name="whitelist_add")
async def whitelist_add(ctx,user_id:str):
    if ctx.author.id!=MY_ID: return
    WHITELIST_IDS.add(int(user_id)); save_whitelist()
    await ctx.send(embed=bubble(f"( {user_id} )\nadded to whitelist"))
@bot.command(name="whitelist_remove")
async def whitelist_remove(ctx,user_id:str):
    if ctx.author.id!=MY_ID: return
    uid=int(user_id)
    if uid in WHITELIST_IDS:
        WHITELIST_IDS.remove(uid); save_whitelist()
        await ctx.send(embed=bubble(f"( {uid} )\nremoved from whitelist"))
@bot.command(name="whitelist_list")
async def whitelist_list(ctx):
    if ctx.author.id!=MY_ID: return
    if not WHITELIST_IDS:
        await ctx.send(embed=bubble("Whitelist vacía"))
    else:
        text = "\n".join(f"<@{u}> - ( {u} )" for u in WHITELIST_IDS)
        await ctx.send(embed=bubble(f"{text}"))

# --- PUBLICOS ---
@bot.command(name="avatar")
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = bubble(f"**Avatar de {member.name}**\n( {member.id} )")
    embed.set_image(url=member.display_avatar.url)
    await ctx.send(embed=embed)
@bot.command(name="userinfo")
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    created = discord.utils.format_dt(member.created_at, "R")
    joined = discord.utils.format_dt(member.joined_at, "R") if member.joined_at else "No"
    roles = ", ".join([r.mention for r in member.roles[1:][::-1][:8]]) or "Ninguno"
    desc = f"**User:** {member.mention} - ( {member.id} )\n**Creado:** {created}\n**Se unió:** {joined}\n**Roles [{len(member.roles)-1}]:** {roles}"
    embed = bubble(desc)
    embed.set_thumbnail(url=member.display_avatar.url)
    await ctx.send(embed=embed)
@bot.command(name="serverinfo")
async def serverinfo(ctx):
    g = ctx.guild
    desc = f"**Server:** {g.name}\n**ID:** ( {g.id} )\n**Owner:** <@{g.owner_id}> - ( {g.owner_id} )\n**Miembros:** {g.member_count}\n**Canales:** {len(g.channels)} | **Roles:** {len(g.roles)}\n**Boosts:** {g.premium_subscription_count}\n**Creado:** {discord.utils.format_dt(g.created_at, 'R')}"
    embed = bubble(desc)
    if g.icon:
        embed.set_thumbnail(url=g.icon.url)
    await ctx.send(embed=embed)

# --- BACKUP SYSTEM ---
@bot.command(name="backup")
async def backup(ctx, action: str = None):
    if not has_perm(ctx): return
    guild = ctx.guild
    path = f"{BACKUP_DIR}/{guild.id}.json"

    if action == "create":
        data = {
            "guild_name": guild.name,
            "roles": [],
            "categories": [],
            "channels": []
        }
        for r in reversed(guild.roles):
            if r.is_default() or r.managed or r.is_bot_managed(): continue
            data["roles"].append({
                "name": r.name, "color": r.color.value,
                "permissions": r.permissions.value, "hoist": r.hoist,
                "mentionable": r.mentionable
            })
        for cat in guild.categories:
            data["categories"].append({"name": cat.name, "position": cat.position})
        for ch in guild.channels:
            if isinstance(ch, discord.CategoryChannel): continue
            data["channels"].append({
                "name": ch.name, "type": str(ch.type),
                "category": ch.category.name if ch.category else None,
                "position": ch.position,
                "topic": getattr(ch, 'topic', None)
            })
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        await ctx.send(embed=bubble(f"✅ Backup creado: {len(data['roles'])} roles, {len(data['channels'])} canales guardados"), file=discord.File(path))

    elif action == "load":
        if not os.path.exists(path):
            await ctx.send(embed=bubble("❌ No hay backup, haz `_backup create` primero"))
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        await ctx.send(embed=bubble(f"♻️ Restaurando... {len(data['roles'])} roles y {len(data['channels'])} canales"))
        # Crear roles que no existan
        existing_roles = [r.name for r in guild.roles]
        for r in data["roles"]:
            if r["name"] not in existing_roles:
                try:
                    await guild.create_role(name=r["name"], colour=discord.Colour(r["color"]), permissions=discord.Permissions(r["permissions"]), hoist=r["hoist"], mentionable=r["mentionable"])
                    await asyncio.sleep(0.3)
                except: pass
        # Crear categorias
        existing_cats = {c.name: c for c in guild.categories}
        for c in data["categories"]:
            if c["name"] not in existing_cats:
                try:
                    new_cat = await guild.create_category(c["name"])
                    existing_cats[c["name"]] = new_cat
                    await asyncio.sleep(0.3)
                except: pass
        # Crear canales
        existing_channels = [ch.name for ch in guild.channels]
        for ch in data["channels"]:
            if ch["name"] in existing_channels: continue
            try:
                cat = existing_cats.get(ch["category"]) if ch["category"] else None
                if "text" in ch["type"]:
                    await guild.create_text_channel(ch["name"], category=cat)
                elif "voice" in ch["type"]:
                    await guild.create_voice_channel(ch["name"], category=cat)
                await asyncio.sleep(0.3)
            except: pass
        await ctx.send(embed=bubble("✅ Restauración completada"))
    else:
        await ctx.send(embed=bubble("Usa: `_backup create` para guardar y `_backup load` para restaurar"))

bot.run(TOKEN)