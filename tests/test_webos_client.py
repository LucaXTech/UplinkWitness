import json
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBOS = ROOT / "clients" / "webos"


def png_size(path):
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", data[16:24])


class WebOSTVClientTests(unittest.TestCase):
    def test_appinfo_has_required_webos_metadata(self):
        info = json.loads((WEBOS / "appinfo.json").read_text(encoding="utf-8"))
        self.assertEqual(info["id"], "com.lucaxtech.app.uplinkwitness")
        self.assertEqual(info["type"], "web")
        self.assertEqual(info["main"], "index.html")
        self.assertEqual(info["version"], "0.1.0")
        self.assertEqual(info["resolution"], "1920x1080")
        self.assertEqual(info["icon"], "icon.png")
        self.assertEqual(info["largeIcon"], "largeicon.png")
        self.assertTrue(info["handlesRelaunch"])

    def test_webos_icons_match_lg_test_sizes(self):
        self.assertEqual(png_size(WEBOS / "icon.png"), (80, 80))
        self.assertEqual(png_size(WEBOS / "largeicon.png"), (130, 130))

    def test_launcher_persists_server_and_opens_wallboard(self):
        html = (WEBOS / "index.html").read_text(encoding="utf-8")
        self.assertIn("uplinkwitness.server", html)
        self.assertIn("/wallboard?webos=1", html)
        self.assertIn("405", html)  # Yellow key
        self.assertIn('placeholder="http://your-host.local:8080"', html)
        self.assertNotIn("linewatch.local", html)
        self.assertNotIn("type=\"module\"", html)

    def test_launcher_accepts_server_launch_parameter(self):
        html = (WEBOS / "index.html").read_text(encoding="utf-8")
        self.assertIn("webOSLaunch", html)
        self.assertIn("webOSRelaunch", html)
        self.assertIn("PalmSystem.launchParams", html)
        self.assertIn("detail.server", html)
        self.assertIn("openServer(detail.server)", html)

    def test_devmode_renewal_uses_current_cli_launch_flow(self):
        script = (WEBOS / "renew-devmode.sh").read_text(encoding="utf-8")
        installer = (WEBOS / "install-renewal-timer.sh").read_text(encoding="utf-8")
        self.assertIn("com.palmdts.devmode", script)
        self.assertIn('extend=true', script)
        self.assertIn("uplinkwitness-webos-renew.timer", installer)
        self.assertIn("OnUnitActiveSec=7d", installer)
        self.assertNotIn("192.168.", script + installer)

    def test_tv_wallboard_uses_legacy_safe_surface(self):
        html = (ROOT / "templates" / "wallboard.html").read_text(encoding="utf-8")
        for marker in ("Overview", "Network", "Router", "Incidents", "/api/status", "/api/history?hours=24", "/api/events?limit=30"):
            self.assertIn(marker, html)
        self.assertIn("XMLHttpRequest", html)
        self.assertNotIn("display:grid", html)
        self.assertNotIn("fetch(", html)
        self.assertNotIn("=>", html)
        self.assertNotIn("dateStyle", html)


if __name__ == "__main__":
    unittest.main()
