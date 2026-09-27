import os, json, discord, asyncio, time
from discord.ext import commands
from datetime import datetime, timezone
from collections import defaultdict

TOKEN = os.getenv("DISCORD_BOT_TOKEN") or os.getenv("TOKEN") or os.getenv("DISCORD_TOKEN")
MY_ID = 1310357536087740450
OWNER_FILE="owners.json"
WHITELIST_PINGS_FILE="whitelist_pings.json"
WHITELIST_ROLES_FILE="whitelist_roles.json"
ROLE_IMMUNE_FILE="role_immune.json"
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
def load_set(path):
    if os.path.exists(path):
        try:
            with open(path,"r") as f: return set(map(int,json.load(f)))
        except: return set()
    return set()
def save_set(path, data):
    with open(path,"w") as f: json.dump(list(data), f)

OWNER_IDS=load_owners(); OWNER_IDS.add(MY_ID)
WHITELIST_PINGS=load_set(WHITELIST_PINGS_FILE)
WHITELIST_ROLES=load_set(WHITELIST_ROLES_FILE)
IMMUNE_ROLES=load_set(ROLE_IMMUNE_FILE)

intents=discord.Intents.default()
intents.message_content=True
intents.members=True
intents.guilds=True
bot=commands.Bot(command_prefix="_",intents=intents,help_command=None)

def sync_owners():
    o=load_owners(); o.add(MY_ID); OWNER_IDS.clear(); OWNER_IDS.update(o); return o
def has_perm(ctx): return ctx.author.id in sync_owners()
def has_immune_role(guild, uid):
    try:
        m = guild.get_member(uid)
        if not m: return False
        return any(r.id in IMMUNE_ROLES for r in m.roles)
    except: return False
def is_safe(uid, owner_id=None):
    return uid==MY_ID or uid in OWNER_IDS or uid==owner_id
def is_role_allowed(guild, uid, owner_id=None):
    if is_safe(uid, owner_id): return True
    if uid in WHITELIST_ROLES: return True
    if has_immune_role(guild, uid): return True
    return False
def is_pings_allowed(guild, uid, owner_id=None):
    if is_safe(uid, owner_id): return True
    if uid in WHITELIST_PINGS: return True
    if has_immune_role(guild, uid): return True
    return False

LIMIT=3
TIME_WINDOW=10
cache=defaultdict(list)
pings_warns=defaultdict(int)
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
    if has_immune_role(guild, uid): return
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
        if has_immune_role(guild, uid): return
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
            if is_role_allowed(after.guild, entry.user.id, after.guild.owner_id): return
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
            if has_immune_role(guild, e.user.id): return
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
            if has_immune_role(member.guild, e.user.id): return
            if is_spam(e.user.id): await nuke_punish(member.guild,e.user.id,"Mass Kick")
    except: pass

@bot.event
async def on_guild_channel_delete(channel):
    try:
        async for e in channel.guild.audit_logs(limit=1,action=discord.AuditLogAction.channel_delete):
            if (datetime.now(timezone.utc)-e.created_at).total_seconds()>10: continue
            if is_safe(e.user.id, channel.guild.owner_id): return
            if has_immune_role(channel.guild, e.user.id): return
            if is_spam(e.user.id): await nuke_punish(channel.guild,e.user.id,"Channel Delete")
    except: pass

@bot.event
async def on_guild_channel_create(channel):
    try:
        async for e in channel.guild.audit_logs(limit=1,action=discord.AuditLogAction.channel_create):
            if (datetime.now(timezone.utc)-e.created_at).total_seconds()>10: continue
            if is_safe(e.user.id, channel.guild.owner_id): return
            if has_immune_role(channel.guild, e.user.id): return
            if is_spam(e.user.id): await nuke_punish(channel.guild,e.user.id,"Channel Create")
    except: pass

@bot.event
async def on_guild_role_delete(role):
    try:
        async for e in role.guild.audit_logs(limit=1,action=discord.AuditLogAction.role_delete):
            if (datetime.now(timezone.utc)-e.created_at).total_seconds()>10: continue
            if is_safe(e.user.id, role.guild.owner_id): return
            if has_immune_role(role.guild, e.user.id): return
            if is_spam(e.user.id): await nuke_punish(role.guild,e.user.id,"Role Delete")
    except: pass

