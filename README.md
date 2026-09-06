# UplinkWitness

[![CI](https://github.com/LucaXTech/UplinkWitness/actions/workflows/ci.yml/badge.svg)](https://github.com/LucaXTech/UplinkWitness/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/LucaXTech/UplinkWitness)](https://github.com/LucaXTech/UplinkWitness/releases/latest)
![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![Linux](https://img.shields.io/badge/Linux-self--hosted-success)
![License](https://img.shields.io/badge/license-MIT-green)

> **Know what actually went down.**

**UplinkWitness is a self-hosted Internet connection black box for Linux.** Most uptime monitors tell you that something stopped answering; UplinkWitness tries to preserve enough local evidence to tell you **where the failure was**: local link, gateway, upstream Internet, DNS, HTTP, or — with optional router telemetry — the router/WAN session itself.

It works with ordinary routers in **generic Linux mode** and becomes more diagnostic with a **FRITZ!Box** through TR-064. A Raspberry Pi is a convenient always-on deployment target, **not a requirement**.

**Latest stable release:** [GitHub Releases](https://github.com/LucaXTech/UplinkWitness/releases/latest) · [Quick install](#quick-install) · [Compatibility](docs/COMPATIBILITY.md) · [Roadmap](ROADMAP.md) · [Router adapters](docs/ROUTER_ADAPTERS.md) · [Contributing](CONTRIBUTING.md)

> **Project rename:** releases through v1.1.0 were published as **LineWatch**. The public project is now **UplinkWitness**. Existing runtime identifiers such as `linewatch.service`, `LINEWATCH_*` environment variables and `data/linewatch.sqlite3` are intentionally retained for upgrade compatibility. See [docs/RENAMING.md](docs/RENAMING.md).

## v1.3 development

The current v1.3 development branch extends evidence quality without turning UplinkWitness into a general observability stack. It adds:

- independent TCP-connect evidence alongside ICMP, DNS and HTTP
- IPv6 reachability when Linux exposes an IPv6 default route
- host interface speed/duplex and gateway neighbour state
- default-route and host-link change evidence
- 24 h ICMP loss/jitter statistics
- a stable router-adapter boundary
- FRITZ!Box `WANCommonInterfaceConfig` physical-WAN status/access type
- best-effort WAN activity and Online Monitor sync context
- active-fiber optical diagnostics only when the actual WAN access type indicates fiber
- a dependency-free `/wallboard` intended for large displays and TV browsers such as LG webOS

These features remain **development candidates until physical v1.3 validation is complete**. See [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md) and [docs/TESTING.md](docs/TESTING.md); the latest tagged stable release remains v1.2.1.

## Screenshots

### Desktop dashboard

![UplinkWitness desktop dashboard](docs/screenshots/dashboard-desktop.png)

### Mobile dashboard

<p align="center">
  <img src="docs/screenshots/dashboard-mobile.png" alt="UplinkWitness mobile dashboard" width="360">
</p>

> The screenshots show the FRITZ!Box-enhanced dashboard from the stable v1.2.x baseline. Development UI may contain additional diagnostics.

## Why UplinkWitness?

A normal uptime check can tell you that a target stopped answering. That is useful, but it often does not tell you **which part of a home Internet connection failed**.

UplinkWitness combines multiple signals and keeps the evidence locally:

- Linux network-link state when available
- default-gateway reachability
- multiple Internet ICMP targets
- DNS resolution
- HTTP connectivity
- public IP changes
- outage duration and availability
- optional router/WAN telemetry

This is particularly useful for short or intermittent faults that disappear before ISP support looks at the line.

## Two operating modes

| Capability | Generic Linux | FRITZ!Box enhanced |
| --- | :---: | :---: |
| Internet reachability | ✅ | ✅ |
| DNS / HTTP checks | ✅ | ✅ |
| Latency history | ✅ | ✅ |
| Gateway monitoring | ✅ | ✅ |
| Public IP changes | ✅ | ✅ |
| Outage / downtime history | ✅ | ✅ |
| ISP report + CSV export | ✅ | ✅ |
| Router model / firmware | — | ✅ |
| Router uptime / reboot detection | — | ✅ |
| WAN-session uptime | — | ✅ |
| WAN / PPPoE reset detection | — | ✅ |
| Router CPU-temperature telemetry | — | ✅* |
| FRITZ!Box event log around incidents | — | ✅ |

`*` Best-effort and model/firmware dependent.

`LINEWATCH_ROUTER_MODE=auto` selects FRITZ!Box enhanced mode when credentials are configured; otherwise it runs generically.

## What it detects

### On any supported Linux host

Stable v1.2.x detection includes:

- local network-link loss when exposed by Linux sysfs
- gateway reachability changes
- complete Internet loss
- DNS failures
- HTTP connectivity failures
- public IP changes
- latency trends
- outage duration, total downtime and observed-period availability

The v1.3 development branch additionally records TCP-connect evidence, IPv6 reachability when available, link speed/duplex, gateway-neighbour state, route changes and packet-loss/jitter windows.

UplinkWitness does **not** assume that every router or Internet path answers ICMP. In automatic gateway-probe mode, a router that drops ping while other connectivity paths remain healthy is not incorrectly classified as down.

### With FRITZ!Box telemetry

Stable v1.2.x provides:

- FRITZ!Box reboot through router-uptime reset
- correlation of a confirmed reboot with the outage that contains the estimated router boot time
- WAN / PPPoE session reset without a router reboot
- WAN connection state
- source-separated router WAN IP tracking
- WAN transport details
- PPPoE access concentrator when exposed
- FRITZ!Box device logs around incidents when available
- best-effort CPU-temperature telemetry with 24 h min / average / max and trend history where supported

v1.3 development adds primary physical-WAN evidence from `WANCommonInterfaceConfig`, WAN activity/sync context and active-only `X_AVM-DE_WANFiber` optical diagnostics. Service presence alone is never treated as proof that a WAN medium is active.

## Dashboard and wallboard

The responsive local dashboard provides:

- current connection health
- automatic generic / FRITZ-enhanced presentation
- latency with 24 h min / average / P95 / max
- FRITZ!Box CPU-temperature trend with current / min / average / max when available
- outage counters and downtime statistics
- observed-period availability
- event timeline
- Italian / English UI
- CSV event export
- human-readable ISP diagnostic report

The v1.3 development branch adds the new host/physical-WAN evidence and a dedicated large-display view at:

```text
http://<host-lan-ip>:8080/wallboard
```

The wallboard has no external JavaScript dependency and is suitable for a TV browser. Whether a TV such as LG webOS automatically reopens that page when powered on is device/platform dependent, not an UplinkWitness guarantee.

Availability is calculated only over the period UplinkWitness has actually observed. A new installation does not pretend to have 30 days of monitoring history.

## Where it can run

The monitor is designed for an **always-on Linux host**. Good deployment targets include Raspberry Pi, Debian/Ubuntu mini-PCs, home servers, Linux VMs and other ARM/x86 Linux systems with the required networking tools.

For meaningful line diagnostics, an **Ethernet-connected always-on machine is recommended**. Wi-Fi can work, but then local wireless problems become part of what UplinkWitness observes.

The automatic installer currently targets systems with `apt` and `systemd`, including Debian, Ubuntu and Raspberry Pi OS. Other Linux distributions can use the manual setup path once Python, `iproute2` and `ping` are available.

## Compatibility status

The v1.2.x stable baseline has been validated on a physical ARM64 Raspberry Pi running Debian 13. Generic mode includes a controlled Ethernet disconnect/recovery test. FRITZ!Box enhanced mode has been validated with a FRITZ!Box 5530 Fiber on FRITZ!OS 8.20 and PPPoE, including reboot detection/correlation, backwards-compatible SQLite migration and CPU-temperature telemetry. WSL2/Ubuntu on x86_64 is also used for generic/install regression testing.

The v1.3 evidence surface is tracked separately as a physical-validation candidate rather than being silently folded into those stable claims.

See [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md) for the current matrix and [docs/TESTING.md](docs/TESTING.md) for the validation checklist.

## Quick install

Recommended: an always-on Debian/Ubuntu/Raspberry Pi OS machine connected by Ethernet.

```bash
git clone https://github.com/LucaXTech/UplinkWitness.git
cd UplinkWitness
chmod +x install.sh
./install.sh
```

The installer asks whether you want FRITZ!Box enhanced diagnostics.

### Generic mode

Choose **No** when asked about FRITZ!Box integration. No router credentials are required.

### FRITZ!Box enhanced mode

Choose **Yes** and provide a FRITZ!Box account allowed to access router settings through TR-064. A dedicated account is optional. Remote/Internet access for that account is not required.

After installation, open the dashboard on port `8080` of the Linux host, for example:

```text
http://<host-lan-ip>:8080
```

If the machine is already reachable as `linewatch.local`, that hostname continues to work; the project rename does not change your host's network name.

## Manual configuration

```bash
cp .env.example .env
chmod 600 .env
```

The most relevant stable options are:

```text
LINEWATCH_ROUTER_MODE=auto
LINEWATCH_INTERFACE=
LINEWATCH_GATEWAY_PROBE=auto

FRITZ_USER=
FRITZ_PASSWORD=
FRITZ_HOST=
```

v1.3 development also exposes optional TCP/IPv6 probe controls:

```text
LINEWATCH_TCP_HOST=1.1.1.1
LINEWATCH_TCP_PORT=443
LINEWATCH_TCP_SECONDS=10
LINEWATCH_IPV6_SECONDS=10
LINEWATCH_IPV6_PING_TARGETS=2606:4700:4700::1111,2001:4860:4860::8888
```

IPv6 is only probed when the host has an IPv6 default route. Leaving `LINEWATCH_INTERFACE` empty lets UplinkWitness detect the interface associated with the Linux IPv4 default route.

## Services

Existing service identifiers deliberately retain the original internal name:

```bash
systemctl status linewatch
systemctl status linewatch-dashboard
```

Live monitor log:

```bash
journalctl -u linewatch -f
```

## Remote access

The dashboard deliberately has no public-Internet authentication layer. **Do not expose port 8080 with router port forwarding.**

For private remote access, use a VPN or mesh VPN such as Tailscale.

## Data and privacy

Runtime data stays on the machine running UplinkWitness:

- `data/linewatch.sqlite3` — SQLite database; legacy-compatible filename
- `data/events/` — incident bundles and optional FRITZ!Box logs

The repository ignores `.env`, runtime databases and logs. Do not commit real router credentials, event logs, public IP addresses or personal network data.

v1.3 fiber diagnostics intentionally do not persist SFP serial numbers, GPON serial numbers or similar hardware identifiers.

## Architecture

```text
                  UplinkWitness Core
                          │
         ┌────────────────┼────────────────┐
         │                │                │
   Linux / gateway    Internet probes   Router adapter
         │          ICMP · TCP · DNS · HTTP    │
         │                │                    └── FRITZ!Box / TR-064
         │                │
         └────────────────┴───────────────┐
                                          │
                                  Incident classifier
                                          │
                              SQLite + event bundles
                                          │
                           Dashboard / wallboard :8080
```

The router integration contract is documented in [docs/ROUTER_ADAPTERS.md](docs/ROUTER_ADAPTERS.md). Generic monitoring must continue to work when an adapter is absent, partially supported or temporarily unavailable.

Potential future integrations include OpenWrt, MikroTik, UniFi and standards-based telemetry where reliable interfaces exist. They are **not currently advertised as supported**.

## Development

CI checks Python 3.11 and 3.13, compiles the monitor/dashboard, runs unit tests and validates the shell scripts.

Run tests locally with:

```bash
python -m unittest discover -s tests -v
```

Development features are promoted to stable only after the relevant physical validation in [docs/TESTING.md](docs/TESTING.md).

## Contributing

Bug reports, Linux compatibility results, FRITZ!Box model reports, tests and router-adapter contributions are welcome.

Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. The current development priorities are tracked in [ROADMAP.md](ROADMAP.md).

If you test UplinkWitness on different hardware, include Linux distribution/version, architecture, interface type, router model, operating mode and which validation sections passed or failed.

## Author

Created and maintained by **Luca Serioli** ([@LucaXTech](https://github.com/LucaXTech)).

See [AUTHORS.md](AUTHORS.md) for project attribution and contributor information.

## License

UplinkWitness is open-source software released under the **MIT License**. See [LICENSE](LICENSE).

## Status

Active early-stage open-source project. The goal is to keep the generic monitoring core small and dependable while adding deeper router diagnostics through optional adapters.
