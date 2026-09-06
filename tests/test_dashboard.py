import sqlite3
import unittest
from datetime import datetime, timezone
from pathlib import Path

import dashboard


class DashboardTests(unittest.TestCase):
    def test_fmt_duration(self):
        self.assertEqual(dashboard.fmt_duration(None), "-")
        self.assertEqual(dashboard.fmt_duration(42), "42s")
        self.assertEqual(dashboard.fmt_duration(125), "2m 5s")
        self.assertEqual(dashboard.fmt_duration(3661), "1h 1m 1s")

    def test_percentile(self):
        self.assertIsNone(dashboard.percentile([], 0.95))
        self.assertEqual(dashboard.percentile([10], 0.95), 10)
        self.assertAlmostEqual(dashboard.percentile([1, 2, 3, 4], 0.5), 2.5)

    def test_temperature_stats_handles_legacy_schema(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE samples(id INTEGER PRIMARY KEY, ts TEXT)")
        self.assertEqual(
            dashboard.temperature_stats(conn, 24),
            {"min": None, "avg": None, "max": None, "samples": 0},
        )
        conn.close()

    def test_temperature_stats_returns_min_avg_max(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            "CREATE TABLE samples(id INTEGER PRIMARY KEY, ts TEXT, router_cpu_temp_c REAL)"
        )
        ts = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        conn.executemany(
            "INSERT INTO samples(ts,router_cpu_temp_c) VALUES(?,?)",
            [(ts, 110.0), (ts, 116.0), (ts, 118.0)],
        )
        stats = dashboard.temperature_stats(conn, 24)
        self.assertEqual(stats["min"], 110.0)
        self.assertEqual(stats["avg"], 114.7)
        self.assertEqual(stats["max"], 118.0)
        self.assertEqual(stats["samples"], 3)
        conn.close()

    def test_uplinkwitness_dashboard_branding(self):
        template = (Path(__file__).resolve().parents[1] / "templates" / "index.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("<title>UplinkWitness</title>", template)
        self.assertIn("<h1>UplinkWitness</h1>", template)
        self.assertNotIn("<h1>LineWatch</h1>", template)
        self.assertIn("router_cpu_temp_c", template)


if __name__ == "__main__":
    unittest.main()
