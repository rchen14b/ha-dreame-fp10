# Dreame FP10 Air Purifier Integration for Home Assistant

Custom Home Assistant integration for the **Dreame FP10 Air Purifier** (model `dreame.airp.u2513`, the self-cleaning roller pet purifier), using the Dreame Cloud API — the same API the Dreamehome app uses.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![HACS](https://img.shields.io/badge/HACS-custom-orange.svg)
![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.6%2B-brightgreen.svg)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-support-yellow?style=flat&logo=buy-me-a-coffee)](https://buymeacoffee.com/rchen14b)

## Features

### Fan Entity
- **Power on/off** — "Off" uses Sleep mode at minimum speed to keep the device cloud-connected (Dreame purifiers cannot be woken remotely from true standby)
- **Preset modes** — Smart, Sleep, Customize, Pet
- **Fan speed** — 5 speed levels (shown as 20/40/60/80/100% in HA)
- Setting fan speed automatically switches to Customize mode

### Sensors
- **PM2.5** — real-time particulate matter (µg/m³)
- **Air Quality Level** — numeric air quality index from the device
- **HEPA Filter Life / Days Left / Hours Used**
- **Filter 2 / Filter 3 Life** — the FP10's additional filter components (roller/pre-filter/carbon — exact identity TBD)
- **Device Location**

### Controls
- **Switches** — Child Lock, Voice Interaction, Keypress Tone
- **Selects** — Light Control (Off/Blue/Orange/Green), Voice Interaction Volume
- **Number** — Off Timer (0–12 hours)
- **Button** — HEPA Filter Reset

## Installation

### Via HACS (Recommended)

1. In Home Assistant: **HACS → Integrations**
2. Click **⋮** (top right) → **Custom repositories**
3. Paste URL: `https://github.com/rchen14b/ha-dreame-fp10`
4. Category: **Integration** → **Add**
5. Search **"Dreame FP10"** → **Download** → restart HA
6. **Settings → Devices & Services → + Add Integration** → search "Dreame FP10" → enter your Dreamehome app credentials

### Manual Installation

1. Download or clone this repo
2. Copy `custom_components/dreame_fp10/` into your HA `config/custom_components/` directory
3. Restart Home Assistant
4. **Settings → Devices & Services → + Add Integration** → search "Dreame FP10"

## Setup

- Use your **Dreamehome app** credentials (email + password)
- Select your server region (US, EU, CN, SG, KR)
- The integration automatically discovers all Dreame air purifiers on your account
- Multiple purifiers are supported — each appears as a separate device in HA

## Important Notes

### Power Behavior
Dreame purifiers enter a deep standby when powered off that disconnects them from the cloud entirely. **Neither the Dreamehome app nor this integration can wake the device remotely.** To keep it controllable:

- **"Turn off" in HA** switches to Sleep mode at the lowest fan speed (near silent, minimal power draw)
- **"Turn on" in HA** switches back to AI Purify mode
- **Avoid using the physical power button to turn it off** if you want remote control to keep working

### Cloud Polling
This integration communicates via the Dreame Cloud API (same as the Dreamehome app). It polls for state updates every 30 seconds. Commands are sent through the cloud — there is no local API available for this device.

## Property Map

Mapped by live read-only probes of a real FP10 (`dreame.airp.u2513`, firmware 2062), July 2026.

| siid | piid | Property | Values | Status |
|------|------|----------|--------|--------|
| 1 | 4 | Firmware Revision | string, e.g. "2062" | live-read |
| 1 | 5 | Serial Number | string | live-read |
| 2 | 1 | Power | 1=on, 2=standby | live-read |
| 2 | 3 | Mode | 0=Smart, 2=Sleep, 3=Customize, 4=Pet | 0 and 2 observed live; 3 and 4 unconfirmed |
| 2 | 4 | Fan Speed | 1–5 (device may support 1–10) | read 1; max unconfirmed |
| 2 | 6 | Light Control | enum unknown | read 0 while the light was orange — mapping unconfirmed |
| 2 | 7 | Keypress Tone | 0/1 | read 0; unconfirmed |
| 3 | 11 | Air Quality Level | numeric index | plausible — read 0 with clean air |
| 3 | 12 | PM2.5 | µg/m³ | **confirmed** — tracked the app across reads (8 → 10) |
| 3 | 13 | PM2.5 display string | e.g. "PM2.5-10" | live-read, not polled |
| 4 | 1 | Filter Life | 0–100% | live-read (98) |
| 4 | 2 | Filter Days Left | days | live-read (709 ≈ 2-year filter) |
| 4 | 3 | Filter Hours Used | hours | live-read |
| 4 | 5 | Filter 2 Life | 0–100% | live-read (99) — which component (roller/pre-filter/carbon) TBD |
| 4 | 6 | Filter 3 Life | 0–100% | live-read (89) — which component TBD |
| 6 | 1 | Timezone | string | live-read, not polled |
| 6 | 2 | App schedules | encoded string | live-read, not polled |
| 6 | 3 | Device Location | string | live-read |
| 6 | 5 | Child Lock | type unknown | read `""` — semantics unconfirmed |
| 6 | 6 | Voice Volume | 80/90/100 | live-read (80) |
| 6 | 7 | Voice Interaction | 0/1 | read 0; unconfirmed |
| 6 | 8 | Off Timer | hours | read 0 |

Not found on the FP10: temperature, humidity, and TVOC readings (the marketing-spec sensors) — nothing plausible responded anywhere in siid 1–12 / piid 1–20. They may only be pushed over Dreame's separate MQTT channel.

**Probe caveat:** the cloud returns value `0` (success code) for many properties that don't exist — siids 8–12 read `0` for every piid. A `0` in probe output does not prove a property is real; only non-trivial values and app cross-checks do.

**Key protocol note:** power control requires a toggle action (`siid=2, aiid=3`) — direct property writes to `siid=2, piid=1` time out. Everything else uses normal `set_properties`.

### Verifying the map on your FP10

The map was produced by sweeping siid 1–12 / piid 1–20 with read-only `get_properties` calls against the Dreame Cloud API (`POST /dreame-iot-com-{shard}/device/sendCommand` with `{"method": "get_properties", "params": [{"did": ..., "siid": s, "piid": p}]}`) and cross-checking values against the Dreamehome app. If your FP10 behaves differently — or you identify the self-cleaning roller / dust collection properties — please [open an issue](https://github.com/rchen14b/ha-dreame-fp10/issues) so the integration can be updated for everyone.

## Troubleshooting

- **Connection timeouts / `TLS handshake timed out`?** The Dreame API runs on non-standard port **13267**, and the path to the US endpoint (`us.iot.dreame.tech`, Alibaba Cloud) is known to suffer transient packet loss that can push TLS handshakes past 10 seconds. Both the integration and the probe script use generous timeouts and retry transport failures automatically — but if it persists: retry in a minute, check that your firewall/ISP isn't blocking outbound port 13267, or try from another network (e.g. phone hotspot) to compare.
- **Login fails?** Verify your credentials work in the Dreamehome app. The integration uses the same login. Note: the server requires the `Dreame-Rlc` header on all regions (already handled here; older Dreame integrations only sent it for CN and got "invalid credentials" elsewhere).
- **Device unavailable?** Make sure the purifier is powered on (not in deep standby). Check that it shows online in the Dreamehome app.
- **Commands not working?** Check HA logs under Developer Tools → Logs, search for `dreame_fp10`. Your FP10 may use different property ids than the mapped ones — see the [Property Map](#property-map) notes and open an issue.
- **State not updating?** The integration polls every 30 seconds. Cloud state can sometimes lag behind physical changes.

## Credits

- Cloud API groundwork by [@CodyJon](https://github.com/CodyJon/dreame-ap10-integration) — see LICENSE.

## Updating

Releases are published as GitHub releases with semver tags. When installed through HACS, new releases appear automatically in Home Assistant under **Settings → Updates** — click **Update**, then restart HA.

## Contributing

Issues, feature requests, and PRs welcome — especially property-map observations from real FP10 units.

## License

MIT License
