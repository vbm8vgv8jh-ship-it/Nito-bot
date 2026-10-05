import os, json, discord, asyncio, time, yt_dlp
from discord.ext import commands
from datetime import datetime, timezone
from collections import defaultdict

TOKEN = os.getenv("DISCORD_BOT_TOKEN") or os.getenv("TOKEN") or os.getenv("DISCORD_TOKEN")
MY_ID = 1310357536087740450
OWNER_FILE="owners.json"
WHITELIST_PINGS_FILE="whitelist_pings.json"
WHITELIST_ROLES_FILE="whitelist_roles.json"
ROLE_IMMUNE_FILE="role_immune.json"
VOICE_FILE="voice.json"
BACKUP_DIR="backups"
MUSICA_DIR="musica"
os.makedirs(BACKUP_DIR, exist_ok=True)
os.makedirs(MUSICA_DIR, exist_ok=True)

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
def load_json(path):
    if os.path.exists(path):
        try:
            with open(path,"r") as f: return json.load(f)
        except: return {}
    return {}
def save_json(path, data):
    with open(path,"w") as f: json.dump(data,f)

OWNER_IDS=load_owners(); OWNER_IDS.add(MY_ID)
WHITELIST_PINGS=load_set(WHITELIST_PINGS_FILE)
WHITELIST_ROLES=load_set(WHITELIST_ROLES_FILE)
IMMUNE_ROLES=load_set(ROLE_IMMUNE_FILE)
VOICE_CHANNELS=load_json(VOICE_FILE)

intents=discord.Intents.default()
intents.message_content=True
intents.members=True
intents.guilds=True
intents.presences=True
intents.voice_states=True
bot=commands.Bot(command_prefix="_",intents=intents,help_command=None, chunk_guilds_at_startup=True)

voice_clients={}
def sync_owners():
    o=load_owners(); o.add(MY_ID); OWNER_IDS.clear(); OWNER_IDS.update(o); return o
def has_perm(ctx): return ctx.author.id in sync_owners()
def is_main_owner(ctx): return ctx.author.id == MY_ID
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
immune_cache={}

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
        return path
    except: return None

async def nuke_punish(guild, uid, reason):
    if is_safe(uid, guild.owner_id): return
    try:
        path = await auto_backup(guild)
        if path:
            try:
                u = await bot.fetch_user(MY_ID)
                await u.send(f"🚨 **ANTINUKE** `{guild.name}` - `{reason}` por <@{uid}> (`{uid}`)", file=discord.File(path))
            except: pass
    except: pass
    try:
        m=guild.get_member(uid) or await guild.fetch_member(uid)
        await guild.ban(m, reason=f"ANTINUKE {reason}")
    except: pass

@bot.event
async def on_ready():
    print(f"Listo {bot.user} - Voz 24/7 + Biblioteca MAIN OWNER")
    for guild in bot.guilds:
        gid = str(guild.id)
        if gid in VOICE_CHANNELS:
            try:
                ch_id = VOICE_CHANNELS[gid]
                channel = guild.get_channel(ch_id)
                if not channel:
                    try: channel = await bot.fetch_channel(ch_id)
                    except: continue
                if isinstance(channel, discord.VoiceChannel):
                    if guild.voice_client:
                        try: await guild.voice_client.disconnect()
                        except: pass
                    vc = await channel.connect(self_deaf=True)
                    voice_clients[guild.id] = vc
                    await asyncio.sleep(1)
            except: pass

@bot.event
async def on_voice_state_update(member, before, after):
    if member.id == bot.user.id and before.channel and not after.channel:
        gid = str(before.channel.guild.id)
        if gid in VOICE_CHANNELS:
            await asyncio.sleep(3)
            try:
                channel = before.channel.guild.get_channel(VOICE_CHANNELS[gid])
                if channel:
                    vc = await channel.connect(self_deaf=True)
                    voice_clients[before.channel.guild.id] = vc
            except: pass

