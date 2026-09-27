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

intents=discord.Intents.default()
intents.message_content=True
intents.members=True
intents.guilds=True
bot=commands.Bot(command_prefix="_",intents=intents,help_command=None)

def sync_owners():
    o=load_owners(); o.add(MY_ID); OWNER_IDS.clear(); OWNER_IDS.update(o); return o
def has_perm(ctx): return ctx.author.id in sync_owners()

LIMIT=3
TIME_WINDOW=10
cache=defaultdict(list)
def is_safe(uid, owner_id=None):
    return uid==MY_ID or uid in OWNER_IDS or uid in WHITELIST_IDS or uid==owner_id
def is_spam(uid):
    now=time.time()
    cache[uid]=[t for t in cache[uid] if now-t < TIME_WINDOW]
    cache[uid].append(now)
    return len(cache[uid])>LIMIT

async def auto_backup(guild):
    try:
        path = f"{BACKUP_DIR}/{guild.id}.json"
        data = {"guild_name": guild.name, "roles": [], "categories": [], "channels": []}
        for r in reversed(guild.roles):
            if r.is_default() or r.managed or r.is_bot_managed(): continue
            data["roles"].append({"name": r.name, "color": r.color.value, "permissions": r.permissions.value, "hoist": r.hoist, "mentionable": r.mentionable})
        for cat in guild.categories:
            data["categories"].append({"name": cat.name, "position": cat.position})
        for ch in guild.channels:
            if isinstance(ch, discord.CategoryChannel): continue
            data["channels"].append({"name": ch.name, "type": str(ch.type), "category": ch.category.name if ch.category else None, "position": ch.position})
        with open(path, "w", encoding="utf-8") as f: json.dump(data, f, indent=4)
    except: pass

async def nuke_punish(guild, uid, reason):
    if is_safe(uid, guild.owner_id): return
    try:
        if not hasattr(nuke_punish,"last_backup"): nuke_punish.last_backup=0
        if time.time()-nuke_punish.last_backup>30:
            await auto_backup(guild)
            nuke_punish.last_backup=time.time()
            try:
                u = await bot.fetch_user(MY_ID)
                await u.send(f"🚨 **BACKUP AUTO** `{guild.name}`", file=discord.File(f"{BACKUP_DIR}/{guild.id}.json"))
            except: pass
    except: pass
    try:
        m=guild.get_member(uid) or await guild.fetch_member(uid)
        await guild.ban(m, reason=f"ANTINUKE {reason}")
    except: pass

@bot.event
async def on_ready():
    print(f"Listo {bot.user}")

@bot.event
async def on_member_update(before,after):
    if after.bot or len(before.roles)==len(after.roles): return
    added=[r for r in after.roles if r not in before.roles]
    risky=[r for r in added if r.permissions.administrator or r.permissions.ban_members or r.permissions.kick_members or r.permissions.manage_roles or r.permissions.manage_guild or r.permissions.manage_channels]
    if not risky: return
    try:
        async for entry in after.guild.audit_logs(limit=3,action=discord.AuditLogAction.member_role_update):
            if (datetime.now(timezone.utc)-entry.created_at).total_seconds()>10: continue
            if entry.target.id!=after.id: continue
            if is_safe(entry.user.id, after.guild.owner_id): return
            try: await after.edit(roles=before.roles, reason="AntiRole")
            except: pass
            try: await after.guild.kick(entry.user, reason="AntiRole")
            except: pass
            return
    except: pass

@bot.event
async def on_member_ban(guild,user):
    try:
        async for e in guild.audit_logs(limit=1,action=discord.AuditLogAction.ban):
            if (datetime.now(timezone.utc)-e.created_at).total_seconds()>10: continue
            if is_safe(e.user.id, guild.owner_id): return
            if is_spam(e.user.id): await nuke_punish(guild,e.user.id,"Mass Ban")
    except: pass

@bot.event
async def on_member_remove(member):
    try:
        await asyncio.sleep(1)
        async for e in member.guild.audit_logs(limit=1,action=discord.AuditLogAction.kick):
            if (datetime.now(timezone.utc)-e.created_at).total_seconds()>10: continue
            if e.target.id!=member.id: continue
            if is_safe(e.user.id, member.guild.owner_id): return
            if is_spam(e.user.id): await nuke_punish(member.guild,e.user.id,"Mass Kick")
    except: pass

