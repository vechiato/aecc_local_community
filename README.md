# AECC Local (Community)

Community Home Assistant integration for AECC energy management devices (inverters, batteries, EV chargers, smart plugs, hot water controllers).

Discovers devices via mDNS/Zeroconf and communicates over a persistent local TCP connection — no cloud required.

## Supported devices

| Device | Sensors | Control |
|--------|---------|---------|
| Inverter / Storage (e.g. AFERIY PS420) | Battery SoC, discharge power, total PV power, AC input power | Operating mode, SOC limits, charge/discharge power |
| System summary | Total PV, battery, grid, backup, and load power | — |
| Smart Plug | Active power | On/Off |
| EV Charger | Connector status and power | On/Off |
| Hot Water Controller | Power, max power, temperature | On/Off |

## Installation via HACS

1. In HACS, go to **Integrations → ⋮ → Custom repositories**
2. Add `https://github.com/vechiato/aecc_local_community` with category **Integration**
3. Install **AECC Local (Community)**
4. Restart Home Assistant
5. Go to **Settings → Devices & Services → Add Integration** and search for **AECC Local**

## Manual installation

Copy `custom_components/aecc_local_community/` into your HA `custom_components/` directory and restart.

## Energy Dashboard

The integration automatically creates energy sensors (kWh) when a device is added — no manual helpers needed. Values persist across HA restarts.

**System-total sensors** (aggregate across all devices, no device prefix):

| Sensor | Measures |
|--------|----------|
| Solar Energy | Cumulative PV production |
| Battery Charge Energy | Cumulative energy into all batteries |
| Battery Discharge Energy | Cumulative energy out of all batteries |

**Per-device sensors** (one set per device, prefixed with the device serial number, e.g. `ABC123 Battery Charge Energy`):

| Sensor | Measures |
|--------|----------|
| `<SN>` Battery Charge Energy | Cumulative energy into this battery |
| `<SN>` Battery Discharge Energy | Cumulative energy out of this battery |

**Configuring the HA Energy Dashboard:**

1. Go to **Settings → Dashboards → Energy**
2. Under **Solar panels**, add **Solar Energy**
3. Under **Battery systems**, add a battery using **Battery Charge Energy** (in) and **Battery Discharge Energy** (out)

For single-device setups the system-total and per-device values will match — use whichever you prefer. For multi-device setups, use the system-total sensors in the Energy Dashboard so all devices are aggregated.

## Known firmware limitations (tested on firmware 3.2)

Several fields in the device API are not reliably populated and always report 0 regardless of actual device state:

| Sensor | API field | Issue | Reliable alternative |
|--------|-----------|-------|----------------------|
| Battery Charging Power | `Storage_list.BatteryChargingPower` | Always 0 even when battery is charging | **Total Charge Power** (`SSumInfoList.TotalChargePower`) |
| Pv Charging Power | `Storage_list.PvChargingPower` | Always 0 even when PV is producing | **Pv Power** (`SSumInfoList.TotalPVPower`) |
| Pv1–Pv4 Power | `Storage_list.Pv1Power`–`Pv4Power` | Per-string breakdown not reported | **Pv Power** for system total |
| Pv String Count | `Storage_list.PvStringCount` | Always 0 | Not available |
| Total Active Power | `SSumInfoList.MeterTotalActivePower` | Always 0; requires an external grid meter | Not available without meter |

As a result of the `BatteryChargingPower` issue, the per-device `<SN> Battery Charge Energy` sensor will always stay at 0 kWh. Use the system-total **Battery Charge Energy** sensor (driven by `TotalChargePower`) for accurate energy tracking.

