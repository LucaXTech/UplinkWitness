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
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

try:
    from fritzconnection import FritzConnection
except ImportError:  # Generic mode can run without the optional FRITZ!Box adapter.
    FritzConnection = None

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
DNS_NAME = os.getenv("LINEWATCH_DNS_NAME", "www.cloudflare.com")
HTTP_URL = os.getenv(
    "LINEWATCH_HTTP_URL", "https://connectivitycheck.gstatic.com/generate_204"
)
PUBLIC_IP_URL = os.getenv("LINEWATCH_PUBLIC_IP_URL", "https://api.ipify.org")
STOP = False

ROUTER_MODES = {"auto", "generic", "fritz"}
GATEWAY_PROBE_MODES = {"auto", "on", "off"}

# Stronger evidence replaces weaker classifications for one continuous outage.
INCIDENT_PRIORITY = {
    "HTTP_CONNECTIVITY_FAILURE": 10,
    "DNS_FAILURE": 20,
    "INTERNET_UNREACHABLE": 30,
    "WAN_SESSION_DOWN": 40,
    "GATEWAY_UNREACHABLE": 50,
    "NETWORK_LINK_DOWN": 60,
}
REBOOT_ASSOCIATION_SECONDS = max(180.0, RING_SECONDS)
REBOOT_ASSOCIATION_TOLERANCE_SECONDS = max(15.0, FRITZ_EVERY * 2)


def now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def default_route():
    """Return (gateway IPv4, interface) for the host default route."""
    try:
        out = subprocess.check_output(
            ["ip", "-4", "route", "show", "default"], text=True, timeout=2
        )
        line = next((line for line in out.splitlines() if line.strip()), "")
        gw_match = re.search(r"\bvia\s+(\d+\.\d+\.\d+\.\d+)", line)
        dev_match = re.search(r"\bdev\s+(\S+)", line)
        return (
            gw_match.group(1) if gw_match else None,
            dev_match.group(1) if dev_match else None,
        )
    except Exception:
        return None, None


def carrier(interface):
    """Read Linux link carrier when sysfs exposes it; otherwise return unknown."""
    if not interface:
        return None
    try:
        return int(
            Path(f"/sys/class/net/{interface}/carrier").read_text().strip() == "1"
        )
    except Exception:
        return None


def ping(host):
    if not host:
        return 0, None
    try:
        p = subprocess.run(
            ["ping", "-n", "-c", "1", "-W", "1", host],
            capture_output=True,
            text=True,
            timeout=2.5,
        )
        if p.returncode:
            return 0, None
        m = re.search(r"time[=<]([\d.]+)\s*ms", p.stdout)
        return 1, float(m.group(1)) if m else None
    except Exception:
        return 0, None


def dns_check():
    t = time.monotonic()
    try:
        socket.getaddrinfo(DNS_NAME, 443, type=socket.SOCK_STREAM)
        return 1, round((time.monotonic() - t) * 1000, 2)
    except Exception:
        return 0, None


def http_check():
    t = time.monotonic()
    try:
        req = urllib.request.Request(
            HTTP_URL, headers={"User-Agent": "UplinkWitness/1.2.1"}
        )
        with urllib.request.urlopen(req, timeout=3) as response:
            response.read(32)
        return 1, round((time.monotonic() - t) * 1000, 2)
    except Exception:
        return 0, None


def public_ip():
    try:
        req = urllib.request.Request(
            PUBLIC_IP_URL, headers={"User-Agent": "UplinkWitness/1.2.1"}
        )
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


def latest_cpu_temperature(values):
    """Return the newest valid CPU temperature in Celsius, else None."""
    if not values:
        return None
    try:
        value = float(values[0])
    except (TypeError, ValueError):
        return None
    if not (0 < value < 250):
        return None
    return round(value, 1)


def ip_change(previous, current):
    """Return (old, new) only for a real same-source non-empty IP change."""
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


def apply_incident_classification(conn, event_id, current_kind, details, ts, new_kind):
    """Record observed classification and escalate the existing outage row if needed."""
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
    gateway: str
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
          fritz_error TEXT, router_cpu_temp_c REAL)"""
    )
    _ensure_sample_column(conn, "router_cpu_temp_c", "REAL")
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
    """Estimate the router boot timestamp from detection time and current uptime."""
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
    lower = start - timedelta(seconds=tolerance_s)
    upper = (end or boot_time) + timedelta(seconds=tolerance_s)
    return lower <= boot_time <= upper


def associate_reboot_with_incident(
    conn, reboot_event_id, detected_ts, reboot_details, open_event_id=None, open_details=None
):
    """Attach a confirmed reboot to the outage containing the estimated boot time."""
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
        """SELECT id,start_ts,end_ts,details_json
           FROM events
           WHERE duration_s IS NOT NULL
             AND event_type IN (?,?,?,?,?,?)
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
            distance = min(abs((boot_time - start).total_seconds()), abs((boot_time - end).total_seconds()))
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


