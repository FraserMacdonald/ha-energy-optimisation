# CLAUDE.md — Project Instructions for Claude Code

## Project Overview
Home Assistant energy optimization system with three subsystems:
1. **Jacuzzi** – Calendar-based pre-heating with solar/tariff optimization
2. **EV** – Two-Tesla charging with solar surplus, cheap tariff, trip planning
3. **Energy Orchestrator** – Shared arbitration layer (Phase 1C, not yet built)

## Repository Structure
```
ha-energy-optimisation/
├── config/                    # HA configuration (mirrors /homeassistant/)
│   ├── configuration.yaml     # Main config with package/include declarations
│   ├── packages/              # Helper definitions (one package per system)
│   │   ├── jacuzzi_system.yaml
│   │   └── ev_system.yaml
│   ├── automations/           # Subdirectory per system
│   │   ├── jacuzzi/
│   │   ├── ev/
│   │   └── energy/            # Phase 1C
│   ├── templates/             # Template sensors per system
│   │   ├── jacuzzi/
│   │   ├── ev/
│   │   └── energy/            # Phase 1C
│   ├── scripts/               # Manual trigger scripts
│   ├── python_scripts/        # Python helpers (elevation, text store)
│   ├── scenes/
│   └── dashboards/
├── docs/                      # Architecture docs and changelogs
│   ├── 001_architectural_review.md
│   └── 003_phase_1a_changelog.md
└── source_uploads/            # Original uploaded files (read-only reference)
```

## What's Done (Phase 1A)
See `docs/003_phase_1a_changelog.md` for full details.

### Completed:
- [x] `configuration.yaml` rebuilt with proper includes
- [x] `packages/jacuzzi_system.yaml` created (migrated from jacuzzi_helpers.yaml)
  - Bug fix: `input_text` → `input_select` for calendar entity
- [x] `packages/ev_system.yaml` — 6 helpers renamed to add `ev_` prefix
- [x] `automations/jacuzzi/jacuzzi_automations.yaml` — fully rebuilt
  - 7 automations renumbered (auto_jacuzzi_001 through 090)
  - `service:` → `action:` throughout
  - Bug fix: `binary_sensor.solar_available_jacuzzi` → `binary_sensor.solar_available_for_jacuzzi`
  - Trace config added to all automations
- [x] `automations/ev/ev_automations.yaml` — 25 automations renumbered
  - All IDs: `ev_XX_name` → `auto_ev_0XX_name`
  - All aliases: `EV XX –` → `EV 0XX –`
  - 6 entity renames applied (21 references updated)
  - Bug fix: 3-phase multiplier added to ev_043 energy logger
  - Trace config added to all 25 automations
- [x] `templates/jacuzzi/jacuzzi_sensors.yaml` — MeteoSwiss bug already fixed (la_dole)
- [x] `templates/jacuzzi/jacuzzi_binary_sensors.yaml` — unique_id renamed
- [x] `templates/ev/ev_templates.yaml` — entity renames already applied
- [x] `scripts/jacuzzi_scripts.yaml` — already uses `action:`
- [x] `scripts/ev_scripts.yaml` — entity renames already applied
- [x] Python scripts and data files copied

### Deferred to Phase 1B:
- Tariff sensor renames (`sensor.electricity_tariff` → `sensor.energy_tariff_current`) — these will be rebuilt as shared orchestrator sensors

### Phase 1A Verification (completed 2026-02-06):
- [x] Cross-reference: every entity referenced in automations exists in a package or template
  - Fixed: `input_text.ev_last_planner_decision` → `input_select.ev_last_planner_decision` in ev_scripts.yaml
  - Fixed: `input_number.ev_horace_soc_current` → `input_number.ev_horace_current_soc` in ev_automations.yaml (ev_042)
  - Fixed: `input_number.ev_horatio_soc_current` → `input_number.ev_horatio_current_soc` in ev_automations.yaml (ev_042)
- [x] Cross-reference: every entity renamed in the changelog is updated in ALL files
- [x] Verify `service:` → `action:` is complete in EV automations — confirmed zero `service:` calls remain
- [x] Verify `!include_dir_merge_list` format compatibility (each file must be a YAML list)
  - Fixed: `jacuzzi_sensors.yaml` wrapped in `- sensor:` list format
  - Fixed: `jacuzzi_binary_sensors.yaml` wrapped in `- binary_sensor:` list format
- [x] Run `yamllint` on all YAML files — all pass (trailing whitespace cleaned, final newlines added)
- [x] Verify no orphaned automation IDs (old ev_XX IDs do not appear anywhere)
- [x] Duplicate file headers cleaned up in ev_automations.yaml, ev_system.yaml, ev_templates.yaml
- [x] `themes/` directory created (referenced by configuration.yaml)

## Naming Conventions (MUST follow)
- **Helpers:** `{system}_{descriptive_name}` e.g. `ev_horace_allow_charging`
- **Automation IDs:** `auto_{system}_{NNN}_{description}` e.g. `auto_ev_043_charging_logger`
- **Automation aliases:** `{System} {NNN} – {Description}` e.g. `EV 043 – Charging Energy Logger`
- **Template sensors:** `{system}_{descriptive_name}` unique_id
- **Numbering ranges per system:**
  - 001-019: Core / lifecycle
  - 020-039: Solar / energy optimization
  - 040-059: Scheduling / calendar
  - 060-079: Notifications / alerts
  - 080-099: Safety / override

