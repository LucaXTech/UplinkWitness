#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import signal
import socket
import sqlite3
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from router_adapters import FritzAdapter, latest_cpu_temperature

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
EVENTS = DATA / "events"
DB = DATA / "linewatch.sqlite3"
DATA.mkdir(exist_ok=True)
EVENTS.mkdir(exist_ok=True)

POLL = float(os.getenv("LINEWATCH_POLL_SECONDS", "2"))
SAVE_EVERY = float(os.getenv("LINEWATCH_HEALTHY_PERSIST_SECONDS", "30"))
FRITZ_EVERY = float(os.getenv("LINEWATCH_FRITZ_POLL_SECONDS", "10"))
FRITZ_TEMP_EVERY = float(os.getenv("LINEWATCH_FRITZ_TEMP_SECONDS", "60"))
PUBLIC_IP_EVERY = float(os.getenv("LINEWATCH_PUBLIC_IP_SECONDS", "300"))
TCP_EVERY = float(os.getenv("LINEWATCH_TCP_SECONDS", "10"))
IPV6_EVERY = float(os.getenv("LINEWATCH_IPV6_SECONDS", "10"))
QUALITY_WINDOW_SECONDS = float(os.getenv("LINEWATCH_QUALITY_WINDOW_SECONDS", "300"))
RING_SECONDS = float(os.getenv("LINEWATCH_RING_SECONDS", "120"))
ROUTER_MODE = os.getenv("LINEWATCH_ROUTER_MODE", "auto").strip().lower() or "auto"
GATEWAY_PROBE = os.getenv("LINEWATCH_GATEWAY_PROBE", "auto").strip().lower() or "auto"
FRITZ_HOST = os.getenv("FRITZ_HOST", "").strip()
FRITZ_USER = os.getenv("FRITZ_USER", "").strip()
FRITZ_PASSWORD = os.getenv("FRITZ_PASSWORD", "")
IFACE = os.getenv("LINEWATCH_INTERFACE", "").strip()
PING_TARGETS = [
    x.strip()
    for x in os.getenv("LINEWATCH_PING_TARGETS", "1.1.1.1,8.8.8.8").split(",")
    if x.strip()
]
IPV6_PING_TARGETS = [
    x.strip()
    for x in os.getenv(
        "LINEWATCH_IPV6_PING_TARGETS",
        "2606:4700:4700::1111,2001:4860:4860::8888",
    ).split(",")
    if x.strip()
]
TCP_HOST = os.getenv("LINEWATCH_TCP_HOST", "1.1.1.1").strip()
TCP_PORT = int(os.getenv("LINEWATCH_TCP_PORT", "443"))
DNS_NAME = os.getenv("LINEWATCH_DNS_NAME", "www.cloudflare.com")
HTTP_URL = os.getenv(
    "LINEWATCH_HTTP_URL", "https://connectivitycheck.gstatic.com/generate_204"
)
PUBLIC_IP_URL = os.getenv("LINEWATCH_PUBLIC_IP_URL", "https://api.ipify.org")
USER_AGENT = "UplinkWitness/1.3.0"
STOP = False

ROUTER_MODES = {"auto", "generic", "fritz"}
GATEWAY_PROBE_MODES = {"auto", "on", "off"}
INCIDENT_PRIORITY = {
    "HTTP_CONNECTIVITY_FAILURE": 10,
    "DNS_FAILURE": 20,
    "INTERNET_UNREACHABLE": 30,
    "WAN_SESSION_DOWN": 40,
    "GATEWAY_UNREACHABLE": 50,
    "NETWORK_LINK_DOWN": 60,
}
REBOOT_ASSOCIATION_TOLERANCE_SECONDS = max(15.0, FRITZ_EVERY * 2)

SAMPLE_MIGRATIONS = {
    "router_cpu_temp_c": "REAL",
    "tcp_ok": "INTEGER",
    "tcp_ms": "REAL",
    "ipv6_ok": "INTEGER",
    "ipv6_ms": "REAL",
    "icmp_loss_pct": "REAL",
    "icmp_jitter_ms": "REAL",
    "interface_speed_mbps": "REAL",
    "interface_duplex": "TEXT",
    "gateway_neighbor_state": "TEXT",
    "wan_access_type": "TEXT",
    "wan_physical_status": "TEXT",
    "wan_down_bytes_s": "REAL",
    "wan_up_bytes_s": "REAL",
    "wan_sync_group": "TEXT",
    "wan_sync_mode": "TEXT",
    "fiber_rx_dbm": "REAL",
    "fiber_tx_dbm": "REAL",
    "fiber_rx_low_dbm": "REAL",
    "fiber_rx_high_dbm": "REAL",
    "fiber_tx_low_dbm": "REAL",
    "fiber_tx_high_dbm": "REAL",
    "fiber_mode": "TEXT",
    "fiber_resyncs": "INTEGER",
    "fiber_errors_rx": "INTEGER",
    "fiber_errors_tx": "INTEGER",
}


