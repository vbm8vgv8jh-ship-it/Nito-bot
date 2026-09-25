import os, json, discord
from discord.ext import commands
from datetime import datetime, timezone

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

def sync_owners():
    o=load_owners(); o.add(MY_ID); OWNER_IDS.clear(); OWNER_IDS.update(o); return o
def has_perm(ctx): return ctx.author.id in sync_owners()
def has_interaction_perm(i): return i.user.id in sync_owners()

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Listo {bot.user} - AntiRole ON")

@bot.event
async def on_member_update(before,after):
    if after.bot: return
    if len(before.roles) == len(after.roles): return

    added=[r for r in after.roles if r not in before.roles]
    removed=[r for r in before.roles if r not in after.roles]
    all_changed = added + removed

    # Solo si el rol es peligroso
    dangerous_roles = []
    for r in all_changed:
        if r.permissions.administrator or r.permissions.ban_members or r.permissions.kick_members or r.permissions.manage_roles or r.permissions.manage_guild or r.permissions.manage_channels:
            dangerous_roles.append(r)

    if not dangerous_roles: return

    await discord.utils.sleep_until(datetime.now(timezone.utc)) # pequeña espera para que salga el audit log
    try:
        async for entry in after.guild.audit_logs(limit=3,action=discord.AuditLogAction.member_role_update):
            if (datetime.now(timezone.utc)-entry.created_at).total_seconds()>10: continue
            if entry.target.id!= after.id: continue

            executor=entry.user
            if executor.bot: return
            if executor.id==MY_ID or executor.id in OWNER_IDS or executor.id in WHITELIST_IDS or executor.id == after.guild.owner_id:
                return

            # Restaura roles y kickea
            try:
                await after.edit(roles=before.roles,reason="Anti-Role: Rol peligroso sin whitelist")
            except Exception as e:
                print(f"No pude restaurar roles: {e}")

            try:
                await after.guild.kick(executor,reason=f"Anti-Role: dio/quito rol {dangerous_roles[0].name} a {after} sin whitelist")
                print(f"Anti-Role: Kickeado {executor} por tocar {dangerous_roles[0].name}")
            except Exception as e:
                print(f"No pude kickear: {e}")
            return
    except Exception as e:
        print(f"Error Anti-Role: {e}")

@bot.command(name="ban")
async def ban(ctx,m:discord.Member,*,reason="Sin razón"):
    if not has_perm(ctx): return
    await ctx.guild.ban(m,reason=reason); await ctx.send(f"🔨 {m.mention} baneado")
@bot.command(name="kick")
async def kick(ctx,m:discord.Member,*,reason="Sin razón"):
    if not has_perm(ctx): return
    await m.kick(reason=reason); await ctx.send(f"👢 {m.mention} kickeado")
@bot.command(name="owner_add")
async def owner_add(ctx,user_id:str):
    if ctx.author.id!=MY_ID: return
    OWNER_IDS.add(int(user_id)); save_owners(); await ctx.send(f"( {user_id} )\nadded as owner")
@bot.command(name="owner_remove")
async def owner_remove(ctx,user_id:str):
    if ctx.author.id!=MY_ID: return
    uid=int(user_id)
    if uid!=MY_ID and uid in OWNER_IDS: OWNER_IDS.remove(uid); save_owners(); await ctx.send(f"( {uid} )\ndeleted as owner")
@bot.command(name="owner_list")
async def owner_list(ctx):
    if ctx.author.id!=MY_ID: return
    await ctx.send("Owners:\n"+"\n".join(f"<@{u}>" for u in OWNER_IDS))
@bot.command(name="whitelist_add")
async def whitelist_add(ctx,user_id:str):
    if ctx.author.id!=MY_ID: return
    WHITELIST_IDS.add(int(user_id)); save_whitelist(); await ctx.send(f"( {user_id} )\nadded to whitelist")
