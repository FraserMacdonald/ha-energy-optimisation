# Phase 1A – Changelog & Migration Guide

**Date:** 2026-02-05

---

## Bug Fixes

| # | File | Fix |
|---|------|-----|
| 1 | `jacuzzi_automations.yaml` | Automation 020 trigger: `binary_sensor.solar_available_jacuzzi` → `binary_sensor.solar_available_for_jacuzzi` |
| 2 | `jacuzzi_sensors.yaml` | `heating_rate_used` attribute: `sensor.meteoswiss_temperature` → `sensor.la_dole_temperature` |
| 3 | `ev_automations.yaml` | ev_043 energy logger: added `* phases` for 3-phase charging |
| 4 | `jacuzzi_system.yaml` | `input_text.jacuzzi_calendar_entity` → `input_select.jacuzzi_calendar_entity` |
| 5 | All jacuzzi files | `service:` → `action:` (HA 2024.x+ syntax) |

## Entity Renames (6 EV helpers gained `ev_` prefix)

| Old | New |
|-----|-----|
| `input_boolean.horace_allow_charging` | `input_boolean.ev_horace_allow_charging` |
| `input_boolean.horatio_allow_charging` | `input_boolean.ev_horatio_allow_charging` |
| `input_boolean.horace_trip_mode` | `input_boolean.ev_horace_trip_mode` |
| `input_boolean.horatio_trip_mode` | `input_boolean.ev_horatio_trip_mode` |
| `input_number.horace_charge_limit` | `input_number.ev_horace_charge_limit` |
| `input_number.horatio_charge_limit` | `input_number.ev_horatio_charge_limit` |

## Automation Renumbering

### Jacuzzi (7 automations)
| Old ID | New ID |
|--------|--------|
| `jacuzzi_temperature_control` | `auto_jacuzzi_001_temperature_control` |
| `jacuzzi_solar_opportunistic_heating` | `auto_jacuzzi_020_solar_opportunistic` |
| `jacuzzi_low_tariff_preference` | `auto_jacuzzi_021_low_tariff_heating` |
| `jacuzzi_calendar_event_scheduler` | `auto_jacuzzi_040_calendar_scheduler` |
| `jacuzzi_event_reminder` | `auto_jacuzzi_060_event_reminder` |
| `jacuzzi_manual_override` | `auto_jacuzzi_080_manual_override` |
| `jacuzzi_freeze_protection` | `auto_jacuzzi_090_freeze_protection` |

### EV (25 automations)
| Old ID | New ID |
|--------|--------|
| `ev_00_bootstrap` | `auto_ev_001_bootstrap` |
| `ev_01_daily_reset` | `auto_ev_002_daily_reset` |
| `ev_10_calendar_sync` | `auto_ev_010_calendar_sync` |
| `ev_20_soc_tracker` | `auto_ev_020_soc_tracker` |
| `ev_30_planner` | `auto_ev_030_planner` |
| `ev_40_solar_charging` | `auto_ev_040_solar_charging` |
| `ev_41_cheap_tariff_charging` | `auto_ev_041_cheap_tariff` |
| `ev_42_solar_surplus_alert` | `auto_ev_042_solar_surplus_alert` |
| `ev_43_charging_logger` | `auto_ev_043_charging_logger` |
| `ev_44_record_departure_soc` | `auto_ev_044_record_departure_soc` |
| `ev_45_correction_factor_update` | `auto_ev_045_correction_factor` |
| `ev_50_climate_prep` | `auto_ev_050_climate_prep` |
| `ev_51_climate_confirmation` | `auto_ev_051_climate_confirmation` |
| `ev_60_evening_digest` | `auto_ev_060_evening_digest` |
| `ev_61_departure_reminder_fraser` | `auto_ev_061_departure_fraser` |
| `ev_62_departure_reminder_heather` | `auto_ev_062_departure_heather` |
| `ev_63_plug_reminder` | `auto_ev_063_plug_reminder` |
| `ev_64_morning_soc_check` | `auto_ev_064_morning_soc_check` |
| `ev_70_horace_charge_limit_sync` | `auto_ev_070_horace_charge_limit_sync` |
| `ev_71_horatio_charge_limit_sync` | `auto_ev_071_horatio_charge_limit_sync` |
| `ev_72_horace_allow_charging_bridge` | `auto_ev_072_horace_charge_bridge` |
| `ev_73_horatio_allow_charging_bridge` | `auto_ev_073_horatio_charge_bridge` |
| `ev_74_horace_trip_mode` | `auto_ev_074_horace_trip_mode` |
| `ev_75_horatio_trip_mode` | `auto_ev_075_horatio_trip_mode` |
| `ev_76_clear_plug_request` | `auto_ev_076_clear_plug_request` |

## Structural Changes

| Change | Detail |
|--------|--------|
| `jacuzzi_helpers.yaml` | → `packages/jacuzzi_system.yaml` |
| `automations/` | Split into `ev/`, `jacuzzi/`, `energy/` subdirs |
| `templates/` | Split into `ev/`, `jacuzzi/`, `energy/` subdirs |
| `tesla_ev_automations.yaml` | → `ev_automations.yaml` |
| `tesla_ev_templates.yaml` | → `ev_templates.yaml` |
| `scripts/scripts.yaml` | Retired (UI script covered by auto_ev_070) |

## Deployment Steps

1. `ha core backup`
2. Copy `config/` to `/homeassistant/`
3. Delete moved/renamed originals (see list above)
4. `ha core check` → validate YAML
5. `ha core restart`
6. Clean orphaned entities: Settings → Entities → filter "unavailable"
7. Update dashboard cards referencing 6 renamed helpers
8. Delete old automation entries from Settings → Automations
