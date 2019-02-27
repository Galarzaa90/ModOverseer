import configparser

import discord
from discord.ext import commands

from reddit import Reddit


class ModOverseer(commands.Bot):
    def __init__(self, config):
        super().__init__(command_prefix="?")
        reddit_config = config['Reddit']
        self.subreddit = reddit_config['subreddit']
        self.reddit = Reddit(reddit_config['refresh_token'], reddit_config['client_id'], reddit_config['secret'],
                             loop=self.loop)

    async def on_ready(self):
        """Called when the bot is ready."""
        print('Logged in as')
        print(self.user)
        print(self.user.id)
        print('------')

        ret = await self.reddit.get_access_token()
        if ret:
            print("Reddit token obtained successfully.")

    async def on_message(self, message: discord.Message):
        """Called every time a message is sent on a visible channel."""
        # Ignore if message is from any bot
        print("on_message")
        if message.author.bot:
            return
        ctx = await self.get_context(message)
        if ctx.command is not None:
            return await self.invoke(ctx)
        if message.author.id == 162060569803751424:
            print("owner message")
            res = await self.reddit.get_mod_queue("TibiaMMO")
            print(res)
        await bot.process_commands(message)


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
