# UplinkWitness TV for LG webOS

This directory contains the installable launcher shell for the UplinkWitness TV client.

Primary physical target for the first validation is the LG OLED55E8PLA / webOS TV 4.x generation. The package deliberately uses a small ES5-compatible launcher and opens the TV interface served by the UplinkWitness host at `/wallboard?webos=1`.

## Why a hosted UI

The TV package provides the LG launcher integration, icon, persistent server address and fullscreen app container. The actual dashboard is served by the Raspberry Pi / Linux host.

This keeps monitoring and presentation in one UplinkWitness version, avoids duplicating the diagnostic engine on the television, avoids cross-origin API plumbing, and allows dashboard improvements to arrive with normal UplinkWitness updates without reinstalling the IPK.

The universal `/wallboard` browser fallback remains available even when the LG package is not installed.

## Requirements

On the TV:

- LG Developer Mode app installed from the LG Content Store
- Developer Mode enabled
- TV and development computer on the same LAN

On the development computer:

- Node.js + npm
- current LG webOS CLI (`@webos-tools/cli`)

Install the CLI:

    npm install -g @webos-tools/cli
    ares -V

## Package

From the UplinkWitness repository root:

    ares-package ./clients/webos

The expected package name begins with:

    com.lucaxtech.app.uplinkwitness_0.1.0_

CI also packages the client and publishes an `uplinkwitness-tv-ipk` workflow artifact so the exact tested IPK can be installed without rebuilding it locally.

## Register the TV

In the Developer Mode app on the TV, enable Developer Mode and Key Server. Note the TV LAN IP and the six-character passphrase shown by the app.

Then on the development computer:

    ares-setup-device --add livingroom-tv -i "host=TV_IP" -i "port=9922" -i "username=prisoner"
    ares-novacom --device livingroom-tv --getkey

Enter the passphrase shown on the TV when requested.

Check connectivity:

    ares-setup-device --list

## Install and launch

Replace the package filename with the one produced by `ares-package` or downloaded from CI:

    ares-install --device livingroom-tv ./com.lucaxtech.app.uplinkwitness_0.1.0_all.ipk
    ares-launch --device livingroom-tv com.lucaxtech.app.uplinkwitness

The first launch asks for the UplinkWitness server URL. Enter the address shown by `install.sh` on the monitored host, for example:

    http://your-host.local:8080

If mDNS is not resolved by the TV, use the host LAN address instead:

    http://192.168.x.x:8080

The launcher intentionally does not ship with an installation-specific hostname prefilled. The server address is stored locally by the TV app after a successful configuration and survives normal app restarts.

A small **Server settings** button remains available in the launcher shell for the Magic Remote pointer. The Yellow key is also accepted as a shortcut when the launcher shell itself has keyboard focus; it is not relied on as the only recovery path.

## TV controls

Inside the UplinkWitness TV interface:

- Left / Right: switch Overview, Network, Router, Incidents
- Magic Remote pointer: tabs remain clickable
- Back while inside a secondary section: return to Overview
- Magic Remote `Server settings`: reopen the saved-host configuration

## Compatibility rules

The TV UI intentionally avoids:

- CSS Grid
- JavaScript modules
- arrow functions / modern-only syntax
- external JavaScript or CDN dependencies
- direct monitoring logic on the TV

The graphics target is 1920x1080.

## Developer Mode renewal

LG Developer Mode sessions expire unless they are extended. UplinkWitness deliberately does **not** automate renewal by launching `com.palmdts.devmode`, because that can bring the Developer Mode app to the foreground and interrupt whatever is being watched on the TV.

Instead, the renewal helper stores the Developer Mode session token locally on the Raspberry Pi / Linux host and uses LG's Developer Mode service directly. Scheduled checks therefore do not launch an application on the TV, do not change the active HDMI input or app, and do not wake the TV.

The installer needs the TV once to read the current session token over the already configured `ares-novacom` connection:

    ./clients/webos/install-renewal-timer.sh livingroom-tv

The token is stored at:

    ~/.config/uplinkwitness/webos-devmode-token

with mode `0600`. The helper then checks `CheckDevModeSession.dev` once a week and calls `ResetDevModeSession.dev` only when fewer than 14 days remain. A normal session near 1000 hours therefore does not get reset every week.

The systemd timer runs on Sunday around 04:00 with a randomized delay and is persistent. There is no `OnBootSec` action that launches anything on the TV. If a scheduled check was missed while the Linux host was off, systemd may run the server-side check after the host returns, but that check talks only to LG's service.

Useful checks:

    systemctl list-timers uplinkwitness-webos-renew.timer
    sudo systemctl start uplinkwitness-webos-renew.service
    journalctl -u uplinkwitness-webos-renew.service

A healthy manual run with plenty of time remaining should log something similar to:

    Developer Mode remaining: 999:57:56
    Renewal not required.

The session token is not printed by the installer or renewal helper. If Developer Mode is disabled/re-enabled, the token changes, or the session expires, rerun the installer while the TV is available so the token can be captured again.
