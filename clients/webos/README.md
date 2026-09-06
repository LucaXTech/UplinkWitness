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

Automated session renewal from the Raspberry Pi is intentionally a separate deployment task. First validate that the 0.1.0 app packages, installs, launches and survives a normal restart on the physical OLED55E8PLA.
