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

Selecting a mode writes up to 6 control registers atomically. The integration verifies the write was accepted by reading the registers back.

### SOC limits

| Entity | Register | Default | Description |
|--------|----------|---------|-------------|
| **Discharge Limit** | 3023 | 10% | Battery will not discharge below this SoC |
| **Charge Limit** | 3024 | 98% | Battery will not charge above this SoC |

Both sliders write to the device immediately on change. On startup the integration reads the current values from the device, so the sliders always reflect actual device state rather than assumed defaults.

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

Each device exposes two diagnostic sensors to help with troubleshooting:

| Sensor | Description |
|--------|-------------|
| Last Successful Update | Timestamp of the most recent successful data fetch |
| Consecutive Poll Failures | Number of failed polls since the last successful response |

These sensors are hidden by default — enable them under the device's entity list if needed.

## HA diagnostics download

The integration supports the standard Home Assistant diagnostics download. Go to **Settings → Devices & Services → AECC Local (Community) → ⋮ → Download diagnostics** to get a redacted snapshot of the integration state (host, IP, and serial number are omitted).

## Reliability

- **Failure tolerance**: the integration holds the last known values for up to 5 consecutive poll failures (or 120 seconds) before marking entities unavailable. Transient network dropouts no longer cause flapping.
- **SOC cleaning**: battery state-of-charge readings are validated against observable physics. Readings of 0% during active charge or discharge cycles, and impossible rate-of-change jumps, are rejected and replaced with the last accepted value.

## Notes

- Requires the device to be on the same local network
- TCP connection is persistent and shared across all entities for the same device
