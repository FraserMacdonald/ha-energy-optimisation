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

## What's Done (Phase 1D – EV Notification Gaps)
5 notification gaps fixed across 2 files, plus dashboard fixes.

### EV Notification Gaps (ev_automations.yaml):
- [x] `ev_042` rewritten: wake home cars with stale plug state → wait 30s → re-check → alert if not plugged (Gap 5+1A)
  - Removed plug-state condition from `conditions:`, moved check into actions after wake
  - Heather notified if at home (Gap 1A)
- [x] `ev_030` plug-in-tonight notification added after planner's final `shell_command.log_decision`
  - Fires when `night_charge_car` needs charging (current SOC < target)
  - Notifies Fraser always, Heather if at home (Gap 2)
  - Uses chained `- variables:` blocks for dependent variable resolution
- [x] `ev_061` + `ev_062` departure reminders: added `trip_km` variable and updated message with trip distance + drive duration (Gap 4)

### EV Notification Gaps (ev_notification_automations.yaml):
- [x] `ev_079` morning briefing: personalized messages per driver (Gap 3)
  - Fraser: both cars' status, his trip, recommended car, overnight summary, climate note
  - Heather: both cars' status, her trip, plug-in warning if her car isn't plugged, climate note
  - Added `fraser_dep_time`, `heather_dep_time`, `fraser_travel_min`, `heather_travel_min` variables
- [x] `ev_080` plug-in nag: Heather now notified if at home (Gap 1B)

### Feedback Loop Notifications:
- [x] `ev_067` night charge started: now notifies both Fraser and Heather (was Fraser-only)
- [x] `ev_083` solar charge target reached (NEW): notifies assigned driver when SOC reaches charge limit during solar charging
- [x] `ev_084` charging session ended (NEW): notifies assigned driver when charging stops, with final SOC, source, target status, and solar/grid kWh breakdown
- [x] `jacuzzi_072` ready (NEW): notifies both users when jacuzzi crosses 39.5°C during heating session with upcoming event
  - Time-sensitive push, includes start temp and elapsed heating time

### Dashboard Fixes:
- [x] Bug fix: `dashboards/jacuzzi.yaml` had `type: sections` with `cards:` — incompatible in HA 2026 (sections views require `sections:` key). Removed `type: sections` and `max_columns: 2` to match EV/Energy dashboards
- [x] `dashboards/jacuzzi.yaml` + `dashboards/energy.yaml`: updated stale `sensor.electricity_tariff` → `sensor.energy_tariff_current` (4 refs total)
- [x] `dashboards/ev.yaml` + `dashboards/energy.yaml`: fixed `device_tracker.horace` / `device_tracker.horatio` → `device_tracker.horace_location` / `device_tracker.horatio_location` (4 refs — was showing "Unknown")
- [x] yamllint passes on all modified files

## What's Done (Grow Tent Dashboard)
- [x] `dashboards/grow_tent.yaml` created (mushroom cards + mini-graph-card, matching existing dashboard style)
  - Status header: stage display, day count, cultivation phase, mode, lights state, LED%, photoperiod
  - Environment: air temp + humidity vs targets (colour-coded), VPD vs target + fan speed
  - Air graph: 24h mini-graph (temp + humidity, dual-axis)
  - Water & pH: water temp + pH vs targets (colour-coded), reservoir age + volume + change alert
  - Water graph: 24h mini-graph (water temp + pH, dual-axis)
  - Nutrient recipe: per-reservoir volumes for current stage (6 nutrients)
  - Quick actions: Advance Stage, Water Change, New Grow (with confirmation)
  - Energy: daily + monthly totals with CHF cost, per-device daily breakdown (7 devices)
  - Environment settings: mode, stage, light schedule, temp/humidity/water targets + deadbands
  - pH & dosing settings: pH target/limits, dose config, reservoir volume, harvest yield, energy/gram
- [x] `configuration.yaml` updated: `lovelace-grow-tent` dashboard registered (YAML mode, sidebar visible)
- [x] yamllint passes on all files

## What's Done (Phase 1D – Weather Forecast + Standby Boost)
Two enhancements to the jacuzzi thermal model:

