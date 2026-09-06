# UplinkWitness roadmap

UplinkWitness is intentionally developed as a small, dependable Internet-connection black box rather than a general-purpose observability platform.

The roadmap is ordered by reliability and evidence quality first, feature count second.

## Validated baseline — v1.3

The current validated baseline provides:

- vendor-neutral Linux monitoring
- physical/link carrier detection where Linux exposes it
- gateway, Internet, DNS, HTTP and independent TCP-connect evidence
- IPv6 reachability when the host has an IPv6 default route
- recent rolling ICMP packet-loss and jitter evidence derived from every live probe
- interface speed/duplex, gateway-neighbour state and explicit default-route/interface changes
- source-separated public-IP and router-WAN-IP change tracking
- outage classification with in-place escalation to stronger evidence
- local SQLite history and incident bundles
- responsive dashboard, ISP-oriented reports and a dependency-free `/wallboard`
- a documented router-adapter boundary that keeps vendor-specific access outside the generic core
- optional FRITZ!Box/TR-064 telemetry for deeper WAN diagnostics
- FRITZ!Box reboot and WAN/PPPoE session-reset correlation
- best-effort FRITZ!Box CPU-temperature telemetry with 24 h history/statistics where supported
- `WANCommonInterfaceConfig` access type / physical-link evidence and Online Monitor activity/sync context
- active-only `X_AVM-DE_WANFiber` optical diagnostics when the actual WAN medium is fiber

TCP and IPv6 are auxiliary evidence sampled at their own cadence; cached auxiliary results must not mask a current outage classification. Unsupported router fields remain nullable and generic monitoring must continue without router credentials.

### Physical validation

The v1.3 evidence surface passed the maintainer validation on the ARM64 Raspberry Pi / Debian 13 + FRITZ!Box 5530 / FRITZ!OS 8.20 external-ONT deployment before promotion.

The validation confirmed:

- CI green on the supported Python matrix
- in-place SQLite migration on the existing deployment
- 51/51 Raspberry Pi unit tests
- healthy TCP and IPv6 evidence
- populated live-probe loss/jitter, host link and neighbour evidence
- WANCommon `Ethernet / Up` on the real external-ONT topology
- live WAN activity and `ATA` sync context
- WANFiber optical fields remaining null despite the router advertising the service, because fiber is not the active FRITZ!Box WAN medium
- dashboard, `/wallboard`, ISP report and CSV endpoints working after restart

The detailed validation record lives in [`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md) and [`docs/TESTING.md`](docs/TESTING.md).

## Router adapter boundary

The common adapter contract is documented in [`docs/ROUTER_ADAPTERS.md`](docs/ROUTER_ADAPTERS.md). Vendor-specific access remains outside the generic monitor core and unsupported fields remain nullable.

This boundary is intended to unblock future OpenWrt/MikroTik/UniFi work without copying vendor conditionals into incident classification.

## FRITZ!Box physical WAN diagnostics

The current FRITZ adapter uses:

- `WANCommonInterfaceConfig` as the primary physical-WAN evidence source
- active WAN access type and physical link status
- current WAN activity from the newest documented utilization sample, with Online Monitor downstream/upstream arrays as fallback
- Online Monitor sync group/mode context
- physical-WAN/access-type change events for correlation
- active-fiber optical diagnostics through `X_AVM-DE_WANFiber` only when the WAN access type actually indicates fiber
- no persistence of SFP/GPON serial identifiers

Media-specific services remain secondary/model-dependent when they conflict with WANCommon telemetry. Multicast-rate telemetry is not substituted for ordinary downstream activity.

## Dashboard / wallboard

The normal dashboard exposes the current host and WAN evidence. `/wallboard` provides a dependency-free large-display view intended for TV browsers such as LG webOS.

Automatic TV browser launch at power-on remains device/platform dependent and is not part of the UplinkWitness guarantee. A specific TV model should only be called compatible after it has been physically exercised.

## Next integrations

Candidate enhanced integrations include:

- OpenWrt
- MikroTik RouterOS
- UniFi gateways

A vendor is only listed as supported after a real implementation has been validated against actual hardware or a strong external compatibility report. Planned integrations are not advertised as current support.

Other richer diagnostics considered during v1.3 — resolver-specific multi-DNS checks, traceroute/path snapshots, PMTU diagnostics, UPnP IGD/SNMP adapters and media-specific DSL/mobile telemetry — remain intentionally deferred. They should only become focused work when the evidence value justifies the complexity.

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