@bot.event
async def on_guild_role_create(role):
    try:
        async for e in role.guild.audit_logs(limit=1,action=discord.AuditLogAction.role_create):
            if (datetime.now(timezone.utc)-e.created_at).total_seconds()>10: continue
            if is_safe(e.user.id, role.guild.owner_id): return
            if has_immune_role(role.guild, e.user.id): return
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
            if has_immune_role(member.guild, e.user.id): return
            try: await member.ban(reason="Antibot")
            except: pass
            await nuke_punish(member.guild,e.user.id,"Bot Add")
            return
    except: pass

LINK_WORDS = ["http://", "https://", "discord.gg/", "discord.com/invite/", "discordapp.com/invite/"]

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        await bot.process_commands(message)
        return
    is_ping_attempt = "@everyone" in message.content or "@here" in message.content or message.mention_everyone
    is_link_attempt = any(w in message.content.lower() for w in LINK_WORDS)
    if (is_ping_attempt or is_link_attempt) and not is_pings_allowed(message.guild, message.author.id, message.guild.owner_id):
        pings_warns[message.author.id] += 1
        try: await message.delete()
        except: pass
        if pings_warns[message.author.id] == 1:
            try: await message.channel.send(f"⚠️ {message.author.mention} 1ra advertencia: sin `whitelist pings/rol inmune` no puedes usar `@everyone/@here` ni links. 2da = kick.", delete_after=7)
            except: pass
        else:
            try:
                if has_immune_role(message.guild, message.author.id):
                    pings_warns.pop(message.author.id, None)
                    return
                await message.guild.kick(message.author, reason="2da vez everyone/here/links sin whitelist")
                await message.channel.send(f"🔨 {message.author.mention} kickeado (2da vez everyone/links sin whitelist)", delete_after=7)
                pings_warns.pop(message.author.id, None)
            except:
                try: await message.channel.send(f"🚫 No pude kickear a {message.author.mention}", delete_after=7)
                except: pass
        return
    await bot.process_commands(message)

# ===== COMANDOS DE ROLES =====

@bot.command(name="r_add")
async def r_add(ctx, user_id: str = None, *, role_name: str = None):
    if not has_perm(ctx): return
    if not user_id or not role_name:
        return await ctx.send("**Uso:** `_r_add (id usuario) (nombre del rol)`\nEj: `_r_add 123456789 Admin`")
    try:
        uid = int(user_id)
        member = ctx.guild.get_member(uid) or await ctx.guild.fetch_member(uid)
    except:
        return await ctx.send(f"❌ No encontré al usuario `{user_id}`")
    role = discord.utils.find(lambda r: r.name.lower() == role_name.lower(), ctx.guild.roles)
    if not role:
        try: role = ctx.guild.get_role(int(role_name))
        except: pass
    if not role:
        return await ctx.send(f"❌ No encontré el rol `{role_name}`")
    try:
        await member.add_roles(role, reason=f"r_add por {ctx.author}")
        e = discord.Embed(description=f"**Rol Agregado**\n\n━━━━━━━━━━━━━━━━━━━━\n👤 {member.mention} (`{member.id}`)\n🎭 `{role.name}`\n━━━━━━━━━━━━━━━━━━━━", color=0x2b2d31)
        await ctx.send(embed=e)
    except discord.Forbidden:
        await ctx.send("❌ No tengo permisos, pon mi rol arriba del que quieres dar.")
    except Exception as ex:
        await ctx.send(f"❌ Error: {ex}")

@bot.command(name="r_remove")
async def r_remove(ctx, user_id: str = None, *, role_name: str = None):
    if not has_perm(ctx): return
    if not user_id or not role_name:
        return await ctx.send("**Uso:** `_r_remove (id usuario) (nombre del rol)`\nEj: `_r_remove 123456789 Admin`")
    try:
        uid = int(user_id)
        member = ctx.guild.get_member(uid) or await ctx.guild.fetch_member(uid)
    except:
        return await ctx.send(f"❌ No encontré al usuario `{user_id}`")
    role = discord.utils.find(lambda r: r.name.lower() == role_name.lower(), ctx.guild.roles)
    if not role:
        try: role = ctx.guild.get_role(int(role_name))
        except: pass
    if not role:
        return await ctx.send(f"❌ No encontré el rol `{role_name}`")
    try:
        await member.remove_roles(role, reason=f"r_remove por {ctx.author}")
        e = discord.Embed(description=f"**Rol Removido**\n\n━━━━━━━━━━━━━━━━━━━━\n👤 {member.mention} (`{member.id}`)\n🎭 `{role.name}`\n━━━━━━━━━━━━━━━━━━━━", color=0x2b2d31)
        await ctx.send(embed=e)
    except discord.Forbidden:
        await ctx.send("❌ No tengo permisos, pon mi rol arriba.")
    except Exception as ex:
        await ctx.send(f"❌ Error: {ex}")