### Part A: Weather Forecast Integration (Met.no)
- [x] 3 helpers added to `jacuzzi_system.yaml`: `jacuzzi_forecast_temp_at_event`, `jacuzzi_forecast_temp_at_heating`, `jacuzzi_use_forecast`
- [x] `jacuzzi_042` forecast ambient updater automation: fetches Met.no hourly forecast every 30 min, stores forecast ambient at event time and mid-heating time
- [x] `jacuzzi_heat_up_time_required` sensor updated to use forecast ambient when available (with fallback to current)
- [x] `jacuzzi_predicted_temp_at_event` sensor updated to use forecast ambient at event time
- [x] `jacuzzi_max_achievable_temp` sensor: added `forecast_max` attribute
- [x] Heat-up time attributes updated: `forecast_temp`, `using_forecast`, forecast-aware `heating_rate_at_target`, `is_achievable`, `calculation_breakdown`
- [x] Prerequisite: user must configure Met.no integration via HA UI → creates `weather.forecast_home`

### Part B: Standby Thermal Energy Banking
- [x] 2 helpers added to `jacuzzi_system.yaml`: `jacuzzi_boosted_standby_temp` (default 25°C), `jacuzzi_standby_boost_enabled` (default off)
- [x] `sensor.jacuzzi_effective_standby_temp` sensor added: dynamically selects normal or boosted standby based on solar surplus (>3500W) or low tariff
- [x] `jacuzzi_040` default branch: standby reference changed to `sensor.jacuzzi_effective_standby_temp`
- [x] `jacuzzi_022` solar off fallback: standby reference changed to `sensor.jacuzzi_effective_standby_temp`
- [x] `jacuzzi_091` pipe freeze cycling: no change needed (boosted target > standby correctly skips cycling)

### Dashboard Updates
- [x] Standby boost status card (conditional, shows when boost enabled)
- [x] Forecast status card (conditional, shows when forecast active + event upcoming)
- [x] Settings section: added forecast toggle, boost toggle, boosted standby temp, effective standby temp
- [x] yamllint passes on all 4 modified files
- [x] All entity cross-references verified

## What's Done (Database Rebuild – 2026-02-13)
Full HA database loss on mini PC. Config rebuilt from GitHub.

### Infrastructure Restored:
- [x] All config files deployed from git to `/homeassistant/`
- [x] Tesla Fleet integration (Horace + Horatio) — new key pair, public key pushed to `FraserMacdonald.github.io`
- [x] SolarEdge, CalDAV (calendars), Met.no weather, Waze Travel Time
- [x] Mobile app notifications (Fraser + Heather iPhones)
- [x] HACS + Mushroom + Mini Graph Card (frontend)
- [x] Local Tuya (grow tent MarsHydro)
- [x] MariaDB add-on + `ha_analytics` database with 4 tables (decisions, actions, feedback, costs)
- [x] `scripts/log_to_db.py` restored to `/homeassistant/scripts/`
- [x] `energy_orchestrator` package uncommented in `configuration.yaml`
- [x] Git pull pipeline: `/homeassistant/ha-restore/` cloned, deploy via `cd /homeassistant/ha-restore && git pull && cp -r config/* /homeassistant/ && ha core restart`
- [x] Nabu Casa remote access restored
- [x] Entity renames: `sensor.horace_charger_current` → `sensor.horace_charge_amps` (and Horatio) via entity registry

### Not yet restored:
- ~~Balboa Spa WiFi~~ (restored — `climate.jacuzzi` available, `current_temperature` working)
- Grow tent Shelly device naming
- Grow tent ESPHome devices
- Reolink cameras
- History/statistics data (permanently lost)

