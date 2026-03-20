from tweety import Twitter, constants
from tweety.exceptions import DeniedLogin

from src.log import setup_logger
from src.utils import get_accounts

log = setup_logger(__name__)

AUTH_BOOTSTRAP_URLS = (
    'https://x.com/',
    'https://x.com/i/notifications',
    'https://business.x.com/en',
)


def parse_cookie_string(raw_cookies: str) -> dict[str, str]:
    cookies = {}
    for raw_cookie in raw_cookies.split(';'):
        cookie = raw_cookie.strip()
        if not cookie:
            continue

        key, separator, value = cookie.partition('=')
        if separator and key and value:
            cookies[key.strip()] = value.strip()

    return cookies


async def bootstrap_cookies_from_auth_token(app: Twitter, auth_token: str) -> dict[str, str]:
    cookies = {'auth_token': auth_token}

    for url in AUTH_BOOTSTRAP_URLS:
        for headers in ({}, {'authorization': constants.DEFAULT_BEARER_TOKEN}):
            response = await app.request.session.get(url, cookies=cookies, headers=headers)
            cookies.update(dict(response.cookies))
            if cookies.get('ct0'):
                return cookies

    raise DeniedLogin(response=response, message="Auth Token isn't Valid")


async def authenticate_twitter_account(account_name: str, credential: str | None = None, *, reuse_session: bool = True) -> Twitter:
    app = Twitter(account_name)

    if reuse_session:
        try:
            await app.connect()
            return app
        except Exception as exc:
            log.warning(f'failed to reuse saved Tweety session for {account_name}: {exc}')

    if credential is None:
        credential = get_accounts()[account_name]

    cookies = parse_cookie_string(credential)
    auth_token = cookies.get('auth_token') if cookies else credential.strip()

    if cookies and cookies.get('auth_token') and cookies.get('ct0'):
        await app.load_cookies(cookies)
        return app

    try:
        await app.load_auth_token(auth_token)
        return app
    except Exception as auth_error:
        log.warning(f'load_auth_token failed for {account_name}, trying manual cookie bootstrap: {auth_error}')

    if cookies and cookies.get('auth_token'):
        cookies.setdefault('auth_token', auth_token)
        if cookies.get('ct0'):
            await app.load_cookies(cookies)
            return app

    bootstrapped_cookies = await bootstrap_cookies_from_auth_token(app, auth_token)
    if cookies:
        bootstrapped_cookies.update(cookies)

    await app.load_cookies(bootstrapped_cookies)
    return app
