# UplinkWitness roadmap

UplinkWitness is intentionally developed as a small, dependable Internet-connection black box rather than a general-purpose observability platform.

The roadmap is ordered by reliability and evidence quality first, feature count second.

## Stable baseline — v1.2.x

The current stable baseline provides:

- vendor-neutral Linux monitoring
- physical/link carrier detection where Linux exposes it
- gateway, Internet, DNS and HTTP probes
- source-separated public-IP and router-WAN-IP change tracking
- outage classification with in-place escalation to stronger evidence
- local SQLite history and incident bundles
- responsive dashboard and ISP-oriented reports
- optional FRITZ!Box/TR-064 telemetry for deeper WAN diagnostics
- FRITZ!Box reboot and WAN/PPPoE session-reset correlation
- best-effort FRITZ!Box CPU-temperature telemetry with 24 h history/statistics where supported

## v1.3 development milestone — richer evidence surfaces

The v1.3 development target groups the next diagnostic work into one coherent release instead of adding isolated probes one at a time.

### Generic Linux evidence

- independent TCP-connect evidence alongside ICMP/DNS/HTTP
- IPv6 reachability when the host has an IPv6 default route
- interface speed/duplex when exposed by Linux sysfs
- gateway neighbour/ARP state
- explicit default-route/interface changes, including disappearance/restoration
- recent ICMP packet-loss and jitter evidence derived from every live probe in a rolling window

TCP and IPv6 are auxiliary evidence sampled at their own cadence; cached auxiliary results must not mask a current outage classification. These features remain best-effort and must not require router credentials.

### Router adapter boundary

The common adapter contract is documented in [`docs/ROUTER_ADAPTERS.md`](docs/ROUTER_ADAPTERS.md). Vendor-specific access remains outside the generic monitor core and unsupported fields remain nullable.

This boundary is intended to unblock future OpenWrt/MikroTik/UniFi work without copying vendor conditionals into incident classification.

### FRITZ!Box physical WAN diagnostics

- `WANCommonInterfaceConfig` as the primary physical-WAN evidence source
- active WAN access type and physical link status
- current WAN activity from the newest documented utilization sample, with Online Monitor downstream/upstream arrays as fallback
- Online Monitor sync group/mode context
- physical-WAN/access-type change events for correlation
- active-fiber optical diagnostics through `X_AVM-DE_WANFiber` only when the WAN access type actually indicates fiber
- no persistence of SFP/GPON serial identifiers

Media-specific services remain secondary/model-dependent when they conflict with WANCommon telemetry. Multicast-rate telemetry is not substituted for ordinary downstream activity.

### Dashboard / wallboard

- expose the new host and WAN evidence in the normal dashboard and ISP report
- keep the existing mobile layout coherent
- provide a dependency-free `/wallboard` view intended for large displays and TV browsers such as LG webOS

Automatic TV browser launch at power-on remains device/platform dependent and is not part of the UplinkWitness guarantee.

## Validation before v1.3 stable

Before a v1.3 release is tagged:

- CI must pass on the supported Python matrix
- the existing Raspberry Pi / Debian deployment must upgrade its SQLite database in place
- generic host/TCP/IPv6/link evidence must degrade cleanly when unavailable
- the FRITZ!Box 5530 / FRITZ!OS 8.20 external-ONT deployment must report WANCommon access type/status without treating the advertised WANFiber service as active fiber
- WAN activity/sync telemetry must be physically checked against the live router
- dashboard, `/wallboard`, CSV and ISP exports must remain functional
- existing v1.2.x outage/reboot/IP/temperature behavior must regress cleanly

The detailed procedure lives in [`docs/TESTING.md`](docs/TESTING.md).

## Next integrations

After the adapter contract and v1.3 evidence surfaces are stable, candidate enhanced integrations include:

- OpenWrt
- MikroTik RouterOS
- UniFi gateways

A vendor is only listed as supported after a real implementation has been validated against actual hardware or a strong external compatibility report. Planned integrations are not advertised as current support.

## Packaging and portability

The automatic installer currently targets `apt` + `systemd` systems. Future portability work may include cleaner manual-install documentation and packaging/service recipes for additional Linux distributions.

Containerization is not automatically considered a win for UplinkWitness: network namespaces can hide the host link and default-route state that the monitor is specifically trying to observe. Any container deployment must preserve diagnostic fidelity.

## Non-goals

UplinkWitness is not trying to become:

- a hosted SaaS monitoring service
- a replacement for Prometheus/Grafana or full infrastructure observability
- a public Internet status page
- a router-management suite
- a cloud-dependent agent

The project should remain useful when the Internet is failing, keep its evidence local, and make unsupported claims conservatively.

## How to help

Useful contributions include compatibility reports, reproducible failure cases, tests, documentation and focused router-adapter work. See [`CONTRIBUTING.md`](CONTRIBUTING.md).
