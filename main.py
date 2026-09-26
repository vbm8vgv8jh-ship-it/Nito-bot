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

# ===== DISEÑO EXACTO DE TU FOTO =====
def v2_list_embed(title, count, lines_str, author_obj, thumb_url=None):
    full_title = f"{title} ({count})" if count is not None else title
    desc = f"**{full_title}**\n\n━━━━━━━━━━━━━━━━━━━━\n{lines_str}\n━━━━━━━━━━━━━━━━━━━━\n\nRequested by {author_obj.name}"
    e = discord.Embed(description=desc, color=0x2b2d31)
    if thumb_url:
        e.set_thumbnail(url=thumb_url)
    else:
        e.set_thumbnail(url=author_obj.display_avatar.url)
    return e

def sync_owners():
    o=load_owners(); o.add(MY_ID); OWNER_IDS.clear(); OWNER_IDS.update(o); return o
def has_perm(ctx): return ctx.author.id in sync_owners()

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
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        try:
            u = await bot.fetch_user(MY_ID)
            await u.send(f"🚨 **BACKUP AUTO** `{guild.name}`", file=discord.File(path))
        except: pass
    except Exception as e:
        print(e)

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

async def nuke_punish(guild, uid, reason):
    if is_safe(uid, guild.owner_id): return
    try:
        if not hasattr(nuke_punish,"last_backup"): nuke_punish.last_backup=0
        if time.time()-nuke_punish.last_backup>30:
            await auto_backup(guild)
            nuke_punish.last_backup=time.time()
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
    risky=[r for r in added if r.permissions.administrator or r.permissions.ban_members or r.permissions.kick_members or r.permissions.manage_roles or r.permissions.manage_guild]
    if not risky: return
    try:
        async for entry in after.guild.audit_logs(limit=3,action=discord.AuditLogAction.member_role_update):
            if (datetime.now(timezone.utc)-entry.created_at).total_seconds()>10: continue
            if entry.target.id!=after.id: continue
            if is_safe(entry.user.id, after.guild.owner_id): return
            try: await after.edit(roles=before.roles)
            except: pass
            try: await after.guild.kick(entry.user, reason="AntiRole")
            except: pass
            return
    except: pass

@bot.event
async def on_member_ban(guild,user):
    try:
        async for entry in guild.audit_logs(limit=1,action=discord.AuditLogAction.ban):
            if (datetime.now(timezone.utc)-entry.created_at).total_seconds()>10: continue
            if is_safe(entry.user.id, guild.owner_id): return
            if is_spam(entry.user.id): await nuke_punish(guild,entry.user.id,"Mass Ban")
    except: pass

@bot.event
async def on_member_remove(member):
    try:
        await asyncio.sleep(1)
        async for entry in member.guild.audit_logs(limit=1,action=discord.AuditLogAction.kick):
            if (datetime.now(timezone.utc)-entry.created_at).total_seconds()>10: continue
            if entry.target.id!=member.id: continue
            if is_safe(entry.user.id, member.guild.owner_id): return
            if is_spam(entry.user.id): await nuke_punish(member.guild,entry.user.id,"Mass Kick")
    except: pass

@bot.event
async def on_guild_channel_delete(channel):
    try:
        async for entry in channel.guild.audit_logs(limit=1,action=discord.AuditLogAction.channel_delete):
            if (datetime.now(timezone.utc)-entry.created_at).total_seconds()>10: continue
            if is_safe(entry.user.id, channel.guild.owner_id): return
            if is_spam(entry.user.id): await nuke_punish(channel.guild,entry.user.id,"Channel Delete")
    except: pass

@bot.event
async def on_guild_channel_create(channel):
    try:
        async for entry in channel.guild.audit_logs(limit=1,action=discord.AuditLogAction.channel_create):
            if (datetime.now(timezone.utc)-entry.created_at).total_seconds()>10: continue
            if is_safe(entry.user.id, channel.guild.owner_id): return
            if is_spam(entry.user.id): await nuke_punish(channel.guild,entry.user.id,"Channel Create")
    except: pass

@bot.event
async def on_guild_role_delete(role):
    try:
        async for entry in role.guild.audit_logs(limit=1,action=discord.AuditLogAction.role_delete):
            if (datetime.now(timezone.utc)-entry.created_at).total_seconds()>10: continue
            if is_safe(entry.user.id, role.guild.owner_id): return
            if is_spam(entry.user.id): await nuke_punish(role.guild,entry.user.id,"Role Delete")
    except: pass