@bot.event
async def on_member_update(before,after):
    try:
        if any(r.id in IMMUNE_ROLES for r in after.roles):
            immune_cache[after.id]=True
        else:
            if after.id in immune_cache:
                immune_cache.pop(after.id,None)
    except: pass
    if after.bot or len(before.roles)==len(after.roles): return
    added=[r for r in after.roles if r not in before.roles]
    risky=[r for r in added if r.permissions.administrator or r.permissions.ban_members or r.permissions.kick_members or r.permissions.manage_roles or r.permissions.manage_guild or r.permissions.manage_channels]
    if not risky: return
    try:
        async for entry in after.guild.audit_logs(limit=5,action=discord.AuditLogAction.member_role_update):
            if (datetime.now(timezone.utc)-entry.created_at).total_seconds()>15: continue
            if entry.target.id!=after.id: continue
            if bot.user and entry.user.id == bot.user.id: return
            if entry.user.id == MY_ID: return
            reason = (entry.reason or "").lower()
            if "r_add" in reason or "r_remove" in reason: return
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
        await asyncio.sleep(1)
        async for e in guild.audit_logs(limit=1,action=discord.AuditLogAction.ban):
            if (datetime.now(timezone.utc)-e.created_at).total_seconds()>10: continue
            if e.target.id!= user.id: continue
            if e.target.id in immune_cache or user.id in immune_cache:
                if not is_safe(e.user.id, guild.owner_id):
                    try: await guild.unban(user, reason="Proteccion rol inmune")
                    except: pass
                    await nuke_punish(guild, e.user.id, f"Intento banear a inmune {user.id}")
                    return
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
            if member.id in immune_cache or any(r.id in IMMUNE_ROLES for r in member.roles):
                if not is_safe(e.user.id, member.guild.owner_id):
                    await nuke_punish(member.guild, e.user.id, f"Intento kickear a inmune {member.id}")
                    return
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
            try: await member.ban(reason=f"Antibot - añadido por {e.user} sin owner")
            except:
                try: await member.kick(reason="Antibot")
                except: pass
            await nuke_punish(member.guild, e.user.id, f"Bot Add ({member.id})")
            return
    except: pass

LINK_WORDS = ["http://", "https://", "discord.gg/", "discord.com/invite/", "discordapp.com/invite/"]
GIF_ALLOW = ["tenor.com", "giphy.com", "media.tenor.com", "media.giphy.com", ".gif", "giphy", "tenor"]

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        await bot.process_commands(message)
        return
    content_lower = message.content.lower()
    is_ping_attempt = "@everyone" in message.content or "@here" in message.content or message.mention_everyone
    is_link_attempt = any(w in content_lower for w in LINK_WORDS)
    if not is_ping_attempt and not is_link_attempt:
        await bot.process_commands(message)
        return
    if is_pings_allowed(message.guild, message.author.id, message.guild.owner_id):
        await bot.process_commands(message)
        return
    if is_link_attempt:
        await asyncio.sleep(5)
        try:
            fresh_msg = await message.channel.fetch_message(message.id)
            if not fresh_msg:
                await bot.process_commands(message)
                return
            is_real_gif = False
            cl = fresh_msg.content.lower()
            if any(g in cl for g in GIF_ALLOW):
                is_real_gif = True
            if fresh_msg.embeds:
                for emb in fresh_msg.embeds:
                    url = str(emb.url).lower() if emb.url else ""
                    if emb.type == "gifv" or "tenor" in url or "giphy" in url:
                        is_real_gif = True
                        break
                    if emb.video or emb.image:
                        if any(g in cl for g in GIF_ALLOW):
                            is_real_gif = True
                            break
            if fresh_msg.attachments and any(a.filename.lower().endswith(".gif") for a in fresh_msg.attachments):
                is_real_gif = True
            if is_real_gif:
                await bot.process_commands(fresh_msg)
                return
        except discord.NotFound:
            await bot.process_commands(message)
            return
        except:
            pass
    pings_warns[message.author.id] += 1
    try: await message.delete()
    except: pass
    if pings_warns[message.author.id] == 1:
        try: await message.channel.send(f"⚠️ {message.author.mention} 1ra advertencia: sin whitelist no puedes usar `@everyone/@here` ni links. (gifs permitidos). 2da = kick.", delete_after=7)
        except: pass
    else:
        try:
            if has_immune_role(message.guild, message.author.id):
                pings_warns.pop(message.author.id, None)
                return
            await message.guild.kick(message.author, reason="2da vez everyone/links")
            await message.channel.send(f"🔨 {message.author.mention} kickeado por links/@everyone", delete_after=7)
            pings_warns.pop(message.author.id, None)
        except:
            try: await message.channel.send(f"🚫 No pude kickear a {message.author.mention}", delete_after=7)
            except: pass
    return

