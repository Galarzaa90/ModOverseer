import datetime
import enum
import logging
from abc import ABC, ABCMeta, abstractmethod, abstractproperty
from typing import Annotated, List, Literal, Optional, Tuple, Union

import aiohttp
from pydantic import BaseModel, Field

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
        self.auth_session = None
        self.refresh_token = refresh_token
        self.auth = aiohttp.BasicAuth(client, secret)
        self.client = client
        self.secret = secret
        self.auth_session: aiohttp.ClientSession = None
        self.api_session: aiohttp.ClientSession = None
        self.expire_time = None
        self.token = None

    async def start(self):
        self.auth_session = aiohttp.ClientSession(auth=self.auth, headers={'User-Agent': USER_AGENT})

    async def stop(self):
        await self.auth_session.close()
        if self.api_session:
            await self.api_session.close()

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
                self.api_session = aiohttp.ClientSession(headers={
                    'User-Agent': USER_AGENT,
                    'Authorization': f'bearer {self.token}'
                })
                log.info(f"[{self.__class__.__name__}] Access token obtained.")
                return True
        except Exception as e:
            log.exception(f"[{self.__class__.__name__}] Exception while getting access token.")
            return False

    @token_request
    async def get_mod_queue(self, subreddit) -> List[Union['QueueCommentEntry', 'QueueLinkEntry']]:
        """Gets the current ModQueue contents."""
        log.info(f"[{self.__class__.__name__}] Getting modqueue")
        async with self.api_session.get(f"{BASE_URL}/r/{subreddit}/about/modqueue") as resp:
            resp.raise_for_status()
            js = await resp.json()
            try:
                listing = RedditListing.model_validate(js)
                log.info(f"[{self.__class__.__name__}] {len(listing.data.children)} queue entries found.")
                return listing.data.children
            except Exception:
                log.exception(f"[{self.__class__.__name__}] Exception while getting mod queue.")
                raise

    @staticmethod
    def get_user_url(username: str) -> str:
        return f"https://www.reddit.com/u/{username}"


class EntryKind(enum.Enum):
    LINK = "t3"
    COMMENT = "t1"


class CommonQueueEntry(metaclass=ABCMeta):

    @property
    @abstractmethod
    def id(self):
        ...

    @property
    @abstractmethod
    def post_title(self):
        ...

    @property
    @abstractmethod
    def post_author(self):
        ...

    @property
    @abstractmethod
    def created(self):
        ...

    @property
    @abstractmethod
    def user_reports(self):
        ...

    @property
    @abstractmethod
    def score(self):
        ...


class CommonData(BaseModel):
    user_reports: List[Tuple[str, int, bool, bool]]
    mod_reports: List[Tuple[str, str, bool, bool]]
    ups: int
    score: int
    approved_by: Optional[str]
    approved: bool
    created_utc: datetime.datetime
    permalink: str
    num_reports: int
    mod_reason_by: Optional[str]
    removed: bool
    id: str


class CommentData(CommonData):
    approved_at_utc: Optional[datetime.datetime]
    author_is_blocked: bool
    edited: bool
    banned_by: Optional[bool] = None
    author_flair_type: str
    total_awards_received: int
    author: str
    link_author: str
    likes: Optional[int]
    ban_note: Optional[str] = None
    banned_at_utc: Optional[datetime.datetime]
    mod_reason_title: Optional[str]
    num_comments: int
    parent_id: str
    author_fullname: str
    body: str
    link_title: str
    name: str
    downs: int
    is_submitter: bool
    link_id: str
    score_hidden: bool
    link_permalink: str
    report_reasons: List
    created: datetime.datetime
    link_url: str
    locked: bool
    mod_reports: List


class QueueCommentEntry(BaseModel, CommonQueueEntry):
    kind: Literal['t1']
    data: CommentData

    @property
    def id(self):
        return self.data.id

    @property
    def post_title(self):
        return self.data.link_title

    @property
    def post_author(self):
        return self.data.link_author

    @property
    def created(self):
        return self.data.created_utc

    @property
    def user_reports(self):
        return self.data.user_reports

    @property
    def score(self):
        return self.data.score

    @property
    def comment_body(self):
        return self.data.body

    @property
    def comment_author(self):
        return self.data.author

    @property
    def comment_url(self):
        return self.data.link_permalink


class LinkData(CommonData):
    approved_at_utc: Optional[datetime.datetime]
    selftext: str
    title: str
    upvote_ratio: float
    ignore_reports: bool
    is_original_content: bool
    author_is_blocked: bool
    author: str
    url: str
    is_self: bool
    thumbnail: str


class QueueLinkEntry(BaseModel, CommonQueueEntry):
    kind: Literal['t3']
    data: LinkData

    @property
    def id(self):
        return self.data.id

    @property
    def post_title(self):
        return self.data.title

    @property
    def post_author(self):
        return self.data.author

    @property
    def created(self):
        return self.data.created_utc

    @property
    def user_reports(self):
        return self.data.user_reports

    @property
    def score(self):
        return self.data.score

    @property
    def post_text(self):
        return self.data.selftext

    @property
    def post_link(self):
        return self.data.url

    @property
    def thumbnail(self):
        return self.data.thumbnail


ListingDataChildren = Annotated[
    Union[QueueCommentEntry, QueueLinkEntry],
    Field(discriminator="kind")
]


class ListingData(BaseModel):
    children: List[ListingDataChildren]


class RedditListing(BaseModel):
    kind: Literal["Listing"]
    data: ListingData