@bot.event
async def on_guild_role_create(role):
    try:
        async for entry in role.guild.audit_logs(limit=1,action=discord.AuditLogAction.role_create):
            if (datetime.now(timezone.utc)-entry.created_at).total_seconds()>10: continue
            if is_safe(entry.user.id, role.guild.owner_id): return
            if is_spam(entry.user.id): await nuke_punish(role.guild,entry.user.id,"Role Create")
    except: pass

@bot.event
async def on_member_join(member):
    if not member.bot: return
    await asyncio.sleep(1.5)
    try:
        async for entry in member.guild.audit_logs(limit=5,action=discord.AuditLogAction.bot_add):
            if (datetime.now(timezone.utc)-entry.created_at).total_seconds()>15: continue
            if entry.target.id!=member.id: continue
            if is_safe(entry.user.id, member.guild.owner_id): return
            try: await member.ban(reason="Antibot")
            except: pass
            await nuke_punish(member.guild,entry.user.id,"Bot Add")
            return
    except: pass

# ===== COMANDOS CON DISEÑO DE TU FOTO =====
@bot.command(name="owner_list")
async def owner_list(ctx):
    if ctx.author.id!=MY_ID: return
    lines=[]
    for uid in OWNER_IDS:
        try:
            u=bot.get_user(uid) or await bot.fetch_user(uid)
            name=u.name if u else "unknown"
        except: name="unknown"
        lines.append(f"• {name} • ( `{uid}` )")
    text="\n".join(lines) if lines else "`Vacío`"
    await ctx.send(embed=v2_list_embed("Bot Owners List", len(OWNER_IDS), text, ctx.author))

@bot.command(name="whitelist_list")
async def whitelist_list(ctx):
    if ctx.author.id!=MY_ID: return
    if not WHITELIST_IDS:
        text="`Vacía`"
    else:
        lines=[]
        for uid in WHITELIST_IDS:
            try:
                u=bot.get_user(uid) or await bot.fetch_user(uid)
                name=u.name if u else "unknown"
            except: name="unknown"
            lines.append(f"• {name} • ( `{uid}` )")
        text="\n".join(lines)
    await ctx.send(embed=v2_list_embed("Whitelist List", len(WHITELIST_IDS), text, ctx.author))

@bot.command(name="owner_add")
async def owner_add(ctx,user_id:str):
    if ctx.author.id!=MY_ID: return
    OWNER_IDS.add(int(user_id)); save_owners()
    await ctx.send(embed=v2_list_embed("Owner Added", None, f"• {user_id} • ( `{user_id}` )", ctx.author))

@bot.command(name="owner_remove")
async def owner_remove(ctx,user_id:str):
    if ctx.author.id!=MY_ID: return
    uid=int(user_id)
    if uid!=MY_ID and uid in OWNER_IDS:
        OWNER_IDS.remove(uid); save_owners()
        await ctx.send(embed=v2_list_embed("Owner Removed", None, f"• {uid} • ( `removed` )", ctx.author))

@bot.command(name="whitelist_add")
async def whitelist_add(ctx,user_id:str):
    if ctx.author.id!=MY_ID: return
    WHITELIST_IDS.add(int(user_id)); save_whitelist()
    await ctx.send(embed=v2_list_embed("Whitelist Added", None, f"• {user_id} • ( `added` )", ctx.author))

@bot.command(name="whitelist_remove")
async def whitelist_remove(ctx,user_id:str):
    if ctx.author.id!=MY_ID: return
    uid=int(user_id)
    if uid in WHITELIST_IDS:
        WHITELIST_IDS.remove(uid); save_whitelist()
        await ctx.send(embed=v2_list_embed("Whitelist Removed", None, f"• {uid} • ( `removed` )", ctx.author))

@bot.command(name="estado")
async def estado(ctx):
    if not has_perm(ctx): return
    g=ctx.guild
    lines=f"• AntiNuke • ( `ACTIVO` )\n• AntiBot • ( `ACTIVO` )\n• AntiBan • ( `ACTIVO` )\n• Servers • ( `{len(bot.guilds)}` )\n• Ping • ( `{round(bot.latency*1000)}ms` )"
    thumb = g.icon.url if g.icon else None
    await ctx.send(embed=v2_list_embed(f"Estado de {g.name}", None, lines, ctx.author, thumb_url=thumb))

