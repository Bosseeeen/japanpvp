import os
import json
import discord
from discord import app_commands, ui
from discord.ext import commands
from dotenv import load_dotenv

# --- Konfiguration ---
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1413978083253289076
TICKET_SEND_ROLE_ID = 1413978327722623077
TICKET_REPLY_ROLE_ID = 1413978397851521056

# --- Kategori-ID per ticket-typ ---
TICKET_CATEGORIES = {
    "General Question": 1413978940552515644,
    "Bug Report": 1413995862610415718,
    "Player Report": 1413995900040380457,
    "Staff Report": 1413995938141311037
}

TICKET_CHANNEL_ID = 1413978084075376773
TRANSCRIPT_CHANNEL_ID = 1413980613073174760
COUNTER_FILE = "ticket_counter.json"
VALID_TICKET_CATEGORY_IDS = list(TICKET_CATEGORIES.values())

# --- Intents ---
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree
guild = discord.Object(id=GUILD_ID)

# --- Persistens ---
if os.path.exists(COUNTER_FILE):
    with open(COUNTER_FILE, "r") as f:
        ticket_counter = json.load(f)
else:
    ticket_counter = {"count": 0}

def save_counter():
    with open(COUNTER_FILE, "w") as f:
        json.dump(ticket_counter, f)

# --- Close Ticket Confirmation Button ---
class ConfirmCloseView(ui.View):
    def __init__(self, ticket_user, channel):
        super().__init__(timeout=60)  # Stänger efter 60s
        self.ticket_user = ticket_user
        self.channel = channel

    @ui.button(label="Yes, I'm sure", style=discord.ButtonStyle.danger)
    async def confirm_close(self, interaction: discord.Interaction, button: ui.Button):
        transcript_channel = bot.get_channel(TRANSCRIPT_CHANNEL_ID)
        if transcript_channel is None:
            return await interaction.response.send_message("❌ Transcript channel does not exist.", ephemeral=True)

        # Hämta alla meddelanden
        messages = [msg async for msg in self.channel.history(limit=None, oldest_first=True)]
        transcript = ""
        for msg in messages:
            time = msg.created_at.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")  # Lokal tid
            author = msg.author
            content = msg.content
            transcript += f"[{time}] {author}: {content}\n"

        # Spara till temporär fil
        with open("temp_transcript.txt", "w", encoding="utf-8") as f:
            f.write(transcript)

        # Skicka till transcript-kanalen
        await transcript_channel.send(file=discord.File("temp_transcript.txt", filename=f"{self.channel.name}_transcript.txt"))

        # Skicka till användarens DM
        try:
            await self.ticket_user.send(
                content=f"Here is the transcript for your ticket **{self.channel.name}**:",
                file=discord.File("temp_transcript.txt", filename=f"{self.channel.name}_transcript.txt")
            )
        except discord.Forbidden:
            await self.channel.send("❌ Could not send DM to the user. They may have DMs disabled.")

        # Ta bort temp-filen
        os.remove("temp_transcript.txt")

        # Stäng ticket-kanalen
        await self.channel.delete()

# --- Close Ticket View (förstaknappen) ---
class CloseTicketView(ui.View):
    def __init__(self, ticket_user):
        super().__init__(timeout=None)
        self.ticket_user = ticket_user

    @ui.button(label="Close Ticket", style=discord.ButtonStyle.danger)
    async def close_ticket(self, interaction: discord.Interaction, button: ui.Button):
        embed = discord.Embed(
            title="⚠️ Confirm Close ⚠️",
            description="Are you sure that you want to close this ticket?",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True, view=ConfirmCloseView(self.ticket_user, interaction.channel))

