import os
import json
import time
import hashlib
import requests
from datetime import datetime
import discord
from discord import app_commands
from discord.ui import Button, View, Select
from discord.ext import tasks
import asyncio
import feedparser
import re
from html import unescape
from email.utils import parsedate_to_datetime

# Configuration from environment variables
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
DISCORD_CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID', '0'))
ADMIN_USER_IDS = [int(uid.strip()) for uid in os.getenv('ADMIN_USER_IDS', '').split(',') if uid.strip()]
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '7200'))  # seconds (default: 2 hours)
SEND_TEST_NOTIFICATION = os.getenv('SEND_TEST_NOTIFICATION', 'true').lower() == 'true'
SEND_STARTUP_RSS_NOTIFICATIONS = os.getenv('SEND_STARTUP_RSS_NOTIFICATIONS', 'false').lower() == 'true'

SUBSCRIPTIONS_FILE = '/app/data/subscriptions.json'
COMICS_FILE = '/app/data/comics.json'

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
monitor_started = False

# Comic configuration management
def initialize_data_files():
    """Initialize JSON files if they don't exist"""
    import os
    
    # Create data directory if it doesn't exist
    data_dir = '/app/data'
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        print(f"Created data directory: {data_dir}")
    
    # Initialize comics.json if it doesn't exist
    if not os.path.exists(COMICS_FILE):
        with open(COMICS_FILE, 'w') as f:
            json.dump({}, f, indent=2)
        print(f"Created {COMICS_FILE} (empty - use /addcomic to add comics)")
    
    # Initialize subscriptions.json if it doesn't exist
    if not os.path.exists(SUBSCRIPTIONS_FILE):
        with open(SUBSCRIPTIONS_FILE, 'w') as f:
            json.dump({}, f, indent=2)
        print(f"Created {SUBSCRIPTIONS_FILE}")

def load_comics():
    """Load comics configuration from JSON file"""
    try:
        if os.path.exists(COMICS_FILE):
            with open(COMICS_FILE, 'r') as f:
                comics = json.load(f)
                # Ensure all comics have the show_caption field (default True)
                for comic_id in comics:
                    if 'show_caption' not in comics[comic_id]:
                        comics[comic_id]['show_caption'] = True
                return comics
    except Exception as e:
        print(f"Error loading comics: {e}")
    return {}

def save_comics(comics):
    """Save comics configuration to JSON file"""
    try:
        with open(COMICS_FILE, 'w') as f:
            json.dump(comics, f, indent=2)
    except Exception as e:
        print(f"Error saving comics: {e}")

def get_enabled_comics():
    """Get dictionary of enabled comics only"""
    comics = load_comics()
    return {cid: comic for cid, comic in comics.items() if comic.get('enabled', True)}

