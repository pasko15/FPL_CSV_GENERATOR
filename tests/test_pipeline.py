import csv
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from fpl_pipeline.api import FPLApi
from fpl_pipeline.config import Config
from fpl_pipeline.exporters import flatten, normalize_my_team, rows_from, snapshot, write_csv


class ExportTests(unittest.TestCase):
    def test_nested_flatten_and_ids(self):
        row = rows_from({"history": [{"stats": {"goals": 2}}]})[0]
        self.assertEqual(row["history"], '[{"stats":{"goals":2}}]')
        self.assertEqual(flatten({"stats": {"goals": 2}})["stats_goals"], 2)
        self.assertEqual(rows_from([{"round": 1}], id_fields={"player_id": 42})[0]["player_id"], 42)

    def test_empty_and_missing_identifier_preserve_existing(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "players.csv"
            write_csv(path, [{"id": 1}], required=("id",))
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                write_csv(path, [], required=("id",))
            with self.assertRaises(ValueError):
                write_csv(path, [{"name": "x"}], required=("id",))
            self.assertEqual(path.read_bytes(), before)

    def test_snapshot_duplicate_detection(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "current.csv"
            rows = [{"id": 1}]
            self.assertTrue(snapshot(path, rows, "fixtures"))
            self.assertFalse(snapshot(path, rows, "fixtures"))

    def test_csv_null_and_empty_response(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "x.csv"
            write_csv(path, [{"id": 4, "value": None}])
            with path.open(encoding="utf-8-sig", newline="") as f:
                row = next(csv.DictReader(f))
            self.assertEqual(row["id"], "4")
            self.assertEqual(row["value"], "")
            write_csv(path, [])
            self.assertTrue(path.exists())

    def test_config_validation(self):
        with patch.dict(os.environ, {"FPL_REFRESH_HOURS": "0"}, clear=True):
            with self.assertRaisesRegex(ValueError, "FPL_REFRESH_HOURS"):
                Config.from_env()

    def test_http_retry_then_success(self):
        error = HTTPError("https://example.test", 503, "busy", {}, io.BytesIO(b""))
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'{"ok":true}'
        with patch("fpl_pipeline.api.urlopen", side_effect=[error, response]), patch("fpl_pipeline.api.time.sleep"):
            self.assertEqual(FPLApi(retries=2).get("test/"), {"ok": True})

    def test_authenticated_endpoint_requires_cookie(self):
        with self.assertRaisesRegex(RuntimeError, "FPL_API_TOKEN"):
            FPLApi().get("my-team/42/", authenticated=True)

    def test_refresh_interval_configuration(self):
        with patch.dict(os.environ, {"FPL_REFRESH_HOURS": "2", "FPL_LIVE_MINUTES": "5"}, clear=True):
            config = Config.from_env()
        self.assertEqual(config.refresh_hours, 2)
        self.assertEqual(config.live_minutes, 5)

    def test_my_team_normalizes_picks_and_chips(self):
        picks, chips = normalize_my_team({
            "picks": [{"element": 12, "position": 1, "is_captain": True}],
            "chips": [{"name": "wildcard", "status_for_entry": "available"}],
        }, 99)
        self.assertEqual(len(picks), 1)
        self.assertEqual(picks[0]["player_id"], 12)
        self.assertEqual(picks[0]["manager_id"], 99)
        self.assertEqual(chips[0]["name"], "wildcard")
        self.assertEqual(chips[0]["manager_id"], 99)


if __name__ == "__main__":
    unittest.main()
