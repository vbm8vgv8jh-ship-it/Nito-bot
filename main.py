import os, json, discord, asyncio, time
from discord.ext import commands
from datetime import datetime, timezone
from collections import defaultdict

TOKEN = os.getenv("DISCORD_BOT_TOKEN") or os.getenv("TOKEN") or os.getenv("DISCORD_TOKEN")
MY_ID = 1310357536087740450
OWNER_FILE="owners.json"
WHITELIST_FILE="whitelist.json"

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
bot=commands.Bot(command_prefix="!",intents=intents,help_command=None)

# EMBED ESTETICO TIPO NITO
def bubble(text):
    return discord.Embed(description=text, color=0x2B2D31)

# ANTINUKE CONFIG - 4+ EN 10s
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

def sync_owners():
    o=load_owners(); o.add(MY_ID); OWNER_IDS.clear(); OWNER_IDS.update(o); return o
def has_perm(ctx): return ctx.author.id in sync_owners()
def has_interaction_perm(i): return i.user.id in sync_owners()

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Listo {bot.user}")

# --- ANTINUKE EVENTS (igual que antes) ---
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

# --- COMANDOS CON BURBUJA ---
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
    await ctx.send(embed=bubble(f"urssian ( `{user_id}` ) added as owner"))
@bot.command(name="owner_remove")
async def owner_remove(ctx,user_id:str):
    if ctx.author.id!=MY_ID: return
    uid=int(user_id)
    if uid!=MY_ID and uid in OWNER_IDS:
        OWNER_IDS.remove(uid); save_owners()
        await ctx.send(embed=bubble(f"( `{uid}` )\ndeleted as owner"))
@bot.command(name="owner_list")
async def owner_list(ctx):
    if ctx.author.id!=MY_ID: return
    text = "\n".join(f"<@{u}> - ( `{u}` )" for u in OWNER_IDS)
    await ctx.send(embed=bubble(f"**Owners:**\n{text}"))
@bot.command(name="whitelist_add")
async def whitelist_add(ctx,user_id:str):
    if ctx.author.id!=MY_ID: return
    WHITELIST_IDS.add(int(user_id)); save_whitelist()
    await ctx.send(embed=bubble(f"( `{user_id}` )\nadded to whitelist"))
@bot.command(name="whitelist_remove")
async def whitelist_remove(ctx,user_id:str):
    if ctx.author.id!=MY_ID: return
    uid=int(user_id)
    if uid in WHITELIST_IDS:
        WHITELIST_IDS.remove(uid); save_whitelist()
        await ctx.send(embed=bubble(f"( `{uid}` )\nremoved from whitelist"))
@bot.command(name="whitelist_list")
async def whitelist_list(ctx):
    if ctx.author.id!=MY_ID: return
    if not WHITELIST_IDS:
        await ctx.send(embed=bubble("Whitelist vacía"))
    else:
        text = "\n".join(f"<@{u}> - ( `{u}` )" for u in WHITELIST_IDS)
        await ctx.send(embed=bubble(f"**Whitelist:**\n{text}"))

# SLASH CON BURBUJA
@bot.tree.command(name="ban",description="Banear")
async def slash_ban(interaction:discord.Interaction,usuario:discord.Member,razon:str="Sin razón"):
    if not has_interaction_perm(interaction): return await interaction.response.send_message(embed=bubble("No tienes permiso"), ephemeral=True)
    await interaction.guild.ban(usuario,reason=razon)
    await interaction.response.send_message(embed=bubble(f"🔨 {usuario.mention} baneado\n`{razon}`"))
@bot.tree.command(name="kick",description="Kickear")
async def slash_kick(interaction:discord.Interaction,usuario:discord.Member,razon:str="Sin razón"):
    if not has_interaction_perm(interaction): return await interaction.response.send_message(embed=bubble("No tienes permiso"), ephemeral=True)
    await usuario.kick(reason=razon)
    await interaction.response.send_message(embed=bubble(f"👢 {usuario.mention} kickeado\n`{razon}`"))
@bot.tree.command(name="owner_add",description="Agregar owner")
async def slash_owner_add(interaction:discord.Interaction,user_id:str):
    if interaction.user.id!=MY_ID: return await interaction.response.send_message(embed=bubble("Solo tu"), ephemeral=True)
    OWNER_IDS.add(int(user_id)); save_owners()
    await interaction.response.send_message(embed=bubble(f"urssian ( `{user_id}` ) added as owner"))
@bot.tree.command(name="owner_remove",description="Quitar owner")
async def slash_owner_remove(interaction:discord.Interaction,user_id:str):
    if interaction.user.id!=MY_ID: return await interaction.response.send_message(embed=bubble("Solo tu"), ephemeral=True)
    OWNER_IDS.remove(int(user_id)); save_owners()
    await interaction.response.send_message(embed=bubble(f"( `{user_id}` )\ndeleted as owner"))
@bot.tree.command(name="owner_list",description="Ver owners")
async def slash_owner_list(interaction:discord.Interaction):
    if interaction.user.id!=MY_ID: return await interaction.response.send_message(embed=bubble("Solo tu"), ephemeral=True)
    text = "\n".join(f"<@{u}> - ( `{u}` )" for u in OWNER_IDS)
    await interaction.response.send_message(embed=bubble(f"**Owners:**\n{text}"), ephemeral=True)
@bot.tree.command(name="whitelist_add",description="Dar whitelist")
async def slash_whitelist_add(interaction:discord.Interaction,user_id:str):
    if interaction.user.id!=MY_ID: return await interaction.response.send_message(embed=bubble("Solo tu"), ephemeral=True)
    WHITELIST_IDS.add(int(user_id)); save_whitelist()
    await interaction.response.send_message(embed=bubble(f"( `{user_id}` )\nadded to whitelist"))
@bot.tree.command(name="whitelist_remove",description="Quitar whitelist")
async def slash_whitelist_remove(interaction:discord.Interaction,user_id:str):
    if interaction.user.id!=MY_ID: return await interaction.response.send_message(embed=bubble("Solo tu"), ephemeral=True)
    uid=int(user_id)
    if uid in WHITELIST_IDS:
        WHITELIST_IDS.remove(uid); save_whitelist()
        await interaction.response.send_message(embed=bubble(f"( `{uid}` )\nremoved from whitelist"))
@bot.tree.command(name="whitelist_list",description="Ver whitelist")
async def slash_whitelist_list(interaction:discord.Interaction):
    if interaction.user.id!=MY_ID: return await interaction.response.send_message(embed=bubble("Solo tu"), ephemeral=True)
    if not WHITELIST_IDS:
        await interaction.response.send_message(embed=bubble("Whitelist vacía"), ephemeral=True)
    else:
        text = "\n".join(f"<@{u}> - ( `{u}` )" for u in WHITELIST_IDS)
        await interaction.response.send_message(embed=bubble(f"**Whitelist:**\n{text}"), ephemeral=True)

bot.run(TOKEN)