# Subscription management
def load_subscriptions():
    """Load subscriptions from JSON file"""
    try:
        if os.path.exists(SUBSCRIPTIONS_FILE):
            with open(SUBSCRIPTIONS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading subscriptions: {e}")
    return {}

def save_subscriptions(subscriptions):
    """Save subscriptions to JSON file"""
    try:
        with open(SUBSCRIPTIONS_FILE, 'w') as f:
            json.dump(subscriptions, f, indent=2)
    except Exception as e:
        print(f"Error saving subscriptions: {e}")

def get_subscribed_users(comic_id):
    """Get list of user IDs subscribed to a specific comic"""
    subscriptions = load_subscriptions()
    users = []
    for user_id, comics in subscriptions.items():
        if comic_id in comics:
            users.append(user_id)
    return users

def add_subscription(user_id, comic_ids):
    """Add comic subscriptions for a user"""
    subscriptions = load_subscriptions()
    user_id_str = str(user_id)
    
    if user_id_str not in subscriptions:
        subscriptions[user_id_str] = []
    
    for comic_id in comic_ids:
        if comic_id not in subscriptions[user_id_str]:
            subscriptions[user_id_str].append(comic_id)
    
    save_subscriptions(subscriptions)

def remove_subscription(user_id, comic_ids):
    """Remove comic subscriptions for a user"""
    subscriptions = load_subscriptions()
    user_id_str = str(user_id)
    
    if user_id_str in subscriptions:
        for comic_id in comic_ids:
            if comic_id in subscriptions[user_id_str]:
                subscriptions[user_id_str].remove(comic_id)
        
        # Remove user entry if no subscriptions left
        if not subscriptions[user_id_str]:
            del subscriptions[user_id_str]
    
    save_subscriptions(subscriptions)

def get_user_subscriptions(user_id):
    """Get list of comics a user is subscribed to"""
    subscriptions = load_subscriptions()
    user_id_str = str(user_id)
    # Filter to only show enabled comics
    all_subs = subscriptions.get(user_id_str, [])
    enabled_comics = get_enabled_comics()
    return [cid for cid in all_subs if cid in enabled_comics]

def is_admin(user_id):
    """Check if user is an admin"""
    return user_id in ADMIN_USER_IDS

def parse_color(color_input):
    """Parse color input and return hex string in format '0xRRGGBB'"""
    # Predefined color names
    color_presets = {
        'red': 'FF0000',
        'green': '00FF00',
        'blue': '0000FF',
        'black': '000000',
        'white': 'FFFFFF',
        'lightgreen': 'AAE5A4',
        'lightblue': '00BBFF',
        'purple': '6600FF',
        'pink': 'FF00FB',
        'yellow': 'FFFF00',
        'orange': 'FF7B00'
    }
    
    # Check if it's a preset color name
    color_lower = color_input.lower().strip()
    if color_lower in color_presets:
        return f"0x{color_presets[color_lower]}"
    
    # Remove any whitespace
    color_input = color_input.strip()
    
    # Handle different formats
    if color_input.startswith('0x'):
        # Already in 0xRRGGBB format
        hex_part = color_input[2:]
    elif color_input.startswith('#'):
        # #RRGGBB format
        hex_part = color_input[1:]
    else:
        # Assume RRGGBB format
        hex_part = color_input
    
    # Validate hex part is 6 characters and valid hex
    if len(hex_part) != 6:
        return None
    
    try:
        int(hex_part, 16)
        return f"0x{hex_part.upper()}"
    except ValueError:
        return None

# Helper functions
def get_content_hash(url):
    """Fetch URL content and return its hash"""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return hashlib.sha256(response.text.encode()).hexdigest()
    except Exception as e:
        print(f"Error fetching URL: {e}")
        return None

def extract_caption_from_html(html_content):
    """Extract the first meaningful caption/text from HTML content"""
    if not html_content:
        return None
    
    text = re.sub(r'<[^>]+>', '', html_content)
    text = unescape(text)
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    for line in lines:
        if line and not line.startswith('http') and len(line) > 10:
            if len(line) > 200:
                return line[:197] + "..."
            return line
    
    return None

def format_publish_date(date_string):
    """Format publish date to 'D MMM YYYY HH:MM (UTC)' format"""
    if not date_string:
        return None
    
    try:
        dt = parsedate_to_datetime(date_string)
        dt_utc = dt.astimezone(datetime.now().astimezone().tzinfo).astimezone()
        return dt_utc.strftime('%d %b %Y %H:%M (UTC)')
    except Exception as e:
        print(f"Error formatting date '{date_string}': {e}")
        return date_string

def get_latest_rss_entry(rss_url):
    """Fetch RSS feed and return the latest entry"""
    try:
        feed = feedparser.parse(rss_url)
        if feed.entries:
            latest = feed.entries[0]
            
            # Try to extract caption from content or description
            caption = None
            if hasattr(latest, 'content') and latest.content:
                caption = extract_caption_from_html(latest.content[0].value)
            elif hasattr(latest, 'description'):
                caption = extract_caption_from_html(latest.description)
            
            return {
                'title': latest.get('title', 'No title'),
                'description': latest.get('description', 'No description'),
                'caption': caption,
                'link': latest.get('link', ''),
                'pubDate': latest.get('published', ''),
                'guid': latest.get('guid', '')
            }
        return None
    except Exception as e:
        print(f"Error fetching RSS feed: {e}")
        return None

# Generic notification functions
async def send_test_notification(channel):
    """Send a test notification to Discord channel"""
    comics = get_enabled_comics()
    comic_names = ', '.join([c['name'] for c in comics.values()])
    
    embed = discord.Embed(
        title="Webcomic Update Monitoring System is Online!",
        description=f"Currently monitoring: {comic_names}\n\nUse `/subscribe` to get notified about updates!",
        color=0x3498DB,
        url="http://chihuahuaspin.com/"
    )
    
    view = View(timeout=None)
    button = Button(label="Don't click me", style=discord.ButtonStyle.url, url="http://chihuahuaspin.com/")
    view.add_item(button)
    
    try:
        await channel.send(embed=embed, view=view)
        print("Test notification sent successfully")
    except Exception as e:
        print(f"Error sending test notification: {e}")

async def send_html_update_notification(channel, comic_id, comic):
    """Send HTML-based comic update notification"""
    alarm = "\U0001F6A8"
    subscribed_users = get_subscribed_users(comic_id)
    mentions = " ".join([f"<@{user_id}>" for user_id in subscribed_users])
    
    embed = discord.Embed(
        title=f"{alarm} NEW {comic['name'].upper()} UPDATE (maybe) {alarm}",
        description=f"There might be a new {comic['name']} update, or this could be a false alarm. Either way, check it out!",
        color=int(comic['color'], 16),
        url=comic['url']
    )
    
    view = View(timeout=None)
    button = Button(label="Check it out!", style=discord.ButtonStyle.url, url=comic['url'])
    view.add_item(button)
    
    try:
        content = mentions if mentions else None
        await channel.send(content=content, embed=embed, view=view)
        print(f"{comic['name']} update notification sent successfully")
    except Exception as e:
        print(f"Error sending {comic['name']} update notification: {e}")

async def send_rss_update_notification(channel, comic_id, comic, entry):
    """Send RSS-based comic update notification"""
    alarm = "\U0001F6A8"
    subscribed_users = get_subscribed_users(comic_id)
    mentions = " ".join([f"<@{user_id}>" for user_id in subscribed_users])
    
    # Build description
    description = f"**{entry['title']}**"
    
    # Only add caption if show_caption is True and caption exists
    if comic.get('show_caption', True) and entry['caption']:
        description += f"\n\n*{entry['caption']}*"
    
    embed = discord.Embed(
        title=f"{alarm} NEW {comic['name'].upper()} UPDATE {alarm}",
        description=description,
        color=int(comic['color'], 16),
        url=entry['link']
    )
    
    formatted_date = format_publish_date(entry['pubDate'])
    if formatted_date:
        embed.add_field(name="Published", value=formatted_date, inline=False)
    
    view = View(timeout=None)
    button = Button(label="Read the comic!", style=discord.ButtonStyle.url, url=entry['link'])
    view.add_item(button)
    
    try:
        content = mentions if mentions else None
        await channel.send(content=content, embed=embed, view=view)
        print(f"{comic['name']} update notification sent successfully")
    except Exception as e:
        print(f"Error sending {comic['name']} update notification: {e}")

async def send_error_notification(channel, comic_name, url, error_message):
    """Send error notification to Discord channel"""
    embed = discord.Embed(
        title=f"⚠️ {comic_name} Monitoring Error",
        description=f"There was a problem checking {comic_name}. The site may be rate limiting requests or temporarily unavailable.\n\n**Error details:** {error_message}",
        color=0xE74C3C,
        url=url
    )
    
    view = View(timeout=None)
    button = Button(label="Check the site manually", style=discord.ButtonStyle.url, url=url)
    view.add_item(button)
    
    try:
        await channel.send(embed=embed, view=view)
        print(f"{comic_name} error notification sent successfully")
    except Exception as e:
        print(f"Error sending {comic_name} error notification: {e}")

# Select menu view for subscriptions
class ComicSelectView(View):
    def __init__(self, mode='subscribe', available_comics=None):
        super().__init__(timeout=60)
        
        # Build options directly here
        comics_to_show = available_comics if available_comics is not None else list(get_enabled_comics().keys())
        comics_config = load_comics()
        
        options = [
            discord.SelectOption(
                label=comics_config[comic_id]['name'],
                value=comic_id,
                description=f"{'Get notified for' if mode == 'subscribe' else 'Unsubscribe from'} {comics_config[comic_id]['name']} updates"
            )
            for comic_id in comics_to_show if comic_id in comics_config
        ]
        
        # Create select with options directly
        select = Select(
            custom_id=f"comic_select_{mode}",
            placeholder="Choose comics...",
            min_values=1,
            max_values=len(options),
            options=options
        )
        
        # Store mode for callback
        select.mode = mode
        select.callback = self.make_callback(mode)
        
        self.add_item(select)
    
    def make_callback(self, mode):
        async def callback(interaction: discord.Interaction):
            comics_config = load_comics()
            select = interaction.data['values']
            if mode == 'subscribe':
                add_subscription(interaction.user.id, select)
                comic_names = [comics_config[cid]['name'] for cid in select]
                await interaction.response.edit_message(
                    content=f"You're now subscribed to: {', '.join(comic_names)}",
                    view=None
                )
            else:  # unsubscribe
                remove_subscription(interaction.user.id, select)
                comic_names = [comics_config[cid]['name'] for cid in select]
                await interaction.response.edit_message(
                    content=f"Unsubscribed from: {', '.join(comic_names)}",
                    view=None
                )
        return callback

# User slash commands
@tree.command(name="subscribe", description="Subscribe to comic update notifications")
async def subscribe_command(interaction: discord.Interaction):
    current_subs = get_user_subscriptions(interaction.user.id)
    enabled_comics = get_enabled_comics()
    
    # Find comics user is NOT subscribed to
    available_comics = [comic_id for comic_id in enabled_comics.keys() if comic_id not in current_subs]
    
    if not available_comics:
        await interaction.response.send_message(
            "You're already subscribed to all available comics!",
            ephemeral=True
        )
        return
    
    view = ComicSelectView(mode='subscribe', available_comics=available_comics)
    await interaction.response.send_message(
        "Select the comics you want to be notified about:",
        view=view,
        ephemeral=True
    )

@tree.command(name="unsubscribe", description="Unsubscribe from comic update notifications")
async def unsubscribe_command(interaction: discord.Interaction):
    current_subs = get_user_subscriptions(interaction.user.id)
    
    if not current_subs:
        await interaction.response.send_message(
            "You're not subscribed to any comics!",
            ephemeral=True
        )
        return
    
    view = ComicSelectView(mode='unsubscribe', available_comics=current_subs)
    await interaction.response.send_message(
        "Select the comics you want to unsubscribe from:",
        view=view,
        ephemeral=True
    )

@tree.command(name="subscriptions", description="View your current comic subscriptions")
async def subscriptions_command(interaction: discord.Interaction):
    current_subs = get_user_subscriptions(interaction.user.id)
    
    if not current_subs:
        await interaction.response.send_message(
            "You're not subscribed to any comics yet! Use `/subscribe` to get started.",
            ephemeral=True
        )
        return
    
    comics_config = load_comics()
    comic_names = [comics_config[cid]['name'] for cid in current_subs if cid in comics_config]
    await interaction.response.send_message(
        f"You're subscribed to: {', '.join(comic_names)}",
        ephemeral=True
    )

# Admin slash commands
@tree.command(name="listcomics", description="[Admin] List all configured comics")
async def listcomics_command(interaction: discord.Interaction):
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return
    
    comics = load_comics()
    
    if not comics:
        await interaction.response.send_message("No comics configured.", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="Configured Comics",
        color=0x3498DB
    )
    
    for comic_id, comic in comics.items():
        status = "[ENABLED]" if comic.get('enabled', True) else "[DISABLED]"
        caption_status = "[Show captions]" if comic.get('show_caption', True) else "[Hide captions]"
        embed.add_field(
            name=f"{comic['name']} ({comic_id})",
            value=f"Type: {comic['type']}\nStatus: {status}\nCaptions: {caption_status}\nURL: {comic['url'][:50]}...",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="togglecomic", description="[Admin] Enable or disable a comic")
async def togglecomic_command(interaction: discord.Interaction, comic_id: str):
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    
    comics = load_comics()
    
    if comic_id not in comics:
        await interaction.response.send_message(f"Comic '{comic_id}' not found.", ephemeral=True)
        return
    
    # Toggle enabled status
    current_status = comics[comic_id].get('enabled', True)
    comics[comic_id]['enabled'] = not current_status
    save_comics(comics)
    
    new_status = "enabled" if comics[comic_id]['enabled'] else "disabled"
    await interaction.response.send_message(
        f"{comics[comic_id]['name']} is now {new_status}.",
        ephemeral=True
    )

@tree.command(name="togglecaption", description="[Admin] Toggle caption display for a comic")
async def togglecaption_command(interaction: discord.Interaction, comic_id: str):
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    
    comics = load_comics()
    
    if comic_id not in comics:
        await interaction.response.send_message(f"Comic '{comic_id}' not found.", ephemeral=True)
        return
    
    if comics[comic_id]['type'] != 'rss':
        await interaction.response.send_message(f"{comics[comic_id]['name']} is not an RSS comic. Caption toggle only applies to RSS comics.", ephemeral=True)
        return
    
    # Toggle show_caption status
    current_status = comics[comic_id].get('show_caption', True)
    comics[comic_id]['show_caption'] = not current_status
    save_comics(comics)
    
    new_status = "shown" if comics[comic_id]['show_caption'] else "hidden"
    await interaction.response.send_message(
        f"Captions for {comics[comic_id]['name']} will now be {new_status}.",
        ephemeral=True
    )

@tree.command(name="addcomic", description="[Admin] Add a new comic to monitor")
async def addcomic_command(
    interaction: discord.Interaction,
    comic_id: str,
    name: str,
    url: str,
    comic_type: str,
    color: str
):
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    
    # Validate inputs
    if comic_type not in ['html', 'rss']:
        await interaction.response.send_message("Type must be 'html' or 'rss'.", ephemeral=True)
        return
    
    # Parse and validate color
    parsed_color = parse_color(color)
    if not parsed_color:
        await interaction.response.send_message(
            "Invalid color. Use:\n"
            "- Preset: red, green, blue, black, white, lightgreen, lightblue, purple, pink, yellow, orange\n"
            "- Hex: 0xRRGGBB, #RRGGBB, or RRGGBB",
            ephemeral=True
        )
        return
    
    comics = load_comics()
    
    if comic_id in comics:
        await interaction.response.send_message(f"Comic '{comic_id}' already exists. Use a different ID.", ephemeral=True)
        return
    
    # Add the comic
    comics[comic_id] = {
        'name': name,
        'type': comic_type,
        'url': url,
        'color': parsed_color,
        'enabled': True
    }
    
    save_comics(comics)
    
    await interaction.response.send_message(
        f"Added {name} ({comic_id}) successfully!\nType: {comic_type}\nURL: {url}\nColor: {parsed_color}",
        ephemeral=True
    )

@tree.command(name="removecomic", description="[Admin] Remove a comic from monitoring")
async def removecomic_command(interaction: discord.Interaction, comic_id: str):
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    
    comics = load_comics()
    
    if comic_id not in comics:
        await interaction.response.send_message(f"Comic '{comic_id}' not found.", ephemeral=True)
        return
    
    comic_name = comics[comic_id]['name']
    del comics[comic_id]
    save_comics(comics)
    
    # Also clean up subscriptions for this comic
    subscriptions = load_subscriptions()
    for user_id in subscriptions:
        if comic_id in subscriptions[user_id]:
            subscriptions[user_id].remove(comic_id)
    save_subscriptions(subscriptions)
    
    await interaction.response.send_message(
        f"Removed {comic_name} ({comic_id}) successfully.",
        ephemeral=True
    )

@tree.command(name="inspectcomic", description="[Admin] Preview what a comic's notification would look like")
async def inspectcomic_command(interaction: discord.Interaction, comic_id: str):
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    
    comics = load_comics()
    
    if comic_id not in comics:
        await interaction.response.send_message(f"Comic '{comic_id}' not found.", ephemeral=True)
        return
    
    comic = comics[comic_id]
    
    await interaction.response.send_message("Fetching latest entry...", ephemeral=True)
    
    if comic['type'] == 'html':
        # For HTML, just show what we'd monitor
        current_hash = get_content_hash(comic['url'])
        if current_hash:
            embed = discord.Embed(
                title=f"Preview: {comic['name']} (HTML Monitor)",
                description=f"**Type:** HTML hash comparison\n**URL:** {comic['url']}\n**Current Hash:** `{current_hash[:16]}...`\n\nThis comic is monitored by checking if the HTML content changes. No preview content available.",
                color=int(comic['color'], 16)
            )
            await interaction.edit_original_response(content=None, embed=embed)
        else:
            await interaction.edit_original_response(content="Failed to fetch the HTML page.")
    
    elif comic['type'] == 'rss':
        # For RSS, fetch and show the latest entry
        entry = get_latest_rss_entry(comic['url'])
        
        if not entry:
            await interaction.edit_original_response(content="Failed to fetch RSS feed.")
            return
        
        # Also fetch raw feed to check content field
        try:
            feed = feedparser.parse(comic['url'])
            raw_entry = feed.entries[0] if feed.entries else None
            has_content = hasattr(raw_entry, 'content') if raw_entry else False
            content_preview = raw_entry.content[0].value[:200] if has_content else "No content field"
        except:
            content_preview = "Error fetching content"
        
        # Build the description as it would appear in notification
        description = f"**Title:** {entry['title']}\n\n"
        
        if entry['caption']:
            description += f"**Extracted Caption:**\n*{entry['caption']}*\n\n"
        else:
            description += f"**Extracted Caption:** None found\n\n"
        
        description += f"**Raw Description (first 200 chars):**\n```{entry['description'][:200]}...```\n\n"
        description += f"**Raw Content Field (first 200 chars):**\n```{content_preview}...```\n\n"
        description += f"**Link:** {entry['link']}\n"
        description += f"**Published:** {entry['pubDate']}"
        
        embed = discord.Embed(
            title=f"Preview: {comic['name']} (RSS)",
            description=description,
            color=int(comic['color'], 16)
        )
        
        # Show what the notification would look like
        caption_status = "(captions disabled)" if not comic.get('show_caption', True) else ""
        embed.add_field(
            name=f"Notification Preview {caption_status}",
            value=f"Title: **{entry['title']}**\nCaption: *{entry['caption'] if (comic.get('show_caption', True) and entry['caption']) else 'None or hidden'}*",
            inline=False
        )
        
        await interaction.edit_original_response(content=None, embed=embed)

# Main monitoring loop
@tasks.loop(seconds=CHECK_INTERVAL)
async def monitor_comics():
    """Monitor all enabled comics for changes"""
    channel = client.get_channel(DISCORD_CHANNEL_ID)
    
    if not channel:
        print(f"ERROR: Could not find channel with ID {DISCORD_CHANNEL_ID}")
        return
    
    comics = get_enabled_comics()
    
    for comic_id, comic in comics.items():
        comic_type = comic['type']
        
        if comic_type == 'html':
            # HTML hash monitoring
            current_hash = get_content_hash(comic['url'])
            
            if current_hash:
                # Reset error counter
                if hasattr(monitor_comics, f'{comic_id}_consecutive_errors'):
                    prev_errors = getattr(monitor_comics, f'{comic_id}_consecutive_errors')
                    if prev_errors >= 3:
                        print(f"{comic['name']} is accessible again after errors")
                setattr(monitor_comics, f'{comic_id}_consecutive_errors', 0)
                
                # Check for changes
                if not hasattr(monitor_comics, f'{comic_id}_previous_hash'):
                    print(f"{comic['name']} initial hash: {current_hash}")
                    setattr(monitor_comics, f'{comic_id}_previous_hash', current_hash)
                else:
                    prev_hash = getattr(monitor_comics, f'{comic_id}_previous_hash')
                    if current_hash != prev_hash:
                        print(f"{comic['name']} content changed!")
                        await send_html_update_notification(channel, comic_id, comic)
                        setattr(monitor_comics, f'{comic_id}_previous_hash', current_hash)
                    else:
                        print(f"{comic['name']}: No changes at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                # Handle error
                if not hasattr(monitor_comics, f'{comic_id}_consecutive_errors'):
                    setattr(monitor_comics, f'{comic_id}_consecutive_errors', 0)
                
                errors = getattr(monitor_comics, f'{comic_id}_consecutive_errors') + 1
                setattr(monitor_comics, f'{comic_id}_consecutive_errors', errors)
                print(f"{comic['name']} error count: {errors}")
                
                if errors == 3:
                    await send_error_notification(
                        channel,
                        comic['name'],
                        comic['url'],
                        f"Failed to fetch the website {errors} times in a row."
                    )
        
        elif comic_type == 'rss':
            # RSS feed monitoring
            entry = get_latest_rss_entry(comic['url'])
            
            if entry:
                # Reset error counter
                if hasattr(monitor_comics, f'{comic_id}_consecutive_errors'):
                    prev_errors = getattr(monitor_comics, f'{comic_id}_consecutive_errors')
                    if prev_errors >= 3:
                        print(f"{comic['name']} RSS is accessible again after errors")
                setattr(monitor_comics, f'{comic_id}_consecutive_errors', 0)
                
                current_guid = entry['guid']
                
                # Check for new entry
                if not hasattr(monitor_comics, f'{comic_id}_previous_guid'):
                    print(f"{comic['name']} initial entry: {entry['title']}")
                    setattr(monitor_comics, f'{comic_id}_previous_guid', current_guid)
                else:
                    prev_guid = getattr(monitor_comics, f'{comic_id}_previous_guid')
                    if current_guid != prev_guid:
                        print(f"New {comic['name']} comic: {entry['title']}")
                        await send_rss_update_notification(channel, comic_id, comic, entry)
                        setattr(monitor_comics, f'{comic_id}_previous_guid', current_guid)
                    else:
                        print(f"{comic['name']}: No new comics at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                # Handle error
                if not hasattr(monitor_comics, f'{comic_id}_consecutive_errors'):
                    setattr(monitor_comics, f'{comic_id}_consecutive_errors', 0)
                
                errors = getattr(monitor_comics, f'{comic_id}_consecutive_errors') + 1
                setattr(monitor_comics, f'{comic_id}_consecutive_errors', errors)
                print(f"{comic['name']} error count: {errors}")
                
                if errors == 3:
                    await send_error_notification(
                        channel,
                        comic['name'],
                        comic['url'],
                        f"Failed to fetch RSS feed {errors} times in a row."
                    )

@monitor_comics.before_loop
async def before_monitor():
    await client.wait_until_ready()
    channel = client.get_channel(DISCORD_CHANNEL_ID)
    
    if not channel:
        print(f"ERROR: Could not find channel with ID {DISCORD_CHANNEL_ID}")
        return
    
    print(f"Connected to channel: {channel.name}")
    print(f"Starting monitoring:")
    
    comics = get_enabled_comics()
    for comic_id, comic in comics.items():
        print(f"  - {comic['name']}: {comic['url']}")
    
    print(f"Check interval: {CHECK_INTERVAL} seconds")
    print(f"Admin user IDs: {ADMIN_USER_IDS}")
    
    # Send test notification on startup if enabled
    if SEND_TEST_NOTIFICATION:
        print("Sending test notification...")
        await send_test_notification(channel)
    else:
        print("Test notification disabled, skipping...")
    
    # Send startup RSS notifications if enabled
    if SEND_STARTUP_RSS_NOTIFICATIONS:
        print("Sending startup RSS notifications for current entries...")
        
        for comic_id, comic in comics.items():
            if comic['type'] == 'rss':
                entry = get_latest_rss_entry(comic['url'])
                if entry:
                    print(f"Sending {comic['name']} startup notification: {entry['title']}")
                    await send_rss_update_notification(channel, comic_id, comic, entry)
    else:
        print("Startup RSS notifications disabled, skipping...")

@client.event
async def on_ready():
    global monitor_started
    if not monitor_started:
        print(f'Bot logged in as {client.user}')
        await tree.sync()
        print("Slash commands synced")
        monitor_comics.start()
        monitor_started = True

def main():
    # Initialize data files on startup
    initialize_data_files()
    
    if not DISCORD_BOT_TOKEN:
        print("ERROR: DISCORD_BOT_TOKEN not set!")
        return
    
    if not DISCORD_CHANNEL_ID:
        print("ERROR: DISCORD_CHANNEL_ID not set!")
        return
    
    if not ADMIN_USER_IDS:
        print("WARNING: No admin users configured. Admin commands will not work.")
    
    client.run(DISCORD_BOT_TOKEN)

if __name__ == "__main__":
    main()
