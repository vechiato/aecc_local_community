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

## Notes

- Requires the device to be on the same local network
- TCP connection is persistent and shared across all entities for the same device
- Polling interval: 10 seconds
