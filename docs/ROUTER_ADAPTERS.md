# Router adapter contract

UplinkWitness keeps vendor-specific router access behind a deliberately small adapter boundary so the generic Linux monitor remains useful without router credentials or vendor APIs.

## Contract

A router adapter implements one operation:

```python
snapshot() -> tuple[dict, Optional[str]]
```

The first return value is a dictionary of nullable telemetry. The second value is optional vendor log/context that may be attached to an incident bundle.

The generic core must tolerate:

- no adapter at all
- an unsupported telemetry field
- a partial snapshot
- a temporary adapter failure
- a router exposing a service that is not active for the current WAN medium

Unsupported or unavailable evidence is represented as `None`; it must not be fabricated from another source.

## Common telemetry surface

Current fields consumed by the core include:

- router model / firmware
- router uptime
- WAN connection state and session uptime
- router-reported WAN IP
- WAN transport and last connection error
- optional provider/session context such as PPPoE access concentrator
- optional router health evidence such as CPU temperature
- physical-WAN access type and link status
- current/recent WAN activity evidence
- WAN sync group/mode
- media-specific evidence such as active-fiber optical levels and counters

The core remains responsible for generic Linux/link/gateway/Internet probes, event classification, SQLite persistence and incident correlation.

## Evidence rules

Router telemetry is evidence, not permission to over-classify incidents.

- A single vendor metric must not become a root-cause claim by itself.
- Service presence is capability evidence, not proof that the service represents the active WAN medium.
- Physical-WAN data from a general WAN service should be preferred over a media-specific service when the platform exposes contradictory values.
- Missing adapter data must degrade to nulls without disabling generic monitoring.
- Values with privacy or identification risk should not be persisted unless they are necessary for diagnosis.

## FRITZ!Box implementation

`FritzAdapter` uses local TR-064 through `fritzconnection`.

For v1.3 development it uses `WANCommonInterfaceConfig` as the primary source for physical access type/status and Online Monitor activity. Official FRITZ! documentation defines the relevant utilization series as bytes per second.

`X_AVM-DE_WANFiber` is queried only when the active WAN access type indicates fiber. Optical levels are converted from dBm/1000 to dBm. SFP serial numbers, GPON serial numbers and similar hardware identifiers are intentionally not stored.

CPU temperature remains best-effort. A failed temperature poll returns null rather than indefinitely re-emitting a stale cached value.

## Adding another adapter

A future adapter should:

1. implement the same `snapshot()` contract;
2. map only well-understood fields into the common telemetry names;
3. keep unsupported fields nullable;
4. avoid vendor conditionals in `monitor.py` beyond adapter selection;
5. add tests for success, partial telemetry and temporary failure;
6. document authentication and least-privilege requirements;
7. be validated against real hardware or a strong external compatibility report before being advertised as supported.

OpenWrt, MikroTik and UniFi remain candidates, not current supported adapters.
