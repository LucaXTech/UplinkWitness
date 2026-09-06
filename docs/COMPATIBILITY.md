# Compatibility matrix

This document separates **verified configurations** from development candidates and planned/community-reported support. UplinkWitness intentionally avoids claiming broad compatibility without evidence.

## Verified by the maintainer

| Host / environment | Architecture | Network path | Mode | Router | Validation status |
| --- | --- | --- | --- | --- | --- |
| Raspberry Pi running Debian 13 (trixie) | ARM64 / aarch64 | Physical Ethernet | Generic | ordinary default-gateway path | Fresh install, systemd services, gateway/interface autodetection, Internet/DNS/HTTP probes, physical cable disconnect, `NETWORK_LINK_DOWN` classification, automatic recovery, persistence and outage-duration consistency verified |
| Raspberry Pi running Debian 13 (trixie) | ARM64 / aarch64 | Physical Ethernet | FRITZ!Box enhanced | FRITZ!Box 5530 Fiber, FRITZ!OS 8.20, PPPoE, external ONT -> Ethernet WAN | TR-064 connectivity, router model/firmware, WAN state/transport, reboot detection/correlation, source-separated WAN/public IP handling, CPU-temperature telemetry, backwards-compatible SQLite migration, TCP and IPv6 probes, live ICMP loss/jitter window, host speed/duplex, gateway-neighbour state, WANCommon access/link state, Online Monitor activity/sync context, dashboard, wallboard endpoint and report/export paths verified on real hardware |
| Ubuntu under WSL2 | x86_64 | Virtualized network | Generic / install regression | LAN gateway reachable from WSL | Installer/systemd flow, generic monitoring, dashboard and automated tests verified; not used to claim physical-link carrier behavior |

## v1.3 maintainer validation record

The v1.3 diagnostics candidate was physically validated on 2026-09-06 at commit `ae00f0d` using the existing ARM64 Raspberry Pi + FRITZ!Box 5530 / FRITZ!OS 8.20 external-ONT deployment.

Observed results:

- full Raspberry Pi unit-test suite passed: 51/51
- both systemd services restarted and remained active
- the existing SQLite database migrated in place with all new nullable v1.3 columns present
- independent TCP-connect evidence was healthy
- IPv6 reachability was detected and healthy because an IPv6 default route was present
- recent live-probe ICMP quality reported 0% loss and a finite jitter value
- Linux host link reported 100 Mbps full duplex and the gateway neighbour was reachable
- `WANCommonInterfaceConfig` reported active access type `Ethernet` and physical link `Up`
- Online Monitor returned live WAN activity with sync mode `ATA`
- router CPU-temperature telemetry remained available
- `X_AVM-DE_WANFiber` optical fields remained null, as required for this external-ONT / Ethernet-WAN topology even though the service is advertised by the router
- dashboard, `/wallboard`, ISP report and CSV export endpoints all returned successfully
- no recent monitor/dashboard traceback, exception, failed or critical service log entries were found after restart

The WANCommon result is the important topology check: service presence is not treated as proof of an active medium. On this installation the physically meaningful WAN path is external ONT -> Ethernet, so fiber optical telemetry correctly remains unavailable.

The LG webOS browser itself is not part of this compatibility claim yet. `/wallboard` is implemented as a dependency-free large-display page and has been validated through application tests and the physical Raspberry Pi HTTP endpoint; TV power-on/autolaunch behavior remains device-specific.

## Automated regression coverage

The automated regression suite runs in CI against Python 3.11 and 3.13. Test coverage evolves with the project, so this matrix does not pin a stale test-count total to a specific release.

Current regression coverage includes generic/FRITZ mode selection, gateway-probe behavior, outage classification/escalation, router/public-IP source separation, reboot correlation, temperature freshness/failure handling, router-adapter capability behavior, WANCommon parsing, Online Monitor downstream/upstream parsing, active-only fiber collection, host route/link helpers, TCP freshness semantics, IPv6 route handling, SQLite schema migration, live-probe link-quality statistics and dashboard/wallboard compatibility.

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

The following remain roadmap candidates, not current compatibility claims:

- OpenWrt enhanced telemetry
- MikroTik RouterOS enhanced telemetry
- UniFi gateway enhanced telemetry
- media-specific DSL/mobile diagnostics beyond the common adapter evidence surface
- standards-based UPnP IGD or SNMP adapters

Generic mode may already work behind many of these routers because it does not require router-specific APIs, but that is different from claiming a tested enhanced integration.
