import asyncio
import configparser
import datetime
import json
import logging
import os
from json import JSONDecodeError
from logging.handlers import TimedRotatingFileHandler
from typing import Optional, Union

import discord
from discord.ext import commands, tasks

try:
    import sentry_sdk
except ImportError:
    sentry_sdk = None

from reddit import QueueCommentEntry, QueueLinkEntry, RedditClient

os.makedirs("logs", exist_ok=True)

logging_formatter = logging.Formatter('[%(asctime)s][%(levelname)s] %(message)s')
logging_suffix = "%Y_%m_%d.log"
file_handler = TimedRotatingFileHandler('logs/overseer', when='midnight')
file_handler.suffix = logging_suffix
file_handler.setFormatter(logging_formatter)

discord_file_handler = TimedRotatingFileHandler('logs/discord', when='midnight')
discord_file_handler.suffix = logging_suffix
discord_file_handler.setFormatter(logging_formatter)

console_handler = logging.StreamHandler()
console_handler.setFormatter(logging_formatter)

log = logging.getLogger("overseer")
log.setLevel(logging.INFO)
log.addHandler(file_handler)
log.addHandler(console_handler)

discord_log = logging.getLogger("discord")
discord_log.setLevel(logging.INFO)
discord_log.addHandler(discord_file_handler)

COMMENT_COLOR = discord.colour.Colour.green()
LINK_COLOR = discord.colour.Colour.gold()

if sentry_sdk and os.getenv("SENTRY_DSN"):
    sentry_sdk.init(
        dsn=os.getenv("SENTRY_DSN"),
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        traces_sample_rate=1.0,
        # Set profiles_sample_rate to 1.0 to profile 100%
        # of sampled transactions.
        # We recommend adjusting this value in production.
        profiles_sample_rate=1.0,
    )

