# Linux validation checklist

Use this checklist before claiming a Linux distribution or device class as tested with UplinkWitness.

## Fresh install

- Start from a clean Linux installation.
- Connect the test machine by Ethernet when possible.
- Run `./install.sh` as a normal user.
- Verify both systemd services start and remain active.

```bash
systemctl status linewatch
systemctl status linewatch-dashboard
journalctl -u linewatch -n 100 --no-pager
```

The `linewatch` service names are intentionally retained as stable runtime identifiers during the UplinkWitness rename.

## Generic mode

Configure `LINEWATCH_ROUTER_MODE=generic` and verify:

- default IPv4 gateway is detected
- active network interface is detected
- interface speed/duplex appear when Linux sysfs exposes them
- gateway neighbour/ARP state is best-effort and nullable
- dashboard loads on port 8080
- Internet latency samples appear when ICMP is available
- the independent TCP-connect probe appears
- DNS and HTTP checks are healthy
- public IP is populated
- IPv6 is probed only when an IPv6 default route exists
- ICMP loss and jitter evidence are calculated from the observed sample window
- FRITZ-specific fields are not presented as available

## Gateway ICMP behavior

If the gateway answers ping, verify UplinkWitness logs that gateway ICMP is supported.

If the gateway does not answer ping while Internet access works, verify automatic mode disables gateway-based outage classification instead of reporting a false outage. A healthy TCP/DNS/HTTP path must also prevent a failed gateway ping from being treated as a complete Internet outage.

## Route and host-link evidence

Where practical, verify:

- a real default-route/interface change creates `DEFAULT_ROUTE_CHANGED`
- a negotiated host-link speed/duplex change creates `HOST_LINK_PROPERTIES_CHANGED` only when both old and new values are known
- temporary absence of sysfs speed/duplex while a link is down does not invent a link-property event

These are evidence events, not outage classifications by themselves.

## Controlled network faults

Where safe and practical, test one fault at a time and restore connectivity after each test:

- disconnect the Ethernet cable briefly -> `NETWORK_LINK_DOWN`
- disable upstream Internet while keeping the LAN/router available -> `INTERNET_UNREACHABLE`
- configure or simulate a DNS failure -> `DNS_FAILURE`
- block the configured HTTP connectivity endpoint -> `HTTP_CONNECTIVITY_FAILURE`

Confirm each event opens and closes with a sensible duration and appears in the dashboard/export.

For an incident that changes character while it is still open, confirm the existing event is escalated to the strongest observed classification rather than creating duplicate downtime rows.

## FRITZ!Box enhanced mode

On a compatible FRITZ!Box, configure TR-064 credentials and verify:

- router model and FRITZ!OS appear
- router uptime and WAN uptime are populated
- WAN status is available
- generic Internet probes continue to work when TR-064 temporarily fails
- router-reported WAN IP and the external public-IP probe are tracked as separate sources
- a telemetry-source disappearance/reappearance does not create a false `WAN_IP_CHANGED` event
- CPU temperature is shown only when the router/firmware exposes a valid reading
- a failed temperature poll becomes nullable instead of silently persisting an old value indefinitely
- the 24 h temperature panel/history remains absent or nullable when temperature telemetry is unsupported

### Physical WAN / Online Monitor

If `WANCommonInterfaceConfig` is exposed, verify:

- WAN access type is nullable but meaningful when returned
- physical link status is nullable but meaningful when returned
- activity values are treated as bytes/s, matching the FRITZ! TR-064 specification
- sync group/mode are best-effort diagnostics
- `WANCommonInterfaceConfig` is the primary physical-WAN evidence source
- media-specific services such as `WANEthernetLinkConfig` are not treated as authoritative when they contradict WANCommon telemetry

A real change in physical-link status may create `WAN_PHYSICAL_LINK_CHANGED`; an access-type change may create `WAN_ACCESS_TYPE_CHANGED`. Neither event is a standalone root-cause claim.

### Fiber telemetry

`X_AVM-DE_WANFiber` must be queried for optical diagnostics only when the active WAN access type actually indicates fiber. Merely advertising the service is not enough.

When active fiber telemetry is available, verify RX/TX optical levels and alarm thresholds are converted from dBm/1000 to dBm, and resync/error counters remain nullable. Do not persist SFP or GPON serial numbers.

On an external-ONT/Ethernet deployment, all fiber optical fields should remain null even if the router advertises the WANFiber service.

When a real reboot is observed, verify the router-uptime reset is detected and correlated with the outage containing the estimated router boot time. Do not deliberately reboot production networking equipment just to complete this checklist unless disruption is acceptable.

Temperature, traffic activity and optical levels are supporting evidence only. A single metric must not be reported as the cause of a reboot or outage.

## TV wallboard

Open `/wallboard` from a desktop/mobile browser and, where available, the browser built into a TV such as LG webOS. Verify:

- the page loads without external JavaScript dependencies
- status, WAN, physical-WAN, uptime, temperature and availability cards update automatically
- the 24 h latency graph updates
- the layout remains readable at TV distance and degrades to a two-column/mobile layout on narrow screens

Automatic browser launch at TV power-on is device/webOS dependent and is not a UplinkWitness guarantee.

## Persistence and migration

Reboot the Linux host and verify the monitor/dashboard return automatically and the previous SQLite history is preserved.

When upgrading an older database, verify all new v1.3 diagnostic columns are added as nullable fields in place and existing samples/events remain readable.

## Report compatibility

Export both CSV and ISP text reports. Check that generic mode does not invent FRITZ-specific telemetry and enhanced mode includes physical-WAN/fiber evidence only when actually available.

When opening a compatibility issue, include distribution/version, architecture, network interface type, router model, UplinkWitness commit/version, and which checklist sections passed.