# --- Ticket Form ---
class TicketForm(ui.Modal):
    def __init__(self, ticket_type):
        super().__init__(title=f"{ticket_type} Form")
        self.ticket_type = ticket_type

        if ticket_type == "Bug Report":
            self.add_item(ui.TextInput(label="Your Minecraft Name"))
            self.add_item(ui.TextInput(label="Describe the bug, send a video if u can"))
        elif ticket_type == "Staff Report":
            self.add_item(ui.TextInput(label="Your Minecraft Name"))
            self.add_item(ui.TextInput(label="Name of the Staff"))
            self.add_item(ui.TextInput(label="Why are you reporting this staff?"))
        elif ticket_type == "Player Report":
            self.add_item(ui.TextInput(label="Your Minecraft Name"))
            self.add_item(ui.TextInput(label="Name of the Player"))
            self.add_item(ui.TextInput(label="Why are you reporting this player?"))
        else:  # General Question
            self.add_item(ui.TextInput(label="Your Minecraft Name"))
            self.add_item(ui.TextInput(label="Your Question"))

    async def on_submit(self, interaction: discord.Interaction):
        category_id = TICKET_CATEGORIES.get(self.ticket_type)
        category = bot.get_channel(category_id)
        if category is None:
            return await interaction.response.send_message(f"❌ Category for {self.ticket_type} not found.", ephemeral=True)

        ticket_name = f"ticket-{self.ticket_type.lower().replace(' ','-')}-{interaction.user.name}"
        for ch in category.channels:
            if ch.name == ticket_name:
                return await interaction.response.send_message("❌ You already have a ticket open in this category.", ephemeral=True)

        ticket_counter["count"] += 1
        save_counter()

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            discord.utils.get(interaction.guild.roles, id=TICKET_REPLY_ROLE_ID): discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        }

        ticket_channel = await category.create_text_channel(ticket_name, overwrites=overwrites, topic=f"owner:{interaction.user.id}")

        embed = discord.Embed(
            title=f"{self.ticket_type} - Ticket for {interaction.user.name}",
            description="Click the button below to close this ticket.",
            color=discord.Color.red()
        )
        embed.add_field(name="Category:", value=self.ticket_type, inline=False)
        for item in self.children:
            embed.add_field(name=item.label, value=item.value, inline=False)

        await ticket_channel.send(content=f"<@&{TICKET_REPLY_ROLE_ID}> New **{self.ticket_type.lower()} ticket** opened by {interaction.user.mention}!", embed=embed, view=CloseTicketView(interaction.user))
        await interaction.response.send_message(f"✅ {self.ticket_type} ticket created: {ticket_channel.mention}", ephemeral=True)

# --- Ticket Dropdown ---
class TicketTypeSelect(ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=t) for t in TICKET_CATEGORIES.keys()]
        super().__init__(placeholder="Select ticket type...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TicketForm(self.values[0]))

# --- Ticket Button View ---
class TicketButtonView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketTypeSelect())

# --- Rollbegränsning ---
def limited_role_check():
    async def predicate(interaction: discord.Interaction) -> bool:
        return any(role.id == TICKET_SEND_ROLE_ID for role in interaction.user.roles)
    return app_commands.check(predicate)

# --- Event: on_ready ---
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} ({bot.user.id})")
    await tree.sync(guild=None)
    await tree.sync(guild=guild)

    ticket_channel = bot.get_channel(TICKET_CHANNEL_ID)
    if ticket_channel:
        async for msg in ticket_channel.history(limit=50):
            if msg.author == bot.user:
                await msg.delete()
        embed = discord.Embed(title="🎫 Open a Ticket! 🎫", description="Select a ticket type from the dropdown below.", color=discord.Color.red())
        await ticket_channel.send(embed=embed, view=TicketButtonView())

