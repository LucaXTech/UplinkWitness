# Compatibility matrix

This document separates **verified** configurations from planned or community-reported support. UplinkWitness intentionally avoids claiming broad compatibility without evidence.

## Verified by the maintainer

| Host / environment | Architecture | Network path | Mode | Router | Validation status |
| --- | --- | --- | --- | --- | --- |
| Raspberry Pi running Debian 13 (trixie) | ARM64 / aarch64 | Physical Ethernet | Generic | ordinary default-gateway path | Fresh install, systemd services, gateway/interface autodetection, Internet/DNS/HTTP probes, physical cable disconnect, `NETWORK_LINK_DOWN` classification, automatic recovery, persistence and outage-duration consistency verified |
| Raspberry Pi running Debian 13 (trixie) | ARM64 / aarch64 | Physical Ethernet | FRITZ!Box enhanced | FRITZ!Box 5530 Fiber, FRITZ!OS 8.20, PPPoE | TR-064 connectivity, router model/firmware, WAN state/transport, reboot detection, WAN-session correlation, source-separated WAN/public IP handling, backwards-compatible SQLite migration, CPU-temperature telemetry and dashboard/API statistics verified on real hardware |
| Ubuntu under WSL2 | x86_64 | Virtualized network | Generic / install regression | LAN gateway reachable from WSL | Installer/systemd flow, generic monitoring, dashboard and automated tests verified; not used to claim physical-link carrier behavior |

## Automated regression coverage

The automated regression suite runs in CI against Python 3.11 and 3.13. Test coverage evolves with the project, so this matrix does not pin a stale test-count total to a specific release.

Current regression coverage includes generic/FRITZ mode selection, gateway-probe behavior, outage classification/escalation, router/public-IP source separation, reboot correlation, CPU-temperature parsing/failure handling, SQLite schema migration and dashboard history compatibility.

Automated tests complement real network-fault testing; they do not replace it.

## What “verified” means

A configuration should only be added to the verified table after the relevant sections of [`TESTING.md`](TESTING.md) have been exercised. For router-specific enhanced modes, vendor telemetry must be observed from a real compatible device or backed by a sufficiently detailed external validation report.

## Community compatibility reports

Compatibility reports are welcome for other:

- Debian / Ubuntu versions
- Raspberry Pi models and other ARM64 hosts
- x86_64 mini-PCs and home servers
- FRITZ!Box models / FRITZ!OS releases
- routers that do not answer ICMP on the default gateway

Please use the repository’s **Compatibility report** issue template and include the UplinkWitness version/commit, Linux distribution, architecture, interface type, router model and the checklist sections that passed or failed.

Releases through v1.1.0 were published under the former **LineWatch** name. Results from those releases remain valid after the public rename because the runtime monitoring core and compatibility identifiers are unchanged.

## Not yet advertised as supported

The following are roadmap candidates, not current compatibility claims:

- OpenWrt enhanced telemetry
- MikroTik RouterOS enhanced telemetry
- UniFi gateway enhanced telemetry
- FRITZ!Box physical-WAN/Online Monitor/fiber diagnostics beyond the currently shipped telemetry

Generic mode may already work behind many of these routers because it does not require router-specific APIs, but that is different from claiming a tested enhanced integration.