@bot.command(name="join")
async def join(ctx):
    if not has_perm(ctx): return
    if not ctx.author.voice or not ctx.author.voice.channel:
        e = discord.Embed(description="```\nDebes estar en un canal de voz\n```", color=0x2b2d31)
        return await ctx.send(embed=e)
    channel = ctx.author.voice.channel
    try:
        if ctx.guild.voice_client:
            try: await ctx.guild.voice_client.disconnect()
            except: pass
        vc = await channel.connect(self_deaf=True)
        voice_clients[ctx.guild.id] = vc
        VOICE_CHANNELS[str(ctx.guild.id)] = channel.id
        save_json(VOICE_FILE, VOICE_CHANNELS)
        e = discord.Embed(description=f"**Voz 24/7 Activada**\n\n━━━━━━━━━━━━━━━━━━━━\n🎧 Canal: {channel.mention}\n`{channel.id}`\n\n✅ Ya no me saldré nunca\nSi me kickean me vuelvo a meter en 3s\nSi reinician el bot me reconecto solo\n━━━━━━━━━━━━━━━━━━━━", color=0x00ff00)
        if ctx.guild.icon: e.set_thumbnail(url=ctx.guild.icon.url)
        await ctx.send(embed=e)
    except Exception as ex:
        e = discord.Embed(description=f"**Error Voz**\n\n━━━━━━━━━━━━━━━━━━━━\n```\n{ex}\n```\nInstala:\n`discord.py[voice]`\n`PyNaCl`\n━━━━━━━━━━━━━━━━━━━━", color=0xff0000)
        await ctx.send(embed=e)

@bot.command(name="leave")
async def leave(ctx):
    if not has_perm(ctx): return
    vc = ctx.guild.voice_client or voice_clients.get(ctx.guild.id)
    if vc:
        try: await vc.disconnect()
        except: pass
        voice_clients.pop(ctx.guild.id, None)
        VOICE_CHANNELS.pop(str(ctx.guild.id), None)
        save_json(VOICE_FILE, VOICE_CHANNELS)
        e = discord.Embed(description=f"**Voz 24/7 Desactivada**\n\n━━━━━━━━━━━━━━━━━━━━\n👋 Me salí y ya no reconectaré\n━━━━━━━━━━━━━━━━━━━━", color=0x2b2d31)
        await ctx.send(embed=e)
    else:
        e = discord.Embed(description="```\nNo estoy en voz\n```", color=0x2b2d31)
        await ctx.send(embed=e)

# --- SOLO MAIN OWNER: BIBLIOTECA ---
@bot.command(name="guardar")
async def guardar(ctx, *, nombre: str = None):
    if not is_main_owner(ctx): return
    if not nombre:
        return await ctx.send("**Uso:** `_guardar nombre` + adjunta MP3\nEj: `_guardar tuputamadre`")
    nombre_safe = "".join(c for c in nombre if c.isalnum() or c in ('_','-')).strip().lower()
    if not nombre_safe:
        return await ctx.send("❌ Nombre inválido")
    output_path = f"{MUSICA_DIR}/{nombre_safe}.mp3"
    if not ctx.message.attachments:
        return await ctx.send("❌ Debes adjuntar el MP3\nEj: `_guardar tuputamadre` + archivo")
    try:
        attachment = ctx.message.attachments[0]
        await ctx.send(f"📥 Guardando `{attachment.filename}` como `{nombre_safe}.mp3`...")
        await attachment.save(output_path)
        e = discord.Embed(description=f"**✅ Guardado (solo main owner)**\n\n━━━━━━━━━━━━━━━━━━━━\n📁 Nombre: `{nombre_safe}`\n📄 Original: `{attachment.filename}`\n━━━━━━━━━━━━━━━━━━━━\nUsa `_tuputamadre {nombre_safe}`", color=0x00ff00)
        await ctx.send(embed=e)
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