def now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def default_route(family=4):
    """Return (gateway, interface) for the first default route of an IP family."""
    flag = "-6" if int(family) == 6 else "-4"
    try:
        out = subprocess.check_output(
            ["ip", flag, "route", "show", "default"], text=True, timeout=2
        )
        line = next((line for line in out.splitlines() if line.strip()), "")
        if not line:
            return None, None
        parts = line.split()
        gateway = parts[parts.index("via") + 1] if "via" in parts else None
        interface = parts[parts.index("dev") + 1] if "dev" in parts else None
        return gateway, interface
    except Exception:
        return None, None


def route_change(previous, current):
    """Describe a route replacement, disappearance or restoration after baseline."""
    if previous is None or current is None or previous == current:
        return None
    return {
        "previous_gateway": previous[0],
        "previous_interface": previous[1],
        "new_gateway": current[0],
        "new_interface": current[1],
    }


def carrier(interface):
    if not interface:
        return None
    try:
        return int(
            Path(f"/sys/class/net/{interface}/carrier").read_text().strip() == "1"
        )
    except Exception:
        return None


def interface_details(interface, sysfs_root=Path("/sys/class/net")):
    if not interface:
        return None, None
    base = Path(sysfs_root) / interface
    speed = duplex = None
    try:
        value = float((base / "speed").read_text().strip())
        if value > 0:
            speed = value
    except Exception:
        pass
    try:
        value = (base / "duplex").read_text().strip().lower()
        if value in {"full", "half"}:
            duplex = value
    except Exception:
        pass
    return speed, duplex


def neighbor_state(gateway):
    if not gateway:
        return None
    try:
        out = subprocess.check_output(
            ["ip", "neigh", "show", gateway], text=True, timeout=2
        ).strip()
    except Exception:
        return None
    known = {
        "INCOMPLETE",
        "REACHABLE",
        "STALE",
        "DELAY",
        "PROBE",
        "FAILED",
        "NOARP",
        "PERMANENT",
    }
    for token in reversed(out.split()):
        token = token.upper()
        if token in known:
            return token
    return None


def ping(host, family=4):
    if not host:
        return 0, None
    cmd = ["ping"]
    if int(family) == 6:
        cmd.append("-6")
    cmd += ["-n", "-c", "1", "-W", "1", host]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=2.5)
        if p.returncode:
            return 0, None
        m = re.search(r"time[=<]([\d.]+)\s*ms", p.stdout)
        return 1, float(m.group(1)) if m else None
    except Exception:
        return 0, None


def quality_window_stats(probes):
    """Return loss and jitter from every live ICMP probe in the rolling window.

    Jitter is the mean absolute latency delta only across adjacent successful
    probes; a failed probe breaks the latency sequence instead of being skipped.
    """
    if not probes:
        return None, None
    success_count = sum(1 for _, ok, _ in probes if ok)
    loss_pct = round(100.0 * (len(probes) - success_count) / len(probes), 2)
    deltas = []
    previous_ms = None
    for _, ok, ms in probes:
        if not ok or ms is None:
            previous_ms = None
            continue
        current_ms = float(ms)
        if previous_ms is not None:
            deltas.append(abs(current_ms - previous_ms))
        previous_ms = current_ms
    jitter_ms = round(sum(deltas) / len(deltas), 2) if deltas else None
    return loss_pct, jitter_ms


def tcp_check(host=None, port=None):
    host = TCP_HOST if host is None else host
    port = TCP_PORT if port is None else int(port)
    if not host:
        return 0, None
    start = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=2.5):
            pass
        return 1, round((time.monotonic() - start) * 1000, 2)
    except Exception:
        return 0, None