class ModOverseer(commands.Bot):
    def __init__(self, config):
        super().__init__(command_prefix="?", help_command=None, intents=discord.Intents(
            guilds=True,
        ))
        reddit_config = config['Reddit']
        self.subreddit = reddit_config['subreddit']
        self.reddit = RedditClient(reddit_config['refresh_token'], reddit_config['client_id'], reddit_config['secret'],
                                   loop=self.loop)
        self.queue_map = {}

        self.modqueue_check.add_exception_type(Exception)
        self.subreddit_info_check.add_exception_type(Exception)
        self.last_channel_update = self.now

    @property
    def now(self):
        return datetime.datetime.now()

    async def setup_hook(self) -> None:
        await self.reddit.start()

    async def close(self) -> None:
        await self.reddit.stop()

    async def on_ready(self):
        """Called when the bot is ready."""
        print('Logged in as')
        print(self.user)
        print(self.user.id)
        print('------')

        try:
            with open("queue.json") as f:
                self.queue_map = json.load(f)
        except (FileNotFoundError, JSONDecodeError):
            pass

        self.subreddit_info_check.start()
        self.modqueue_check.start()


    @tasks.loop(minutes=6)
    async def subreddit_info_check(self):
        tag = "[subreddit_info_check]"
        await self.wait_until_ready()
        guild: discord.Guild = self.get_guild(int(config["Discord"]["guild_id"]))
        if guild is None:
            log.warning(f"{tag} Could not find discord guild.")
            return
        channel_id = int(config["Discord"]["subscriber_count_channel"])
        if not channel_id:
            return
        channel: discord.VoiceChannel = guild.get_channel(channel_id)
        subreddit_info = await self.reddit.get_subreddit_about(config["Reddit"]["subreddit"])
        if channel is None:
            log.warning(f"{tag} Could not find channel.")
            return
        if subreddit_info is None:
            log.warning(f"{tag} Failed getting subreddit info")
            return
        new_name = f"Reddit Subs: {subreddit_info.subscribers:,}"
        if new_name != channel.name:
            log.info(f"{tag} Trying to update name")
            await channel.edit(name=new_name, reason="Subscriber count changed")
            log.info(f"{tag} Updated channel name to '{new_name}'")


    @tasks.loop(minutes=6)
    async def modqueue_check(self):
        tag = "[subreddit_info_check]"
        await self.wait_until_ready()
        while self.is_ready():
            try:
                entries = await self.reddit.get_mod_queue(config["Reddit"]["subreddit"])
                guild: discord.Guild = self.get_guild(int(config["Discord"]["guild_id"]))
                if guild is None:
                    log.warning(f"{tag} Could not find discord guild.")
                    await asyncio.sleep(120)
                    continue
                channel: discord.TextChannel = guild.get_channel(int(config["Discord"]["modqueue_channel"]))
                if channel is None:
                    log.warning(f"{tag} Could not find channel.")
                    await asyncio.sleep(120)
                    continue
                if entries is None:
                    log.warning(f"{tag} Failed getting mod queue entries")
                    await asyncio.sleep(60)
                    continue
                for r in entries:
                    # New entry, add message
                    if r.id not in self.queue_map:
                        log.info(f"{tag} Adding new entry with id: {r.id}")
                        msg = await channel.send(embed=self.embed_from_queue_entry(r))
                        self.queue_map[r.id] = msg.id
                    # Existing entry, update message
                    else:
                        msg = await self.safe_get_message(channel, self.queue_map[r.id])
                        if msg:
                            await msg.edit(embed=self.embed_from_queue_entry(r))
                        else:
                            log.info(f"{tag} Message for entry with id {r.id} not found, readding.")
                            msg = await channel.send(embed=self.embed_from_queue_entry(r))
                            self.queue_map[r.id] = msg.id
                # Check entries that are now gone
                temp = {k: v for k, v in self.queue_map.items()}
                current_ids = [e.id for e in entries]
                for entry_id, msg_id in temp.items():
                    if entry_id not in current_ids:
                        msg: discord.Message = await self.safe_get_message(channel, msg_id)
                        if msg:
                            await msg.delete()
                        log.info(f"{tag} Entry with id {entry_id} no longer in queue")
                        del self.queue_map[entry_id]
                original_name = channel.name.split("·", 1)[0]
                new_name = f"{original_name}·{len(entries)}"
                # Only update channel every 5 minutes, as the rate limit is 2 every 10 minutes.
                if new_name != channel.name and (self.now - self.last_channel_update) > datetime.timedelta(minutes=5):
                    await channel.edit(name=new_name, reason="Queue count changed")
                    self.last_channel_update = self.now
                with open("queue.json", "w") as f:
                    json.dump(self.queue_map, f, indent=2)
                await asyncio.sleep(120)
            except Exception:
                log.exception(f"{tag} Exception")
                await asyncio.sleep(60)

    @staticmethod
    async def safe_get_message(channel: discord.TextChannel, message_id: int) -> Optional[discord.Message]:
        """Finds a message in a channel by its id.

        Instead of throwing a NotFound exception, it just returns None if the message is not found."""
        try:
            return await channel.fetch_message(message_id)
        except discord.NotFound:
            return None

    @staticmethod
    async def safe_delete_message(message: discord.Message):
        """Tries to delete a message, ignoring any errors if it fails."""
        try:
            await message.delete()
        except discord.DiscordException:
            pass

    @staticmethod
    def embed_from_queue_entry(entry: Union[QueueCommentEntry, QueueLinkEntry]):
        """Builds a discord embed from a Mod Queue entry."""
        embed = discord.Embed(title=entry.post_title, timestamp=entry.created)
        if isinstance(entry, QueueCommentEntry):
            embed.title = f"Comment in '{entry.post_title}'"
            embed.description = entry.comment_body
            embed.url = entry.comment_url
            embed.set_author(name=f"u/{entry.comment_author}", url=RedditClient.get_user_url(entry.comment_author))
        else:
            embed.description = entry.post_text
            embed.url = entry.post_url
            embed.set_thumbnail(url=entry.data.thumbnail)
            embed.set_author(name=f"u/{entry.post_author}", url=RedditClient.get_user_url(entry.post_author))
        embed.colour = COMMENT_COLOR if isinstance(entry, QueueCommentEntry) else LINK_COLOR
        if entry.user_reports:
            embed.add_field(name="Reports", value="\n".join(f"{c}: {t}" for t, c, _, _ in entry.user_reports))
        if entry.mod_reports:
            embed.add_field(name="Mod Reports", value="\n".join(f"{a}: {t}" for t, a, _, _ in entry.mod_reports))
        embed.set_footer(text=f"Score: {entry.score}")
        return embed


if __name__ == "__main__":
    config = configparser.ConfigParser()
    if not config.read('config.ini'):
        print("Could not find config file.")
        exit()
    bot = ModOverseer(config)
    try:
        token = config['Discord']['token']
    except KeyError:
        token = None
        print("Discord token not found")
        exit()
    bot.run(token)