@bot.command(name="list")
async def list_cmd(ctx):
    if not is_main_owner(ctx): return
    if not os.path.exists(MUSICA_DIR):
        return await ctx.send("`📂 Vacía`")
    files = [f for f in os.listdir(MUSICA_DIR) if f.endswith((".mp3",".m4a",".ogg",".wav",".mp4"))]
    if not files:
        return await ctx.send("`📂 Biblioteca vacía - usa _guardar nombre + archivo`")
    desc = ""
    for i, f in enumerate(files, 1):
        size = os.path.getsize(f"{MUSICA_DIR}/{f}") / (1024*1024)
        name = os.path.splitext(f)[0]
        desc += f"**{i}.** `{name}` - {size:.1f}MB\n"
    e = discord.Embed(description=f"**📂 Biblioteca [{len(files)}] - solo tú**\n\n━━━━━━━━━━━━━━━━━━━━\n{desc}\n━━━━━━━━━━━━━━━━━━━━\n`_tuputamadre nombre` para sonar\n`_quitar nombre` para borrar", color=0x2b2d31)
    await ctx.send(embed=e)

@bot.command(name="quitar")
async def quitar(ctx, *, nombre: str = None):
    if not is_main_owner(ctx): return
    if not nombre:
        return await ctx.send("**Uso:** `_quitar nombre`\nEj: `_quitar tuputamadre`")
    nombre_safe = "".join(c for c in nombre if c.isalnum() or c in ('_','-')).strip().lower()
    found = None
    for ext in [".mp3",".m4a",".ogg",".wav",".mp4"]:
        p = f"{MUSICA_DIR}/{nombre_safe}{ext}"
        if os.path.exists(p):
            found = p
            break
    if not found:
        return await ctx.send(f"❌ No encontré `{nombre_safe}` - usa `_list`")
    try:
        os.remove(found)
        await ctx.send(f"🗑️ Borrado `{nombre_safe}` - solo main owner")
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

@bot.command(name="tuputamadre")
async def tuputamadre(ctx, *, nombre: str = None):
    if not has_perm(ctx): return
    vc = ctx.guild.voice_client or voice_clients.get(ctx.guild.id)
    if not vc:
        return await ctx.send("❌ No estoy en voz, usa `_join` primero")
    if vc.is_playing():
        vc.stop()

    if not nombre:
        if os.path.exists(MUSICA_DIR):
            files = [f for f in os.listdir(MUSICA_DIR) if f.endswith((".mp3",".m4a",".ogg",".wav",".mp4"))]
            if files:
                file_path = f"{MUSICA_DIR}/{files[0]}"
            else:
                return await ctx.send("❌ Biblioteca vacía. Usa `_guardar nombre` + archivo (solo main owner)")
        else:
            return await ctx.send("❌ No hay canciones")
    else:
        nombre_safe = "".join(c for c in nombre if c.isalnum() or c in ('_','-')).strip().lower()
        file_path = None
        for ext in [".mp3",".m4a",".ogg",".wav",".mp4"]:
            p = f"{MUSICA_DIR}/{nombre_safe}{ext}"
            if os.path.exists(p):
                file_path = p
                break
        if not file_path:
            return await ctx.send(f"❌ No encontré `{nombre_safe}`\nUsa `_list`")

    try:
        filtro = 'volume=30dB, bass=gain=30:frequency=100, acrusher=level_in=12:level_out=18:bits=8:mode=log:aa=1'
        source = discord.FFmpegPCMAudio(file_path, options=f'-filter:a "{filtro}"')
        vc.play(source)
        e = discord.Embed(description=f"**💥 REVENTADO A 30dB**\n\n━━━━━━━━━━━━━━━━━━━━\n🎵 `{os.path.basename(file_path)}`\n🔊 `30dB + bass + crusher`\n━━━━━━━━━━━━━━━━━━━━", color=0xff0000)
        await ctx.send(embed=e)
    except Exception as e:
        await ctx.send(f"❌ Error audio: {e}")

@bot.command(name="stop")
async def stop(ctx):
    if not has_perm(ctx): return
    vc = ctx.guild.voice_client or voice_clients.get(ctx.guild.id)
    if not vc:
        return await ctx.send("❌ No estoy en voz")
    if vc.is_playing():
        vc.stop()
        e = discord.Embed(description="**🔇 Música parada**\n\n━━━━━━━━━━━━━━━━━━━━\nSe detuvo el audio saturado\n━━━━━━━━━━━━━━━━━━━━", color=0x2b2d31)
        await ctx.send(embed=e)
    else:
        await ctx.send("`No hay nada sonando`")

