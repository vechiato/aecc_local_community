# AECC Local (Community)

Community Home Assistant integration for AECC energy management devices (inverters, batteries, EV chargers, smart plugs, hot water controllers).

Discovers devices via mDNS/Zeroconf and communicates over a persistent local TCP connection — no cloud required.

## Supported devices

| Device | Data |
|--------|------|
| Inverter / Storage (e.g. AFERIY PS420) | Battery SoC, charge/discharge power, PV power per string, AC input power |
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

The integration automatically creates three energy sensors (kWh) when a device is added — no manual helpers needed:

| Sensor | Measures |
|--------|----------|
| Solar Energy | Cumulative PV production |
| Battery Charge Energy | Cumulative energy into the battery |
| Battery Discharge Energy | Cumulative energy out of the battery |

To configure the HA Energy Dashboard:

1. Go to **Settings → Dashboards → Energy**
2. Under **Solar panels**, add the **Solar Energy** sensor
3. Under **Battery systems**, add a battery using **Battery Charge Energy** (energy going in) and **Battery Discharge Energy** (energy going out)

> Energy values persist across HA restarts.

## Notes

- Requires the device to be on the same local network
- TCP connection is persistent and shared across all entities for the same device
- Polling interval: 10 seconds