class Fritz:
    def __init__(self, host):
        self.host = host
        self.fc = None
        self.wan = None
        self.last_temp = None
        self.last_temp_poll = 0.0

    def _connect(self):
        if FritzConnection is None:
            raise RuntimeError(
                "FRITZ!Box support requires the 'fritzconnection' Python package"
            )
        self.fc = FritzConnection(
            address=self.host,
            user=FRITZ_USER,
            password=FRITZ_PASSWORD,
            timeout=4,
        )
        candidates = [
            service
            for service in self.fc.services
            if "WANPPPConnection" in service or "WANIPConnection" in service
        ]
        self.wan = None
        for service in candidates:
            try:
                info = self.fc.call_action(service, "GetInfo")
                if info.get("NewEnable") and str(info.get("NewName", "")).lower() == "internet":
                    self.wan = service
                    break
                if info.get("NewEnable") and not self.wan:
                    self.wan = service
            except Exception:
                pass

    def _cpu_temperature(self):
        mono = time.monotonic()
        if self.last_temp is not None and mono - self.last_temp_poll < FRITZ_TEMP_EVERY:
            return self.last_temp
        self.last_temp_poll = mono
        try:
            value = latest_cpu_temperature(self.fc.get_cpu_temperatures())
            if value is not None:
                self.last_temp = value
        except Exception:
            pass
        return self.last_temp

    def snapshot(self):
        try:
            if not self.fc:
                self._connect()
            device = self.fc.call_action("DeviceInfo1", "GetInfo")
            out = {
                "router_uptime_s": device.get("NewUpTime"),
                "router_model": device.get("NewModelName"),
                "fritzos": device.get("NewSoftwareVersion"),
            }
            if self.wan:
                wan = self.fc.call_action(self.wan, "GetInfo")
                out.update(
                    wan_status=wan.get("NewConnectionStatus"),
                    wan_uptime_s=wan.get("NewUptime"),
                    wan_ip=wan.get("NewExternalIPAddress"),
                    wan_last_error=wan.get("NewLastConnectionError"),
                    wan_transport=wan.get("NewTransportType"),
                    pppoe_ac_name=wan.get("NewPPPoEACName"),
                )
            out["router_cpu_temp_c"] = self._cpu_temperature()
            try:
                log = self.fc.call_action("DeviceInfo1", "GetDeviceLog").get(
                    "NewDeviceLog"
                )
            except Exception:
                log = None
            out["fritz_error"] = None
            return out, log
        except Exception as exc:
            self.fc = None
            self.wan = None
            self.last_temp = None
            self.last_temp_poll = 0.0
            return {"fritz_error": f"{type(exc).__name__}: {exc}"}, None


def classify(sample, gateway_probe_active=True):
    """Classify an incident without assuming every network permits ICMP."""
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

    # ICMP may be blocked even when DNS and HTTP are healthy.
    return "OK"


def bundle(event_id, samples, log, details):
    directory = EVENTS / f"event_{event_id:05d}"
    directory.mkdir(exist_ok=True)
    (directory / "details.json").write_text(
        json.dumps(details, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (directory / "samples.jsonl").write_text(
        "".join(
            json.dumps(asdict(sample), ensure_ascii=False) + "\n" for sample in samples
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

    route_gateway, route_iface = default_route()
    if not route_gateway:
        raise SystemExit(
            "No IPv4 default gateway found. Ensure the host has an active network connection."
        )

    interface = IFACE or route_iface
    router_host = FRITZ_HOST or route_gateway
    fritz = Fritz(router_host) if router_mode == "fritz" else None
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
    if fritz:
        print(f"[UplinkWitness] FRITZ!Box/TR-064 host: {router_host}", flush=True)

    conn = connect_db()
    state = {}
    last_log = None
    last_fritz = last_save = last_ip = 0.0
    pub = None
    prev_router = prev_wan = None
    prev_router_wan_ip = None
    prev_public_ip = None
    open_event = None
    open_kind = None
    open_started = None
    open_details = {}
    history = []

    while not STOP:
        cycle = time.monotonic()
        ts = now()
        current_gateway, current_iface = default_route()
        gateway = current_gateway or route_gateway
        if current_gateway:
            route_gateway = current_gateway
        if not IFACE and current_iface:
            interface = current_iface

        car = carrier(interface)
        gok, gms = ping(gateway)

        iok = 0
        ims = None
        for target in PING_TARGETS:
            iok, ims = ping(target)
            if iok:
                break
        dok, dms = dns_check()
        hok, hms = http_check()
        mono = time.monotonic()

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

        if fritz and mono - last_fritz >= FRITZ_EVERY:
            state, log = fritz.snapshot()
            last_log = log or last_log
            last_fritz = mono
        elif not fritz:
            state = {}

        sample = Sample(
            ts,
            car,
            gateway,
            gok,
            gms,
            iok,
            ims,
            dok,
            dms,
            hok,
            hms,
            pub,
            state.get("router_uptime_s"),
            state.get("router_model"),
            state.get("fritzos"),
            state.get("wan_status"),
            state.get("wan_uptime_s"),
            state.get("wan_ip"),
            state.get("wan_last_error"),
            state.get("wan_transport"),
            state.get("pppoe_ac_name"),
            state.get("fritz_error"),
            state.get("router_cpu_temp_c"),
        )
        history.append(sample)
        history = history[-ring_samples:]

        router_reboot = False
        if sample.router_uptime_s is not None:
            router_uptime = int(sample.router_uptime_s)
            if prev_router is not None and router_uptime + 30 < prev_router:
                router_reboot = True
                details = {
                    "previous_router_uptime_s": prev_router,
                    "current_router_uptime_s": router_uptime,
                    "wan_status": sample.wan_status,
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

        router_change = ip_change(prev_router_wan_ip, sample.wan_ip)
        if router_change:
            add_event(
                conn,
                "WAN_IP_CHANGED",
                {
                    "previous": router_change[0],
                    "new": router_change[1],
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