@bot.command(name="role_inmune_add")
async def role_inmune_add(ctx, *, role_name: str = None):
    if not has_perm(ctx): return
    if not role_name: return await ctx.send("**Uso:** `_role_inmune_add nombre del rol`\nEj: `_role_inmune_add Staff`")
    role = discord.utils.find(lambda r: r.name.lower() == role_name.lower(), ctx.guild.roles)
    if not role:
        try: role = ctx.guild.get_role(int(role_name))
        except: pass
    if not role: return await ctx.send(f"❌ No encontré el rol `{role_name}`")
    IMMUNE_ROLES.add(role.id)
    save_set(ROLE_IMMUNE_FILE, IMMUNE_ROLES)
    e = discord.Embed(description=f"**Rol Inmune Agregado**\n\n━━━━━━━━━━━━━━━━━━━━\n🎭 {role.mention} (`{role.id}`)\nAhora es inmune a ban/kick y puede dar roles y pings.\n━━━━━━━━━━━━━━━━━━━━", color=0x2b2d31)
    await ctx.send(embed=e)

@bot.command(name="role_inmune_remove")
async def role_inmune_remove(ctx, *, role_name: str = None):
    if not has_perm(ctx): return
    if not role_name: return await ctx.send("**Uso:** `_role_inmune_remove nombre del rol`")
    role = discord.utils.find(lambda r: r.name.lower() == role_name.lower(), ctx.guild.roles)
    if not role:
        try: role = ctx.guild.get_role(int(role_name))
        except: pass
    if role and role.id in IMMUNE_ROLES:
        IMMUNE_ROLES.remove(role.id)
        save_set(ROLE_IMMUNE_FILE, IMMUNE_ROLES)
        await ctx.send(f"✅ Rol `{role.name}` ya no es inmune")
    else:
        await ctx.send(f"❌ `{role_name}` no estaba como inmune")

@bot.command(name="role_inmune_list")
async def role_inmune_list(ctx):
    if not has_perm(ctx): return
    if not IMMUNE_ROLES:
        return await ctx.send("`Lista de roles inmunes vacía`")
    lines=[]
    for rid in IMMUNE_ROLES:
        r = ctx.guild.get_role(rid)
        if r: lines.append(f"{r.mention} (`{rid}`)")
        else: lines.append(f"ID {rid} (rol no encontrado)")
    body = "━━━━━━━━━━━━━━━━━━━━\n" + "\n".join(lines) + "\n━━━━━━━━━━━━━━━━━━━━"
    e = discord.Embed(description=f"**Roles Inmunes [{len(IMMUNE_ROLES)}]**\n\n{body}", color=0x2b2d31)
    await ctx.send(embed=e)

@bot.command(name="owner_list")
async def owner_list(ctx):
    if ctx.author.id!=MY_ID: return
    lines=[]
    for uid in OWNER_IDS:
        try:
            u = bot.get_user(uid) or await bot.fetch_user(uid)
            name = u.name if u else f"ID {uid}"
        except: name = f"ID {uid}"
        lines.append(f"{name} (`{uid}`)")
    body = "━━━━━━━━━━━━━━━━━━━━\n" + "\n".join(lines) + "\n━━━━━━━━━━━━━━━━━━━━" if lines else "━━━━━━━━━━━━━━━━━━━━\n`Vacío`\n━━━━━━━━━━━━━━━━━━━━"
    e = discord.Embed(description=f"**Bot Owners List ({len(OWNER_IDS)})**\n\n{body}\n\nRequested by {ctx.author.name}", color=0x2b2d31)
    if ctx.guild.icon: e.set_thumbnail(url=ctx.guild.icon.url)
    await ctx.send(embed=e)

@bot.command(name="whitelist_list")
async def whitelist_list(ctx):
    if ctx.author.id!=MY_ID: return
    def fmt(ids):
        if not ids: return "`Vacía`"
        lines=[]
        for uid in ids:
            u = bot.get_user(uid)
            name = u.name if u else f"ID {uid}"
            lines.append(f"{name} (`{uid}`)")
        return "\n".join(lines)
    p_txt = fmt(WHITELIST_PINGS)
    r_txt = fmt(WHITELIST_ROLES)
    body = f"━━━━━━━━━━━━━━━━━━━━\n**PINGS [{len(WHITELIST_PINGS)}]:**\n{p_txt}\n\n**ROL [{len(WHITELIST_ROLES)}]:**\n{r_txt}\n━━━━━━━━━━━━━━━━━━━━"
    e = discord.Embed(description=f"**Whitelist List**\n\n{body}\n\nRequested by {ctx.author.name}", color=0x2b2d31)
    if ctx.guild.icon: e.set_thumbnail(url=ctx.guild.icon.url)
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
    if ctx.guild.icon: e.set_thumbnail(url=ctx.guild.icon.url)
    await ctx.send(embed=e)