If you are running a different firmware version and some of these fields work correctly, please [open an issue](https://github.com/vechiato/aecc_local_community/issues).

## Battery control

Inverter/Storage devices expose five control entities in addition to read-only sensors.

### Operating Mode

| Mode | Behaviour |
|------|-----------|
| **Self-Gen / Zero Export** | AI self-consumption — the battery decides when to charge and discharge automatically. This is the safe default to return to after manual control. |
| **Idle** | Battery does nothing — no charging or discharging. |
| **Charge** | Forces the battery to charge at the **Charge Power** slider value. |
| **Discharge** | Forces the battery to discharge at the **Discharge Power** slider value. |

Selecting a mode writes up to 6 control registers atomically. The integration verifies the write was accepted by reading the registers back. On success, all coordinator state variables are updated immediately and pushed to all listening entities — no need to wait for the next poll.

### SOC limits

| Entity | Register | Default | Description |
|--------|----------|---------|-------------|
| **Discharge Limit** | 3023 | 10% | Battery will not discharge below this SoC |
| **Charge Limit** | 3024 | 98% | Battery will not charge above this SoC |

Both sliders write to the device immediately on change. On startup the integration reads the current values from the device, so the sliders always reflect actual device state rather than assumed defaults. If you change a limit while Operating Mode is Charge or Discharge, the active command is re-sent with the new limit at the same power, because the battery applies the limits stored with the running command, not the separate limit registers.

### Power targets

| Entity | Default | Description |
|--------|---------|-------------|
| **Charge Power** | 800 W | Power applied when Operating Mode → Charge |
| **Discharge Power** | 800 W | Power applied when Operating Mode → Discharge |

These sliders are passive — they store the target locally and do not send a command to the device by themselves. The power is applied the next time the mode is set to Charge or Discharge.

> **Note:** 800 W is the observed reliable limit for local TCP control. Higher values may work on some devices but are not guaranteed.

## Configuration options

After adding a device, open **Settings → Devices & Services → AECC Local (Community) → Configure** to adjust:

| Option | Default | Range | Description |
|--------|---------|-------|-------------|
| Poll interval | 10 s | 5–60 s | How often the integration fetches data from the device |

Changes take effect immediately (the integration reloads automatically).

## Diagnostic entities

Each device exposes these diagnostic sensors to help with troubleshooting:

| Sensor | Description |
|--------|-------------|
| Last Successful Update | Timestamp of the most recent successful data fetch |
| Consecutive Poll Failures | Number of failed polls since the last successful response |
| Wi-Fi Signal | Datalogger Wi-Fi strength in dBm, refreshed every 60 seconds. Only created if the device reports it at setup; not all AECC firmware does |

These sensors are hidden by default — enable them under the device's entity list if needed.

## HA diagnostics download

Go to **Settings → Devices & Services → AECC Local (Community) → ⋮ → Download diagnostics** to get a full redacted snapshot including:

- Integration version and device identity (host, IP, and serial number redacted)
- Live coordinator state — commanded mode, SOC limits, failure reason, consecutive failures, Wi-Fi signal
- SOC cleaner state — last accepted values and timestamps
- Partial-frame counters — how many incomplete battery-list polls were held and the last reason (unit count only, no serials)
- Last raw poll response
- Fresh control-register dump (registers 3000–3130 read at download time)
- Last 20 control writes with payloads, attempt counts and per-register verify outcomes

This makes it easy to diagnose silent register drops or mode changes not sticking without needing shell access to the device.

## Reliability

- **Failure tolerance**: the integration holds the last known values for up to 5 consecutive poll failures (or 120 seconds) before marking entities unavailable. Transient network dropouts no longer cause flapping.
- **SOC cleaning**: battery state-of-charge readings are validated against observable physics. Readings of 0% during active charge or discharge cycles, and impossible rate-of-change jumps, are rejected and replaced with the last accepted value.
- **Startup SOC guard**: for the first 60 seconds after startup, a 0% battery reading with nothing earlier to compare against is held back and the sensor shows unknown. Some devices report a false 0% for 15–20 seconds while warming up. A battery that really is empty shows 0% once the window passes.
- **Partial battery-list protection**: if a poll returns an empty battery list or omits a unit it previously reported, the last good data is kept for up to 3 polls. If the change persists, it's accepted as real (unit removed or replaced). A unit that reports without its SoC keeps its last value.
- **Missing units show unavailable**: a battery unit absent from the device's report shows as unavailable instead of dropping to 0. Its entities are kept; delete them manually if the unit was permanently removed.
- **Restart during a reporting gap**: if Home Assistant starts while a unit is temporarily missing, its known sensors are restored from the entity registry and resume when the unit reports again, with no reload needed.
- **Write verification**: every control register write is verified by reading the register back after 0.5 seconds. Mismatches are logged as warnings. All writes are recorded in a rolling audit trail (last 20) visible in the diagnostics download.
- **Write retries**: a write the device doesn't confirm is re-sent up to 2 more times, which covers the device's periodic connection resets. Retries stop early if the device looks unreachable, so a real outage fails fast. Writes run one at a time in the order they were made, so a re-sent write can never overwrite a newer one. If another write is already waiting, the read-back check for the earlier one is skipped, because it would read the newer value.
- **Connection resilience**: after a TCP error the integration waits before reconnecting, starting at 2 seconds and doubling up to 60 seconds during a sustained outage, then back to 2 seconds once the device answers. The old socket is always closed before a new one opens, since some firmware only serves one client at a time. After 3 requests in a row get no reply, the socket is assumed dead and replaced.
- **One request at a time**: polls and control writes share one socket and take turns, so they can't read each other's replies. Each reply is matched to its request by serial number, and a late reply to an earlier request is discarded instead of being taken as the answer to the next one.

## Notes

- Requires the device to be on the same local network
- TCP connection is persistent and shared across all entities for the same device
