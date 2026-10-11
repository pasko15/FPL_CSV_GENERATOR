from __future__ import annotations

import concurrent.futures
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .api import FPLApi
from .config import Config
from .exporters import normalize_my_team, rows_from, snapshot, write_csv

LOG = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, config: Config, api: FPLApi | None = None):
        self.config = config
        self.api = api or FPLApi(config.timeout, config.retries, config.api_token)
        self.current = config.data_dir / "current"
        self.state_path = config.data_dir / ".refresh_state.json"
        self.report: dict[str, Any] = {"successful": [], "failed": {}, "rows": {}, "skipped": []}

    def _fetch_export(self, label: str, path: str, filename: str, *, required=(), ids=None,
                      transform=None, authenticated=False, snap_name=None):
        try:
            data = self.api.get(path, authenticated=authenticated)
            rows = transform(data) if transform else rows_from(data, id_fields=ids)
            if not isinstance(rows, list):
                raise ValueError("transform did not return rows")
            count = write_csv(self.current / filename, rows, required=required)
            if snap_name:
                snapshot(self.current, rows, snap_name)
            self.report["successful"].append(label)
            self.report["rows"][label] = count
            return True
        except Exception as exc:
            self.report["failed"][label] = f"{type(exc).__name__}: {exc}"
            LOG.exception("Refresh failed for %s", label)
            return False

    def _fetch_my_team(self, manager_id: int) -> bool:
        label = "my-team"
        try:
            payload = self.api.get(f"my-team/{manager_id}/", authenticated=True)
            if not isinstance(payload, dict):
                raise ValueError("my-team response is not an object")
            pick_rows, chip_rows = normalize_my_team(payload, manager_id)
            pick_count = write_csv(self.current / "my_team_picks.csv", pick_rows,
                                   required=("manager_id", "player_id"))
            chip_count = write_csv(self.current / "my_team_chips.csv", chip_rows)
            metadata_count = write_csv(self.current / "my_team.csv", rows_from(payload, id_fields={"manager_id": manager_id}),
                                       required=("manager_id",))
            self.report["successful"].append(label)
            self.report["rows"][label] = metadata_count
            self.report["rows"]["my_team_picks.csv"] = pick_count
            self.report["rows"]["my_team_chips.csv"] = chip_count
            return True
        except Exception as exc:
            self.report["failed"][label] = f"{type(exc).__name__}: {exc}"
            LOG.exception("Refresh failed for %s", label)
            return False

    @staticmethod
    def _event_status_is_live(payload: Any) -> bool:
        if not isinstance(payload, list):
            return False
        return any(isinstance(row, dict) and row.get("status") in {"live", "in season"} for row in payload)

    def _fixtures_are_live(self) -> bool:
        path = self.current / "fixtures.csv"
        if not path.exists():
            return False
        import csv
        with path.open(encoding="utf-8-sig", newline="") as stream:
            return any(str(row.get("started", "")).lower() == "true"
                       and str(row.get("finished", "")).lower() == "false"
                       for row in csv.DictReader(stream))

    def refresh(self, *, full: bool = False, historical_backfill: bool = False) -> dict[str, Any]:
        started = time.monotonic()
        self.current.mkdir(parents=True, exist_ok=True)
        state = {}
        if self.state_path.exists():
            try:
                state = json.loads(self.state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                state = {}
        now = datetime.now(timezone.utc)

        def due(key: str, hours: int) -> bool:
            if full or historical_backfill:
                return True
            try:
                then = datetime.fromisoformat(state[key])
                return (now - then).total_seconds() >= hours * 3600
            except (KeyError, ValueError, TypeError):
                return True

        def due_minutes(key: str, minutes: int) -> bool:
            if full:
                return True
            try:
                then = datetime.fromisoformat(state[key])
                return (now - then).total_seconds() >= minutes * 60
            except (KeyError, ValueError, TypeError):
                return True

        def mark(key: str) -> None:
            state[key] = now.isoformat()

        bootstrap = None
        if due("bootstrap", self.config.bootstrap_hours):
            try:
                bootstrap = self.api.get("bootstrap-static/")
                if not isinstance(bootstrap, dict) or not isinstance(bootstrap.get("elements"), list):
                    raise ValueError("bootstrap-static response missing elements")
                for section, filename in (("elements", "players.csv"), ("teams", "teams.csv"), ("events", "gameweeks.csv")):
                    rows = rows_from(bootstrap[section])
                    count = write_csv(self.current / filename, rows, required=("id",))
                    self.report["rows"][filename] = count
                snapshot(self.current, rows_from(bootstrap["elements"]), "bootstrap_static")
                self.report["successful"].append("bootstrap-static")
                mark("bootstrap")
            except Exception as exc:
                self.report["failed"]["bootstrap-static"] = f"{type(exc).__name__}: {exc}"
                LOG.exception("Refresh failed for bootstrap-static")
        if bootstrap is None:
            cache = self.current / "players.csv"
            if cache.exists():
                import csv
                with cache.open(encoding="utf-8-sig", newline="") as stream:
                    players = list(csv.DictReader(stream))
            else:
                players = []
        else:
            players = bootstrap.get("elements", [])
        event_id = self.config.event_id
        if not event_id:
            source = bootstrap
            if source is None:
                try:
                    source = self.api.get("bootstrap-static/")
                except Exception:
                    source = None
            if isinstance(source, dict):
                current = next((e for e in source.get("events", []) if isinstance(e, dict) and e.get("is_current")), None)
                next_event = next((e for e in source.get("events", []) if isinstance(e, dict) and e.get("is_next")), None)
                chosen = current or next_event
                event_id = chosen.get("id") if chosen else None

        if due("fixtures", self.config.fixtures_hours):
            before = len(self.report["failed"])
            self._fetch_export("fixtures", "fixtures/", "fixtures.csv", snap_name="fixtures")
            if len(self.report["failed"]) == before:
                mark("fixtures")
        status = None
        if due("event_status", self.config.event_status_hours):
            try:
                status = self.api.get("event-status/")
                write_csv(self.current / "event_status.csv", rows_from(status))
                self.report["rows"]["event_status"] = len(rows_from(status))
                self.report["successful"].append("event-status")
                mark("event_status")
            except Exception as exc:
                self.report["failed"]["event-status"] = f"{type(exc).__name__}: {exc}"
            else:
                pass
        if due("player_history", self.config.player_history_hours) and players:
            all_history, all_upcoming = [], []
            def get_summary(player):
                pid = player.get("id")
                if pid is None:
                    return pid, None, RuntimeError("player row missing id")
                try:
                    return pid, self.api.get(f"element-summary/{pid}/"), None
                except Exception as exc:
                    return pid, None, exc
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.config.workers) as pool:
                for pid, payload, error in pool.map(get_summary, players):
                    if error:
                        self.report["failed"][f"player-summary-{pid}"] = f"{type(error).__name__}: {error}"
                        continue
                    all_history.extend(rows_from(payload.get("history", []), id_fields={"player_id": pid}))
                    all_upcoming.extend(rows_from(payload.get("fixtures", []), id_fields={"player_id": pid}))
            player_errors = any(key.startswith("player-summary-") for key in self.report["failed"])
            for name, rows in (("player_history.csv", all_history), ("player_upcoming_fixtures.csv", all_upcoming)):
                if rows and not player_errors:
                    count = write_csv(self.current / name, rows, required=("player_id",))
                    self.report["rows"][name] = count
            if not player_errors:
                self.report["successful"].append("player-history-batch")
                mark("player_history")

        if self.config.manager_id:
            mid = self.config.manager_id
            if due("manager", self.config.manager_hours):
                profile_ok = self._fetch_export("manager-profile", f"entry/{mid}/", "manager_profile.csv", ids={"manager_id": mid}, required=("manager_id",))
                history_ok = self._fetch_export("manager-history", f"entry/{mid}/history/", "manager_history.csv", ids={"manager_id": mid})
                if profile_ok and history_ok:
                    mark("manager")
            if event_id and due("picks", self.config.picks_hours):
                picks_ok = self._fetch_export("manager-picks", f"entry/{mid}/event/{event_id}/picks/", "manager_picks.csv", ids={"manager_id": mid, "event_id": event_id})
                if self.config.api_token:
                    my_team_ok = self._fetch_my_team(mid)
                elif full:
                    self.report["skipped"].append("my-team (FPL_API_TOKEN is not configured)")
                    my_team_ok = True
                else:
                    my_team_ok = True
                if picks_ok and my_team_ok:
                    mark("picks")
        elif full:
            self.report["skipped"].append("manager datasets (FPL_MANAGER_ID is not configured)")
        if self.config.league_id and due("standings", self.config.standings_hours):
            self._fetch_export("league-standings", f"leagues-classic/{self.config.league_id}/standings/", "league_standings.csv")
            mark("standings")
        elif full and not self.config.league_id:
            self.report["skipped"].append("league standings (FPL_LEAGUE_ID is not configured)")
        if due("set_piece_notes", self.config.set_piece_hours):
            if self._fetch_export("set-piece-notes", "team/set-piece-notes/", "set_piece_notes.csv"):
                mark("set_piece_notes")
        if event_id:
            if due("dream_team", 24):
                if self._fetch_export("dream-team", f"dream-team/{event_id}/", "dream_team.csv", ids={"event_id": event_id}):
                    mark("dream_team")
            live_status = status
            if live_status is None and (self.current / "event_status.csv").exists():
                import csv
                with (self.current / "event_status.csv").open(encoding="utf-8-sig", newline="") as stream:
                    live_status = list(csv.DictReader(stream))
            if due_minutes("live", self.config.live_minutes) and (
                self._event_status_is_live(live_status) or self._fixtures_are_live()
            ):
                before = len(self.report["failed"])
                self._fetch_export("live-player-stats", f"event/{event_id}/live/", "live_player_stats.csv", transform=lambda d: rows_from(d.get("elements", []), id_fields={"event_id": event_id}))
                if len(self.report["failed"]) == before:
                    mark("live")
        state_path = self.state_path
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        self.report["elapsed_seconds"] = round(time.monotonic() - started, 2)
        self.report["refreshed_at_utc"] = now.isoformat()
        LOG.info("Refresh summary: %s", json.dumps(self.report, sort_keys=True))
        return self.report