@bot.command(name="r_add")
async def r_add(ctx, user_id: str = None, *, role_name: str = None):
    if not has_perm(ctx): return
    if not user_id or not role_name:
        return await ctx.send(embed=discord.Embed(description="```\nSyntax: _r_add (id) role name\n```", color=0x2b2d31))
    try:
        uid = int(user_id)
        member = ctx.guild.get_member(uid) or await ctx.guild.fetch_member(uid)
    except:
        return await ctx.send(f"❌ No encontré al usuario `{user_id}`")
    if member.id == ctx.guild.owner_id:
        return await ctx.send("❌ No puedo dar/quitar roles al **owner del servidor**")
    role = discord.utils.find(lambda r: r.name.lower() == role_name.lower().strip(), ctx.guild.roles)
    if not role:
        try: role = ctx.guild.get_role(int(role_name))
        except: pass
    if not role:
        return await ctx.send(f"❌ No encontré el rol `{role_name}`")
    me = ctx.guild.me
    if not me.guild_permissions.manage_roles:
        return await ctx.send("❌ Yo no tengo el permiso `Gestionar Roles`")
    if role.managed:
        return await ctx.send(f"❌ `{role.name}` es un rol de bot/integración")
    if role.position >= me.top_role.position:
        return await ctx.send(f"❌ **Jerarquía:** Mi rol `{me.top_role.name}` pos {me.top_role.position} y `{role.name}` pos {role.position}. Súbeme.")
    try:
        await member.add_roles(role, reason=f"r_add por {ctx.author}")
        await asyncio.sleep(0.7)
        member = ctx.guild.get_member(uid) or await ctx.guild.fetch_member(uid)
        if role in member.roles:
            e = discord.Embed(description=f"**Rol Agregado ✅**\n\n━━━━━━━━━━━━━━━━━━━━\n👤 {member.mention} (`{member.id}`)\n🎭 `{role.name}`\n━━━━━━━━━━━━━━━━━━━━", color=0x00ff00)
            await ctx.send(embed=e)
        else:
            await ctx.send(f"⚠️ Le di la orden pero `{role.name}` no aparece en {member.mention}.")
    except Exception as ex:
        await ctx.send(f"❌ Error: {ex}")

@bot.command(name="r_remove")
async def r_remove(ctx, user_id: str = None, *, role_name: str = None):
    if not has_perm(ctx): return
    if not user_id or not role_name:
        return await ctx.send(embed=discord.Embed(description="```\nSyntax: _r_remove (id) role name\n```", color=0x2b2d31))
    try:
        uid = int(user_id)
        member = ctx.guild.get_member(uid) or await ctx.guild.fetch_member(uid)
    except:
        return await ctx.send(f"❌ No encontré al usuario `{user_id}`")
    if member.id == ctx.guild.owner_id:
        return await ctx.send("❌ No puedo dar/quitar roles al **owner**")
    role = discord.utils.find(lambda r: r.name.lower() == role_name.lower().strip(), ctx.guild.roles)
    if not role:
        try: role = ctx.guild.get_role(int(role_name))
        except: pass
    if not role:
        return await ctx.send(f"❌ No encontré el rol `{role_name}`")
    me = ctx.guild.me
    if role.position >= me.top_role.position:
        return await ctx.send(f"❌ Mi rol `{me.top_role.name}` está debajo de `{role.name}`. Súbeme.")
    try:
        await member.remove_roles(role, reason=f"r_remove por {ctx.author}")
        e = discord.Embed(description=f"**Rol Removido**\n\n━━━━━━━━━━━━━━━━━━━━\n👤 {member.mention} (`{member.id}`)\n🎭 `{role.name}`\n━━━━━━━━━━━━━━━━━━━━", color=0x2b2d31)
        await ctx.send(embed=e)
    except Exception as ex:
        await ctx.send(f"❌ Error: {ex}")

@bot.command(name="debug_rol")
async def debug_rol(ctx, *, role_name: str = None):
    if not has_perm(ctx): return
    if not role_name: return await ctx.send("Uso: `_debug_rol nombre del rol`")
    role = discord.utils.find(lambda r: r.name.lower() == role_name.lower(), ctx.guild.roles)
    if not role:
        try: role = ctx.guild.get_role(int(role_name))
        except: pass
    if not role: return await ctx.send(f"No encontré `{role_name}`")
    me = ctx.guild.me
    e = discord.Embed(description=f"**Debug Rol**\n\n━━━━━━━━━━━━━━━━━━━━\n**Yo:** {me.top_role.mention} pos `{me.top_role.position}`\n**Objetivo:** {role.mention} pos `{role.position}`\n**¿Puedo darlo?:** {'✅ SI' if role.position < me.top_role.position else '❌ NO - súbeme'}\n**Manage Roles:** {'✅' if me.guild_permissions.manage_roles else '❌'}\n**Admin:** {'✅' if me.guild_permissions.administrator else '❌'}\n━━━━━━━━━━━━━━━━━━━━", color=0x2b2d31)
    await ctx.send(embed=e)