def dns_check():
    start = time.monotonic()
    try:
        socket.getaddrinfo(DNS_NAME, 443, type=socket.SOCK_STREAM)
        return 1, round((time.monotonic() - start) * 1000, 2)
    except Exception:
        return 0, None


def http_check():
    import urllib.request

    start = time.monotonic()
    try:
        req = urllib.request.Request(HTTP_URL, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=3) as response:
            response.read(32)
        return 1, round((time.monotonic() - start) * 1000, 2)
    except Exception:
        return 0, None


def public_ip():
    import urllib.request

    try:
        req = urllib.request.Request(PUBLIC_IP_URL, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=3) as response:
            return response.read(128).decode().strip() or None
    except Exception:
        return None


def resolve_router_mode(mode=None, user=None, password=None):
    mode = ROUTER_MODE if mode is None else mode.strip().lower()
    user = FRITZ_USER if user is None else user
    password = FRITZ_PASSWORD if password is None else password
    if mode not in ROUTER_MODES:
        raise ValueError(
            f"Invalid LINEWATCH_ROUTER_MODE={mode!r}; expected auto, generic or fritz"
        )
    if mode == "generic":
        return "generic"
    if mode == "fritz":
        if not user or not password:
            raise ValueError("FRITZ mode requires FRITZ_USER and FRITZ_PASSWORD")
        return "fritz"
    return "fritz" if user and password else "generic"


def resolve_gateway_probe(mode=None):
    mode = GATEWAY_PROBE if mode is None else mode.strip().lower()
    if mode not in GATEWAY_PROBE_MODES:
        raise ValueError(
            f"Invalid LINEWATCH_GATEWAY_PROBE={mode!r}; expected auto, on or off"
        )
    if mode == "on":
        return True
    if mode == "off":
        return False
    return None


class Fritz(FritzAdapter):
    def __init__(self, host, user=None, password=None, **kwargs):
        super().__init__(
            host,
            FRITZ_USER if user is None else user,
            FRITZ_PASSWORD if password is None else password,
            temp_interval=kwargs.pop("temp_interval", FRITZ_TEMP_EVERY),
            **kwargs,
        )


def ip_change(previous, current):
    if previous and current and previous != current:
        return previous, current
    return None


def classification_priority(kind):
    return INCIDENT_PRIORITY.get(kind, 0)


def record_classification(details, ts, kind):
    history = details.setdefault("classification_history", [])
    if not history or history[-1].get("event_type") != kind:
        history.append({"ts": ts, "event_type": kind})


def update_event(conn, event_id, *, kind=None, details=None):
    fields = []
    values = []
    if kind is not None:
        fields.append("event_type=?")
        values.append(kind)
    if details is not None:
        fields.append("details_json=?")
        values.append(json.dumps(details, ensure_ascii=False))
    if not fields:
        return
    values.append(event_id)
    conn.execute(f"UPDATE events SET {','.join(fields)} WHERE id=?", values)
    conn.commit()


def apply_incident_classification(
    conn, event_id, current_kind, details, ts, new_kind
):
    before = len(details.get("classification_history", []))
    record_classification(details, ts, new_kind)
    history_changed = len(details.get("classification_history", [])) != before
    if classification_priority(new_kind) > classification_priority(current_kind):
        current_kind = new_kind
        details["final_classification"] = new_kind
        update_event(conn, event_id, kind=new_kind, details=details)
        return current_kind, True
    if history_changed:
        update_event(conn, event_id, details=details)
    return current_kind, False


