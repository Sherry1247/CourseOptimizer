"""Server-side Madgrades API client.

Obtain a token through https://api.madgrades.com/ and expose it to the server as
MADGRADES_API_TOKEN.  Tokens must never be sent to browser JavaScript or checked
into source control.
"""

from __future__ import annotations

import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class MadgradesNotConfigured(RuntimeError):
    pass


class MadgradesClient:
    def __init__(self, token: str | None = None, base_url: str = "https://api.madgrades.com"):
        self.token = token or os.getenv("MADGRADES_API_TOKEN")
        self.base_url = base_url.rstrip("/")
        if not self.token:
            raise MadgradesNotConfigured(
                "Set MADGRADES_API_TOKEN after creating a token at api.madgrades.com."
            )

    def get(self, path: str, **params) -> dict:
        query = f"?{urlencode(params)}" if params else ""
        request = Request(
            f"{self.base_url}/{path.lstrip('/')}{query}",
            headers={
                "Authorization": f"Token {self.token}",
                "Accept": "application/json",
                "User-Agent": "BadgerPlan/0.2",
            },
        )
        with urlopen(request, timeout=15) as response:
            return json.load(response)

    def request_documented_endpoint(self, path: str, **params) -> dict:
        """Call an endpoint copied from the account-specific API documentation.

        Madgrades can change its endpoint contract.  Keeping the path explicit
        prevents this project from silently depending on an undocumented route.
        """

        return self.get(path, **params)
