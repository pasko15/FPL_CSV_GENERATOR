# FPL API to CSV pipeline

This Python 3.10+ project downloads public Fantasy Premier League API datasets and writes normalized CSV files. It uses only the Python standard library; no dependency installation is required.

## Setup and commands

Copy `.env.example` to `.env`, then set the manager and league IDs you want. They are independent and both optional. `FPL_EVENT_ID` overrides automatic selection of the current gameweek (or next gameweek if none is current). The default output directory is `data/current/`.

Run from the repository root:

```sh
python -m fpl_pipeline refresh
python -m fpl_pipeline update
python -m fpl_pipeline schedule
python -m fpl_pipeline backfill
```

On Windows, double-click `Refresh All.bat` for a full refresh or `Update Due.bat` for datasets whose interval has elapsed. These open a console window and pause at the end so you can read the result. `refresh` fetches all configured datasets. `update` fetches only datasets due since the last successful refresh. `backfill` explicitly refreshes every player's complete history and upcoming fixtures. `schedule` stays running and is optional; you do not need it for manual laptop use. Refresh timestamps are kept in `data/.refresh_state.json`.

## Configuration

| Setting | Default | Purpose |
|---|---:|---|
| `FPL_MANAGER_ID` | unset | Manager profile, history, and picks |
| `FPL_LEAGUE_ID` | unset | Classic league standings |
| `FPL_EVENT_ID` | auto | Gameweek for picks, live stats, and dream team |
| `FPL_DATA_DIR` | `data` | Output and refresh state directory |
| `FPL_REFRESH_HOURS` | 3 | Scheduler interval |
| `FPL_HTTP_TIMEOUT` / `FPL_HTTP_RETRIES` | 20 / 4 | HTTP timeout and retry attempts |
| `FPL_PLAYER_WORKERS` | 4 | Maximum parallel player summary requests |
| `FPL_BOOTSTRAP_HOURS` | 3 | Bootstrap static refresh interval |
| `FPL_FIXTURES_HOURS` | 12 | Fixtures refresh interval |
| `FPL_PLAYER_HISTORY_HOURS` | 24 | Player history refresh interval |
| `FPL_MANAGER_HOURS` | 12 | Manager profile and history interval |
| `FPL_PICKS_HOURS` | 3 | Manager picks and my-team interval |
| `FPL_STANDINGS_HOURS` | 3 | League standings interval |
| `FPL_EVENT_STATUS_HOURS` | 2 | Event status interval |
| `FPL_SET_PIECE_HOURS` | 12 | Set-piece notes interval |
| `FPL_LIVE_MINUTES` | 3 | Live polling cadence while event status indicates live play |
| `FPL_API_TOKEN` | unset | Optional short-lived bearer token for authenticated `my-team` requests |

All interval and ID values must be positive integers when set. Manager and league identifiers can be set independently.

## CSV outputs

Files are written to `data/current/`; bootstrap and fixture snapshots are stored in `data/snapshots/`. Repeated snapshots with identical normalized content are suppressed using a SHA-256 sidecar. CSV replacement is atomic, and failed fetches retain the previous output.

| File | Row unit and key columns |
|---|---|
| `players.csv` | Player, `id`, `team`, position and bootstrap fields |
| `teams.csv` | Team, `id` and bootstrap fields |
| `gameweeks.csv` | Event, `id`, deadlines and status fields |
| `fixtures.csv` | Fixture, `id`, `event`, home/away team IDs |
| `player_history.csv` | Player-gameweek row, `player_id`, fixture and stats |
| `player_upcoming_fixtures.csv` | Player-fixture row, `player_id`, fixture and opponent |
| `live_player_stats.csv` | Live player row with `event_id`; nested stats are JSON encoded |
| `manager_profile.csv` | One manager, `manager_id` |
| `manager_history.csv` | Manager season/event rows, `manager_id` |
| `league_standings.csv` | League entry rows (API paging fields remain available) |
| `manager_picks.csv` | Pick rows; single-object metadata is flattened and list fields retained as JSON |
| `event_status.csv` | Event status row(s) |
| `dream_team.csv` | Dream team item(s), with `event_id` |
| `set_piece_notes.csv` | Team notes and available fields |
| `my_team.csv` | Authenticated team response; nested data is retained as JSON |
| `my_team_picks.csv` | One row per current squad pick; join `player_id` to `players.id` and `manager_id` to manager data |
| `my_team_chips.csv` | One row per chip record; includes chip status and `manager_id` |

Unknown fields are retained. Nested objects become underscore-separated columns; lists that do not represent a dataset's primary rows are JSON-encoded. Nulls remain empty CSV cells.

## Authenticated my-team endpoint

The endpoint is skipped unless `FPL_MANAGER_ID` and `FPL_API_TOKEN` are configured. Current FPL web sessions use a bearer token sent in the `X-API-Authorization` request header; older guides describe session cookies, which may no longer work. Sign in to FPL in your browser, open Developer Tools → Network, visit your My Team page, select its `/api/my-team/` request, and inspect Request Headers for `X-API-Authorization: Bearer …`. Put only the token after `Bearer` in `.env` as `FPL_API_TOKEN=...`. Tokens expire, so you may need to replace it. This project does not collect your password or automate login. Treat the token like a password: never share it, commit it, or include it in screenshots/logs. If authentication is unavailable, public endpoints continue independently.

## Reliability, scheduling, and limitations

Transient HTTP errors, rate limits, timeouts, and invalid JSON are retried with exponential backoff. Player summaries use bounded concurrency. Each endpoint is isolated, logs failures, and reports rows, failures, skips, and elapsed time. The public API can be unavailable, incomplete, or change shape; event status and live information reflect what the API returns at fetch time. The pipeline polls live data when event status indicates live play or cached fixtures show a started but unfinished match. API paging for classic league standings is retained as returned; standings beyond the first page may require additional pagination support.

## Tests

```sh
python -m unittest discover -s tests -v
```

Tests use fake responses and do not call the live FPL API.