## Key Entity Mappings
Two Tesla vehicles: **Horace** and **Horatio**
- Native Tesla entities: `sensor.horace_battery_level`, `switch.horace_charge`, `number.horace_charge_current`, `climate.horace_climate`, `switch.horace_defrost` (same pattern for Horatio)
- Custom helpers: `input_boolean.ev_horace_allow_charging`, `input_boolean.ev_horace_trip_mode`, `input_number.ev_horace_charge_limit`
- Jacuzzi: `climate.jacuzzi` (native), all custom helpers prefixed `jacuzzi_`
- SolarEdge: `sensor.solaredge_current_power`, `sensor.solaredge_power_consumption`, `sensor.solaredge_imported_energy`, `sensor.solaredge_exported_energy`

## What's Done (Phase 1B)
- [x] `templates/energy/energy_shared_sensors.yaml` created (6 shared sensors + decision sensor)
  - Tariff, low tariff binary, solar surplus (W), production scenario (1/2/3)
  - Jacuzzi demand scenario (A–E), EV demand scenario (X/Y/idle)
  - SolarEdge unit normalization (kW → W via unit_of_measurement check)

## What's Done (Phase 1C Stage 1 – Shadow Mode)
See `docs/005_phase_1c_orchestrator.md` for full details.
- [x] `packages/energy_orchestrator_system.yaml` created (5 output helpers)
- [x] `automations/energy/energy_orchestrator_automations.yaml` created (3 automations)
  - 001: Evaluate scenario (30s loop, priority queue algorithm)
  - 060: Decision logger (logbook audit trail)
  - 061: Conflict alert (persistent notification for solar contention)
- [x] `sensor.energy_orchestrator_decision` added to shared sensors
- [x] `configuration.yaml` updated (energy_orchestrator package uncommented)
- [x] All entity cross-references verified
- [x] yamllint passes on all files
- [x] Note: `energy_last_decision` uses `input_select` (not `input_text`) — HA 2026 workaround

## What's Done (Phase 1C Stage 2 – Wired Mode)
See `docs/005_phase_1c_orchestrator.md` Stage 2 section for full details.
- [x] `input_boolean.energy_orchestrator_enabled` added (master switch, default OFF)
- [x] `jacuzzi_020` solar opportunistic: orchestrator gate added to conditions
- [x] `jacuzzi_021` low tariff heating: orchestrator gate added to conditions
- [x] `jacuzzi_040` calendar scheduler: orchestrator gate added to both 40°C branches
- [x] `ev_040` solar charging: orchestrator gate + amps capped to `energy_ev_max_solar_amps`
- [x] `ev_041` cheap tariff: orchestrator gate on "should charge" branch
- [x] No automations disabled or deleted — orchestrator gates via OR condition
- [x] yamllint passes on all modified files

## What's Done (Phase 1D – Enhancements)
See `docs/006_phase_1d_enhancements.md` for full details.
- [x] `jacuzzi_091` pipe freeze pump cycling — safety tier 0, bypasses orchestrator
- [x] `jacuzzi_061` not ready warning — 30 min before event if temp < 38°C
- [x] `jacuzzi_022` solar off fallback — reverts to standby when solar drops
- [x] `ev_050` climate prep — departure proximity trigger (45 min window, /5 re-eval)
- [x] yamllint passes on all modified files

## What's Done (Phase 1D – Notifications)
See `docs/009_notification_implementation.md` for full details.
- [x] Critical bug fix: `jacuzzi_sensors.yaml` heat-up time now uses hardcoded 40°C (was using standby temp)
- [x] `automations/jacuzzi/jacuzzi_notification_automations.yaml` created (10 automations: 062-071)
- [x] `automations/ev/ev_notification_automations.yaml` created (6 automations: 065-069, 077)
- [x] `automations/energy/energy_notification_automations.yaml` created (7 automations: 062-068)
- [x] 3 helpers added to `energy_orchestrator_system.yaml` (start temp, progress temp, progress time)
- [x] `jacuzzi_060` enhanced: specific mobile targets, heating source/start temp
- [x] `jacuzzi_061` enhanced: time-sensitive, rate/ETA/late minutes
- [x] `ev_064` already had time-sensitive — no change needed
- [x] yamllint passes on all new and modified files

## What's Done (Phase 1D – Thermal Model & EV Calendar Fix)
See `docs/011_thermal_model_and_ev_calendar_fixes.md` for full details.
- [x] Physics-based thermal model: 13 new helpers, 8 new/replaced sensors, 2 adaptive feedback automations (095, 096)
- [x] Heat-up time sensor uses integral formula with Newton's law (not linear approximation)
- [x] Adaptive learning: P_net via EWM (heating), k per temp band via EWM (cooling)
- [x] EV calendar sync split into today/tomorrow data paths
- [x] New helpers: `ev_trip_km_fraser_today`, `ev_trip_km_heather_today`
- [x] Daily reset copies tomorrow→today before clearing
- [x] Planner uses today-first-else-tomorrow logic for car assignment
- [x] Departure reminders guard against `assigned_car = None`
- [x] Morning SOC check + morning summary + orchestrator demand sensor updated to use `_today`
- [x] yamllint passes on all modified files

## HA Version
Targeting Home Assistant 2026.2+. Use `action:` not `service:`, `triggers:` not `trigger:` (list format), `conditions:` and `actions:` (plural).
