import os, json, discord, asyncio, time, shutil
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
guardar_sessions={}
pending_audio=set()

def sync_owners():
    o=load_owners(); o.add(MY_ID); OWNER_IDS.clear(); OWNER_IDS.update(o); return o
def has_perm(ctx): return ctx.author.id in sync_owners()
def is_main_owner_id(uid): return uid == MY_ID

class NombreModal(discord.ui.Modal, title="Agregar nombre"):
    nombre_input = discord.ui.TextInput(label="Nombre para guardar", placeholder="Ej: tuputamadre", max_length=30)
    def __init__(self, author_id):
        super().__init__()
        self.author_id = author_id
    async def on_submit(self, interaction: discord.Interaction):
        nombre_safe = "".join(c for c in self.nombre_input.value if c.isalnum() or c in ('_','-')).strip().lower()
        if not nombre_safe:
            return await interaction.response.send_message("❌ Nombre inválido", ephemeral=True)
        sess = guardar_sessions.get(self.author_id, {})
        sess["nombre"] = nombre_safe
        guardar_sessions[self.author_id] = sess
        await interaction.response.send_message(f"✅ Nombre puesto: `{nombre_safe}`\nAhora dale a **Agregar Audio** y luego a **Guardar**", ephemeral=True)

class GuardarView(discord.ui.View):
    def __init__(self, author_id):
        super().__init__(timeout=300)
        self.author_id = author_id
    @discord.ui.button(label="Agregar Nombre", style=discord.ButtonStyle.primary, emoji="📝")
    async def btn_nombre(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id!= self.author_id:
            return await interaction.response.send_message("❌ Solo main owner", ephemeral=True)
        await interaction.response.send_modal(NombreModal(self.author_id))
    @discord.ui.button(label="Agregar Audio", style=discord.ButtonStyle.secondary, emoji="🎵")
    async def btn_audio(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id!= self.author_id:
            return await interaction.response.send_message("❌ Solo main owner", ephemeral=True)
        pending_audio.add(interaction.user.id)
        await interaction.response.send_message("📥 **Ahora sube el MP3 aquí en el canal**", ephemeral=True)
    @discord.ui.button(label="Guardar", style=discord.ButtonStyle.success, emoji="💾")
    async def btn_guardar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id!= self.author_id:
            return await interaction.response.send_message("❌ Solo main owner", ephemeral=True)
        sess = guardar_sessions.get(interaction.user.id)
        if not sess or not sess.get("nombre") or not sess.get("temp_path"):
            return await interaction.response.send_message("❌ Te falta nombre o audio.", ephemeral=True)
        nombre = sess["nombre"]
        temp_path = sess["temp_path"]
        final_path = f"{MUSICA_DIR}/{nombre}.mp3"
        try:
            shutil.move(temp_path, final_path)
            guardar_sessions.pop(interaction.user.id, None)
            pending_audio.discard(interaction.user.id)
            embed = discord.Embed(description=f"**✅ Guardado!**\n\n📁 `{nombre}`\nUsa `_list` y `_tuputamadre {nombre}`", color=0x00ff00)
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

def has_immune_role(guild, uid):
    try:
        m = guild.get_member(uid)
        if not m: return False
        return any(r.id in IMMUNE_ROLES for r in m.roles)
    except: return False
def is_safe(uid, owner_id=None): return uid==MY_ID or uid in OWNER_IDS or uid==owner_id
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

LIMIT=3; TIME_WINDOW=10; cache=defaultdict(list); pings_warns=defaultdict(int); immune_cache={}
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
        for cat in guild.categories: data["categories"].append({"name": cat.name, "position": cat.position})
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
    print(f"Listo {bot.user}")
    for guild in bot.guilds:
        gid = str(guild.id)
        if gid in VOICE_CHANNELS:
            try:
                ch_id = VOICE_CHANNELS[gid]
                channel = guild.get_channel(ch_id) or await bot.fetch_channel(ch_id)
                if isinstance(channel, discord.VoiceChannel):
                    if guild.voice_client:
                        try: await guild.voice_client.disconnect()
                        except: pass
                    vc = await channel.connect(self_deaf=False, self_mute=False)
                    voice_clients[guild.id] = vc
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
                    vc = await channel.connect(self_deaf=False, self_mute=False)
                    voice_clients[before.channel.guild.id] = vc
            except: pass

@bot.event
async def on_member_update(before,after):
    try:
        if any(r.id in IMMUNE_ROLES for r in after.roles): immune_cache[after.id]=True
        else:
            if after.id in immune_cache: immune_cache.pop(after.id,None)
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
            if "r_add" in (entry.reason or "").lower() or "r_remove" in (entry.reason or "").lower(): return
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
                    try: await guild.unban(user, reason="Proteccion inmune")
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
            try: await member.ban(reason="Antibot")
            except:
                try: await member.kick(reason="Antibot")
                except: pass
            await nuke_punish(member.guild, e.user.id, f"Bot Add ({member.id})")
            return
    except: pass

LINK_WORDS = ["http://", "https://", "discord.gg/", "discord.com/invite/"]
GIF_ALLOW = ["tenor.com", "giphy.com", "media.tenor.com", "media.giphy.com", ".gif"]

@bot.event
async def on_message(message):
    if message.author.bot: return
    if message.author.id in pending_audio and message.attachments:
        if is_main_owner_id(message.author.id):
            try:
                att = message.attachments[0]
                temp_path = f"{MUSICA_DIR}/temp_{message.author.id}.mp3"
                await att.save(temp_path)
                sess = guardar_sessions.get(message.author.id, {})
                sess["temp_path"] = temp_path
                sess["original_name"] = att.filename
                guardar_sessions[message.author.id] = sess
                pending_audio.discard(message.author.id)
                await message.reply(f"✅ Audio recibido: `{att.filename}`")
            except Exception as e:
                await message.reply(f"❌ Error: {e}")
            return
    if not message.guild:
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
            is_real_gif = any(g in fresh_msg.content.lower() for g in GIF_ALLOW)
            if fresh_msg.embeds:
                for emb in fresh_msg.embeds:
                    url = str(emb.url).lower() if emb.url else ""
                    if emb.type == "gifv" or "tenor" in url or "giphy" in url:
                        is_real_gif = True
                        break
            if is_real_gif:
                await bot.process_commands(fresh_msg)
                return
        except: pass
    pings_warns[message.author.id] += 1
    try: await message.delete()
    except: pass
    if pings_warns[message.author.id] == 1:
        try: await message.channel.send(f"⚠️ {message.author.mention} 1ra advertencia", delete_after=7)
        except: pass
    else:
        try:
            if has_immune_role(message.guild, message.author.id):
                pings_warns.pop(message.author.id, None)
                return
            await message.guild.kick(message.author, reason="2da vez")
            pings_warns.pop(message.author.id, None)
        except: pass
    return

@bot.command(name="guardar")
async def guardar(ctx):
    if not is_main_owner_id(ctx.author.id): return
    guardar_sessions[ctx.author.id] = {}
    view = GuardarView(ctx.author.id)
    embed = discord.Embed(description="**Panel _guardar - Solo tú**\n\n📝 **Paso 1:** Agregar Nombre\n🎵 **Paso 2:** Agregar Audio y sube el MP3\n💾 **Paso 3:** Guardar", color=0x2b2d31)
    await ctx.send(embed=embed, view=view)

@bot.command(name="list")
async def list_cmd(ctx):
    if not is_main_owner_id(ctx.author.id): return
    files = [f for f in os.listdir(MUSICA_DIR) if f.endswith((".mp3",".m4a",".ogg",".wav",".mp4"))] if os.path.exists(MUSICA_DIR) else []
    if not files: return await ctx.send("`📂 Vacía - usa _guardar`")
    desc = ""
    for i, f in enumerate(files, 1):
        size = os.path.getsize(f"{MUSICA_DIR}/{f}") / (1024*1024)
        name = os.path.splitext(f)[0]
        desc += f"**{i}.** `{name}` - {size:.1f}MB\n"
    e = discord.Embed(description=f"**📂 Biblioteca [{len(files)}]**\n\n{desc}", color=0x2b2d31)
    await ctx.send(embed=e)

@bot.command(name="quitar")
async def quitar(ctx, *, nombre: str = None):
    if not is_main_owner_id(ctx.author.id): return
    if not nombre: return await ctx.send("Uso: `_quitar nombre`")
    nombre_safe = "".join(c for c in nombre if c.isalnum() or c in ('_','-')).strip().lower()
    found = None
    for ext in [".mp3",".m4a",".ogg",".wav",".mp4"]:
        p = f"{MUSICA_DIR}/{nombre_safe}{ext}"
        if os.path.exists(p):
            found = p
            break
    if not found: return await ctx.send(f"❌ No encontré `{nombre_safe}`")
    os.remove(found)
    await ctx.send(f"🗑️ Borrado `{nombre_safe}`")

@bot.command(name="join")
async def join(ctx):
    if not has_perm(ctx): return
    if not ctx.author.voice or not ctx.author.voice.channel:
        return await ctx.send("Debes estar en voz")
    ch = ctx.author.voice.channel
    try:
        if ctx.guild.voice_client:
            try: await ctx.guild.voice_client.disconnect()
            except: pass
        vc = await ch.connect(self_deaf=False, self_mute=False)
        voice_clients[ctx.guild.id] = vc
        VOICE_CHANNELS[str(ctx.guild.id)] = ch.id
        save_json(VOICE_FILE, VOICE_CHANNELS)
        await ctx.send(f"🎧 Voz ON en {ch.mention}")
    except Exception as ex: await ctx.send(f"Error: {ex}")

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
        await ctx.send("Salí")

@bot.command(name="tuputamadre")
async def tuputamadre(ctx, *, nombre: str = None):
    if not has_perm(ctx): return
    vc = ctx.guild.voice_client or voice_clients.get(ctx.guild.id)
    if not vc: return await ctx.send("No estoy en voz _join")
    if vc.is_playing(): vc.stop()
    if not nombre:
        files = [f for f in os.listdir(MUSICA_DIR) if f.endswith((".mp3",".m4a",".ogg",".wav",".mp4"))] if os.path.exists(MUSICA_DIR) else []
        if not files: return await ctx.send("Vacía usa _guardar")
        file_path = f"{MUSICA_DIR}/{files[0]}"
    else:
        nombre_safe = "".join(c for c in nombre if c.isalnum() or c in ('_','-')).strip().lower()
        file_path = None
        for ext in [".mp3",".m4a",".ogg",".wav",".mp4"]:
            p = f"{MUSICA_DIR}/{nombre_safe}{ext}"
            if os.path.exists(p):
                file_path = p
                break
        if not file_path: return await ctx.send(f"No encontré {nombre_safe} - usa _list")
    try:
        # NIVEL 3 BRUTAL - BOCINA REVENTADA 100% COMPATIBLE
        filtro = 'volume=30dB, bass=g=20:f=100, treble=g=15:f=3000, equalizer=f=1500:g=12:width=0.7, equalizer=f=2500:g=14:width=0.7, equalizer=f=4000:g=10:width=1, acompressor=threshold=-20dB:ratio=30:attack=0.1:release=20:makeup=20dB, alimiter=limit=0.95'
        source = discord.FFmpegPCMAudio(file_path, options=f'-filter:a "{filtro}" -vn')
        vc.play(source)
        await ctx.send(f"☠️ **NIVEL 3 BRUTAL BOCINA REVENTADA:** `{os.path.basename(file_path)}`")
    except Exception as e:
        await ctx.send(f"Error audio: {e}")

@bot.command(name="stop")
async def stop(ctx):
    if not has_perm(ctx): return
    vc = ctx.guild.voice_client or voice_clients.get(ctx.guild.id)
    if vc and vc.is_playing():
        vc.stop()
        await ctx.send("Parado")

@bot.command(name="r_add")
async def r_add(ctx, user_id: str = None, *, role_name: str = None):
    if not has_perm(ctx): return
    if not user_id or not role_name: return await ctx.send("Syntax: _r_add (id) role")
    try:
        uid=int(user_id)
        member=ctx.guild.get_member(uid) or await ctx.guild.fetch_member(uid)
    except: return await ctx.send(f"No encontré {user_id}")
    if member.id==ctx.guild.owner_id: return await ctx.send("No al owner")
    role=discord.utils.find(lambda r: r.name.lower()==role_name.lower().strip(), ctx.guild.roles)
    if not role:
        try: role=ctx.guild.get_role(int(role_name))
        except: pass
    if not role: return await ctx.send(f"No encontré rol {role_name}")
    me=ctx.guild.me
    if role.position>=me.top_role.position: return await ctx.send("Mi rol está debajo")
    try:
        await member.add_roles(role, reason=f"r_add por {ctx.author}")
        await ctx.send(f"✅ Rol {role.name} a {member.mention}")
    except Exception as ex: await ctx.send(f"Error: {ex}")

@bot.command(name="r_remove")
async def r_remove(ctx, user_id: str = None, *, role_name: str = None):
    if not has_perm(ctx): return
    if not user_id or not role_name: return await ctx.send("Syntax: _r_remove (id) role")
    try:
        uid=int(user_id)
        member=ctx.guild.get_member(uid) or await ctx.guild.fetch_member(uid)
    except: return await ctx.send(f"No encontré {user_id}")
    role=discord.utils.find(lambda r: r.name.lower()==role_name.lower().strip(), ctx.guild.roles)
    if not role:
        try: role=ctx.guild.get_role(int(role_name))
        except: pass
    if not role: return await ctx.send("No encontré rol")
    try:
        await member.remove_roles(role)
        await ctx.send(f"✅ Rol {role.name} quitado")
    except Exception as ex: await ctx.send(f"Error: {ex}")

@bot.command(name="whitelist_pings_add")
async def whitelist_pings_add(ctx, user_id: str = None):
    if not has_perm(ctx): return
    if not user_id: return await ctx.send("Uso: `_whitelist_pings_add ID`")
    try: uid=int(user_id)
    except: return await ctx.send("ID invalido")
    WHITELIST_PINGS.add(uid)
    save_set(WHITELIST_PINGS_FILE, WHITELIST_PINGS)
    await ctx.send(f"✅ Whitelist pings: `{uid}` ya puede usar @everyone y links")

@bot.command(name="whitelist_pings_remove")
async def whitelist_pings_remove(ctx, user_id: str = None):
    if not has_perm(ctx): return
    if not user_id: return await ctx.send("Uso: `_whitelist_pings_remove ID`")
    try: uid=int(user_id)
    except: return await ctx.send("ID invalido")
    if uid in WHITELIST_PINGS:
        WHITELIST_PINGS.remove(uid)
        save_set(WHITELIST_PINGS_FILE, WHITELIST_PINGS)
        await ctx.send(f"❌ Whitelist pings: `{uid}` removido")
    else: await ctx.send("No estaba en la lista")

@bot.command(name="whitelist_pings_list")
async def whitelist_pings_list(ctx):
    if not has_perm(ctx): return
    if not WHITELIST_PINGS: return await ctx.send("📭 Whitelist pings vacía")
    lines=[]
    for uid in WHITELIST_PINGS:
        try:
            u=bot.get_user(uid) or await bot.fetch_user(uid)
            name=u.name if u else f"ID {uid}"
        except: name=f"ID {uid}"
        lines.append(f"{name} (`{uid}`)")
    await ctx.send("**Whitelist Pings:**\n" + "\n".join(lines))

@bot.command(name="whitelist_roles_add")
async def whitelist_roles_add(ctx, user_id: str = None):
    if not has_perm(ctx): return
    if not user_id: return await ctx.send("Uso: `_whitelist_roles_add ID`")
    try: uid=int(user_id)
    except: return await ctx.send("ID invalido")
    WHITELIST_ROLES.add(uid)
    save_set(WHITELIST_ROLES_FILE, WHITELIST_ROLES)
    await ctx.send(f"✅ Whitelist roles: `{uid}` ya puede dar roles peligrosos")

@bot.command(name="whitelist_roles_remove")
async def whitelist_roles_remove(ctx, user_id: str = None):
    if not has_perm(ctx): return
    if not user_id: return await ctx.send("Uso: `_whitelist_roles_remove ID`")
    try: uid=int(user_id)
    except: return await ctx.send("ID invalido")
    if uid in WHITELIST_ROLES:
        WHITELIST_ROLES.remove(uid)
        save_set(WHITELIST_ROLES_FILE, WHITELIST_ROLES)
        await ctx.send(f"❌ Whitelist roles: `{uid}` removido")
    else: await ctx.send("No estaba en la lista")

@bot.command(name="whitelist_roles_list")
async def whitelist_roles_list(ctx):
    if not has_perm(ctx): return
    if not WHITELIST_ROLES: return await ctx.send("📭 Whitelist roles vacía")
    lines=[]
    for uid in WHITELIST_ROLES:
        try:
            u=bot.get_user(uid) or await bot.fetch_user(uid)
            name=u.name if u else f"ID {uid}"
        except: name=f"ID {uid}"
        lines.append(f"{name} (`{uid}`)")
    await ctx.send("**Whitelist Roles:**\n" + "\n".join(lines))

@bot.command(name="role_inmune_add")
async def role_inmune_add(ctx, role_id: str = None):
    if not has_perm(ctx): return
    if not role_id: return await ctx.send("Uso: _role_inmune_add ID")
    try:
        rid=int(role_id)
        role=ctx.guild.get_role(rid)
        if not role: return await ctx.send(f"No encontré rol {rid}")
    except: return await ctx.send("ID invalido")
    IMMUNE_ROLES.add(rid)
    save_set(ROLE_IMMUNE_FILE, IMMUNE_ROLES)
    await ctx.send(f"Rol inmune {role.mention} agregado")

@bot.command(name="role_inmune_remove")
async def role_inmune_remove(ctx, role_id: str = None):
    if not has_perm(ctx): return
    if not role_id: return await ctx.send("Uso: _role_inmune_remove ID")
    try: rid=int(role_id)
    except: return await ctx.send("ID invalido")
    if rid in IMMUNE_ROLES:
        IMMUNE_ROLES.remove(rid)
        save_set(ROLE_IMMUNE_FILE, IMMUNE_ROLES)
        await ctx.send(f"Rol {rid} ya no es inmune")

@bot.command(name="role_inmune_list")
async def role_inmune_list(ctx):
    if not has_perm(ctx): return
    if not IMMUNE_ROLES: return await ctx.send("Vacía")
    lines=[]
    for rid in IMMUNE_ROLES:
        r=ctx.guild.get_role(rid)
        lines.append(f"{r.mention} (`{rid}`)" if r else f"ID {rid}")
    await ctx.send("\n".join(lines))

@bot.command(name="owner_list")
async def owner_list(ctx):
    if ctx.author.id!=MY_ID: return
    lines=[]
    for uid in OWNER_IDS:
        try:
            u=bot.get_user(uid) or await bot.fetch_user(uid)
            name=u.name if u else f"ID {uid}"
        except: name=f"ID {uid}"
        lines.append(f"{name} (`{uid}`)")
    await ctx.send("\n".join(lines))

@bot.command(name="owner_add")
async def owner_add(ctx, user_id: str):
    if ctx.author.id!=MY_ID: return
    uid=int(user_id)
    OWNER_IDS.add(uid)
    save_owners()
    await ctx.send(f"Owner Added {uid}")

@bot.command(name="owner_remove")
async def owner_remove(ctx, user_id: str = None):
    if ctx.author.id!= MY_ID: return
    if not user_id: return await ctx.send("Uso: `_owner_remove ID`")
    try: uid=int(user_id)
    except: return await ctx.send("ID invalido")
    if uid == MY_ID: return await ctx.send("No puedes quitarte a ti mismo")
    if uid in OWNER_IDS:
        OWNER_IDS.remove(uid)
        save_owners()
        await ctx.send(f"❌ Owner removido: `{uid}`")
    else:
        await ctx.send("No estaba en la lista")

@bot.command(name="backup")
async def backup(ctx, action: str = None):
    if not has_perm(ctx): return
    path=f"{BACKUP_DIR}/{ctx.guild.id}.json"
    if action=="create":
        p=await auto_backup(ctx.guild)
        await ctx.send(f"Backup creado", file=discord.File(p))
    elif action=="load":
        if not os.path.exists(path): return await ctx.send("No hay backup")
        with open(path,"r",encoding="utf-8") as f: data=json.load(f)
        for r in data["roles"]:
            if r["name"] not in [x.name for x in ctx.guild.roles]:
                try:
                    await ctx.guild.create_role(name=r["name"], colour=discord.Colour(r["color"]), permissions=discord.Permissions(r["permissions"]), hoist=r["hoist"], mentionable=r["mentionable"])
                    await asyncio.sleep(0.3)
                except: pass
        await ctx.send("Backup cargado")

@bot.command(name="userinfo")
async def userinfo(ctx, user_id: str = None):
    if not has_perm(ctx): return
    try:
        if user_id:
            uid=int(user_id)
            member=ctx.guild.get_member(uid) or await ctx.guild.fetch_member(uid)
        else:
            member=ctx.author
        roles = ", ".join([r.mention for r in member.roles if not r.is_default()][:10])
        e = discord.Embed(title=f"👤 {member}", color=0x2b2d31)
        e.set_thumbnail(url=member.display_avatar.url)
        e.add_field(name="ID", value=f"`{member.id}`", inline=True)
        e.add_field(name="Cuenta creada", value=f"<t:{int(member.created_at.timestamp())}:R>", inline=True)
        e.add_field(name="Se unió", value=f"<t:{int(member.joined_at.timestamp())}:R>" if member.joined_at else "N/A", inline=True)
        e.add_field(name=f"Roles [{len(member.roles)-1}]", value=roles or "Ninguno", inline=False)
        e.add_field(name="¿Es inmune?", value="✅ Sí" if has_immune_role(ctx.guild, member.id) else "❌ No", inline=True)
        e.add_field(name="¿Es Owner?", value="✅ Sí" if member.id in OWNER_IDS else "❌ No", inline=True)
        await ctx.send(embed=e)
    except Exception as ex: await ctx.send(f"Error: {ex}")

@bot.command(name="serverinfo")
async def serverinfo(ctx):
    if not has_perm(ctx): return
    g=ctx.guild
    e=discord.Embed(title=f"📊 {g.name}", color=0x2b2d31)
    if g.icon: e.set_thumbnail(url=g.icon.url)
    e.add_field(name="ID", value=f"`{g.id}`", inline=True)
    e.add_field(name="Owner", value=f"<@{g.owner_id}>", inline=True)
    e.add_field(name="Creado", value=f"<t:{int(g.created_at.timestamp())}:R>", inline=True)
    e.add_field(name="Miembros", value=f"👥 {g.member_count}", inline=True)
    e.add_field(name="Canales", value=f"📁 {len(g.channels)}", inline=True)
    e.add_field(name="Roles", value=f"🎭 {len(g.roles)}", inline=True)
    e.add_field(name="Boosts", value=f"✨ {g.premium_subscription_count}", inline=True)
    e.add_field(name="Emojis", value=f"😀 {len(g.emojis)}", inline=True)
    await ctx.send(embed=e)

@bot.command(name="ban")
async def ban_cmd(ctx, user_id: str = None, *, reason: str = "No reason"):
    if not has_perm(ctx): return
    if not user_id: return await ctx.send("Uso: `_ban ID razon`")
    try:
        uid=int(user_id)
        if is_safe(uid, ctx.guild.owner_id): return await ctx.send("No puedo banear a owner/inmune")
        m=ctx.guild.get_member(uid) or await ctx.guild.fetch_member(uid)
        await ctx.guild.ban(m, reason=reason)
        await ctx.send(f"🔨 Baneado `{uid}` | {reason}")
    except Exception as ex: await ctx.send(f"Error: {ex}")

@bot.command(name="unban")
async def unban_cmd(ctx, user_id: str = None):
    if not has_perm(ctx): return
    if not user_id: return await ctx.send("Uso: `_unban ID`")
    try:
        uid=int(user_id)
        user=await bot.fetch_user(uid)
        await ctx.guild.unban(user)
        await ctx.send(f"✅ Unbaneado `{uid}`")
    except Exception as ex: await ctx.send(f"Error: {ex}")

@bot.command(name="kick")
async def kick_cmd(ctx, user_id: str = None, *, reason: str = "No reason"):
    if not has_perm(ctx): return
    if not user_id: return await ctx.send("Uso: `_kick ID`")
    try:
        uid=int(user_id)
        if is_safe(uid, ctx.guild.owner_id): return await ctx.send("No puedo kickear a owner/inmune")
        m=ctx.guild.get_member(uid) or await ctx.guild.fetch_member(uid)
        await m.kick(reason=reason)
        await ctx.send(f"👢 Kickeado `{uid}`")
    except Exception as ex: await ctx.send(f"Error: {ex}")

@bot.command(name="purge")
async def purge(ctx, amount: int = 10):
    if not has_perm(ctx): return
    try:
        deleted = await ctx.channel.purge(limit=amount+1)
        await ctx.send(f"🗑️ {len(deleted)-1} mensajes borrados", delete_after=3)
    except Exception as ex: await ctx.send(f"Error: {ex}")

@bot.command(name="lock")
async def lock(ctx):
    if not has_perm(ctx): return
    try:
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
        await ctx.send("🔒 Canal bloqueado")
    except Exception as ex: await ctx.send(f"Error: {ex}")

@bot.command(name="unlock")
async def unlock(ctx):
    if not has_perm(ctx): return
    try:
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
        await ctx.send("🔓 Canal desbloqueado")
    except Exception as ex: await ctx.send(f"Error: {ex}")

@bot.command(name="say")
async def say(ctx, *, text: str = None):
    if not has_perm(ctx): return
    if not text: return
    try: await ctx.message.delete()
    except: pass
    await ctx.send(text)

@bot.command(name="nick")
async def nick(ctx, user_id: str = None, *, new_nick: str = None):
    if not has_perm(ctx): return
    if not user_id or not new_nick: return await ctx.send("Uso: `_nick ID nuevo_nick`")
    try:
        uid=int(user_id)
        m=ctx.guild.get_member(uid) or await ctx.guild.fetch_member(uid)
        await m.edit(nick=new_nick)
        await ctx.send(f"✏️ Nick de {m.mention} cambiado a `{new_nick}`")
    except Exception as ex: await ctx.send(f"Error: {ex}")

@bot.command(name="help")
async def help_cmd(ctx):
    if not has_perm(ctx): return
    embed = discord.Embed(title="📜 PANEL DE COMANDOS - NIVEL 3 BRUTAL", description=f"Bot de <@{MY_ID}> | Prefijo `_`", color=0xff0000)
    embed.add_field(name="🎵 MÚSICA / VOZ [7]", value="`_guardar, _list, _quitar, _join, _leave, _tuputamadre [nombre], _stop`", inline=False)
    embed.add_field(name="🛡️ ROLES [5]", value="`_r_add ID rol, _r_remove ID rol, _role_inmune_add ID, _role_inmune_remove ID, _role_inmune_list`", inline=False)
    embed.add_field(name="✅ WHITELIST [6]", value="`_whitelist_pings_add/remove/list, _whitelist_roles_add/remove/list`", inline=False)
    embed.add_field(name="👑 OWNERS [3]", value="`_owner_add ID, _owner_remove ID, _owner_list`", inline=False)
    embed.add_field(name="🔨 MODERACIÓN [8]", value="`_ban ID, _unban ID, _kick ID, _purge, _lock, _unlock, _say, _nick`", inline=False)
    embed.add_field(name="👤 INFO [2]", value="`_userinfo [ID], _serverinfo`", inline=False)
    embed.add_field(name="💾 BACKUP [1]", value="`_backup create / load`", inline=False)
    embed.add_field(name="☠️ AUDIO", value="**NIVEL 3 BRUTAL:** 30dB + bass 20 + treble 15 + 3x EQ + compressor 30:1", inline=False)
    embed.set_footer(text=f"Total: 32 comandos • Solicitado por {ctx.author}")
    await ctx.send(embed=embed)

@bot.command(name="comandos")
async def comandos_cmd(ctx):
    await help_cmd(ctx)

bot.run(TOKEN)