@bot.command(name="whitelist_add")
async def whitelist_add(ctx, user_id: str = None, tipo: str = None):
    if ctx.author.id!= MY_ID: return
    if not user_id: return await ctx.send("Uso: `_whitelist_add (id) p` o `r`")
    try: uid = int(user_id)
    except: return await ctx.send("ID invalido")
    if not tipo: return await ctx.send(f"`_whitelist_add {uid} p` → pings/links\n`_whitelist_add {uid} r` → dar roles")
    t = tipo.lower()
    if t in ["pings","ping","p"]:
        WHITELIST_PINGS.add(uid); save_set(WHITELIST_PINGS_FILE, WHITELIST_PINGS)
        await ctx.send(f"✅ {uid} agregado a PINGS")
    elif t in ["rol","roles","r"]:
        WHITELIST_ROLES.add(uid); save_set(WHITELIST_ROLES_FILE, WHITELIST_ROLES)
        await ctx.send(f"✅ {uid} agregado a ROL")
    else: await ctx.send("Usa `p` o `r`")

@bot.command(name="whitelist_remove")
async def whitelist_remove(ctx, user_id: str = None, tipo: str = None):
    if ctx.author.id!=MY_ID: return
    if not user_id: return await ctx.send("Uso: `_whitelist_remove (id) p, r`")
    try: uid=int(user_id)
    except: return await ctx.send("ID invalido")
    if not tipo: return await ctx.send(f"`_whitelist_remove {uid} p` o `r`")
    t = tipo.lower()
    if t in ["pings","ping","p"] and uid in WHITELIST_PINGS:
        WHITELIST_PINGS.remove(uid); save_set(WHITELIST_PINGS_FILE, WHITELIST_PINGS)
        await ctx.send(f"`{uid}` removido de PINGS")
    elif t in ["rol","roles","r"] and uid in WHITELIST_ROLES:
        WHITELIST_ROLES.remove(uid); save_set(WHITELIST_ROLES_FILE, WHITELIST_ROLES)
        await ctx.send(f"`{uid}` removido de ROL")
    else: await ctx.send(f"`{uid}` no estaba en {tipo}")

@bot.command(name="userinfo")
async def userinfo(ctx, member: discord.Member = None):
    m = member or ctx.author
    created = discord.utils.format_dt(m.created_at, "F")
    ago_c = discord.utils.format_dt(m.created_at, "R")
    joined = discord.utils.format_dt(m.joined_at, "F") if m.joined_at else "Desconocido"
    ago_j = discord.utils.format_dt(m.joined_at, "R") if m.joined_at else ""
    roles = m.roles[1:][::-1]
    roles_txt = " ".join([r.mention for r in roles[:10]]) if roles else "`Sin roles`"
    if len(roles) > 10: roles_txt += f" `+{len(roles)-10} más`"
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
    e = discord.Embed(description=f"**Información de {m.name}**\n\n{body}", color=0x2b2d31)
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
    e = discord.Embed(description=f"**{g.name}**\n\n{body}", color=0x2b2d31)
    if g.icon: e.set_thumbnail(url=g.icon.url)
    await ctx.send(embed=e)

@bot.command(name="estado")
async def estado(ctx):
    if not has_perm(ctx): return
    g = ctx.guild
    body = f"""━━━━━━━━━━━━━━━━━━━━
🛡️ **AntiNuke** - 🟢 ACTIVO
🤖 **AntiBot** - 🟢 ACTIVO
🔨 **AntiBan/Kick** - 🟢 ACTIVO
📢 **AntiEveryone/Links** - 🟢 1ra borra / 2da kick
🛡️ **Rol Inmune** - {len(IMMUNE_ROLES)} roles
📦 **Backup Auto** - 1 DM cada 30s
📊 **Servers:** {len(bot.guilds)} | **Ping:** {round(bot.latency*1000)}ms
━━━━━━━━━━━━━━━━━━━━"""
    e = discord.Embed(description=f"**Estado de {g.name}**\n\n{body}", color=0x2b2d31)
    if g.icon: e.set_thumbnail(url=g.icon.url)
    await ctx.send(embed=e)

