#!/usr/bin/env python3
from __future__ import annotations

import time
from typing import Optional, Protocol

try:
    from fritzconnection import FritzConnection
except ImportError:  # Generic mode must work without the optional FRITZ!Box dependency.
    FritzConnection = None


class RouterAdapter(Protocol):
    """Small vendor-neutral contract consumed by the monitor core."""

    def snapshot(self) -> tuple[dict, Optional[str]]:
        """Return nullable router telemetry and optional incident-log context."""


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


def numeric_series(value):
    """Parse a FRITZ! comma-separated numeric telemetry series."""
    if value in (None, ""):
        return []
    if isinstance(value, (list, tuple)):
        parts = value
    else:
        parts = str(value).split(",")
    result = []
    for item in parts:
        try:
            number = float(str(item).strip())
        except (TypeError, ValueError):
            continue
        if number >= 0:
            result.append(number)
    return result


def _positive_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    return round(number, 2)


def _optical_dbm(value):
    """Convert FRITZ! WANFiber dBm/1000 values to dBm; zero means unavailable/default."""
    try:
        raw = float(value)
    except (TypeError, ValueError):
        return None
    if raw == 0:
        return None
    return round(raw / 1000.0, 3)


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class FritzAdapter:
    """Best-effort FRITZ!Box/TR-064 adapter.

    The generic monitor does not depend on these fields. Unsupported actions remain
    nullable and do not make the adapter fail as a whole.
    """

    def __init__(
        self,
        host,
        user,
        password,
        *,
        temp_interval=60.0,
        connection_factory=None,
    ):
        self.host = host
        self.user = user
        self.password = password
        self.temp_interval = float(temp_interval)
        self.connection_factory = connection_factory or FritzConnection
        self.fc = None
        self.wan = None
        self.wan_common_services = []
        self.wan_fiber_services = []
        self.last_temp = None
        self.last_temp_poll = 0.0
        self.last_temp_ok = False

    def _connect(self):
        if self.connection_factory is None:
            raise RuntimeError(
                "FRITZ!Box support requires the 'fritzconnection' Python package"
            )
        self.fc = self.connection_factory(
            address=self.host,
            user=self.user,
            password=self.password,
            timeout=4,
        )
        services = list(self.fc.services)
        wan_candidates = [
            service
            for service in services
            if "WANPPPConnection" in service or "WANIPConnection" in service
        ]
        self.wan_common_services = [service for service in services if "WANCommon" in service]
        self.wan_fiber_services = [service for service in services if "WANFiber" in service]

        self.wan = None
        for service in wan_candidates:
            try:
                info = self.fc.call_action(service, "GetInfo")
                if info.get("NewEnable") and str(info.get("NewName", "")).lower() == "internet":
                    self.wan = service
                    break
                if info.get("NewEnable") and not self.wan:
                    self.wan = service
            except Exception:
                continue

    def _call_first(self, services, action, **kwargs):
        for service in services:
            try:
                return self.fc.call_action(service, action, **kwargs)
            except Exception:
                continue
        return None

    def _cpu_temperature(self):
        mono = time.monotonic()
        if mono - self.last_temp_poll < self.temp_interval:
            return self.last_temp if self.last_temp_ok else None

        self.last_temp_poll = mono
        self.last_temp_ok = False
        try:
            value = latest_cpu_temperature(self.fc.get_cpu_temperatures())
        except Exception:
            return None
        if value is None:
            return None
        self.last_temp = value
        self.last_temp_ok = True
        return value

    def _wan_common_snapshot(self):
        out = {
            "wan_access_type": None,
            "wan_physical_status": None,
            "wan_down_bytes_s": None,
            "wan_up_bytes_s": None,
            "wan_sync_group": None,
            "wan_sync_mode": None,
        }
        if not self.wan_common_services:
            return out

        common = self._call_first(self.wan_common_services, "GetCommonLinkProperties")
        if common:
            out["wan_access_type"] = common.get("NewWANAccessType")
            out["wan_physical_status"] = common.get("NewPhysicalLinkStatus")
            out["wan_down_bytes_s"] = _positive_number(
                common.get("NewX_AVM-DE_DownstreamCurrentMaxSpeed")
            )
            out["wan_up_bytes_s"] = _positive_number(
                common.get("NewX_AVM-DE_UpstreamCurrentMaxSpeed")
            )

        online = self._call_first(
            self.wan_common_services,
            "X_AVM-DE_GetOnlineMonitor",
            NewSyncGroupIndex=0,
        )
        if online:
            out["wan_sync_group"] = online.get("NewSyncGroupName")
            out["wan_sync_mode"] = online.get("NewSyncGroupMode")
            # Official FRITZ! documentation defines these series as bytes/s.
            # Keep only an aggregate recent value in SQLite instead of persisting arrays.
            if out["wan_down_bytes_s"] is None:
                down = numeric_series(online.get("Newmc_current_bps"))
                if down:
                    out["wan_down_bytes_s"] = round(max(down), 2)
            if out["wan_up_bytes_s"] is None:
                up = numeric_series(online.get("Newus_current_bps"))
                if up:
                    out["wan_up_bytes_s"] = round(max(up), 2)
        return out

    def _fiber_snapshot(self, access_type):
        out = {
            "fiber_rx_dbm": None,
            "fiber_tx_dbm": None,
            "fiber_rx_low_dbm": None,
            "fiber_rx_high_dbm": None,
            "fiber_tx_low_dbm": None,
            "fiber_tx_high_dbm": None,
            "fiber_mode": None,
            "fiber_resyncs": None,
            "fiber_errors_rx": None,
            "fiber_errors_tx": None,
        }
        # Service presence is not evidence that the FRITZ!Box is actually using fiber.
        if not self.wan_fiber_services or "fiber" not in str(access_type or "").lower():
            return out

        info = self._call_first(self.wan_fiber_services, "GetInfo")
        if info:
            out.update(
                fiber_rx_dbm=_optical_dbm(info.get("NewOpticalSignalLevel")),
                fiber_tx_dbm=_optical_dbm(info.get("NewTransmitOpticalLevel")),
                fiber_rx_low_dbm=_optical_dbm(info.get("NewLowerOpticalThreshold")),
                fiber_rx_high_dbm=_optical_dbm(info.get("NewUpperOpticalThreshold")),
                fiber_tx_low_dbm=_optical_dbm(info.get("NewLowerTransmitPowerThreshold")),
                fiber_tx_high_dbm=_optical_dbm(info.get("NewUpperTransmitPowerThreshold")),
                fiber_mode=info.get("NewFiberMode"),
            )

        stats = self._call_first(self.wan_fiber_services, "GetStatistics")
        if stats:
            out.update(
                fiber_resyncs=_int_or_none(stats.get("NewResyncs")),
                fiber_errors_rx=_int_or_none(stats.get("NewPacketErrorsReceived")),
                fiber_errors_tx=_int_or_none(stats.get("NewPacketErrorsSent")),
            )
        return out

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

            common = self._wan_common_snapshot()
            out.update(common)
            out.update(self._fiber_snapshot(common.get("wan_access_type")))
            out["router_cpu_temp_c"] = self._cpu_temperature()

            try:
                log = self.fc.call_action("DeviceInfo1", "GetDeviceLog").get("NewDeviceLog")
            except Exception:
                log = None
            out["fritz_error"] = None
            return out, log
        except Exception as exc:
            self.fc = None
            self.wan = None
            self.wan_common_services = []
            self.wan_fiber_services = []
            self.last_temp = None
            self.last_temp_poll = 0.0
            self.last_temp_ok = False
            return {"fritz_error": f"{type(exc).__name__}: {exc}"}, None