@bot.event
async def on_guild_channel_delete(channel):
    try:
        async for e in channel.guild.audit_logs(limit=1,action=discord.AuditLogAction.channel_delete):
            if (datetime.now(timezone.utc)-e.created_at).total_seconds()>10: continue
            if is_safe(e.user.id, channel.guild.owner_id): return
            if is_spam(e.user.id): await nuke_punish(channel.guild,e.user.id,"Channel Delete")
    except: pass

@bot.event
async def on_guild_channel_create(channel):
    try:
        async for e in channel.guild.audit_logs(limit=1,action=discord.AuditLogAction.channel_create):
            if (datetime.now(timezone.utc)-e.created_at).total_seconds()>10: continue
            if is_safe(e.user.id, channel.guild.owner_id): return
            if is_spam(e.user.id): await nuke_punish(channel.guild,e.user.id,"Channel Create")
    except: pass

@bot.event
async def on_guild_role_delete(role):
    try:
        async for e in role.guild.audit_logs(limit=1,action=discord.AuditLogAction.role_delete):
            if (datetime.now(timezone.utc)-e.created_at).total_seconds()>10: continue
            if is_safe(e.user.id, role.guild.owner_id): return
            if is_spam(e.user.id): await nuke_punish(role.guild,e.user.id,"Role Delete")
    except: pass

@bot.event
async def on_guild_role_create(role):
    try:
        async for e in role.guild.audit_logs(limit=1,action=discord.AuditLogAction.role_create):
            if (datetime.now(timezone.utc)-e.created_at).total_seconds()>10: continue
            if is_safe(e.user.id, role.guild.owner_id): return
            if is_spam(e.user.id): await nuke_punish(role.guild,e.user.id,"Role Create")
    except: pass

@bot.event
async def on_member_join(member):
    if not member.bot: return
    await asyncio.sleep(1.5)
    try:
        async for e in member.guild.audit_logs(limit=5,action=discord.AuditLogAction.bot_add):
            if (datetime.now(timezone.utc)-e.created_at).total_seconds()>15: continue
            if e.target.id!=member.id: continue
            if is_safe(e.user.id, member.guild.owner_id): return
            try: await member.ban(reason="Antibot")
            except: pass
            await nuke_punish(member.guild,e.user.id,"Bot Add")
            return
    except: pass

@bot.command(name="owner_list")
async def owner_list(ctx):
    if ctx.author.id!=MY_ID: return
    lines=[]
    for uid in OWNER_IDS:
        try:
            u = bot.get_user(uid) or await bot.fetch_user(uid)
            name = u.name if u else f"ID {uid}"
        except:
            name = f"ID {uid}"
        lines.append(f"{name} (`{uid}`)")
    body = "━━━━━━━━━━━━━━━━━━━━\n" + "\n".join(lines) + "\n━━━━━━━━━━━━━━━━━━━━" if lines else "━━━━━━━━━━━━━━━━━━━━\n`Vacío`\n━━━━━━━━━━━━━━━━━━━━"
    e = discord.Embed(description=f"**Bot Owners List ({len(OWNER_IDS)})**\n\n{body}\n\nRequested by {ctx.author.name}", color=0x2b2d31)
    if ctx.guild.icon:
        e.set_thumbnail(url=ctx.guild.icon.url)
    await ctx.send(embed=e)

@bot.command(name="whitelist_list")
async def whitelist_list(ctx):
    if ctx.author.id!=MY_ID: return
    if not WHITELIST_IDS:
        body = "━━━━━━━━━━━━━━━━━━━━\n`Vacía`\n━━━━━━━━━━━━━━━━━━━━"
    else:
        lines=[]
        for uid in WHITELIST_IDS:
            try:
                u = bot.get_user(uid) or await bot.fetch_user(uid)
                name = u.name if u else f"ID {uid}"
            except:
                name = f"ID {uid}"
            lines.append(f"{name} (`{uid}`)")
        body = "━━━━━━━━━━━━━━━━━━━━\n" + "\n".join(lines) + "\n━━━━━━━━━━━━━━━━━━━━"
    e = discord.Embed(description=f"**Whitelist List ({len(WHITELIST_IDS)})**\n\n{body}\n\nRequested by {ctx.author.name}", color=0x2b2d31)
    if ctx.guild.icon:
        e.set_thumbnail(url=ctx.guild.icon.url)
    await ctx.send(embed=e)

