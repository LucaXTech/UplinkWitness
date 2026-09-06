import sqlite3
import unittest
from datetime import datetime, timezone
from pathlib import Path

import dashboard


class V13DashboardTests(unittest.TestCase):
    def test_link_quality_stats_reports_loss_and_jitter(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            "CREATE TABLE samples(id INTEGER PRIMARY KEY, ts TEXT, internet_ok INTEGER, internet_ms REAL)"
        )
        ts = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        conn.executemany(
            "INSERT INTO samples(ts,internet_ok,internet_ms) VALUES(?,?,?)",
            [
                (ts, 1, 10.0),
                (ts, 1, 14.0),
                (ts, 0, None),
                (ts, 1, 12.0),
            ],
        )
        stats = dashboard.link_quality_stats(conn, 24)
        self.assertEqual(stats["loss_pct"], 25.0)
        self.assertEqual(stats["jitter_ms"], 3.0)
        self.assertEqual(stats["samples"], 4)
        conn.close()

    def test_format_rate_uses_bytes_per_second_units(self):
        self.assertEqual(dashboard.format_rate(500), "500.0 B/s")
        self.assertEqual(dashboard.format_rate(1500), "1.5 KB/s")
        self.assertEqual(dashboard.format_rate(2_000_000), "2.0 MB/s")

    def test_wallboard_route_and_branding(self):
        client = dashboard.app.test_client()
        response = client.get("/wallboard")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("UplinkWitness Wallboard", html)
        self.assertIn("/api/status", html)
        self.assertIn("/api/history?hours=24", html)
        self.assertIn("quality_recent", html)

    def test_main_dashboard_links_wallboard_and_v13_diagnostics(self):
        template = (
            Path(__file__).resolve().parents[1] / "templates" / "index.html"
        ).read_text(encoding="utf-8")
        self.assertIn('href="/wallboard"', template)
        self.assertIn("wan_physical_status", template)
        self.assertIn("quality_recent", template)
        self.assertIn("ipv6_ok", template)
        self.assertNotIn("quality_24h", template)


if __name__ == "__main__":
    unittest.main()