@bot.command(name="role_inmune_add")
async def role_inmune_add(ctx, role_id: str = None):
    if not has_perm(ctx): return
    if not role_id: return await ctx.send("**Uso:** `_role_inmune_add ID_DEL_ROL`")
    try:
        rid = int(role_id)
        role = ctx.guild.get_role(rid)
        if not role: return await ctx.send(f"❌ No encontré rol con ID `{rid}`")
    except: return await ctx.send("❌ ID invalido")
    IMMUNE_ROLES.add(rid)
    save_set(ROLE_IMMUNE_FILE, IMMUNE_ROLES)
    e = discord.Embed(description=f"**Rol Inmune Agregado por ID**\n\n━━━━━━━━━━━━━━━━━━━━\n🎭 {role.mention} (`{role.id}`)\nAhora es inmune a ban/kick y solo owners pueden banearlo.\n━━━━━━━━━━━━━━━━━━━━", color=0x2b2d31)
    await ctx.send(embed=e)

@bot.command(name="role_inmune_remove")
async def role_inmune_remove(ctx, role_id: str = None):
    if not has_perm(ctx): return
    if not role_id: return await ctx.send("**Uso:** `_role_inmune_remove ID_DEL_ROL`")
    try: rid = int(role_id)
    except: return await ctx.send("❌ ID invalido")
    role = ctx.guild.get_role(rid)
    if rid in IMMUNE_ROLES:
        IMMUNE_ROLES.remove(rid)
        save_set(ROLE_IMMUNE_FILE, IMMUNE_ROLES)
        name = role.name if role else str(rid)
        await ctx.send(f"✅ Rol `{name}` (`{rid}`) ya no es inmune")
    else:
        await ctx.send(f"❌ ID `{rid}` no estaba como inmune")

@bot.command(name="role_inmune_list")
async def role_inmune_list(ctx):
    if not has_perm(ctx): return
    if not IMMUNE_ROLES:
        return await ctx.send("`Lista de roles inmunes vacía`")
    lines=[]
    for rid in IMMUNE_ROLES:
        r = ctx.guild.get_role(rid)
        if r: lines.append(f"{r.mention} (`{rid}`)")
        else: lines.append(f"ID {rid} (no encontrado)")
    body = "━━━━━━━━━━━━━━━━━━━━\n" + "\n".join(lines) + "\n━━━━━━━━━━━━━━━━━━━━"
    e = discord.Embed(description=f"**Roles Inmunes por ID [{len(IMMUNE_ROLES)}]**\n\n{body}", color=0x2b2d31)
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
    if not user_id or not tipo:
        return await ctx.send(embed=discord.Embed(description="```\nSyntax: _whitelist_add (id) r/p\n```", color=0x2b2d31))
    try: uid = int(user_id)
    except: return await ctx.send(embed=discord.Embed(description="```\nID invalido\n```", color=0x2b2d31))
    if tipo.lower() in ["pings","ping","p"]:
        WHITELIST_PINGS.add(uid); save_set(WHITELIST_PINGS_FILE, WHITELIST_PINGS)
        await ctx.send(embed=discord.Embed(description=f"```\n{uid} add wh p\n```", color=0x2b2d31))
    elif tipo.lower() in ["rol","roles","r"]:
        WHITELIST_ROLES.add(uid); save_set(WHITELIST_ROLES_FILE, WHITELIST_ROLES)
        await ctx.send(embed=discord.Embed(description=f"```\n{uid} add wh r\n```", color=0x2b2d31))

