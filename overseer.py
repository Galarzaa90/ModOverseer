import asyncio
import configparser
import json
import logging
import os
from logging.handlers import TimedRotatingFileHandler
from typing import Optional

import discord
from discord.ext import commands, tasks

from reddit import EntryKind, QueueEntry, RedditClient

os.makedirs("logs", exist_ok=True)

logging_formatter = logging.Formatter('[%(asctime)s][%(levelname)s] %(message)s')
file_handler = TimedRotatingFileHandler('logs/overseer', when='midnight')
file_handler.suffix = "%Y_%m_%d.log"
file_handler.setFormatter(logging_formatter)

discord_file_handler = TimedRotatingFileHandler('logs/overseer', when='midnight')
discord_file_handler.suffix = "%Y_%m_%d.log"
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


class ModOverseer(commands.Bot):
    def __init__(self, config):
        super().__init__(command_prefix="?", help_command=None)
        reddit_config = config['Reddit']
        self.subreddit = reddit_config['subreddit']
        self.reddit = RedditClient(reddit_config['refresh_token'], reddit_config['client_id'], reddit_config['secret'],
                                   loop=self.loop)
        self.queue_map = {}

        self.modqueue_check.add_exception_type(Exception)
        self.modqueue_check.start()

    async def on_ready(self):
        """Called when the bot is ready."""
        print('Logged in as')
        print(self.user)
        print(self.user.id)
        print('------')

        try:
            with open("queue.json") as f:
                self.queue_map = json.load(f)
        except FileNotFoundError:
            pass

    @tasks.loop(minutes=2)
    async def modqueue_check(self):
        tag = "[modqueue_check]"
        await self.wait_until_ready()
        entries = await self.reddit.get_mod_queue(config["Reddit"]["subreddit"])
        guild: discord.Guild = self.get_guild(int(config["Discord"]["guild_id"]))
        if guild is None:
            log.warning(f"{tag} Could not find discord guild.")
            await asyncio.sleep(120)
            return
        channel: discord.TextChannel = guild.get_channel(int(config["Discord"]["modqueue_channel"]))
        if channel is None:
            log.warning(f"{tag} Could not find channel.")
            await asyncio.sleep(120)
            return
        if entries is None:
            log.warning(f"{tag} Failed getting mod queue entries")
            await asyncio.sleep(60)
            return
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
        for entry_id, msg_id in temp.items():
            if entry_id not in entries:
                msg: discord.Message = await self.safe_get_message(channel, msg_id)
                if msg:
                    await msg.delete()
                log.info(f"{tag} Entry with id {entry_id} no longer in queue")
                del self.queue_map[entry_id]
        with open("queue.json", "w") as f:
            json.dump(self.queue_map, f, indent=2)
        await asyncio.sleep(120)

    @staticmethod
    async def safe_get_message(channel: discord.TextChannel, message_id: int) -> Optional[discord.Message]:
        """Finds a message in a channel by its id.

        Instead of throwing a NotFound exception, it just returns None if the message is not found."""
        try:
            return await channel.fetch_message(message_id)
        except discord.NotFound:
            return None

    @staticmethod
    def embed_from_queue_entry(entry: QueueEntry):
        """Builds a discord embed from a Mod Queue entry."""
        title = entry.post_title
        if entry.type == EntryKind.COMMENT:
            title = f"Comment in '{title}'"
            description = entry.comment_body
            link = entry.comment_link
        else:
            description = entry.post_text
            link = entry.post_link
        color = COMMENT_COLOR if entry.type == EntryKind.COMMENT else LINK_COLOR
        embed = discord.Embed(title=title, description=description, url=link, timestamp=entry.created, colour=color)
        if entry.thumbnail:
            embed.set_thumbnail(url=entry.thumbnail)
        embed.set_author(name=f"u/{entry.comment_author}", url=RedditClient.get_user_url(entry.comment_author))
        if entry.reports:
            embed.add_field(name="Reports", value="\n".join(f"{c}: {t}" for t, c in entry.reports))
        if entry.mod_reports:
            embed.add_field(name="Mod Reports", value="\n".join(f"{a}: {t}" for t, a in entry.mod_reports))
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
        print("Discord token not found")
        exit()
    bot.run(token)
