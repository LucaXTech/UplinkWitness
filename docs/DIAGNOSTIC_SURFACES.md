# Diagnostic surfaces

UplinkWitness separates diagnostics by evidence source so optional router integrations never weaken the generic Linux core.

## Generic Linux core (no router API required)

Available on ordinary Linux hosts with a working network stack:

- interface carrier where exposed by sysfs
- default route and gateway changes
- gateway reachability when ICMP is supported
- Internet ICMP reachability and latency
- DNS resolution success/latency
- HTTP connectivity success/latency
- externally observed public IPv4 address
- correlated outage timeline and event bundles

Future router-agnostic probes can add host-side evidence such as IPv6 reachability, route changes, resolver-specific DNS checks, jitter/loss windows, path-MTU checks and optional traceroute snapshots without requiring vendor APIs.

## Generic router integration candidates

UPnP Internet Gateway Device (IGD) is the most realistic vendor-neutral router adapter when enabled by the router. Standard services can expose connection status, connection uptime, external IP and some WAN/link counters. Support is optional and inconsistent across products, so UplinkWitness should treat it as an optional adapter rather than part of the generic baseline.

SNMP can provide richer router telemetry on devices that expose it, but consumer routers often disable or omit SNMP. It should likewise be implemented as an optional adapter.

## FRITZ!Box enhanced diagnostics

TR-064 already provides model/firmware, device uptime, WAN/session status, WAN uptime, external WAN address, PPPoE context and device logs.

Additional evidence being evaluated/implemented:

- CPU temperature through the experimental FRITZ HTTP `query.lua` surface used by `fritzconnection`
- WAN physical-link status, access type, negotiated/max rates and utilization via `WANCommonInterfaceConfig`
- traffic counters / current transmission rate
- fiber optical diagnostics on supported FRITZ!Box Fiber devices via `X_AVM-DE_WANFiber`
  - receive optical level and alarm thresholds
  - transmit optical level and alarm thresholds
  - fiber mode
  - packet error counters
  - connection rates
  - resync counter / minutes in showtime

Router-only telemetry must remain nullable and best-effort. A missing or unsupported service must never break generic monitoring or outage detection.
