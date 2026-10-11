from __future__ import annotations

import json
import logging
import random
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

LOG = logging.getLogger(__name__)
BASE = "https://fantasy.premierleague.com/api"


class FPLApi:
    def __init__(self, timeout: float = 20, retries: int = 4, api_token: str | None = None):
        self.timeout, self.retries = timeout, retries
        self.api_token = api_token

    def get(self, path: str, authenticated: bool = False):
        if authenticated and not self.api_token:
            raise RuntimeError("my-team requires FPL_API_TOKEN; see README authentication setup")
        url = f"{BASE}/{path.lstrip('/')}"
        headers = {"User-Agent": "fpl-csv-pipeline/1.0", "Accept": "application/json"}
        if authenticated:
            headers["X-API-Authorization"] = f"Bearer {self.api_token}"
        for attempt in range(self.retries):
            try:
                req = Request(url, headers=headers)
                with urlopen(req, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                retryable = exc.code == 429 or 500 <= exc.code < 600
                if not retryable or attempt + 1 == self.retries:
                    raise
                delay = min(60, 2 ** attempt) + random.uniform(0, 0.5)
                retry_after = exc.headers.get("Retry-After")
                if retry_after:
                    try:
                        delay = min(120, float(retry_after))
                    except ValueError:
                        pass
                LOG.warning("HTTP %s from %s; retrying in %.1fs", exc.code, path, delay)
                time.sleep(delay)
            except (URLError, TimeoutError, json.JSONDecodeError) as exc:
                if attempt + 1 == self.retries:
                    raise RuntimeError(f"Request failed for {path}: {type(exc).__name__}") from exc
                delay = min(60, 2 ** attempt) + random.uniform(0, 0.5)
                LOG.warning("Request error for %s (%s); retrying in %.1fs", path, type(exc).__name__, delay)
                time.sleep(delay)
        raise RuntimeError(f"Request failed for {path}")