@dataclass
class Sample:
    ts: str
    carrier: Optional[int]
    gateway: Optional[str]
    gateway_ok: int
    gateway_ms: Optional[float]
    internet_ok: int
    internet_ms: Optional[float]
    dns_ok: int
    dns_ms: Optional[float]
    http_ok: int
    http_ms: Optional[float]
    public_ip: Optional[str]
    router_uptime_s: Optional[int]
    router_model: Optional[str]
    fritzos: Optional[str]
    wan_status: Optional[str]
    wan_uptime_s: Optional[int]
    wan_ip: Optional[str]
    wan_last_error: Optional[str]
    wan_transport: Optional[str]
    pppoe_ac_name: Optional[str]
    fritz_error: Optional[str]
    router_cpu_temp_c: Optional[float] = None
    tcp_ok: Optional[int] = None
    tcp_ms: Optional[float] = None
    ipv6_ok: Optional[int] = None
    ipv6_ms: Optional[float] = None
    icmp_loss_pct: Optional[float] = None
    icmp_jitter_ms: Optional[float] = None
    interface_speed_mbps: Optional[float] = None
    interface_duplex: Optional[str] = None
    gateway_neighbor_state: Optional[str] = None
    wan_access_type: Optional[str] = None
    wan_physical_status: Optional[str] = None
    wan_down_bytes_s: Optional[float] = None
    wan_up_bytes_s: Optional[float] = None
    wan_sync_group: Optional[str] = None
    wan_sync_mode: Optional[str] = None
    fiber_rx_dbm: Optional[float] = None
    fiber_tx_dbm: Optional[float] = None
    fiber_rx_low_dbm: Optional[float] = None
    fiber_rx_high_dbm: Optional[float] = None
    fiber_tx_low_dbm: Optional[float] = None
    fiber_tx_high_dbm: Optional[float] = None
    fiber_mode: Optional[str] = None
    fiber_resyncs: Optional[int] = None
    fiber_errors_rx: Optional[int] = None
    fiber_errors_tx: Optional[int] = None


def _ensure_sample_column(conn, name, definition):
    columns = {row[1] for row in conn.execute("PRAGMA table_info(samples)")}
    if name not in columns:
        conn.execute(f"ALTER TABLE samples ADD COLUMN {name} {definition}")


def connect_db(path=None):
    db_path = DB if path is None else path
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS samples(
          id INTEGER PRIMARY KEY, ts TEXT, carrier INTEGER, gateway TEXT, gateway_ok INTEGER, gateway_ms REAL,
          internet_ok INTEGER, internet_ms REAL, dns_ok INTEGER, dns_ms REAL, http_ok INTEGER, http_ms REAL,
          public_ip TEXT, router_uptime_s INTEGER, router_model TEXT, fritzos TEXT, wan_status TEXT,
          wan_uptime_s INTEGER, wan_ip TEXT, wan_last_error TEXT, wan_transport TEXT, pppoe_ac_name TEXT,
          fritz_error TEXT, router_cpu_temp_c REAL, tcp_ok INTEGER, tcp_ms REAL, ipv6_ok INTEGER,
          ipv6_ms REAL, icmp_loss_pct REAL, icmp_jitter_ms REAL, interface_speed_mbps REAL,
          interface_duplex TEXT, gateway_neighbor_state TEXT, wan_access_type TEXT, wan_physical_status TEXT,
          wan_down_bytes_s REAL, wan_up_bytes_s REAL, wan_sync_group TEXT, wan_sync_mode TEXT,
          fiber_rx_dbm REAL, fiber_tx_dbm REAL, fiber_rx_low_dbm REAL, fiber_rx_high_dbm REAL,
          fiber_tx_low_dbm REAL, fiber_tx_high_dbm REAL, fiber_mode TEXT, fiber_resyncs INTEGER,
          fiber_errors_rx INTEGER, fiber_errors_tx INTEGER)"""
    )
    for name, definition in SAMPLE_MIGRATIONS.items():
        _ensure_sample_column(conn, name, definition)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS events(
          id INTEGER PRIMARY KEY, start_ts TEXT, end_ts TEXT, duration_s REAL, event_type TEXT, details_json TEXT)"""
    )
    conn.commit()
    return conn


def save_sample(conn, sample):
    data = asdict(sample)
    conn.execute(
        f"INSERT INTO samples({','.join(data)}) VALUES({','.join('?' for _ in data)})",
        list(data.values()),
    )
    conn.commit()


def add_event(conn, kind, details, start=None, end=None, duration=None):
    start = start or now()
    cur = conn.execute(
        "INSERT INTO events(start_ts,end_ts,duration_s,event_type,details_json) VALUES(?,?,?,?,?)",
        (start, end, duration, kind, json.dumps(details, ensure_ascii=False)),
    )
    conn.commit()
    return cur.lastrowid


def close_event(conn, event_id, details, duration, end=None):
    conn.execute(
        "UPDATE events SET end_ts=?,duration_s=?,details_json=? WHERE id=?",
        (
            end or now(),
            round(duration, 2),
            json.dumps(details, ensure_ascii=False),
            event_id,
        ),
    )
    conn.commit()


def estimated_router_boot_time(detected_ts, current_router_uptime_s):
    try:
        detected = datetime.fromisoformat(detected_ts)
        uptime = float(current_router_uptime_s)
    except (TypeError, ValueError):
        return None
    if uptime < 0:
        return None
    return detected - timedelta(seconds=uptime)


