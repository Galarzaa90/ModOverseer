import datetime

import aiohttp

ACCESS_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
BASE_URL = "https://oauth.reddit.com"
USER_AGENT = "ModOverseer by /u/Galarzaa"


def request(func):
    async def wrapper(*args):
        # If token is expired, get new token before
        if args[0].token is None or datetime.datetime.now() >= args[0].expire_time:
            await args[0].get_access_token()
        return await func(*args)
    return wrapper


class Reddit:
    def __init__(self, refresh_token, client, secret, loop):
        self.refresh_token = refresh_token
        self.auth = aiohttp.BasicAuth(client, secret)
        self.client = client
        self.secret = secret
        self.loop = loop
        self.auth_session = aiohttp.ClientSession(loop=self.loop, auth=self.auth, headers={'User-Agent': USER_AGENT})
        self.api_session = None
        self.expire_time = None
        self.token = None

    async def get_access_token(self):
        print("Getting access token")
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
                return True
        except:
            return False

    @request
    async def get_mod_queue(self, subreddit):
        print("Getting modqueue")
        async with self.api_session.get(f"{BASE_URL}/r/{subreddit}/about/modqueue") as resp:
            js = await resp.json()
            print(js)
            return js