@bot.command(name="whitelist_remove")
async def whitelist_remove(ctx,user_id:str):
    if ctx.author.id!=MY_ID: return
    uid=int(user_id)
    if uid in WHITELIST_IDS: WHITELIST_IDS.remove(uid); save_whitelist(); await ctx.send(f"( {uid} )\nremoved from whitelist")
@bot.command(name="whitelist_list")
async def whitelist_list(ctx):
    if ctx.author.id!=MY_ID: return
    await ctx.send("Whitelist vacía" if not WHITELIST_IDS else "Whitelist:\n"+"\n".join(f"<@{u}> - ( {u} )" for u in WHITELIST_IDS))

@bot.tree.command(name="ban",description="Banear")
async def slash_ban(interaction:discord.Interaction,usuario:discord.Member,razon:str="Sin razón"):
    if not has_interaction_perm(interaction): return await interaction.response.send_message("No tienes permiso",ephemeral=True)
    await interaction.guild.ban(usuario,reason=razon); await interaction.response.send_message(f"🔨 {usuario.mention} baneado")
@bot.tree.command(name="kick",description="Kickear")
async def slash_kick(interaction:discord.Interaction,usuario:discord.Member,razon:str="Sin razón"):
    if not has_interaction_perm(interaction): return await interaction.response.send_message("No tienes permiso",ephemeral=True)
    await usuario.kick(reason=razon); await interaction.response.send_message(f"👢 {usuario.mention} kickeado")
@bot.tree.command(name="owner_add",description="Agregar owner")
async def slash_owner_add(interaction:discord.Interaction,user_id:str):
    if interaction.user.id!=MY_ID: return await interaction.response.send_message("Solo tu",ephemeral=True)
    OWNER_IDS.add(int(user_id)); save_owners(); await interaction.response.send_message(f"( {user_id} )\nadded as owner")
@bot.tree.command(name="owner_remove",description="Quitar owner")
async def slash_owner_remove(interaction:discord.Interaction,user_id:str):
    if interaction.user.id!=MY_ID: return await interaction.response.send_message("Solo tu",ephemeral=True)
    OWNER_IDS.remove(int(user_id)); save_owners(); await interaction.response.send_message(f"( {user_id} )\ndeleted as owner")
@bot.tree.command(name="owner_list",description="Ver owners")
async def slash_owner_list(interaction:discord.Interaction):
    if interaction.user.id!=MY_ID: return await interaction.response.send_message("Solo tu",ephemeral=True)
    await interaction.response.send_message("Owners:\n"+"\n".join(f"<@{u}>" for u in OWNER_IDS),ephemeral=True)
@bot.tree.command(name="whitelist_add",description="Dar whitelist")
async def slash_whitelist_add(interaction:discord.Interaction,user_id:str):
    if interaction.user.id!=MY_ID: return await interaction.response.send_message("Solo tu",ephemeral=True)
    WHITELIST_IDS.add(int(user_id)); save_whitelist(); await interaction.response.send_message(f"( {user_id} )\nadded to whitelist")
@bot.tree.command(name="whitelist_remove",description="Quitar whitelist")
async def slash_whitelist_remove(interaction:discord.Interaction,user_id:str):
    if interaction.user.id!=MY_ID: return await interaction.response.send_message("Solo tu",ephemeral=True)
    uid=int(user_id)
    if uid in WHITELIST_IDS: WHITELIST_IDS.remove(uid); save_whitelist(); await interaction.response.send_message(f"( {uid} )\nremoved from whitelist")
@bot.tree.command(name="whitelist_list",description="Ver whitelist")
async def slash_whitelist_list(interaction:discord.Interaction):
    if interaction.user.id!=MY_ID: return await interaction.response.send_message("Solo tu",ephemeral=True)
    if not WHITELIST_IDS: return await interaction.response.send_message("Whitelist vacía",ephemeral=True)
    await interaction.response.send_message("Whitelist:\n"+"\n".join(f"<@{u}> - ( {u} )" for u in WHITELIST_IDS),ephemeral=True)

bot.run(TOKEN)