@bot.command(name="serverinfo")
async def serverinfo(ctx):
    g=ctx.guild
    owner=g.owner or await bot.fetch_user(g.owner_id)
    lines=f"• Name • ( `{g.name}` )\n• ID • ( `{g.id}` )\n• Owner • ( `{owner.name}` )\n• Members • ( `{g.member_count}` )\n• Channels • ( `{len(g.channels)}` )\n• Roles • ( `{len(g.roles)}` )\n• Boosts • ( `{g.premium_subscription_count}` )"
    thumb = g.icon.url if g.icon else None
    await ctx.send(embed=v2_list_embed("Server Info", None, lines, ctx.author, thumb_url=thumb))

@bot.command(name="userinfo")
async def userinfo(ctx, member: discord.Member=None):
    m=member or ctx.author
    lines=f"• User • ( `{m.name}` )\n• ID • ( `{m.id}` )\n• Nick • ( `{m.display_name}` )\n• Top Rol • ( `{m.top_role.name}` )\n• Joined • ( `<t:{int(m.joined_at.timestamp())}:R>` )\n• Created • ( `<t:{int(m.created_at.timestamp())}:R>` )"
    await ctx.send(embed=v2_list_embed("User Info", None, lines, ctx.author, thumb_url=m.display_avatar.url))

@bot.command(name="avatar")
async def avatar(ctx, member: discord.Member=None):
    m=member or ctx.author
    e=v2_list_embed(f"Avatar de {m.name}", None, f"• {m.name} • ( `{m.id}` )", ctx.author, thumb_url=m.display_avatar.url)
    e.set_image(url=m.display_avatar.url)
    await ctx.send(embed=e)

@bot.command(name="ban")
async def ban(ctx,m:discord.Member,*,reason="Sin razón"):
    if not has_perm(ctx): return
    await ctx.guild.ban(m,reason=reason)
    await ctx.send(embed=v2_list_embed("Member Banned", None, f"• {m.name} • ( `{m.id}` )\n• Reason • ( `{reason}` )", ctx.author))

@bot.command(name="kick")
async def kick(ctx,m:discord.Member,*,reason="Sin razón"):
    if not has_perm(ctx): return
    await m.kick(reason=reason)
    await ctx.send(embed=v2_list_embed("Member Kicked", None, f"• {m.name} • ( `{m.id}` )\n• Reason • ( `{reason}` )", ctx.author))

@bot.command(name="backup")
async def backup(ctx, action: str=None):
    if not has_perm(ctx): return
    guild=ctx.guild
    path=f"{BACKUP_DIR}/{guild.id}.json"
    if action=="create":
        data={"guild_name": guild.name, "roles": [], "categories": [], "channels": []}
        for r in reversed(guild.roles):
            if r.is_default() or r.managed or r.is_bot_managed(): continue
            data["roles"].append({"name": r.name, "color": r.color.value, "permissions": r.permissions.value, "hoist": r.hoist, "mentionable": r.mentionable})
        for cat in guild.categories:
            data["categories"].append({"name": cat.name, "position": cat.position})
        for ch in guild.channels:
            if isinstance(ch, discord.CategoryChannel): continue
            data["channels"].append({"name": ch.name, "type": str(ch.type), "category": ch.category.name if ch.category else None, "position": ch.position})
        with open(path,"w",encoding="utf-8") as f: json.dump(data,f,indent=4)
        await ctx.send(embed=v2_list_embed("Backup Created", None, f"• Roles • ( `{len(data['roles'])}` )\n• Channels • ( `{len(data['channels'])}` )", ctx.author), file=discord.File(path))
    elif action=="load":
        if not os.path.exists(path):
            await ctx.send(embed=v2_list_embed("Error", None, f"• Backup • ( `No existe` )", ctx.author))
            return
        with open(path,"r",encoding="utf-8") as f: data=json.load(f)
        await ctx.send(embed=v2_list_embed("Restoring", None, f"• Roles • ( `{len(data['roles'])}` )\n• Channels • ( `{len(data['channels'])}` )", ctx.author))
        existing_roles=[r.name for r in guild.roles]
        for r in data["roles"]:
            if r["name"] not in existing_roles:
                try:
                    await guild.create_role(name=r["name"], colour=discord.Colour(r["color"]), permissions=discord.Permissions(r["permissions"]), hoist=r["hoist"], mentionable=r["mentionable"])
                    await asyncio.sleep(0.3)
                except: pass
        await ctx.send(embed=v2_list_embed("Restored", None, f"• Status • ( `Completado` )", ctx.author))
    else:
        await ctx.send(embed=v2_list_embed("Backup Help", None, f"• _backup create • ( `guardar` )\n• _backup load • ( `restaurar` )", ctx.author))

bot.run(TOKEN)