# --- /ticket_send ---
@tree.command(name="ticket_send", description="Send the Open Ticket button")
@limited_role_check()
async def ticket_send(interaction: discord.Interaction):
    ticket_channel = bot.get_channel(TICKET_CHANNEL_ID)
    if ticket_channel is None:
        return await interaction.response.send_message("❌ Ticket channel does not exist.", ephemeral=True)

    async for msg in ticket_channel.history(limit=50):
        if msg.author == bot.user:
            await msg.delete()

    embed = discord.Embed(title="🎫 Open a Ticket!", description="Select a ticket type from the dropdown below.", color=discord.Color.red())
    await ticket_channel.send(embed=embed, view=TicketButtonView())
    await interaction.response.send_message(f"✅ The button is now sent to {ticket_channel.mention}", ephemeral=True)

# --- /add_person och /remove_person commands ---
@tree.command(name="add_person", description="Add a person to your ticket")
async def add_person(interaction: discord.Interaction, member: discord.Member):
    channel = interaction.channel
    if not channel or not any(channel.category_id == cid for cid in VALID_TICKET_CATEGORY_IDS):
        return await interaction.response.send_message("❌ This command can only be used inside a valid ticket channel.", ephemeral=True)

    owner_id = int(channel.topic.split("owner:")[-1].strip()) if channel.topic and "owner:" in channel.topic else None
    is_owner = (owner_id == interaction.user.id)
    is_staff = any(r.id == TICKET_REPLY_ROLE_ID for r in interaction.user.roles)
    if not (is_owner or is_staff):
        return await interaction.response.send_message("❌ Only the ticket owner or staff can add people.", ephemeral=True)

    await channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
    await interaction.response.send_message(f"✅ {member.mention} has been added to this ticket!", ephemeral=True)
    embed = discord.Embed(title="👤 User Added", description=f"{interaction.user.mention} added {member.mention} to this ticket.", color=discord.Color.red())
    await channel.send(embed=embed)
    try:
        dm_embed = discord.Embed(title="🎫 You have been added to a ticket", description=f"You were added to the ticket: {channel.mention}", color=discord.Color.green())
        dm_embed.add_field(name="Added by", value=interaction.user.mention, inline=False)
        dm_embed.add_field(name="Ticket", value=f"[Open ticket]({channel.jump_url})", inline=False)
        await member.send(embed=dm_embed)
    except discord.Forbidden:
        await interaction.followup.send(f"⚠️ Could not DM {member.mention}. They might have DMs disabled.", ephemeral=True)

@tree.command(name="remove_person", description="Remove a person from your ticket")
async def remove_person(interaction: discord.Interaction, member: discord.Member):
    channel = interaction.channel
    if not channel or not any(channel.category_id == cid for cid in VALID_TICKET_CATEGORY_IDS):
        return await interaction.response.send_message("❌ This command can only be used inside a valid ticket channel.", ephemeral=True)

    owner_id = int(channel.topic.split("owner:")[-1].strip()) if channel.topic and "owner:" in channel.topic else None
    is_owner = (owner_id == interaction.user.id)
    is_staff = any(r.id == TICKET_REPLY_ROLE_ID for r in interaction.user.roles)
    if not (is_owner or is_staff):
        return await interaction.response.send_message("❌ Only the ticket owner or staff can remove people.", ephemeral=True)

    await channel.set_permissions(member, overwrite=None)
    await interaction.response.send_message(f"✅ {member.mention} has been removed from this ticket!", ephemeral=True)
    embed = discord.Embed(title="🚫 User Removed", description=f"{interaction.user.mention} removed {member.mention} from this ticket.", color=discord.Color.red())
    await channel.send(embed=embed)
    try:
        dm_embed = discord.Embed(title="🚫 You have been removed from a ticket", description=f"You were removed from the ticket: **{channel.name}**", color=discord.Color.red())
        dm_embed.add_field(name="Removed by", value=interaction.user.mention, inline=False)
        dm_embed.add_field(name="Ticket (no longer accessible)", value=channel.name, inline=False)
        await member.send(embed=dm_embed)
    except discord.Forbidden:
        await interaction.followup.send(f"⚠️ Could not DM {member.mention}. They might have DMs disabled.", ephemeral=True)

# --- Starta botten ---
bot.run(TOKEN)