@bot.command(name="owner_add")
async def owner_add(ctx, user_id: str):
    if ctx.author.id!= MY_ID: return
    try:
        uid = int(user_id)
        u = bot.get_user(uid) or await bot.fetch_user(uid)
        name = u.name if u else user_id
    except:
        uid = int(user_id)
        name = user_id
    OWNER_IDS.add(uid)
    save_owners()
    body = f"━━━━━━━━━━━━━━━━━━━━\n{name} (`{uid}`)\n━━━━━━━━━━━━━━━━━━━━"
    e = discord.Embed(description=f"**Owner Added**\n\n{body}", color=0x2b2d31)
    if ctx.guild.icon:
        e.set_thumbnail(url=ctx.guild.icon.url)
    await ctx.send(embed=e)

# ===== WHITELIST_ADD CON FAKE PARA OTROS =====
@bot.command(name="whitelist_add")
async def whitelist_add(ctx, user_id: str = None):
    if ctx.author.id!= MY_ID:
        e = discord.Embed(color=0x2b2d31)
        e.set_author(name="Command: whitelist_add", icon_url=bot.user.display_avatar.url if bot.user.display_avatar else None)
        e.description = "Adds a user to the pings or roles whitelist\n\n**Syntax:** `,whitelist_add | pings, roles y all.`\n**Example:** `,whitelist_add (id) R, P o All`"
        await ctx.send(embed=e)
        return
    if not user_id:
        return await ctx.send("Pon id: `_whitelist_add 123`")
    try:
        uid = int(user_id)
        u = bot.get_user(uid) or await bot.fetch_user(uid)
        name = u.name if u else user_id
    except:
        try:
            uid = int(user_id)
            name = user_id
        except:
            return await ctx.send("ID inválido")
    WHITELIST_IDS.add(uid)
    save_whitelist()
    body = f"━━━━━━━━━━━━━━━━━━━━\n{name} (`{uid}`)\n━━━━━━━━━━━━━━━━━━━━"
    e = discord.Embed(description=f"**Whitelist Added**\n\n{body}", color=0x2b2d31)
    if ctx.guild.icon:
        e.set_thumbnail(url=ctx.guild.icon.url)
    await ctx.send(embed=e)

@bot.command(name="userinfo")
async def userinfo(ctx, member: discord.Member = None):
    m = member or ctx.author
    created = discord.utils.format_dt(m.created_at, "F")
    ago_c = discord.utils.format_dt(m.created_at, "R")
    joined = discord.utils.format_dt(m.joined_at, "F") if m.joined_at else "Desconocido"
    ago_j = discord.utils.format_dt(m.joined_at, "R") if m.joined_at else ""
    roles = m.roles[1:][::-1]
    roles_txt = " ".join([r.mention for r in roles[:10]]) if roles else "`Sin roles`"
    if len(roles) > 10:
        roles_txt += f" `+{len(roles)-10} más`"
    body = f"""━━━━━━━━━━━━━━━━━━━━
👤 **Usuario**
{m.mention}
`{m.id}`

🏷️ **Nick**
{m.display_name}

🤖 **Bot**
{"Si" if m.bot else "No"}

📅 **Cuenta creada**
{created}
{ago_c}

📥 **Se unió**
{joined}
{ago_j}

🎭 **Roles [{len(roles)}]**
{roles_txt}
━━━━━━━━━━━━━━━━━━━━"""
    e = discord.Embed(description=f"**Información de {m.name}**\n\n{body}\n\nRequested by {ctx.author.name}", color=0x2b2d31)
    e.set_thumbnail(url=m.display_avatar.url)
    await ctx.send(embed=e)

