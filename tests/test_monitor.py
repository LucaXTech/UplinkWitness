import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import monitor


class MonitorTests(unittest.TestCase):
    def sample(self, **overrides):
        values = dict(
            ts="2026-09-05T12:00:00+00:00",
            carrier=1,
            gateway="192.168.1.1",
            gateway_ok=1,
            gateway_ms=1.2,
            internet_ok=1,
            internet_ms=10.0,
            dns_ok=1,
            dns_ms=8.0,
            http_ok=1,
            http_ms=30.0,
            public_ip="203.0.113.10",
            router_uptime_s=None,
            router_model=None,
            fritzos=None,
            wan_status=None,
            wan_uptime_s=None,
            wan_ip=None,
            wan_last_error=None,
            wan_transport=None,
            pppoe_ac_name=None,
            fritz_error=None,
            router_cpu_temp_c=None,
        )
        values.update(overrides)
        return monitor.Sample(**values)

    def event_db(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            """
            CREATE TABLE events(
                id INTEGER PRIMARY KEY,
                start_ts TEXT,
                end_ts TEXT,
                duration_s REAL,
                event_type TEXT,
                details_json TEXT
            )
            """
        )
        return conn

    def test_auto_router_mode_defaults_to_generic_without_credentials(self):
        self.assertEqual(
            monitor.resolve_router_mode("auto", user="", password=""), "generic"
        )

    def test_auto_router_mode_enables_fritz_when_credentials_exist(self):
        self.assertEqual(
            monitor.resolve_router_mode("auto", user="user", password="secret"),
            "fritz",
        )

    def test_explicit_fritz_mode_requires_credentials(self):
        with self.assertRaises(ValueError):
            monitor.resolve_router_mode("fritz", user="", password="")

    def test_gateway_probe_modes(self):
        self.assertIsNone(monitor.resolve_gateway_probe("auto"))
        self.assertTrue(monitor.resolve_gateway_probe("on"))
        self.assertFalse(monitor.resolve_gateway_probe("off"))
        with self.assertRaises(ValueError):
            monitor.resolve_gateway_probe("invalid")

    def test_failed_gateway_ping_is_not_an_outage_when_internet_is_healthy(self):
        sample = self.sample(gateway_ok=0, gateway_ms=None, internet_ok=0, internet_ms=None)
        self.assertEqual(monitor.classify(sample, gateway_probe_active=True), "OK")

    def test_gateway_unreachable_when_probe_is_supported_and_all_paths_fail(self):
        sample = self.sample(
            gateway_ok=0,
            gateway_ms=None,
            internet_ok=0,
            internet_ms=None,
            dns_ok=0,
            dns_ms=None,
            http_ok=0,
            http_ms=None,
        )
        self.assertEqual(
            monitor.classify(sample, gateway_probe_active=True),
            "GATEWAY_UNREACHABLE",
        )

    def test_generic_outage_when_gateway_probe_is_disabled(self):
        sample = self.sample(
            gateway_ok=0,
            gateway_ms=None,
            internet_ok=0,
            internet_ms=None,
            dns_ok=0,
            dns_ms=None,
            http_ok=0,
            http_ms=None,
        )
        self.assertEqual(
            monitor.classify(sample, gateway_probe_active=False),
            "INTERNET_UNREACHABLE",
        )

    def test_link_down_has_highest_priority(self):
        sample = self.sample(carrier=0)
        self.assertEqual(monitor.classify(sample), "NETWORK_LINK_DOWN")

    def test_wan_session_down_is_detected_with_router_telemetry(self):
        sample = self.sample(wan_status="Disconnected")
        self.assertEqual(monitor.classify(sample), "WAN_SESSION_DOWN")

    def test_dns_failure_is_separate_from_internet_outage(self):
        sample = self.sample(dns_ok=0, dns_ms=None)
        self.assertEqual(monitor.classify(sample), "DNS_FAILURE")

    def test_http_failure_is_separate_from_internet_outage(self):
        sample = self.sample(http_ok=0, http_ms=None)
        self.assertEqual(monitor.classify(sample), "HTTP_CONNECTIVITY_FAILURE")

    @patch.object(
        monitor.subprocess,
        "check_output",
        return_value="default via 192.168.178.1 dev enp3s0 proto dhcp src 192.168.178.20\n",
    )
    def test_default_route_detects_gateway_and_interface(self, _):
        self.assertEqual(monitor.default_route(), ("192.168.178.1", "enp3s0"))

    def test_close_event_uses_explicit_end_timestamp(self):
        conn = self.event_db()
        start = "2026-09-05T18:00:00+02:00"
        end = "2026-09-05T18:00:15+02:00"
        event_id = monitor.add_event(conn, "NETWORK_LINK_DOWN", {}, start=start)
        monitor.close_event(
            conn,
            event_id,
            {"duration_s": 15.0},
            15.0,
            end=end,
        )
        row = conn.execute(
            "SELECT start_ts, end_ts, duration_s FROM events WHERE id=?",
            (event_id,),
        ).fetchone()
        self.assertEqual(row[0], start)
        self.assertEqual(row[1], end)
        self.assertEqual(row[2], 15.0)
        conn.close()

    def test_router_and_public_ip_sources_are_independent(self):
        router_prev = "100.64.0.10"
        public_prev = "203.0.113.10"
        self.assertIsNone(monitor.ip_change(router_prev, None))
        self.assertIsNone(monitor.ip_change(public_prev, public_prev))
        self.assertIsNone(monitor.ip_change(router_prev, router_prev))

    def test_same_source_router_ip_change_is_detected(self):
        self.assertEqual(
            monitor.ip_change("100.64.0.10", "100.64.0.11"),
            ("100.64.0.10", "100.64.0.11"),
        )

    def test_same_source_public_ip_change_is_detected(self):
        self.assertEqual(
            monitor.ip_change("203.0.113.10", "203.0.113.11"),
            ("203.0.113.10", "203.0.113.11"),
        )

    def test_latest_cpu_temperature_uses_newest_valid_value(self):
        self.assertEqual(monitor.latest_cpu_temperature([116, 115, 114]), 116.0)
        self.assertEqual(monitor.latest_cpu_temperature(["116", 115]), 116.0)

    def test_latest_cpu_temperature_rejects_empty_zero_and_invalid(self):
        self.assertIsNone(monitor.latest_cpu_temperature([]))
        self.assertIsNone(monitor.latest_cpu_temperature([0]))
        self.assertIsNone(monitor.latest_cpu_temperature(["bad"]))
        self.assertIsNone(monitor.latest_cpu_temperature([300]))

    def test_temperature_api_failure_is_best_effort(self):
        fritz = monitor.Fritz("192.0.2.1")
        fritz.fc = Mock()
        fritz.fc.get_cpu_temperatures.side_effect = RuntimeError("unsupported")
        self.assertIsNone(fritz._cpu_temperature())

    def test_estimated_router_boot_time_uses_current_uptime(self):
        boot = monitor.estimated_router_boot_time(
            "2026-09-06T03:15:41+02:00", 119
        )
        self.assertEqual(boot.isoformat(timespec="seconds"), "2026-09-06T03:13:42+02:00")

    def test_reboot_association_uses_outage_containing_estimated_boot(self):
        conn = self.event_db()
        target_id = monitor.add_event(
            conn,
            "NETWORK_LINK_DOWN",
            {},
            start="2026-09-06T03:13:15+02:00",
            end="2026-09-06T03:14:29+02:00",
            duration=74.0,
        )
        monitor.add_event(
            conn,
            "DNS_FAILURE",
            {},
            start="2026-09-06T03:15:00+02:00",
            end="2026-09-06T03:15:10+02:00",
            duration=10.0,
        )
        reboot_id = monitor.add_event(
            conn,
            "FRITZBOX_REBOOT_DETECTED",
            {},
            start="2026-09-06T03:15:41+02:00",
            end="2026-09-06T03:15:41+02:00",
            duration=0,
        )
        related = monitor.associate_reboot_with_incident(
            conn,
            reboot_id,
            "2026-09-06T03:15:41+02:00",
            {
                "previous_router_uptime_s": 43246,
                "current_router_uptime_s": 119,
            },
        )
        self.assertEqual(related, target_id)
        details = json.loads(
            conn.execute("SELECT details_json FROM events WHERE id=?", (target_id,)).fetchone()[0]
        )
        self.assertEqual(
            details["confirmed_router_reboot"]["estimated_boot_ts"],
            "2026-09-06T03:13:42+02:00",
        )
        conn.close()

    def test_reboot_association_does_not_use_unrelated_recent_outage(self):
        conn = self.event_db()
        monitor.add_event(
            conn,
            "DNS_FAILURE",
            {},
            start="2026-09-06T03:15:00+02:00",
            end="2026-09-06T03:15:10+02:00",
            duration=10.0,
        )
        reboot_id = monitor.add_event(
            conn,
            "FRITZBOX_REBOOT_DETECTED",
            {},
            start="2026-09-06T03:15:41+02:00",
            end="2026-09-06T03:15:41+02:00",
            duration=0,
        )
        related = monitor.associate_reboot_with_incident(
            conn,
            reboot_id,
            "2026-09-06T03:15:41+02:00",
            {
                "previous_router_uptime_s": 43246,
                "current_router_uptime_s": 119,
            },
        )
        self.assertIsNone(related)
        conn.close()

    def test_incident_escalation_reuses_one_event_row(self):
        conn = self.event_db()
        start = "2026-09-06T03:13:15+02:00"
        details = {"classification_history": [{"ts": start, "event_type": "DNS_FAILURE"}]}
        event_id = monitor.add_event(conn, "DNS_FAILURE", details, start=start)
        kind, escalated = monitor.apply_incident_classification(
            conn,
            event_id,
            "DNS_FAILURE",
            details,
            "2026-09-06T03:13:29+02:00",
            "NETWORK_LINK_DOWN",
        )
        self.assertTrue(escalated)
        self.assertEqual(kind, "NETWORK_LINK_DOWN")
        rows = conn.execute(
            "SELECT id,event_type,details_json FROM events"
        ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1], "NETWORK_LINK_DOWN")
        payload = json.loads(rows[0][2])
        self.assertEqual(payload["classification_history"][-1]["event_type"], "NETWORK_LINK_DOWN")
        conn.close()

    def test_weaker_classification_does_not_downgrade_incident(self):
        conn = self.event_db()
        start = "2026-09-06T03:13:29+02:00"
        details = {"classification_history": [{"ts": start, "event_type": "NETWORK_LINK_DOWN"}]}
        event_id = monitor.add_event(conn, "NETWORK_LINK_DOWN", details, start=start)
        kind, escalated = monitor.apply_incident_classification(
            conn,
            event_id,
            "NETWORK_LINK_DOWN",
            details,
            "2026-09-06T03:13:59+02:00",
            "INTERNET_UNREACHABLE",
        )
        self.assertFalse(escalated)
        self.assertEqual(kind, "NETWORK_LINK_DOWN")
        row = conn.execute("SELECT event_type FROM events WHERE id=?", (event_id,)).fetchone()
        self.assertEqual(row[0], "NETWORK_LINK_DOWN")
        conn.close()

    def test_existing_database_migrates_temperature_column_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.sqlite3"
            conn = sqlite3.connect(path)
            conn.execute(
                """
                CREATE TABLE samples(
                  id INTEGER PRIMARY KEY, ts TEXT, carrier INTEGER, gateway TEXT, gateway_ok INTEGER, gateway_ms REAL,
                  internet_ok INTEGER, internet_ms REAL, dns_ok INTEGER, dns_ms REAL, http_ok INTEGER, http_ms REAL,
                  public_ip TEXT, router_uptime_s INTEGER, router_model TEXT, fritzos TEXT, wan_status TEXT,
                  wan_uptime_s INTEGER, wan_ip TEXT, wan_last_error TEXT, wan_transport TEXT, pppoe_ac_name TEXT,
                  fritz_error TEXT
                )
                """
            )
            conn.execute(
                "INSERT INTO samples(id,ts,carrier,gateway,gateway_ok,internet_ok,dns_ok,http_ok) VALUES(1,?,?,?,?,?,?,?)",
                ("2026-09-05T12:00:00+00:00", 1, "192.168.1.1", 1, 1, 1, 1),
            )
            conn.commit()
            conn.close()

            migrated = monitor.connect_db(path)
            columns = {row[1] for row in migrated.execute("PRAGMA table_info(samples)")}
            self.assertIn("router_cpu_temp_c", columns)
            self.assertEqual(
                migrated.execute("SELECT COUNT(*) FROM samples").fetchone()[0],
                1,
            )
            migrated.close()


if __name__ == "__main__":
    unittest.main()
