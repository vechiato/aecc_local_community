# AECC Local (Community)

Community Home Assistant integration for AECC energy management devices (inverters, batteries, EV chargers, smart plugs, hot water controllers).

Discovers devices via mDNS/Zeroconf and communicates over a persistent local TCP connection — no cloud required.

## Supported devices

| Device | Data |
|--------|------|
| Inverter / Storage (e.g. AFERIY PS420) | Battery SoC, discharge power, total PV power, AC input power |
| System summary | Total PV, battery, grid, backup, and load power |
| Smart Plug | Active power |
| EV Charger | Connector status and power |
| Hot Water Controller | Power, max power, temperature |

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

## Notes

- Requires the device to be on the same local network
- TCP connection is persistent and shared across all entities for the same device
- Polling interval: 10 seconds
