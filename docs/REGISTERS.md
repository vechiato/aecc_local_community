<!--
Reference copy of docs/REGISTERS.md from makstech/esphome-aecc
(https://github.com/makstech/esphome-aecc, commit 5436c19, 2026-09-26),
licensed GPL-3.0. Copied unmodified apart from this note and these changes:
- 0xFE08 relabelled as AC charge power and 0xFE1F (PV power) added, following
  makstech/esphome-aecc commit 3556259; that repo's own REGISTERS.md still
  says "losses".
- Notes on 3021 and 3039 in "Not on Modbus", from StekkerDeal/aecc-battery-local
  issue #36 and StekkerDeal/aecc-battery-homey docs/protocol.md. Reported on
  other AECC-platform brands, not yet confirmed on an AFERIY PS240/PS420.

These are the inverter's own Modbus register addresses (0xFExx, 0xAxxx),
read over the RS485 link by that ESPHome component. This integration talks
to the datalogger over TCP, which uses different register numbers
(3000-3030, see custom_components/aecc_local_community/const.py). Use the
vendor names here to identify a setting, not the addresses.
-->

# Register map

Everything the component knows about, so you can reach a setting it does not model.

**Key** is what you write under `aecc:` to get a control, with `_number`, `_switch` or
`_select` after it. **Vendor name** is the identifier the vendor's own app uses, typos
included. **`scale:`** is the literal value to type when reaching the register by address
instead; a key already carries its own.

Verified on a Humsienk `HSBPSS2K5W7K68WHEU`. Other units on this platform run the same
firmware, but enum values and defaults differ between builds, so read a value back before
trusting it.

## Reaching a register the component does not model

Read one:

```yaml
sensor:
  - platform: aecc
    registers:
      - name: Parallel mode
        address: 0xA02C
        interval: 60s
```

Read and write one:

```yaml
aecc:
  registers:
    - name: Parallel mode
      address: 0xA02C
      max_value: 7
```

Or write once, without an entity, with the `aecc.write_register` action.

`scale` multiplies the register in both places, so a register holding tenths of a volt
wants `scale: 0.1`. A bare `aecc: registers:` entry defaults to `0`–`65535` at scale 1, so
set `max_value` to something the register actually accepts.

## Live telemetry

Read-only, and each has a `sensor:` key.

| Meaning | Key | Address | Notes |
|---|---|---|---|
| State of charge | `soc` | `0xFE06` | % |
| Battery power | `battery_power` | `0xFE07` | signed; positive discharging |
| AC charge power | `ac_charge_power` | `0xFE08` | W; drawn from AC to charge, including AC-coupled PV; 0 while discharging |
| Grid power at the inverter's own port | `grid_power` | `0xFE0A` | signed; positive exporting |
| Backup (EPS) load | `backup_load` | `0xFE10` | W |
| PV power | `pv_power` | `0xFE1F` | signed; AC-coupled PV port, negative producing |
| Active power setpoint | `setpoint` | `0xFE16` | signed; positive discharging |

## Battery

| Meaning | Key | Address | Vendor name | `scale:` |
|---|---|---|---|---|
| [Battery type](#battery-type) | `battery_type` | `0xA08C` | `batType` | `1` |
| Constant voltage | `cv_voltage` | `0xA08D` | `cvVolt` | `0.1` |
| Float voltage | `float_voltage` | `0xA08E` | `floatVolt` | `0.1` |
| Constant voltage charging time, minutes | `cv_charge_time` | `0xA090` | `cvChgTimeSet` | `1` |
| Return-to-CV voltage | `cv_return_voltage` | `0xA091` | `cvChgBackVolt` | `0.1` |
| Battery → mains switchover voltage | `battery_to_mains_voltage` | `0xA092` | `inv2LineVolt` | `0.1` |
| Mains → battery switchover voltage | `mains_to_battery_voltage` | `0xA093` | `lineBack2InvVolt` | `0.1` |
| Undervoltage alarm | `undervoltage_alarm` | `0xA094` | `battLowVolt` | `0.1` |
| Low-voltage shutdown | `low_voltage_shutdown` | `0xA095` | `battDelayOffVolt` | `0.1` |
| End-of-discharge voltage | `eod_voltage` | `0xA096` | `battEodVolt` | `0.1` |
| Voltage shutdown delay, seconds | `shutdown_delay` | `0xA097` | `battDelayOffTime` | `1` |
| End-of-discharge clear voltage | `eod_clear_voltage` | `0xA098` | `battEodBackVolt` | `0.1` |
| RS485 BMS link, off drops it | `bms_function` | `0xA099` | `bmsSet` | `1` |
| [BMS protocol](#bms-protocol) | `bms_protocol` | `0xA09A` | `bmsProtocal` | `1` |
| Battery activation | `battery_activation` | `0xA03E` | `battActiveSet` | `1` |
| Independent pack enable | `independent_pack` | `0xA0AF` | `battPackNotUnion` | `1` |

## Charging

| Meaning | Key | Address | Vendor name | `scale:` |
|---|---|---|---|---|
| [Charge priority](#charge-priority) | `charge_priority` | `0xA02E` | `chgPriority` | `1` |
| Max charge current, stand-alone | `max_charge_current` | `0xA02F` | `maxChgCurrSet` | `0.1` |
| Max charge current from PV | `pv_max_charge_current` | `0xA030` | `chgCurrByPvSet` | `0.1` |
| Max charge current from mains — unconfirmed, see below | `mains_max_charge_current` | `0xA031` | `chgCurrByLineSet` | `0.1` |
| Saturation current | `saturation_current` | `0xA035` | `chgFullCurrSet` | `0.1` |

## State of charge limits

| Meaning | Key | Address | Vendor name | `scale:` |
|---|---|---|---|---|
| Low alarm, % | `soc_low_alarm` | `0xA09B` | — | `1` |
| Shutdown point, % | `soc_shutdown` | `0xA09C` | — | `1` |
| Full judgement, % | `soc_full` | `0xA09D` | — | `1` |
| Inverter → mains, % | `soc_inverter_to_mains` | `0xA09E` | — | `1` |
| Mains → inverter, % | `soc_mains_to_inverter` | `0xA09F` | — | `1` |

## Grid and output

| Meaning | Key | Address | Vendor name | `scale:` |
|---|---|---|---|---|
| Device on/off — switches the inverter off | `device_power` | `0x9C40` | `onOffCtrl` | `1` |
| [Inverter operating mode](#inverter-operating-mode) | `inverter_mode` | `0xA028` | `outPriority` | `1` |
| Output voltage | `output_voltage` | `0xA029` | `outVoltSet` | `0.1` |
| Output frequency | `output_frequency` | `0xA02A` | `outFreqSet` | `0.01` |
| [Utility range](#utility-range) | `utility_range` | `0xA02B` | `lineRangeSet` | `1` |
| [Parallel mode](#parallel-mode) | `parallel_mode` | `0xA02C` | `paraModeSet` | `1` |
| Energy saving mode | `eco_mode` | `0xA02D` | `ecoEn` | `1` |
| Buzzer mute | `buzzer_mute` | `0xA033` | `muteEn` | `1` |
| [Energy internet setting](#on-grid-mode) | `on_grid_mode` | `0xA034` | `onGirdSet` | `1` |
| Neutral–earth bond — probably not, see below | — | `0xA036` | `nG_FuncEn` | `1` |
| Grid-tie power cap, W — see below | `grid_export_limit` | `0xA03F` | `onGridActivePowerSet` | `1` |
| Grid-tie power cap, second copy, W | — | `0x9ACE` | — | `1` |
| Mixing priority | `mixing_priority` | `0xA041` | `hybirdPriorityEn` | `1` |
| [Grid standard](#grid-standard) | `grid_standard` | `0xA043` | `gridStandardSet` | `1` |
| Take the grid reading from the EMS host | `external_ct_host` | `0xA047` | `extCtGetHostEn` | `1` |
| Anti-islanding — off stops it disconnecting from a dead grid | `anti_islanding` | `0xA069` | `islandEn` | `1` |
| Grid code trip thresholds, apart from the registers above | — | `0xA04D`–`0xA0F9` | — | `0.1` V, `0.01` Hz |

## Enum values

Values are the index into the vendor app's own list, in the order the app displays them,
confirmed against the app's own code.

Where the whole list is known the component exposes a `_select` with real labels. Where it
is not, there is no key at all: an index with no meaning attached is a worse control than
none, so reaching those takes an explicit `registers:` entry.

### Utility range

`0xA02B` `lineRangeSet` — the AC input acceptance window, narrowest first.

| | |
|---|---|
| `0` | UPS mode |
| `1` | APL mode |
| `2` | GEN mode |

### On-grid mode

`0xA034` `onGirdSet` — "PV to grid" means anti-backflow is *off*; `3` is the hook for
feeding a grid reading from your own meter rather than the bundled CT.

| | |
|---|---|
| `0` | PV to load |
| `1` | PV to grid |
| `2` | Prevention of power flow into the grid (external CT sensor) |
| `3` | Power flow prevention (external smart device) |

### Parallel mode

`0xA02C` `paraModeSet` — `3` and `5`–`7` build a three-phase bank from three units; `4` is
split-phase.

| | |
|---|---|
| `0` | Stand-alone |
| `1` | Parallel operation |
| `2` | Split phase reference phase |
| `3` | Split phase with 120° difference from reference phase |
| `4` | Phase with 180° difference between split phase and reference phase |
| `5`–`7` | First, second, third phase of three phases |

### Battery type

`0xA08C` `batType` — the pack chemistry and cell count.

| | |
|---|---|
| `0` | Custom Type |
| `1` | SLD-Sealed Lead Acid |
| `2` | FLD-Flooded Lead Acid |
| `3` | GEL-Gel Lead Acid |
| `4`–`6` | LiFePO4 14S, 15S, 16S |
| `7`–`9` | LiFePO4 7S, 8S, 9S |
| `10`–`13` | Ternary Lithium 7S, 8S, 13S, 14S |

### BMS protocol

`0xA09A` `bmsProtocal` — which BMS the pack speaks. This unit ships on `1`.

| | |
|---|---|
| `0`–`4` | Voltronic, Pylon, Aoguan, Oulite, Gotion |
| `5`–`9` | Sunwoda, CF, Dyuness, Pace, BST |
| `10`–`13` | Foxess, AEC, Pylon-V3.5, MeZic-V3.5 |
| `14`–`17` | Tentek, Rvtran, YUZE, EVT |

### Charge priority

`0xA02E` `chgPriority` — where the charge current comes from.

| | |
|---|---|
| `0` | Photovoltaic priority (OSO) |
| `1` | Utility Priority (OUO) |
| `2` | Mixed mode (SNU) |
| `3` | PV only (NUC) |

### Inverter operating mode

`0xA028` `outPriority` — which source serves the load first.

| | |
|---|---|
| `0` | Photovoltaic priority (PV) |
| `1` | Utility power priority (GID) |
| `2` | PV Battery Priority (BAT) |
| `3` | Hybrid Priority (HBD) |

### Grid standard

`0xA043` `gridStandardSet` — picks one of the firmware's built-in profiles, and a profile
is nothing but a set of trip thresholds. Those thresholds live at `0xA04D`–`0xA0F9` and
are individually readable and writable, so where your grid operator requires particular
voltage or frequency limits, set them directly rather than trusting a profile to match.

| | |
|---|---|
| `0` | GNL |
| `1` | VDE4105 |
| `2` | IEEE1547 |
| `3` | CEI-021 |
| `4` | VDE0126 |
| `5` | EN50549 (General) |
| `6` | EN50549-SE (Switzerland) |
| `7` | EN50549-DK1 (Denmark) |
| `8` | SI4777 (Israel) |
| `9` | TOR-Z1 (Austria) |
| `10` | EN50549-PL (Poland) |

## The bundled CT meter

A separate Modbus device on its own bus. Slave 1, 9600 8N1, IEEE-754 float32 with
big-endian word order, so each value spans two registers.

| Address | Meaning |
|---|---|
| `0` | Line voltage, V |
| `12` | Active power, W — positive is importing |
| `18` | Apparent power, VA |

## The grid-tie cap lives in three places

`0xA03F`, a second copy at `0x9ACE`, and the energy manager's `3039`. Output tops out at
the lowest of them, and the vendor app displays the mirror rather than `0xA03F`.

`grid_export_limit_number` writes both Modbus copies. It does not write `3039`, which is
not on Modbus, so raising the cap above whatever `3039` holds changes nothing. To raise
`3039`, put an `ems 3039 <watts>` line in a restore file and POST it.

The name is the firmware's. It caps on-grid *output*, which includes power serving your
own load, so it is not an export limit on its own.

## Settings whose mapping is unconfirmed

**`0xA036` is named for the neutral–earth bond but may not be it.** It reads 1 while the
app shows it disabled, which inverts the polarity every other boolean follows, and
enabling it never produced a referenced island. It has no key, so reaching it takes an
explicit `registers:` entry.

**`0xA031` does not match the app.** It reads 35.0 A where the app shows 50 A for the same
setting. `0xA02F` matches its app figure correctly, so the discrepancy is specific to this
register.

**`0xA028` is plausibly the inverter operating mode** and was never confirmed against the
app.

## Not on Modbus

The energy manager's own registers — the schedule slots, the enable flag, the SOC window —
are only reachable over the unit's JSON API. The component handles those itself when you
give it a `datalogger:` block.

| Register | Meaning |
|---|---|
| `3000` | Energy manager enable; nothing regulates while it is 0 |
| `3003`–`3018` | Sixteen schedule slots, eleven CSV fields; field four is the signed setpoint |
| `3020` | Scheduler mode: 3 self-consumption, 6 custom — the `work_mode_select` key |
| `3021` / `3022` | Self-consumption charge and discharge enables. Writing `3021` = 1 turns on the vendor app's AI Mode; the cloud then writes its day plan into `3003` onwards, and a slot's discharge SOC overrides `3023` |
| `3023` / `3024` | Min and max SOC, % |
| `3026` / `3029` | Base discharge power and its enable; positive exports unconditionally |
| `3030` | Custom mode; required before `0xFE16` is honoured |
| `3039` | Max feed power, W — the third copy of the grid-tie cap. The firmware clamps the power written to `3003` to this value, an effective 800 W by default; raise it first for more |
