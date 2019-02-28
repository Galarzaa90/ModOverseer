import asyncio
import datetime
import enum
import logging

import aiohttp

ACCESS_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
BASE_URL = "https://oauth.reddit.com"
USER_AGENT = "ModOverseer by /u/Galarzaa"

log = logging.getLogger("overseer")


def token_request(func):
    """Makes sure the current token is valid before performing a request.

    If the token is expired or there's no saved token yet, a new access token is requested."""

    async def wrapper(*args):
        # If token is expired, get new token before
        if args[0].token is None or datetime.datetime.now() >= args[0].expire_time:
            await args[0].get_access_token()
        return await func(*args)

    return wrapper


class RedditClient:
    """Reddit API client

    It does not handle refresh token generation, it requires a previously acquire refresh token.
    It can handle acesss token generation, every time a request is used, the expire time of the token is checked first.
    """

    def __init__(self, refresh_token, client, secret, loop=None):
        """Creates an instance of the client.

        :param refresh_token: The refresh token used to get new access tokens.
        :param client: The application's client ID.
        :param secret: The application's client secret.
        :param loop: The event loop used by the client.
        """
        self.refresh_token = refresh_token
        self.auth = aiohttp.BasicAuth(client, secret)
        self.client = client
        self.secret = secret
        self.loop = loop or asyncio.get_event_loop()
        self.auth_session = aiohttp.ClientSession(loop=self.loop, auth=self.auth, headers={'User-Agent': USER_AGENT})
        self.api_session = None
        self.expire_time = None
        self.token = None

    async def get_access_token(self):
        """Gets a new access token using the current refresh token."""
        log.info(f"[{self.__class__.__name__}] Getting access token")
        try:
            params = {
                'grant_type': 'refresh_token',
                'refresh_token': self.refresh_token
            }
            async with self.auth_session.post(ACCESS_TOKEN_URL, data=params) as resp:
                data = await resp.json()
                self.token = data['access_token']
                self.expire_time = datetime.datetime.now() + datetime.timedelta(seconds=data['expires_in'] - 10)
                self.api_session = aiohttp.ClientSession(loop=self.loop,
                                                         headers={'User-Agent': USER_AGENT,
                                                                  'Authorization': f'bearer {self.token}'})
                log.info(f"[{self.__class__.__name__}] Access token obtained.")
                return True
        except Exception as e:
            log.exception(f"[{self.__class__.__name__}] Exception while getting access token.")
            return False

    @token_request
    async def get_mod_queue(self, subreddit):
        """Gets the current ModQueue contents."""
        log.info(f"[{self.__class__.__name__}] Getting modqueue")
        async with self.api_session.get(f"{BASE_URL}/r/{subreddit}/about/modqueue") as resp:
            js = await resp.json()
            if "error" in js:
                return None
            try:
                children = js["data"]["children"]
                results = []
                for c in children:
                    results.append(QueueEntry(kind=c["kind"], **c["data"]))
                log.info(f"[{self.__class__.__name__}] {len(results)} queue entries found.")
                return results
            except Exception as e:
                log.exception(f"[{self.__class__.__name__}] Exception while getting mod queue.")
                return None

    @staticmethod
    def get_user_url(username: str) -> str:
        return f"https://www.reddit.com/u/{username}"


class EntryKind(enum.Enum):
    LINK = "t3"
    COMMENT = "t1"


class QueueEntry:
    def __init__(self, kind, **kwargs):
        self.comment_link = None
        permalink = kwargs.get("permalink")
        self.type = EntryKind(kind)
        if self.type == EntryKind.LINK:
            self.post_title = kwargs.get("title")
            self.post_author = kwargs.get("author")
            self.post_text = kwargs.get("selftext")
            if permalink:
                self.post_link = f"https://reddit.com{permalink}"

        if self.type == EntryKind.COMMENT:
            self.post_title = kwargs.get("link_title")
            self.post_link = kwargs.get("link_url")
            self.post_author = kwargs.get("link_author")
            if permalink:
                self.comment_link = f"https://reddit.com{permalink}"

        # Post type only
        self.is_self = kwargs.get("is_self", False)
        self.thumbnail = kwargs.get("thumbnail")
        if self.thumbnail == "self":
            self.thumbnail = None

        # Comment type only
        self.comment_author = kwargs.get("author")
        self.comment_body = kwargs.get("body")

        # Any type
        self.reports = kwargs.get("user_reports", [])
        self.mod_reports = kwargs.get("mod_reports", [])
        self.post_text = kwargs.get("selftext")
        self.comments = kwargs.get("num_comments")
        self.ignore_reports = kwargs.get("ignore_reports")
        self.approved = kwargs.get("approved")
        self.created = datetime.datetime.utcfromtimestamp(kwargs.get("created_utc"))
        self.id = kwargs.get("id")
        self.score: int = kwargs.get("score", 0)

    def __eq__(self, o: object) -> bool:
        if isinstance(o, self.__class__):
            return self.id == o.id
        if isinstance(o, str):
            return self.id == o
        return False