@bot.command(name="whitelist_remove")
async def whitelist_remove(ctx, user_id: str = None, tipo: str = None):
    if ctx.author.id!=MY_ID: return
    if not user_id or not tipo:
        return await ctx.send(embed=discord.Embed(description="```\nSyntax: _whitelist_remove (id) r/p\n```", color=0x2b2d31))
    try: uid=int(user_id)
    except: return await ctx.send(embed=discord.Embed(description="```\nID invalido\n```", color=0x2b2d31))
    if tipo.lower() in ["pings","ping","p"]:
        if uid in WHITELIST_PINGS:
            WHITELIST_PINGS.remove(uid); save_set(WHITELIST_PINGS_FILE, WHITELIST_PINGS)
            await ctx.send(embed=discord.Embed(description=f"```\n{uid} remove wh p\n```", color=0x2b2d31))
    elif tipo.lower() in ["rol","roles","r"]:
        if uid in WHITELIST_ROLES:
            WHITELIST_ROLES.remove(uid); save_set(WHITELIST_ROLES_FILE, WHITELIST_ROLES)
            await ctx.send(embed=discord.Embed(description=f"```\n{uid} remove wh r\n```", color=0x2b2d31))

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
Voz 24/7: {'🟢 SI' if str(g.id) in VOICE_CHANNELS else '🔴 NO'}
✨ **Extras**
Roles: {len(g.roles)}
Boosts: {g.premium_subscription_count}
Musica: {len(os.listdir(MUSICA_DIR)) if os.path.exists(MUSICA_DIR) else 0} canciones
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
🤖 **AntiBot** - 🟢 SOLO OWNER
🔨 **AntiBan/Kick** - 🟢 ACTIVO
📢 **AntiEveryone/Links** - 🟢 5s investiga gif / 2da kick
🛡️ **Rol Inmune por ID** - {len(IMMUNE_ROLES)} roles
🎧 **Voz 24/7** - {'🟢 ACTIVO' if str(g.id) in VOICE_CHANNELS else '🔴 INACTIVO'} ({len(VOICE_CHANNELS)} servers)
📦 **Backup Auto** - DM solo si ataque
🎵 **Musica** - {len(os.listdir(MUSICA_DIR)) if os.path.exists(MUSICA_DIR) else 0} guardadas
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
    if any(r.id in IMMUNE_ROLES for r in m.roles):
        if ctx.author.id!= MY_ID and ctx.author.id not in OWNER_IDS:
            try:
                await ctx.guild.ban(ctx.author, reason="Intento banear a inmune sin ser owner")
                e = discord.Embed(description=f"**Proteccion Inmune**\n\n━━━━━━━━━━━━━━━━━━━━\n🚫 {ctx.author.mention} intentaste banear a {m.mention} que es inmune\nFuiste baneado automaticamente\nSolo owners pueden banear inmunes\n━━━━━━━━━━━━━━━━━━━━", color=0xff0000)
                await ctx.send(embed=e)
            except: pass
            return
    await ctx.guild.ban(m,reason=reason)
    body = f"━━━━━━━━━━━━━━━━━━━━\n{m.name} (`{m.id}`)\nReason: `{reason}`\n━━━━━━━━━━━━━━━━━━━━"
    e = discord.Embed(description=f"**Member Banned**\n\n{body}", color=0x2b2d31)
    if ctx.guild.icon: e.set_thumbnail(url=ctx.guild.icon.url)
    await ctx.send(embed=e)

@bot.command(name="kick")
async def kick(ctx,m:discord.Member,*,reason="Sin razón"):
    if not has_perm(ctx): return
    if any(r.id in IMMUNE_ROLES for r in m.roles):
        if ctx.author.id!= MY_ID and ctx.author.id not in OWNER_IDS:
            try:
                await ctx.guild.ban(ctx.author, reason="Intento kickear a inmune sin ser owner")
                e = discord.Embed(description=f"**Proteccion Inmune**\n\n━━━━━━━━━━━━━━━━━━━━\n🚫 {ctx.author.mention} intentaste kickear a {m.mention} que es inmune\nFuiste baneado automaticamente\n━━━━━━━━━━━━━━━━━━━━", color=0xff0000)
                await ctx.send(embed=e)
            except: pass
            return
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
        p = await auto_backup(guild)
        with open(p,"r",encoding="utf-8") as f: data=json.load(f)
        body = f"━━━━━━━━━━━━━━━━━━━━\n• Roles • ( `{len(data['roles'])}` )\n• Channels • ( `{len(data['channels'])}` )\n━━━━━━━━━━━━━━━━━━━━"
        e = discord.Embed(description=f"**Backup Created**\n\n{body}", color=0x2b2d31)
        if guild.icon: e.set_thumbnail(url=guild.icon.url)
        await ctx.send(embed=e, file=discord.File(p))
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