from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from slack_sdk import WebClient


class NwSlackpostProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            wc = WebClient(credentials['bot_token'])
            wc.auth_test()
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))