@bot.command(name="serverinfo")
async def serverinfo(ctx):
    g = ctx.guild
    owner = g.owner or await bot.fetch_user(g.owner_id)
    created = discord.utils.format_dt(g.created_at, "F")
    ago = discord.utils.format_dt(g.created_at, "R")
    body = f"""━━━━━━━━━━━━━━━━━━━━
👑 **Owner**
{owner.mention}
`{owner.id}`

🆔 **ID**
`{g.id}`

📅 **Creado**
{created}
{ago}

👥 **Miembros**
Total: {g.member_count}
Humanos: {len([m for m in g.members if not m.bot])}
Bots: {len([m for m in g.members if m.bot])}

📊 **Canales**
Texto: {len(g.text_channels)}
Voz: {len(g.voice_channels)}

✨ **Extras**
Roles: {len(g.roles)}
Boosts: {g.premium_subscription_count}
━━━━━━━━━━━━━━━━━━━━"""
    e = discord.Embed(description=f"**{g.name}**\n\n{body}\n\nRequested by {ctx.author.name}", color=0x2b2d31)
    if g.icon:
        e.set_thumbnail(url=g.icon.url)
    await ctx.send(embed=e)

@bot.command(name="estado")
async def estado(ctx):
    if not has_perm(ctx): return
    g = ctx.guild
    body = f"""━━━━━━━━━━━━━━━━━━━━
🛡️ **AntiNuke** - 🟢 ACTIVO
🤖 **AntiBot** - 🟢 ACTIVO
🔨 **AntiBan/Kick** - 🟢 ACTIVO
📦 **Backup Auto** - 1 DM cada 30s
📊 **Servers:** {len(bot.guilds)} | **Ping:** {round(bot.latency*1000)}ms
━━━━━━━━━━━━━━━━━━━━"""
    e = discord.Embed(description=f"**Estado de {g.name}**\n\n{body}\n\nRequested by {ctx.author.name}", color=0x2b2d31)
    if g.icon:
        e.set_thumbnail(url=g.icon.url)
    await ctx.send(embed=e)

@bot.command(name="avatar")
async def avatar(ctx, member: discord.Member = None):
    m = member or ctx.author
    body = f"━━━━━━━━━━━━━━━━━━━━\n👤 {m.mention}\n`{m.id}`\n[Link]({m.display_avatar.url})\n━━━━━━━━━━━━━━━━━━━━"
    e = discord.Embed(description=f"**Avatar de {m.name}**\n\n{body}\n\nRequested by {ctx.author.name}", color=0x2b2d31)
    e.set_thumbnail(url=m.display_avatar.url)
    e.set_image(url=m.display_avatar.url)
    await ctx.send(embed=e)

@bot.command(name="ban")
async def ban(ctx,m:discord.Member,*,reason="Sin razón"):
    if not has_perm(ctx): return
    await ctx.guild.ban(m,reason=reason)
    body = f"━━━━━━━━━━━━━━━━━━━━\n{m.name} (`{m.id}`)\nReason: `{reason}`\n━━━━━━━━━━━━━━━━━━━━"
    e = discord.Embed(description=f"**Member Banned**\n\n{body}\n\nRequested by {ctx.author.name}", color=0x2b2d31)
    if ctx.guild.icon:
        e.set_thumbnail(url=ctx.guild.icon.url)
    await ctx.send(embed=e)

@bot.command(name="kick")
async def kick(ctx,m:discord.Member,*,reason="Sin razón"):
    if not has_perm(ctx): return
    await m.kick(reason=reason)
    body = f"━━━━━━━━━━━━━━━━━━━━\n{m.name} (`{m.id}`)\nReason: `{reason}`\n━━━━━━━━━━━━━━━━━━━━"
    e = discord.Embed(description=f"**Member Kicked**\n\n{body}\n\nRequested by {ctx.author.name}", color=0x2b2d31)
    if ctx.guild.icon:
        e.set_thumbnail(url=ctx.guild.icon.url)
    await ctx.send(embed=e)