@bot.command(name="avatar")
async def avatar(ctx, member: discord.Member = None):
    m = member or ctx.author
    body = f"━━━━━━━━━━━━━━━━━━━━\n👤 {m.mention}\n`{m.id}`\n[Link]({m.display_avatar.url})\n━━━━━━━━━━━━━━━━━━━━"
    e = discord.Embed(description=f"**Avatar de {m.name}**\n\n{body}", color=0x2b2d31)
    e.set_thumbnail(url=m.display_avatar.url)
    e.set_image(url=m.display_avatar.url)
    await ctx.send(embed=e)

@bot.command(name="ban")
async def ban(ctx,m:discord.Member,*,reason="Sin razón"):
    if not has_perm(ctx): return
    if has_immune_role(ctx.guild, m.id):
        return await ctx.send(f"❌ {m.mention} tiene rol inmune, no lo puedo banear")
    await ctx.guild.ban(m,reason=reason)
    body = f"━━━━━━━━━━━━━━━━━━━━\n{m.name} (`{m.id}`)\nReason: `{reason}`\n━━━━━━━━━━━━━━━━━━━━"
    e = discord.Embed(description=f"**Member Banned**\n\n{body}", color=0x2b2d31)
    if ctx.guild.icon: e.set_thumbnail(url=ctx.guild.icon.url)
    await ctx.send(embed=e)

@bot.command(name="kick")
async def kick(ctx,m:discord.Member,*,reason="Sin razón"):
    if not has_perm(ctx): return
    if has_immune_role(ctx.guild, m.id):
        return await ctx.send(f"❌ {m.mention} tiene rol inmune, no lo puedo kickear")
    await m.kick(reason=reason)
    body = f"━━━━━━━━━━━━━━━━━━━━\n{m.name} (`{m.id}`)\nReason: `{reason}`\n━━━━━━━━━━━━━━━━━━━━"
    e = discord.Embed(description=f"**Member Kicked**\n\n{body}", color=0x2b2d31)
    if ctx.guild.icon: e.set_thumbnail(url=ctx.guild.icon.url)
    await ctx.send(embed=e)

@bot.command(name="owner_remove")
async def owner_remove(ctx,user_id:str):
    if ctx.author.id!=MY_ID: return
    uid=int(user_id)
    if uid!=MY_ID and uid in OWNER_IDS:
        OWNER_IDS.remove(uid); save_owners()
        e = discord.Embed(description=f"**Owner Removed**\n\n━━━━━━━━━━━━━━━━━━━━\n`{uid}` removed\n━━━━━━━━━━━━━━━━━━━━", color=0x2b2d31)
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
        e = discord.Embed(description=f"**Backup Created**\n\n{body}", color=0x2b2d31)
        if guild.icon: e.set_thumbnail(url=guild.icon.url)
        await ctx.send(embed=e, file=discord.File(path))
    elif action == "load":
        if not os.path.exists(path):
            e = discord.Embed(description=f"**Error**\n\n━━━━━━━━━━━━━━━━━━━━\n`No hay backup`\n━━━━━━━━━━━━━━━━━━━━", color=0x2b2d31)
            await ctx.send(embed=e)
            return
        with open(path,"r",encoding="utf-8") as f: data=json.load(f)
        e = discord.Embed(description=f"**Restoring**\n\n━━━━━━━━━━━━━━━━━━━━\n• {len(data['roles'])} roles\n━━━━━━━━━━━━━━━━━━━━", color=0x2b2d31)
        await ctx.send(embed=e)
        existing=[r.name for r in guild.roles]
        for r in data["roles"]:
            if r["name"] not in existing:
                try:
                    await guild.create_role(name=r["name"], colour=discord.Colour(r["color"]), permissions=discord.Permissions(r["permissions"]), hoist=r["hoist"], mentionable=r["mentionable"])
                    await asyncio.sleep(0.3)
                except: pass
        e = discord.Embed(description=f"**Restored**\n\n━━━━━━━━━━━━━━━━━━━━\n`Completado`\n━━━━━━━━━━━━━━━━━━━━", color=0x2b2d31)
        await ctx.send(embed=e)
    else:
        body = "━━━━━━━━━━━━━━━━━━━━\n• _backup create\n• _backup load\n━━━━━━━━━━━━━━━━━━━━"
        e = discord.Embed(description=f"**Backup Help**\n\n{body}", color=0x2b2d31)
        await ctx.send(embed=e)

bot.run(TOKEN)