### Bug Fixes (discovered during rebuild):
- [x] **EV 030 planner**: SOC drop fallback — when elevation data unavailable (helpers at 0), now estimates SOC drop from `km × Wh/km / (battery_kWh × 10)` instead of using 0 (which caused planner to skip overnight charging)
- [x] **EV 041 cheap tariff**: Tesla wake before plug check — wakes planned car + refreshes entities before evaluating plug state, preventing false `unknown` readings from sleeping Teslas
- [x] **EV 041 cheap tariff**: Tesla API retry — if plug state still `unknown` after wake, reloads Tesla Fleet config entry and retries (up to 2 additional attempts)
- [x] **EV 041 cheap tariff**: Set Tesla charge limit (`number.horace_charge_limit`) to planner target SOC before starting charge — car stops itself at target instead of charging to default 80%
- [x] **EV 041 cheap tariff**: Safety stop — when `plan_car` is cleared (e.g. by daily reset), now turns off both charge switches instead of silently exiting
- [x] **EV 002 daily reset**: Now turns off both charge switches at midnight as safety net
- [x] yamllint passes on all modified files

## Deployment
- **Mini PC path**: `/homeassistant/` (HA OS config directory)
- **Git repo on mini PC**: `/homeassistant/ha-restore/`
- **Manual deploy** (from web terminal): `cd /homeassistant/ha-restore && git pull && cp -r config/* /homeassistant/ && cp scripts/* /homeassistant/scripts/ && ha core restart`
- **Remote deploy** (via HA API): `shell_command.deploy_from_git` pulls git and copies config+scripts. Restart via `homeassistant.restart` service (separate call).
- **API URL**: `http://homeassistant.local:8123`
- **Tesla public key repo**: `FraserMacdonald.github.io` (GitHub Pages, `.well-known/appspecific/com.tesla.3p.public-key.pem`)

## What's Done (Phase 2A-2C – Solar Production Forecasting)
Solar production forecast system: predicts 48-hour solar output using NOAA sun position, dual-slope clear-sky model (23kWp east/west at 35° tilt), Met.no cloud overlay, and auto-calibration.

### New Files:
- [x] `scripts/solar_forecast.py` — Core engine (5 subcommands: init_db, forecast, actual, compare, calibrate)
  - NOAA solar position equations (manual, no pvlib)
  - Dual-slope clear-sky model (east=90°, west=270°, tilt=35°, Meinel DNI + Kasten-Young AM)
  - Kasten-Czeplak cloud scaling from Met.no `cloud_area_fraction`
  - Auto-calibration via EWM (alpha=0.1) from clear-sky days
  - Variance decomposition (model error vs weather error)
  - 4 MariaDB tables: `solar_forecast_hourly`, `solar_actual_hourly`, `solar_forecast_comparison`, `solar_calibration_log`
- [x] `config/packages/energy_solar_forecast_system.yaml` — 13 input_numbers, 1 input_boolean, 2 input_selects
- [x] `config/automations/energy/energy_solar_forecast_automations.yaml` — 4 automations (020-023)
  - 020: Forecast runner (every 30 min, 04:00-22:00)
  - 021: Actual logger (every 30 min)
  - 022: Forecast comparison (:05 past each hour)
  - 023: Weekly calibration (Sunday 23:30)
- [x] `config/templates/energy/energy_solar_forecast_sensors.yaml` — 2 template sensors (summary + quality)

### Modified Files:
- [x] `config/configuration.yaml` — Added `energy_solar_forecast` package + 4 shell_commands + uncommented `energy_orchestrator` package
- [x] `config/dashboards/energy.yaml` — Added 4 cards (forecast overview, forecast vs actual graph, quality, controls)

### Jacuzzi 6kW Heater Update:
Jacuzzi heater power increased from 3.5kW to 6kW. All hardcoded 3500W references updated to 6000W across:
- [x] `packages/jacuzzi_system.yaml` — `jacuzzi_heater_power_rated_kw` initial: 3.0 → 6.0
- [x] `templates/energy/energy_shared_sensors.yaml` — production scenario jacuzzi_w, power_demand_w
- [x] `automations/energy/energy_orchestrator_automations.yaml` — all jac_w and surplus threshold refs
- [x] `automations/energy/energy_notification_automations.yaml` — contention notification jac_w
- [x] `templates/jacuzzi/jacuzzi_binary_sensors.yaml` — solar_available jacuzzi_power
- [x] `templates/jacuzzi/jacuzzi_sensors.yaml` — effective standby temp solar surplus thresholds
- [x] `automations/jacuzzi/jacuzzi_automations.yaml` — solar-off fallback threshold + source detection
- [x] `automations/jacuzzi/jacuzzi_notification_automations.yaml` — source detection + source changed thresholds
- [x] yamllint passes on all modified files

