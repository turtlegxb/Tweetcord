import inspect
from urllib.parse import urlparse

from src.log import setup_logger

log = setup_logger(__name__)


def apply_tweety_compatibility_patch():
    try:
        from tweety.http import Request
        from tweety.exceptions import TwitterError
        from tweety.types.n_types import GenericError
        from tweety.transaction import TransactionGenerator
    except Exception as exc:
        log.warning(f'unable to apply Tweety compatibility patch: {exc}')
        return

    if getattr(Request, '_tweetcord_transaction_patch_applied', False):
        return

    original_init_local_api = Request._init_local_api
    original_get_indices = TransactionGenerator.get_indices

    def patched_get_indices(self, home_page_html=None):
        try:
            return original_get_indices(self, home_page_html)
        except Exception as exc:
            log.warning(f'Tweety transaction parser failed, using fallback transaction indices: {exc}')
            return 0, [1, 2, 3]

    async def patched_init_local_api(self):
        cookies = await self.remove_cookies()

        if not self._transaction:
            try:
                home_page_html = await self.get_home_html()
                self._transaction = TransactionGenerator(home_page_html)
            except Exception as exc:
                log.warning(f'Tweety transaction bootstrap failed, continuing without transaction id support: {exc}')
                self._transaction = None

        if not self._guest_token:
            self._guest_token = await self._get_guest_token()

        self.cookies = cookies

    async def patched_get_response(self, return_raw=False, ignore_none_data=False, is_document=False, **request_data):
        if not self._transaction or not self._guest_token:
            await self._init_local_api()

        new_request = request_data
        new_request["headers"] = self._get_request_headers(request_data.get("headers", {}))
        new_request["cookies"] = self._cookie

        if self._transaction:
            try:
                transaction_id = self._transaction.generate_transaction_id(
                    new_request["method"],
                    urlparse(new_request["url"]).path,
                )
                new_request["headers"]["x-client-transaction-id"] = transaction_id
            except Exception as exc:
                log.warning(f'Tweety transaction id generation failed, retrying request without it: {exc}')

        response = None
        last_error = None

        for _ in range(self._retries):
            try:
                response = await self._session.request(**new_request)
                break
            except Exception as request_failed:
                last_error = request_failed

        if not response:
            raise last_error

        await self._update_rate_limit(response, inspect.stack()[1][3])
        await self._update_cookies(response)

        if is_document:
            return response

        response_json = response.json()
        if ignore_none_data and len(response.text) == 0:
            return None

        if (not response_json and response.text and response.text.lower() == "rate limit exceeded") or response.status_code == 429:
            response_json = {"errors": [{"code": 88, "message": "Rate limit exceeded."}]}
        elif not response_json and response.status_code in [403, 401]:
            response_json = {"errors": [{"code": 32, "message": "Couldn't authenticate you"}]}

        if not response_json:
            raise TwitterError(
                error_code=response.status_code,
                error_name="Server Error",
                response=response,
                message="Unknown Error Occurs on Twitter"
            )

        if response_json.get("errors") and not response_json.get('data'):
            error = response_json['errors'][0]
            error_code = error.get("code", 0)
            error_message = error.get("message")
            return GenericError(response, error_code, error_message)

        if return_raw:
            return response

        return response_json

    TransactionGenerator.get_indices = patched_get_indices
    Request._init_local_api = patched_init_local_api
    Request.__get_response__ = patched_get_response
    Request._tweetcord_transaction_patch_applied = True
