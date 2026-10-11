from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Load simple KEY=VALUE settings without overriding the process environment."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def _positive_int(name: str, default: int | None = None) -> int | None:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


@dataclass(frozen=True)
class Config:
    data_dir: Path
    manager_id: int | None
    league_id: int | None
    event_id: int | None
    refresh_hours: int
    timeout: float
    retries: int
    workers: int
    player_history_hours: int
    bootstrap_hours: int
    fixtures_hours: int
    manager_hours: int
    picks_hours: int
    standings_hours: int
    event_status_hours: int
    set_piece_hours: int
    live_minutes: int
    api_token: str | None

    @classmethod
    def from_env(cls) -> "Config":
        _load_dotenv()
        refresh = _positive_int("FPL_REFRESH_HOURS", 3)
        return cls(
            data_dir=Path(os.getenv("FPL_DATA_DIR", "data")),
            manager_id=_positive_int("FPL_MANAGER_ID"),
            league_id=_positive_int("FPL_LEAGUE_ID"),
            event_id=_positive_int("FPL_EVENT_ID"),
            refresh_hours=refresh or 3,
            timeout=float(os.getenv("FPL_HTTP_TIMEOUT", "20")),
            retries=_positive_int("FPL_HTTP_RETRIES", 4) or 4,
            workers=_positive_int("FPL_PLAYER_WORKERS", 4) or 4,
            player_history_hours=_positive_int("FPL_PLAYER_HISTORY_HOURS", 24) or 24,
            bootstrap_hours=_positive_int("FPL_BOOTSTRAP_HOURS", 3) or 3,
            fixtures_hours=_positive_int("FPL_FIXTURES_HOURS", 12) or 12,
            manager_hours=_positive_int("FPL_MANAGER_HOURS", 12) or 12,
            picks_hours=_positive_int("FPL_PICKS_HOURS", 3) or 3,
            standings_hours=_positive_int("FPL_STANDINGS_HOURS", 3) or 3,
            event_status_hours=_positive_int("FPL_EVENT_STATUS_HOURS", 2) or 2,
            set_piece_hours=_positive_int("FPL_SET_PIECE_HOURS", 12) or 12,
            live_minutes=_positive_int("FPL_LIVE_MINUTES", 3) or 3,
            api_token=os.getenv("FPL_API_TOKEN") or None,
        )