### Deployment:
1. Deploy files: `cd /homeassistant/ha-restore && git pull && cp -r config/* /homeassistant/ && cp scripts/* /homeassistant/scripts/ && ha core restart`
2. Initialize DB tables: SSH to HA → `python3 /homeassistant/scripts/solar_forecast.py init_db`
3. Turn on `input_boolean.energy_solar_forecast_enabled` in HA UI
4. Update `input_number.jacuzzi_heater_power_rated_kw` to 6.0 in HA UI (if not already)

## What's Done (Phase 2D – Smart Thermal Banking)
Jacuzzi pre-heating during cheap energy periods using solar forecast + tariff schedule + calendar events.

### Banking Algorithm:
- `cmd_banking()` subcommand in `scripts/solar_forecast.py` runs every 30 min
- Fetches next calendar event within 48h from HA calendar API
- Builds hourly timeline with cheap/expensive flags (solar >6kW or low tariff)
- Uses Met.no ambient forecast + solar forecast from DB for each hour
- Backward induction from event: inverts cooling through expensive gaps to find banking target
- Cost check: only banks if cheap energy cost < alternative high tariff cost
- Caps banking at 37°C (diminishing returns above this)

### New/Modified Files:
- [x] `scripts/solar_forecast.py` — Added `banking` subcommand + 5 helper functions (`_is_low_tariff_hour`, `_fetch_calendar_events`, `_fetch_solar_forecast_db`, `_clear_banking`, `fetch_metno_temps`, `ha_select_option`)
- [x] `config/packages/jacuzzi_system.yaml` — 3 new input_numbers (banking_target_temp, expected_solar_hours, expected_solar_gain_c), 1 new input_select (banking_strategy). Updated defaults: standby 15→20°C, boosted 25→34°C, max_heat_up 8→6h
- [x] `config/templates/jacuzzi/jacuzzi_sensors.yaml` — Rewrote `sensor.jacuzzi_effective_standby_temp` with banking-aware logic (banking > boost > normal, with expensive period hold at banking-2)
- [x] `config/templates/energy/energy_shared_sensors.yaml` — Changed demand scenario state B from `input_number.jacuzzi_standby_temp` to `sensor.jacuzzi_effective_standby_temp`
- [x] `config/configuration.yaml` — Added `solar_banking` shell command
- [x] `config/automations/energy/energy_solar_forecast_automations.yaml` — Added auto_energy_024 (banking calculator, every 30 min)
- [x] `config/dashboards/jacuzzi.yaml` — Added conditional banking status card
- [x] yamllint passes on all modified files

### Deployment:
1. Deploy: `cd /homeassistant/ha-restore && git pull && cp -r config/* /homeassistant/ && cp scripts/* /homeassistant/scripts/ && ha core restart`
2. Set updated defaults in HA UI (if not auto-applied):
   - `input_number.jacuzzi_standby_temp` → 20
   - `input_number.jacuzzi_boosted_standby_temp` → 34
   - `input_number.jacuzzi_max_heat_up_hours` → 6
3. Verify: run `solar_banking` manually, check helpers update

## What's Done (EV Maintenance Charging)
Ensures at least one car always has minimum SOC (50%) for unplanned trips, regardless of tariff or planner state.

### Problem:
Cars were sitting at 0% SOC because EV 041 only charges when the planner flags a trip-critical need via `night_charge_car`. With no trips planned, no charging occurred.

### Changes:
- [x] `config/packages/ev_system.yaml` — Added `ev_minimum_soc` helper (min 10, max 80, step 5, default 50%)
- [x] `config/automations/ev/ev_automations.yaml` — **EV 041**: Removed switch-off from "no plan" branch (was conflicting with maintenance charging)
- [x] `config/automations/ev/ev_automations.yaml` — **EV 044** (NEW): Maintenance charging automation
  - Triggers every 30 min
  - Skips when EV 041 planner is active (night_charge_car set + cheap tariff)
  - Picks lowest-SOC home car below `ev_minimum_soc`
  - Wakes car, checks plug, charges to minimum SOC
  - No orchestrator gate (readiness priority)
  - Works regardless of tariff
