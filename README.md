# ModOverseer
A basic bot that displays a subreddit's Mod Queue in a designated channel.

Entries are kept up to date and removed when handled.

*This bot is made for personal use, but I'm sharing it in case anyone finds it useful.*

# Usage
To use, create a file called `config.ini`, you can check the example file to see the structure.

To use this, you need to create your own [reddit web application](https://www.reddit.com/prefs/apps),
in order to get a client id and client secret.

Once you have created it, you need to get a refresh token via reddit's oauth method.  
I acquired it using [this script](https://praw.readthedocs.io/en/latest/tutorials/refresh_token.html),
I might add one in the future that doesn't require PRAW.  
The account used to get the token must be a moderator of the subreddit.

Once you have acquired all the required information, you need to specify a discord server id and a discord channel id.
This is all the info you will need for `config.ini`, apart from a token for your discord bot.

You may notice a file `queue.json` is created, this serves as a map to keep track of which discord message belongs to which queue entry. 
Deleting or tampering this file may lead to duplicate and/or orphan messages.

# Example
![image](https://user-images.githubusercontent.com/12865379/53593756-a734ea80-3b56-11e9-8b83-dfb8537db989.png)