@bot.command(name="owner_remove")
async def owner_remove(ctx,user_id:str):
    if ctx.author.id!=MY_ID: return
    uid=int(user_id)
    if uid!=MY_ID and uid in OWNER_IDS:
        OWNER_IDS.remove(uid); save_owners()
        body = f"━━━━━━━━━━━━━━━━━━━━\n`{uid}` removed\n━━━━━━━━━━━━━━━━━━━━"
        e = discord.Embed(description=f"**Owner Removed**\n\n{body}\n\nRequested by {ctx.author.name}", color=0x2b2d31)
        if ctx.guild.icon: e.set_thumbnail(url=ctx.guild.icon.url)
        await ctx.send(embed=e)

@bot.command(name="whitelist_remove")
async def whitelist_remove(ctx,user_id:str):
    if ctx.author.id!=MY_ID: return
    uid=int(user_id)
    if uid in WHITELIST_IDS:
        WHITELIST_IDS.remove(uid); save_whitelist()
        body = f"━━━━━━━━━━━━━━━━━━━━\n`{uid}` removed\n━━━━━━━━━━━━━━━━━━━━"
        e = discord.Embed(description=f"**Whitelist Removed**\n\n{body}\n\nRequested by {ctx.author.name}", color=0x2b2d31)
        if ctx.guild.icon: e.set_thumbnail(url=ctx.guild.icon.url)
        await ctx.send(embed=e)

@bot.command(name="backup")
async def backup(ctx, action: str = None):
    if not has_perm(ctx): return
    guild = ctx.guild
    path = f"{BACKUP_DIR}/{guild.id}.json"
    if action == "create":
        await auto_backup(guild)
        with open(path,"r",encoding="utf-8") as f: data=json.load(f)
        body = f"━━━━━━━━━━━━━━━━━━━━\n• Roles • ( `{len(data['roles'])}` )\n• Channels • ( `{len(data['channels'])}` )\n━━━━━━━━━━━━━━━━━━━━"
        e = discord.Embed(description=f"**Backup Created**\n\n{body}\n\nRequested by {ctx.author.name}", color=0x2b2d31)
        if guild.icon: e.set_thumbnail(url=guild.icon.url)
        await ctx.send(embed=e, file=discord.File(path))
    elif action == "load":
        if not os.path.exists(path):
            e = discord.Embed(description=f"**Error**\n\n━━━━━━━━━━━━━━━━━━━━\n`No hay backup`\n━━━━━━━━━━━━━━━━━━━━\n\nRequested by {ctx.author.name}", color=0x2b2d31)
            await ctx.send(embed=e)
            return
        with open(path,"r",encoding="utf-8") as f: data=json.load(f)
        e = discord.Embed(description=f"**Restoring**\n\n━━━━━━━━━━━━━━━━━━━━\n• {len(data['roles'])} roles\n━━━━━━━━━━━━━━━━━━━━\n\nRequested by {ctx.author.name}", color=0x2b2d31)
        if guild.icon: e.set_thumbnail(url=guild.icon.url)
        await ctx.send(embed=e)
        existing=[r.name for r in guild.roles]
        for r in data["roles"]:
            if r["name"] not in existing:
                try:
                    await guild.create_role(name=r["name"], colour=discord.Colour(r["color"]), permissions=discord.Permissions(r["permissions"]), hoist=r["hoist"], mentionable=r["mentionable"])
                    await asyncio.sleep(0.3)
                except: pass
        e = discord.Embed(description=f"**Restored**\n\n━━━━━━━━━━━━━━━━━━━━\n`Completado`\n━━━━━━━━━━━━━━━━━━━━\n\nRequested by {ctx.author.name}", color=0x2b2d31)
        if guild.icon: e.set_thumbnail(url=guild.icon.url)
        await ctx.send(embed=e)
    else:
        body = "━━━━━━━━━━━━━━━━━━━━\n• _backup create\n• _backup load\n━━━━━━━━━━━━━━━━━━━━"
        e = discord.Embed(description=f"**Backup Help**\n\n{body}\n\nRequested by {ctx.author.name}", color=0x2b2d31)
        if guild.icon: e.set_thumbnail(url=guild.icon.url)
        await ctx.send(embed=e)

bot.run(TOKEN)