- [x] `config/templates/energy/energy_shared_sensors.yaml` — Updated EV demand scenario state Y: `can_use_grid` and `can_use_low_tariff` now return true when any car SOC < `ev_minimum_soc`
- [x] yamllint passes on all modified files

### Deployment:
1. Deploy: `cd /homeassistant/ha-restore && git pull && cp -r config/* /homeassistant/ && ha core restart`
2. Set `input_number.ev_minimum_soc` to 50 in HA UI (if not auto-applied)
3. Verify: check `sensor.energy_ev_demand_scenario` attributes show maintenance logic, EV 044 traces show runs every 30 min

## What's Done (User Guide + Bug Fixes – 2026-02-17)

### User Guide:
- [x] `docs/USER_GUIDE.md` created (~393 lines) — plain-language guide covering all three subsystems
  - Overview, tariff schedule, solar setup
  - Jacuzzi: scheduling, smart start, solar/low-tariff heating, thermal banking, standby boost, weather forecast, freeze protection
  - EV: Horace/Horatio specs, trip planning, car assignment, overnight/solar/maintenance charging, climate prep
  - Energy orchestrator: priority tiers, scenario codes, shadow vs active mode
  - Solar forecast: predictions, calibration, banking integration
  - Full notification reference (grouped by system, with recipients and triggers)
  - Dashboard descriptions, settings tables, quick actions
  - Written for Fraser and Heather, no YAML or code

### Bug Fixes (3 notification bugs):
- [x] **Jacuzzi 061/063/068**: Added `current_temperature is not none` guard — skips warning notifications when `climate.jacuzzi` temperature attribute is unavailable (was defaulting to 0°C/20°C and triggering false warnings)
- [x] **EV 044 maintenance charging**: Skip if another car is already actively charging (`switch.horace_charge` / `switch.horatio_charge` on) — was nagging to plug in Horace while Horatio was already charging to 50%
- [x] **EV 044 + EV 080 plug-in nag**: Fraser's notification now guarded with `device_tracker.fraser_s_iphone` at-home check — was sending regardless of location (Heather already had this guard)
- [x] **EV 044 car selection logic**: Changed from "pick lowest SOC" to "pick car closest to min_soc" — fastest path to having one car at 50%. Cars below hard floor (10%) still take priority as safety override.
- [x] yamllint passes on all modified files

### Deployment Infrastructure:
- [x] `configuration.yaml` — Added `deploy_from_git` shell command (git pull + copy config + scripts)
- [x] `.gitignore` — Added `__pycache__/`
- [x] Remote deploy workflow: `shell_command.deploy_from_git` via HA API, then `homeassistant.restart` separately
- [x] Note: deploy_from_git may not pull latest changes if git repo on mini PC has conflicts — manual `git pull` from web terminal may be needed

### Automated Backups to iCloud:
- [x] `~/ha-backup.sh` on Mac — fully self-contained backup pipeline
  - Creates backup via `hassio.backup_full` HA service (no HA-side script needed)
  - Polls `sensor.backup_backup_manager_state` until idle
  - Extracts backup slug from `/api/hassio/supervisor/logs`
  - Downloads via `/api/hassio/backups/{slug}/download` (hassio proxy, works with long-lived token)
  - Saves to `~/Library/Mobile Documents/com~apple~CloudDocs/HA-Backups/` (iCloud Drive)
  - Cleans up local backups older than 7 days
- [x] `~/Library/LaunchAgents/com.fraser.ha-backup.plist` — runs daily at 02:00
- [x] Note: hassio proxy listing (`/api/hassio/backups`) returns 401 with long-lived tokens, but individual backup download works
- [x] Note: `backup.create_automatic` service returns 500 — use `hassio.backup_full` instead
- [x] Removed HA-side `scripts/ha_backup.py` and `shell_command.ha_backup_copy` — not needed

## HA Version
Targeting Home Assistant 2026.2+. Use `action:` not `service:`, `triggers:` not `trigger:` (list format), `conditions:` and `actions:` (plural).