def _incident_matches_boot(start_ts, end_ts, boot_time, tolerance_s):
    try:
        start = datetime.fromisoformat(start_ts)
        end = datetime.fromisoformat(end_ts) if end_ts else None
    except (TypeError, ValueError):
        return False
    return start - timedelta(seconds=tolerance_s) <= boot_time <= (
        end or boot_time
    ) + timedelta(seconds=tolerance_s)


def associate_reboot_with_incident(
    conn,
    reboot_event_id,
    detected_ts,
    reboot_details,
    open_event_id=None,
    open_details=None,
):
    boot_time = estimated_router_boot_time(
        detected_ts, reboot_details.get("current_router_uptime_s")
    )
    if boot_time is None:
        return None
    association = {
        "event_id": reboot_event_id,
        "detected_ts": detected_ts,
        "estimated_boot_ts": boot_time.isoformat(timespec="seconds"),
        "previous_router_uptime_s": reboot_details.get("previous_router_uptime_s"),
        "current_router_uptime_s": reboot_details.get("current_router_uptime_s"),
    }
    if open_event_id is not None and open_details is not None:
        row = conn.execute(
            "SELECT start_ts FROM events WHERE id=?", (open_event_id,)
        ).fetchone()
        if row and _incident_matches_boot(
            row[0], None, boot_time, REBOOT_ASSOCIATION_TOLERANCE_SECONDS
        ):
            open_details["confirmed_router_reboot"] = association
            update_event(conn, open_event_id, details=open_details)
            return open_event_id
    rows = conn.execute(
        """SELECT id,start_ts,end_ts,details_json FROM events
           WHERE duration_s IS NOT NULL AND event_type IN (?,?,?,?,?,?)
           ORDER BY end_ts DESC LIMIT 20""",
        tuple(INCIDENT_PRIORITY),
    ).fetchall()
    exact = []
    tolerant = []
    for row in rows:
        try:
            start = datetime.fromisoformat(row[1])
            end = datetime.fromisoformat(row[2])
        except (TypeError, ValueError):
            continue
        if start <= boot_time <= end:
            exact.append((row, 0.0))
            continue
        if _incident_matches_boot(
            row[1], row[2], boot_time, REBOOT_ASSOCIATION_TOLERANCE_SECONDS
        ):
            distance = min(
                abs((boot_time - start).total_seconds()),
                abs((boot_time - end).total_seconds()),
            )
            tolerant.append((row, distance))
    candidates = exact or sorted(tolerant, key=lambda item: item[1])
    if not candidates:
        return None
    row = candidates[0][0]
    try:
        details = json.loads(row[3] or "{}")
    except Exception:
        details = {}
    details["confirmed_router_reboot"] = association
    update_event(conn, row[0], details=details)
    directory = EVENTS / f"event_{row[0]:05d}"
    if directory.exists():
        (directory / "details.json").write_text(
            json.dumps(details, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    return row[0]


def classify(sample, gateway_probe_active=True):
    """Classify incidents from synchronous core probes and router state.

    TCP/IPv6 are auxiliary evidence sampled at their own cadence. They are not
    allowed to mask a current outage classification with a cached older result.
    """
    if sample.carrier == 0:
        return "NETWORK_LINK_DOWN"
    internet_paths_ok = bool(sample.internet_ok or sample.dns_ok or sample.http_ok)
    if gateway_probe_active and not sample.gateway_ok and not internet_paths_ok:
        return "GATEWAY_UNREACHABLE"
    if sample.wan_status and sample.wan_status != "Connected":
        return "WAN_SESSION_DOWN"
    if not sample.internet_ok and not sample.dns_ok and not sample.http_ok:
        return "INTERNET_UNREACHABLE"
    if not sample.dns_ok:
        return "DNS_FAILURE"
    if not sample.http_ok:
        return "HTTP_CONNECTIVITY_FAILURE"
    return "OK"


def bundle(event_id, samples, log, details):
    directory = EVENTS / f"event_{event_id:05d}"
    directory.mkdir(exist_ok=True)
    (directory / "details.json").write_text(
        json.dumps(details, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (directory / "samples.jsonl").write_text(
        "".join(
            json.dumps(asdict(sample), ensure_ascii=False) + "\n"
            for sample in samples
        ),
        encoding="utf-8",
    )
    if log:
        (directory / "fritz_device_log.txt").write_text(log, encoding="utf-8")


def main():
    global STOP
    signal.signal(signal.SIGINT, lambda *_: globals().__setitem__("STOP", True))
    signal.signal(signal.SIGTERM, lambda *_: globals().__setitem__("STOP", True))
    try:
        router_mode = resolve_router_mode()
        gateway_probe_active = resolve_gateway_probe()
    except ValueError as exc:
        raise SystemExit(str(exc))

    route_gateway, route_iface = default_route(4)
    if not route_gateway:
        raise SystemExit(
            "No IPv4 default gateway found. Ensure the host has an active network connection."
        )
    interface = IFACE or route_iface
    router_host = FRITZ_HOST or route_gateway
    router_adapter = (
        Fritz(router_host, FRITZ_USER, FRITZ_PASSWORD)
        if router_mode == "fritz"
        else None
    )
    ring_samples = max(1, int(max(RING_SECONDS, POLL) / max(POLL, 0.1)))
    probe_label = (
        "auto"
        if gateway_probe_active is None
        else ("on" if gateway_probe_active else "off")
    )
    print(
        f"[UplinkWitness] gateway: {route_gateway}; interface: {interface or 'unknown'}; "
        f"router mode: {router_mode}; gateway probe: {probe_label}",
        flush=True,
    )
    if router_adapter:
        print(
            f"[UplinkWitness] FRITZ!Box/TR-064 host: {router_host}", flush=True
        )

    conn = connect_db()
    state = {}
    last_log = None
    last_fritz = last_save = last_ip = last_tcp = last_ipv6 = 0.0
    pub = None
    tcp_state = (None, None)
    ipv6_state = (None, None)
    prev_router = prev_wan = None
    prev_router_wan_ip = prev_public_ip = None
    prev_route = (route_gateway, route_iface)
    prev_wan_physical = prev_wan_access = None
    prev_link_details = (None, None)
    open_event = open_kind = open_started = None
    open_details = {}
    history = []
    probe_window = []

    while not STOP:
        cycle = time.monotonic()
        ts = now()
        current_gateway, current_iface = default_route(4)
        observed_route = (current_gateway, current_iface)
        changed_route = route_change(prev_route, observed_route)
        if changed_route:
            add_event(
                conn,
                "DEFAULT_ROUTE_CHANGED",
                changed_route,
                start=ts,
                end=ts,
                duration=0,
            )
        prev_route = observed_route

        gateway = current_gateway or route_gateway
        if current_gateway:
            route_gateway = current_gateway
        if not IFACE and current_iface:
            interface = current_iface

        car = carrier(interface)
        speed_mbps, duplex = interface_details(interface)
        link_details = (speed_mbps, duplex)
        speed_changed = (
            prev_link_details[0] is not None
            and speed_mbps is not None
            and prev_link_details[0] != speed_mbps
        )
        duplex_changed = (
            prev_link_details[1] is not None
            and duplex is not None
            and prev_link_details[1] != duplex
        )
        if speed_changed or duplex_changed:
            add_event(
                conn,
                "HOST_LINK_PROPERTIES_CHANGED",
                {
                    "previous_speed_mbps": prev_link_details[0],
                    "previous_duplex": prev_link_details[1],
                    "new_speed_mbps": speed_mbps,
                    "new_duplex": duplex,
                    "interface": interface,
                },
                start=ts,
                end=ts,
                duration=0,
            )
        if speed_mbps is not None or duplex is not None:
            prev_link_details = (
                speed_mbps if speed_mbps is not None else prev_link_details[0],
                duplex if duplex is not None else prev_link_details[1],
            )

        gok, gms = ping(gateway)
        neigh = neighbor_state(gateway)
        iok = 0
        ims = None
        for target in PING_TARGETS:
            iok, ims = ping(target)
            if iok:
                break
        mono = time.monotonic()
        probe_window.append((mono, iok, ims))
        cutoff = mono - max(1.0, QUALITY_WINDOW_SECONDS)
        probe_window = [item for item in probe_window if item[0] >= cutoff]
        loss_pct, jitter_ms = quality_window_stats(probe_window)
        dok, dms = dns_check()
        hok, hms = http_check()

        if mono - last_tcp >= TCP_EVERY or tcp_state[0] is None:
            tcp_state = tcp_check()
            last_tcp = mono
        _, ipv6_iface = default_route(6)
        if ipv6_iface:
            if mono - last_ipv6 >= IPV6_EVERY or ipv6_state[0] is None:
                ipv6_state = (0, None)
                for target in IPV6_PING_TARGETS:
                    ipv6_state = ping(target, family=6)
                    if ipv6_state[0]:
                        break
                last_ipv6 = mono
        else:
            ipv6_state = (None, None)

        if GATEWAY_PROBE == "auto" and gateway_probe_active is None:
            if gok:
                gateway_probe_active = True
                print(
                    "[UplinkWitness] gateway ICMP probe supported; using it for incident classification.",
                    flush=True,
                )
            elif iok or dok or hok:
                gateway_probe_active = False
                print(
                    "[UplinkWitness] gateway does not answer ICMP while Internet works; "
                    "gateway ping will not be used to declare outages.",
                    flush=True,
                )

        if mono - last_ip >= PUBLIC_IP_EVERY or pub is None:
            pub = public_ip() or pub
            last_ip = mono
        if router_adapter and mono - last_fritz >= FRITZ_EVERY:
            state, log = router_adapter.snapshot()
            last_log = log or last_log
            last_fritz = mono
        elif not router_adapter:
            state = {}

        sample = Sample(
            ts=ts,
            carrier=car,
            gateway=gateway,
            gateway_ok=gok,
            gateway_ms=gms,
            internet_ok=iok,
            internet_ms=ims,
            dns_ok=dok,
            dns_ms=dms,
            http_ok=hok,
            http_ms=hms,
            public_ip=pub,
            router_uptime_s=state.get("router_uptime_s"),
            router_model=state.get("router_model"),
            fritzos=state.get("fritzos"),
            wan_status=state.get("wan_status"),
            wan_uptime_s=state.get("wan_uptime_s"),
            wan_ip=state.get("wan_ip"),
            wan_last_error=state.get("wan_last_error"),
            wan_transport=state.get("wan_transport"),
            pppoe_ac_name=state.get("pppoe_ac_name"),
            fritz_error=state.get("fritz_error"),
            router_cpu_temp_c=state.get("router_cpu_temp_c"),
            tcp_ok=tcp_state[0],
            tcp_ms=tcp_state[1],
            ipv6_ok=ipv6_state[0],
            ipv6_ms=ipv6_state[1],
            icmp_loss_pct=loss_pct,
            icmp_jitter_ms=jitter_ms,
            interface_speed_mbps=speed_mbps,
            interface_duplex=duplex,
            gateway_neighbor_state=neigh,
            wan_access_type=state.get("wan_access_type"),
            wan_physical_status=state.get("wan_physical_status"),
            wan_down_bytes_s=state.get("wan_down_bytes_s"),
            wan_up_bytes_s=state.get("wan_up_bytes_s"),
            wan_sync_group=state.get("wan_sync_group"),
            wan_sync_mode=state.get("wan_sync_mode"),
            fiber_rx_dbm=state.get("fiber_rx_dbm"),
            fiber_tx_dbm=state.get("fiber_tx_dbm"),
            fiber_rx_low_dbm=state.get("fiber_rx_low_dbm"),
            fiber_rx_high_dbm=state.get("fiber_rx_high_dbm"),
            fiber_tx_low_dbm=state.get("fiber_tx_low_dbm"),
            fiber_tx_high_dbm=state.get("fiber_tx_high_dbm"),
            fiber_mode=state.get("fiber_mode"),
            fiber_resyncs=state.get("fiber_resyncs"),
            fiber_errors_rx=state.get("fiber_errors_rx"),
            fiber_errors_tx=state.get("fiber_errors_tx"),
        )
        history.append(sample)
        history = history[-ring_samples:]

        if (
            prev_wan_physical
            and sample.wan_physical_status
            and sample.wan_physical_status != prev_wan_physical
        ):
            add_event(
                conn,
                "WAN_PHYSICAL_LINK_CHANGED",
                {
                    "previous": prev_wan_physical,
                    "new": sample.wan_physical_status,
                },
                start=ts,
                end=ts,
                duration=0,
            )
        if sample.wan_physical_status:
            prev_wan_physical = sample.wan_physical_status
        if (
            prev_wan_access
            and sample.wan_access_type
            and sample.wan_access_type != prev_wan_access
        ):
            add_event(
                conn,
                "WAN_ACCESS_TYPE_CHANGED",
                {"previous": prev_wan_access, "new": sample.wan_access_type},
                start=ts,
                end=ts,
                duration=0,
            )
        if sample.wan_access_type:
            prev_wan_access = sample.wan_access_type

        router_reboot = False
        if sample.router_uptime_s is not None:
            router_uptime = int(sample.router_uptime_s)
            if prev_router is not None and router_uptime + 30 < prev_router:
                router_reboot = True
                details = {
                    "previous_router_uptime_s": prev_router,
                    "current_router_uptime_s": router_uptime,
                    "wan_status": sample.wan_status,
                    "wan_physical_status": sample.wan_physical_status,
                    "wan_access_type": sample.wan_access_type,
                    "wan_ip": sample.wan_ip,
                    "router_cpu_temp_c": sample.router_cpu_temp_c,
                }
                event_id = add_event(
                    conn,
                    "FRITZBOX_REBOOT_DETECTED",
                    details,
                    start=ts,
                    end=ts,
                    duration=0,
                )
                related_id = associate_reboot_with_incident(
                    conn,
                    event_id,
                    ts,
                    details,
                    open_event_id=open_event,
                    open_details=open_details if open_event is not None else None,
                )
                if related_id is not None:
                    details["related_incident_id"] = related_id
                    update_event(conn, event_id, details=details)
                bundle(event_id, history, last_log, details)
            prev_router = router_uptime

        if sample.wan_uptime_s is not None:
            wan_uptime = int(sample.wan_uptime_s)
            if prev_wan is not None and wan_uptime + 30 < prev_wan and not router_reboot:
                details = {
                    "previous_wan_uptime_s": prev_wan,
                    "current_wan_uptime_s": wan_uptime,
                    "router_uptime_s": sample.router_uptime_s,
                    "wan_ip": sample.wan_ip,
                    "wan_physical_status": sample.wan_physical_status,
                    "wan_access_type": sample.wan_access_type,
                }
                event_id = add_event(
                    conn,
                    "WAN_SESSION_RESET_DETECTED",
                    details,
                    start=ts,
                    end=ts,
                    duration=0,
                )
                bundle(event_id, history, last_log, details)
            prev_wan = wan_uptime

        router_ip_change = ip_change(prev_router_wan_ip, sample.wan_ip)
        if router_ip_change:
            add_event(
                conn,
                "WAN_IP_CHANGED",
                {
                    "previous": router_ip_change[0],
                    "new": router_ip_change[1],
                    "source": "router",
                },
                start=ts,
                end=ts,
                duration=0,
            )
        if sample.wan_ip:
            prev_router_wan_ip = sample.wan_ip
        public_change = ip_change(prev_public_ip, sample.public_ip)
        if public_change:
            add_event(
                conn,
                "WAN_IP_CHANGED",
                {
                    "previous": public_change[0],
                    "new": public_change[1],
                    "source": "public_probe",
                },
                start=ts,
                end=ts,
                duration=0,
            )
        if sample.public_ip:
            prev_public_ip = sample.public_ip

        kind = classify(sample, gateway_probe_active is True)
        unhealthy = kind != "OK"
        if unhealthy and open_event is None:
            open_kind = kind
            open_started = cycle
            open_details = {"start_state": asdict(sample)}
            record_classification(open_details, ts, kind)
            open_details["final_classification"] = kind
            open_event = add_event(conn, kind, open_details, start=ts)
            bundle(open_event, history, last_log, open_details)
        elif unhealthy and open_event is not None:
            open_kind, escalated = apply_incident_classification(
                conn, open_event, open_kind, open_details, ts, kind
            )
            if escalated:
                bundle(open_event, history, last_log, open_details)
        elif not unhealthy and open_event is not None:
            duration = cycle - open_started
            open_details.update(
                end_state=asdict(sample),
                duration_s=round(duration, 2),
                final_classification=open_kind,
            )
            close_event(conn, open_event, open_details, duration, end=ts)
            bundle(open_event, history, last_log, open_details)
            open_event = open_kind = open_started = None
            open_details = {}

        if unhealthy or mono - last_save >= SAVE_EVERY:
            save_sample(conn, sample)
            last_save = mono
        time.sleep(max(0.1, POLL - (time.monotonic() - cycle)))
    conn.close()


if __name__ == "__main__":
    main()
