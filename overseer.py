import asyncio
import configparser
import json
import traceback

import discord
from discord.ext import commands

from reddit import QueueEntry, Reddit


class ModOverseer(commands.Bot):
    def __init__(self, config):
        super().__init__(command_prefix="?")
        reddit_config = config['Reddit']
        self.subreddit = reddit_config['subreddit']
        self.reddit = Reddit(reddit_config['refresh_token'], reddit_config['client_id'], reddit_config['secret'],
                             loop=self.loop)
        self.queue_map = {}

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

        self.loop.create_task(self.modqueue_task())

    async def modqueue_task(self):
        await self.wait_until_ready()
        while self.is_ready():
            try:
                entries = await self.reddit.get_mod_queue(config["Reddit"]["subreddit"])
                guild: discord.Guild = self.get_guild(int(config["Discord"]["guild_id"]))
                if guild is None:
                    print("Guild not available")
                    break
                channel: discord.TextChannel = guild.get_channel(int(config["Discord"]["modqueue_channel"]))
                if channel is None:
                    print("Channel not available")
                    break
                if entries is None:
                    await channel.send("No entries found")
                else:
                    for r in entries:
                        # New entry, add message
                        if r.id not in self.queue_map:
                            msg = await channel.send(embed=self.embed_from_queue_entry(r))
                            self.queue_map[r.id] = msg.id
                        # Existing entry, update message
                        else:
                            msg: discord.Message = None
                            try:
                                msg = await channel.get_message(self.queue_map[r.id])
                            except discord.NotFound:
                                pass
                            if msg:
                                await msg.edit(embed=self.embed_from_queue_entry(r))
                            else:
                                msg = await channel.send(embed=self.embed_from_queue_entry(r))
                                self.queue_map[r.id] = msg.id
                    # Check entries that are now gone
                    for id, msg_id in self.queue_map.items():
                        print(id, msg_id)
                        if id not in entries:
                            msg: discord.Message = await channel.get_message(msg_id)
                            if msg:
                                await msg.delete()
                with open("queue.json", "w") as f:
                    json.dump(self.queue_map, f, indent=2)
                await asyncio.sleep(60)
            except Exception:
                traceback.print_exc()
                await asyncio.sleep(60)

    def embed_from_queue_entry(self, entry: QueueEntry):
        title = entry.post_title
        if entry.type == "Comment":
            title = f"Comment in '{title}'"
            description = entry.comment_body
            link = entry.comment_link
        else:
            description = entry.post_text
            link = entry.post_link
        embed = discord.Embed(title=title, description=description, url=link, timestamp=entry.created)
        if entry.thumbnail:
            embed.set_thumbnail(url=entry.thumbnail)
        embed.set_author(name=entry.comment_author)
        if entry.reports:
            embed.add_field(name="Reports", value="\n".join(f"{c}: {t}" for t, c in entry.reports))
        if entry.mod_reports:
            embed.add_field(name="Reports", value="\n".join(f"{a}: {t}" for t, a in entry.mod_reports))
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
