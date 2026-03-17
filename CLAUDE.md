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
│   └── dashboards/            # 3-tier: home.yaml, admin.yaml, debug.yaml
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

### Banking Algorithm (rewritten Mar 2026 — forward simulation):
- `cmd_banking()` subcommand in `scripts/solar_forecast.py` runs every 30 min
- Fetches next calendar event within 48h from HA calendar API
- Builds hourly timeline with Met.no ambient forecast + solar forecast (actual Wh per hour from DB)
- Forward simulation: Newton's cooling + solar heating per hour, 500W base load deducted from solar
- Binary search (20 iterations) for T_bank where simulate(T_bank) reaches 40°C by event
- Cost check: grid_deficit × RATE_LOW vs peak_deficit × RATE_HIGH — only banks if cheaper
- Caps banking at 37°C (BANKING_CAP)
- Decision log includes: grid_deficit_kwh, solar_contribution_kwh, projected_solar_only, banking_cost_chf, peak_alternative_chf

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
- [x] `deploy_from_git` now uses `git fetch --all && git reset --hard origin/main` to avoid stale deploys from local conflicts

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

## What's Done (Tuya Water Monitor — Grow Tent)
LocalTuya couldn't rediscover the water quality monitor after the server failure. Replaced with direct Tuya Cloud API polling.

### New Files:
- [x] `/config/tuya.py` — Tuya Cloud API client (HMAC-SHA256 auth, EU endpoint `openapi.tuyaeu.com`)
  - Called with `python3 /config/tuya.py <device_id>`
  - Returns 8 properties: temp, pH, ORP, TDS, EC, salinity, CF, PRO

### Modified Files:
- [x] `packages/grow_tent/grow_tent_sensors.yaml` — Added `command_line:` block with 8 sensors
  - Water Temperature (`temp_current / 10`, °C)
  - Water pH (`ph_current / 100`, pH) — divisor may need adjusting to /1000 after calibration
  - Water ORP (`orp_current`, mV)
  - Water TDS (`tds_current`, ppm)
  - Water EC (`ec_current`, µS/cm)
  - Water Salinity (`salinity_current`, ppt)
  - Water CF (`cf_current`, CF)
  - Water PRO (`pro_current`, unit TBC)
  - Scan interval: 900s (15 min) — Tuya blocks API if polled faster

### Known Follow-ups:
- [ ] Calibrate probes once reservoir is filled
- [ ] Verify pH divisor (currently /100, may need /1000)
- [ ] Identify unit of measurement for `pro_current`
- [ ] Consider alert automations for out-of-range pH/EC/ORP values

## What's Done (Tariff Update, High-Tariff Avoidance, EV Logic Fix & Solar Optimisation)

### Tariff Schedule Change:
**Old:** Mon-Fri 06:00-22:00 = main (0.35 CHF/kWh), rest = low (0.25 CHF/kWh), solar opportunity 0.10 CHF/kWh
**New:** Mon-Fri 17:00-22:00 = high (0.38 CHF/kWh), rest = low (0.26 CHF/kWh), solar opportunity 0.06 CHF/kWh (changing to market price June 2026)

### Files Modified:
- [x] `templates/energy/energy_shared_sensors.yaml` — Tariff schedule+rates updated, `next_low_start` replaced with `next_high_start`/`next_high_end`/`is_high` attrs, opportunity_cost 0.10→0.06, added `binary_sensor.energy_high_tariff_active`, demand scenario state C 24h→48h
- [x] `templates/ev/ev_templates.yaml` — `sensor.ev_cheap_tariff_active` schedule updated (high = Mon-Fri 17:00-22:00), simplified attrs
- [x] `templates/jacuzzi/jacuzzi_sensors.yaml` — Deprecated `sensor.electricity_tariff` updated to new schedule+rates, `sensor.jacuzzi_smart_start_time` now shifts start earlier to complete before 17:00 peak, peak_rate fallback 0.35→0.38
- [x] `automations/jacuzzi/jacuzzi_automations.yaml` — `jacuzzi_020` solar window 24h→48h, `jacuzzi_021` trigger migrated from `sensor.electricity_tariff` to `binary_sensor.energy_low_tariff_active` + window 12h→48h, `jacuzzi_040` preheat branch: added high-tariff guard (blocks new grid heating during peak unless solar >6kW or already heating)
- [x] `automations/ev/ev_automations.yaml` — EV 044: added `any_home_car_at_target` variable, changed `_needs` logic (if any home car at target: only charge critical <10% cars), suppressed plug-in nag when target met
- [x] `automations/ev/ev_notification_automations.yaml` — EV 080: suppressed nag when any home car >= `ev_minimum_soc`, unless any home car < 10% hard floor
- [x] `scripts/solar_forecast.py` — `_is_low_tariff_hour()` updated to new schedule, RATE_HIGH=0.38, RATE_LOW=0.26, RATE_SOLAR=0.06
- [x] `packages/grow_tent/grow_tent_energy.yaml` — avg_rate 0.30→0.28, fallback rates 0.35→0.38
- [x] `docs/USER_GUIDE.md` — Tariff table, solar feed-in rate, 48h window, high-tariff avoidance, EV maintenance "one car at 50%" rule clarified
- [x] yamllint passes on all modified files

### Key Behaviour Changes:
- Tariff state value changed from `main` to `high` — no downstream code checks `== 'main'`
- Low tariff is now the default (19 hours/day on weekdays, all weekend), high tariff is the 5-hour exception
- Smart start time shifts heating earlier to avoid Mon-Fri 17:00-22:00 peak
- Jacuzzi 040 blocks new grid heating during peak (safety net for edge cases)
- EV maintenance only nags for second car when first car hasn't reached 50% target, or when any car is critically low (<10%)

## What's Done (Decision Audit Trail Logging)
Structured logging to MariaDB `log_decisions` table for visibility into WHY the system makes each decision. ~10-20 rows/day.

### Decision Codes:
| Code | System | Source | When |
|------|--------|--------|------|
| `smart_start_shifted` | jacuzzi | 043 | Start time moved earlier to avoid peak |
| `smart_start_normal` | jacuzzi | 043 | Start calculated, no peak conflict |
| `preheat_blocked_high_tariff` | jacuzzi | 040 | Preheat due but blocked by peak tariff |
| `calendar_preheat` (enhanced) | jacuzzi | 040 | Preheat started — includes tariff/solar context |
| `banking_solar` / `_low_tariff` / `_combined` | jacuzzi | solar_forecast.py | Banking target set |
| `banking_cleared` | jacuzzi | solar_forecast.py | Active banking cleared |
| `maint_nag_suppressed` | ev | 044 | Nag suppressed (other car at target) |
| `maint_charge_started` | ev | 044 | Maintenance charging began |
| `plug_nag_suppressed` | ev | 080 | Plug nag suppressed (home car at target) |
| `tariff_shift_to_high` / `_to_low` | energy | 025 | Tariff window transition |

### Changes:
- [x] `jacuzzi_automations.yaml` — New `jacuzzi_043` smart start logger, restructured `jacuzzi_040` preheat with if/then/else for blocked logging, enhanced `calendar_preheat` context
- [x] `ev_automations.yaml` — `ev_044`: `maint_nag_suppressed` (else branch) + `maint_charge_started` (before log_action)
- [x] `ev_notification_automations.yaml` — `ev_080`: suppression check moved from conditions to actions with `plug_nag_suppressed` logging
- [x] `energy_solar_forecast_automations.yaml` — New `energy_025` tariff transition logger
- [x] `scripts/solar_forecast.py` — Banking decision logging (`banking_*` / `banking_cleared`) in `cmd_banking()`
- [x] yamllint passes on all modified files

## What's Done (EV Peak-Tariff Fix + Manual Car Override)
Two fixes to the EV subsystem: prevent expensive buffer charging and allow manual car selection.

### Part A: ev_044 Peak-Tariff Gate
EV 044 (maintenance/buffer charging) was charging to 80% during Mon-Fri 17:00-22:00 peak at 0.38 CHF/kWh. After the waterfall redesign raised the target from 50% to 80%, the lack of a tariff check became costly.

**Fix:** Tariff gate at top of ev_044 actions, before any other logic:
- If high tariff active AND no car below 10% hard floor → stop any active buffer charge + exit
- If any car below 10% (critical) → fall through to charge at any tariff (safety override)
- New trigger: `binary_sensor.energy_high_tariff_active` → on (immediate reaction when peak starts)

### Part B: ev_030 Manual Car Override
Fraser can now request a specific car via `input_select.ev_requested_vehicle`. The planner checks this before running its optimization:
- If set to Horace/Horatio → assigns that car to Fraser, other car to Heather, calculates charge target, notifies to plug in, then clears to "None" (one-time use)
- If "None" → normal optimization runs unchanged

### New Decision Codes:
| Code | System | Source | When |
|------|--------|--------|------|
| `maint_blocked_high_tariff` | ev | 044 | Buffer charging deferred — high tariff active |
| `maint_stopped_high_tariff` | ev | 044 | Active buffer charge stopped — high tariff started |
| `planner_override` | ev | 030 | Manual car override applied |

### Files Modified:
- [x] `automations/ev/ev_automations.yaml` — ev_044: tariff gate + high-tariff trigger; ev_030: manual override branch
- [x] `dashboards/ev.yaml` — Car Override selector card added
- [x] yamllint passes on all modified files

## What's Done (Dashboard Redesign – 3-Tier Split)
Replaced 4 per-system dashboards (energy, ev, jacuzzi, grow_tent) with 3 role-based dashboards. Heather gets a clean Home view; Fraser gets Admin monitoring with tabs; Debug collects broken entities and watchdog canaries.

### New Dashboards:
| Dashboard | File | Path | Views | Admin-only |
|-----------|------|------|-------|------------|
| Home | `dashboards/home.yaml` | `lovelace-home` | 1 | No |
| Admin | `dashboards/admin.yaml` | `lovelace-admin` | 4 (energy, jacuzzi, ev, grow-tent) | Yes |
| Debug | `dashboards/debug.yaml` | `lovelace-debug` | 1 | Yes |

### Home Dashboard (~15 cards):
- At a Glance: system status + tariff + surplus, solar actual vs forecast, today's savings
- Jacuzzi: climate card, status summary, event/prediction (conditional), quick actions (4h override, heat now, standby), toggle chips (automation, solar priority, manual override)
- Cars: Horace + Horatio status, Fraser/Heather trip today (conditional), EV controls (allow charging x2, trip mode x2, request car, solar mode, external charge)
- Grow Tent: conditional summary (hidden when mode = idle), links to Admin grow-tent view

### Admin Dashboard (~55 cards, 4 views):
- **Energy view**: all existing energy.yaml cards + new issues banner (conditional, links to debug) + orchestrator internals (tier, allocation JSON, heartbeat, output booleans)
- **Jacuzzi view**: all existing jacuzzi.yaml cards + banking internals + heating progress tracking
- **EV view**: all existing ev.yaml cards + planner internals + SOC predictions + energy tracking + advanced settings
- **Grow Tent view**: all existing grow_tent.yaml cards + offline warning banner (links to debug)

### Debug Dashboard (~10 cards):
- Watchdog summary + all 12 canaries (SolarEdge, Tesla Fleet, Balboa Spa, EPEX Spot, CalDAV, Met.no, 6 grow tent groups)
- Grow tent broken devices: Shelly plugs (5), Meross plugs (2), LocalTuya (1), ESPHome pumps/fan (9), automation TODOs (2)
- Watchdog settings

### Files Changed:
- [x] `config/dashboards/home.yaml` — **CREATED**
- [x] `config/dashboards/admin.yaml` — **CREATED**
- [x] `config/dashboards/debug.yaml` — **CREATED**
- [x] `config/configuration.yaml` — 4 dashboard registrations replaced with 3 new ones
- [x] `config/dashboards/energy.yaml` — **DELETED**
- [x] `config/dashboards/ev.yaml` — **DELETED**
- [x] `config/dashboards/jacuzzi.yaml` — **DELETED**
- [x] `config/dashboards/grow_tent.yaml` — **DELETED**
- [x] yamllint passes on all files

## What's Done (EV Override Trigger Fix + Allow Charging Defaults)
Two bugs found during dashboard testing.

### Bug 1: ev_030 manual car override not triggering
`input_select.ev_requested_vehicle` was checked in ev_030's actions but ev_030 had no trigger for it changing. Selecting a car on the dashboard did nothing — the planner only re-ran on trip data or SOC changes.
- [x] `automations/ev/ev_automations.yaml` — Added `input_select.ev_requested_vehicle` trigger (`not_to: "None"`) to ev_030

### Bug 2: allow_charging booleans resetting on restart
`ev_horace_allow_charging` and `ev_horatio_allow_charging` had no `initial:` value, so both defaulted to `off` after every HA restart. Charging was silently blocked until manually re-enabled.
- [x] `packages/ev_system.yaml` — Added `initial: true` to both allow_charging booleans

## What's Done (Solar-First Energy Redesign)
Economics-based energy logic: partial solar use, peak avoidance, 48h rolling window.

### Core Problem Fixed:
Jacuzzi demand scenario was comparing against standby temp (32°C) instead of event target (40°C), so system thought jacuzzi was "satisfied" when an event was upcoming. Multiple 6000W thresholds prevented partial solar use.

### Solar Threshold Changes:
- [x] `binary_sensor.solar_available_for_jacuzzi` — 6000W → 500W (any meaningful surplus)
- [x] `sensor.jacuzzi_effective_standby_temp` — 6000W → 500W solar check (2 places)
- [x] Demand scenario C/D — compare against 39.5°C (event target) not standby
- [x] Orchestrator tiers 3+6 — accept partial solar (was requiring full 6kW)
- [x] Notification source detection — 6000W → 500W (2 places)

### Peak Tariff Economics:
- [x] Orchestrator tier 3 grid: solar blend during peak when surplus >= 2250W (cheaper than low-tariff-later)
- [x] Jacuzzi 020: peak guard (no pure grid heating during peak unless solar >= 2250W)
- [x] Jacuzzi 022: fallback at 500W, only reverts during peak without solar
- [x] Jacuzzi 040: solar threshold 6000W → 2250W for peak blend

### EV 48h Rolling Window:
- [x] EV 010: single 48h calendar query per person (was 4 separate day-bucket queries)
- [x] EV 010: overnight return-home logic — inserts `zone.home` waypoint between events on different calendar dates, multi-day events bridge without return-home
- [x] EV 002: removed tomorrow→today midnight copy (EV 010 recalculates from calendar)
- [x] EV 030: simplified km vars (direct 48h totals, no today/tomorrow fallback)
- [x] EV demand scenario: simplified to use 48h rolling totals
- [x] `_today` helpers repurposed as 48h rolling totals; `_tomorrow` deprecated (always 0)
- [x] `sensor.ev_tomorrow_trip_summary` → `sensor.ev_upcoming_trip_summary`
- [x] Notification labels updated: "tomorrow" → "upcoming trip"
- [x] Admin dashboard: tomorrow trip cards → upcoming trip cards

### Self-Consumption Tracking:
- [x] `sensor.energy_self_consumption_pct` — real-time (production - export) / production
- [x] Home dashboard self-consumption card with colour-coded icon

### Proactive Solar Banking (Thermal Battery):
- [x] `sensor.jacuzzi_effective_standby_temp` — solar > 500W → base = 40°C (highest priority in cascade)
  - Cascade: solar_banking (40°C) > banking calculator > banking_hold > tariff_boost > normal, floored by readiness
- [x] Jacuzzi 020 solar branch — removed event requirement, now banks with any surplus regardless of calendar
  - Triggers when solar_available AND current_temp < (effective_standby - 2)
  - Target set to effective_standby (40°C during solar)
- [x] EV 085 swap cable suggestion (NEW) — notifies when plugged car at limit + solar surplus > 2000W for 10 min + other car at home below limit
  - 60 min cooldown, notifies Fraser always + Heather if home
- [x] Jacuzzi 022 solar-off fallback confirmed correct: during low tariff continues grid (finish what solar started), during peak reverts to effective_standby (which drops from 40°C when solar gone)

### Key Economic Rules:
- Solar pre-heating ALWAYS wins within 48h (break-even at ~156h/6.5 days)
- Any solar surplus > 0 makes heating cheaper (partial solar + grid < full grid)
- During peak with >= 2.25kW solar, heating NOW is cheaper than waiting for low tariff
- 2.28 - 0.32×S vs 1.56 CHF/h → break-even at S = 2.25kW
- Jacuzzi is a thermal battery: heat to 40°C with any solar surplus, cool ~2-3°C over 5h peak, avoids grid heating entirely

## What's Done (Solar-Deficit Jacuzzi Energy Budgeting)
Two changes to eliminate wasteful overnight grid heating when events are far away.

### Part 1: Calendar-Aware Readiness Floor
- [x] `sensor.jacuzzi_minimum_standby_temp` now reads `calendar.jacuzzi_schedule` `start_time` directly instead of using fixed `input_number.jacuzzi_max_heat_up_hours`
- No event or event in past/beyond 48h → T_min = 5°C (freeze protection only)
- Event exists → `effective_h = max(hours_to_event, 1.0)` used in inverted Newton's law formula
- Event 19h away → ~14.8°C (non-binding), event 6h → ~32.5°C (same as before), event 3h → tighter
- New attributes: `event_aware`, `effective_hours`, `hours_to_event`; removed `max_heat_up_hours`

### Part 2: Forward-Simulation Banking Calculator
- [x] `cmd_banking()` rewritten from backward-induction to forward simulation + binary search
- `_simulate_solar_only(t_start, timeline)`: Newton's cooling + solar heating per hour using actual forecast wattage (not binary 6kW threshold), minus 500W base load
- Binary search finds exact T_bank where solar tops up to 40°C; grid covers only the deficit
- Cost check: banking at RATE_LOW vs heating at RATE_HIGH — skips if not cost-effective
- Removed: backward induction, segments, `min_standby` dependency, `SOLAR_THRESHOLD_W`

### Files Modified:
- [x] `config/templates/jacuzzi/jacuzzi_sensors.yaml` — Readiness sensor rewritten (lines 414-475)
- [x] `scripts/solar_forecast.py` — `cmd_banking()` core algorithm replaced (lines ~1938-2116)
- [x] yamllint + python syntax check pass

## What's Done (EPEX Spot Dynamic Pricing Integration)
Switched tariff abstraction layer from fixed schedule to EPEX Spot quantile-based pricing, with fixed-schedule fallback. All downstream automations adapt automatically via existing `binary_sensor.energy_low/high_tariff_active` gates — zero automation file changes required.

### Threshold Strategy:
- **Cheap** = EPEX quantile < 0.33 (bottom third) → actively heat/charge
- **Expensive** = EPEX quantile > 0.67 (top third) → avoid grid
- **Neutral** = between → solar-only, no grid seeking/avoidance
- **Fallback**: EPEX unavailable or `energy_spot_pricing_enabled` = off → fixed Mon-Fri 17:00-22:00 schedule

### New File:
- [x] `config/packages/energy_spot_pricing_system.yaml` — 5 input_numbers + 1 input_boolean
  - `energy_spot_eur_chf_rate` (default 0.95)
  - `energy_spot_surcharge_chf_kwh` (default 0.12 — set from utility bill)
  - `energy_spot_cheap_quantile` (default 0.33)
  - `energy_spot_expensive_quantile` (default 0.67)
  - `energy_spot_solar_feed_in_chf_kwh` (default 0.06)
  - `energy_spot_pricing_enabled` (default OFF — enable after validation)

### Modified Files:
- [x] `config/configuration.yaml` — Added `energy_spot_pricing` package include
- [x] `config/templates/energy/energy_shared_sensors.yaml` — Rewrote 3 tariff sensors + added 1 new:
  - `sensor.energy_tariff_current`: spot mode returns `cheap`/`neutral`/`expensive`, fallback returns `high`/`low`. Rate from EPEX × EUR/CHF + surcharge. New attrs: `spot_enabled`, `market_price_eur`, `quantile`. Removed `next_high_start`/`next_high_end`
  - `binary_sensor.energy_low_tariff_active`: spot mode = `quantile <= cheap_quantile`, fallback unchanged
  - `binary_sensor.energy_high_tariff_active`: spot mode = `quantile >= expensive_quantile`, fallback unchanged
  - `sensor.energy_spot_total_price_chf` (NEW): always-on CHF conversion for dashboard display
- [x] `config/templates/ev/ev_templates.yaml` — `sensor.ev_cheap_tariff_active` replaced duplicated schedule logic with delegation to `binary_sensor.energy_low_tariff_active`. Removed `next_high_start` attribute
- [x] `scripts/solar_forecast.py` — Added 2 new functions + updated banking cost comparison:
  - `_fetch_epex_prices(token)`: reads EPEX `data` attribute → `{utc_naive: eur_kwh}` dict
  - `_get_spot_config(token)`: reads all spot helpers from HA
  - `cmd_banking()`: fetches EPEX prices, adds `price_chf` per timeline hour, banking cost uses avg of cheapest available hours, alternative cost uses event-adjacent hours. Fixed RATE_HIGH/RATE_LOW fallback when EPEX unavailable
- [x] `config/dashboards/home.yaml` — At-a-glance shows spot price CHF when enabled
- [x] `config/dashboards/admin.yaml` — Tariff card spot-aware, new conditional spot pricing status card (price, quantile, today min/max), new spot pricing settings section
- [x] yamllint passes on all modified files

### EPEX Sensor Entities:
- `sensor.epex_spot_data_market_price` — current hourly price (EUR/kWh), `data` attr has 48h hourly prices
- `sensor.epex_spot_data_quantile` — current hour quantile (0.0-1.0) as state, `data` attr has per-hour quantiles
- Also available: `sensor.epex_spot_data_rank`, `lowest_price`, `highest_price`, `average_price`, `median_price`

### No Changes Required (abstraction works):
All automations (jacuzzi 020/021/022/040, EV 040/041/044, orchestrator 001), effective standby cascade, notification automations, smart start

### Deferred:
- `sensor.jacuzzi_smart_start_time` peak avoidance stays Mon-Fri 17:00-22:00 for now. Heating gates use `binary_sensor.energy_high_tariff_active` which IS EPEX-aware, so decisions are correct.

### Deployment:
1. Deploy: `cd /homeassistant/ha-restore && git fetch --all && git reset --hard origin/main && cp -r config/* /config/ && mkdir -p /config/scripts && cp scripts/* /config/scripts/ && ha core restart`
2. Verify with `energy_spot_pricing_enabled = off` → identical to current fixed-schedule behavior
3. Enable → verify tariff sensors react to EPEX quantile
4. Check `sensor.energy_spot_total_price_chf` shows correct CHF conversion
5. Run `solar_banking` manually → verify EPEX prices used in cost comparison
6. Monitor decision logs for 24h
7. Test fallback: temporarily disable EPEX → sensors revert to fixed schedule

## What's Done (Snow on Roof Toggle for Solar Forecast)
Manual toggle to indicate snow covering solar panels. Overrides displayed forecast to 0 and blocks banking/calibration while preserving clear-roof data and calibration coefficients for instant recovery when snow clears.

### Approach:
- Python forecast script continues running normally — helpers and DB keep the real (clear-roof) forecast
- Toggle overrides the **displayed** forecast to 0 via template sensor
- Banking and calibration check toggle and exit early when snow is on
- Toggling snow off resumes everything instantly with preserved coefficients

### Modified Files:
- [x] `config/packages/energy_solar_forecast_system.yaml` — Added `input_boolean.energy_solar_snow_on_roof` (icon: snowflake, default: off)
- [x] `config/templates/energy/energy_solar_forecast_sensors.yaml` — Forecast summary sensor:
  - State: `"Snow: 0 / X.XkWh clear-roof"` when snow on
  - New attrs: `snow_on_roof` (boolean), `clear_roof_forecast_today_kwh` (always real model value)
  - `forecast_today_kwh`, `current_hour_w`, `next_hour_w`, `peak_hour_w`, `tracking_pct` return 0 when snow on
- [x] `scripts/solar_forecast.py` — `cmd_banking()`: early exit when snow on, clears banking, logs `banking_cleared_snow`. `cmd_calibrate()`: early return when snow on, preserves coefficients
- [x] `config/dashboards/home.yaml` — Solar card: snowflake icon + blue color + "Snow on roof (clear-roof: X.X kWh)" when on
- [x] `config/dashboards/admin.yaml` — Conditional snow banner after forecast quality card; snow toggle as first item in Solar Forecast Controls
- [x] yamllint + python syntax check pass

### New Decision Code:
| Code | System | Source | When |
|------|--------|--------|------|
| `banking_cleared_snow` | jacuzzi | solar_forecast.py | Banking cleared due to snow on roof |

## What's Done (EV Solar Charging Cycling Fix)
EV 040 was rapidly cycling charging on/off and overriding the user's manual `allow_charging` toggle.

### Root Cause:
- EV 040 used `input_boolean.ev_horace_allow_charging` as an **output** (toggling it on/off), not a **gate**
- When surplus dropped below 5A minimum (3,450W), the default branch turned OFF `allow_charging`, overriding user manual control
- No hysteresis: charging consumed surplus → surplus dropped → charging stopped → surplus recovered → cycling every 30s
- 500W positive margin meant the system exported surplus instead of absorbing it

### Fixes Applied:

**Fix 1: EV 040 no longer controls `allow_charging`**
- Removed `input_boolean.turn_on/off` from all three branches (trip-critical, solar, default)
- Added `allow_charging` as a **condition gate** — automation skips entirely if user has it off
- Removed unused `allow_charging_entity` variable
- Bridge automations (072/073) still mirror `allow_charging` → switch for user control

**Fix 2: Solar margin allows over-consumption**
- `input_number.ev_solar_margin_w`: min changed `0` → `-500`, initial `500` → `-200`
- Negative margin means system accepts ~200W grid import to maximize solar absorption
- Formula: `ev_solar_surplus_kw = (prod - cons + ev_draw - margin) / 1000`
- User-tunable from Admin dashboard

**Fix 3: 3-minute minimum ON duration**
- Default (stop) branch checks: switch must be ON AND have been on for >180 seconds
- If charging started <3 min ago, stop is skipped — re-evaluated next trigger (30s later)
- Prevents rapid cycling from cloud transients

### Modified Files:
- [x] `config/automations/ev/ev_automations.yaml` — EV 040: allow_charging as condition gate, removed from actions, 3-min minimum ON in default branch
- [x] `config/packages/ev_system.yaml` — `ev_solar_margin_w` min/initial changed
- [x] yamllint passes

### Key Sensor Chain:
- `sensor.solaredge_current_power` / `sensor.solaredge_power_consumption` → raw production/consumption
- `sensor.ev_solar_surplus_kw` = `(prod - cons + ev_draw - margin) / 1000` — adds back charger draw to prevent feedback loop
- `sensor.ev_solar_available_amps` = `surplus_kw * 1000 / (voltage × phases)` capped to max_amps
- EV 040 triggers on SolarEdge sensor changes (30s debounce), charges if available_amps >= min_amps (5A)

### Post-Deploy:
- Manually set `input_number.ev_solar_margin_w` to `-200` in HA UI (`initial` only applies on first entity creation)

## What's Done (EV Priority over Speculative Jacuzzi Solar Banking)
`sensor.jacuzzi_effective_standby_temp` was always 40°C when solar > 500W, regardless of EV state. This caused the jacuzzi to absorb all solar surplus even when an EV was plugged at 42% SOC with no jacuzzi event planned. Heating 39→40°C with no event is pure waste (heat dissipates), while EV stores solar with zero loss.

### Fix:
- Solar banking to 40°C now **yields to EV** when a plugged home car with `allow_charging` on is below `energy_ev_buffer_target_soc` (80%)
- Jacuzzi event imminent (demand states C/D) still overrides EV priority
- New mode attribute value: `ev_priority` (visible on admin dashboard)

### Priority Cascade (updated):
1. **Event imminent + solar** → 40°C (jacuzzi wins, user committed)
2. **Solar + no EV need** → 40°C (speculative banking, no conflict)
3. **Solar + EV needs charging** → normal standby (EV wins, `ev_priority` mode)
4. **Banking calculator target** → banking temp (event-driven grid banking)
5. **Boost enabled + cheap** → boosted standby
6. **Default** → normal standby (20°C)
7. **Floor** → readiness minimum (calendar-aware freeze protection)

### Modified Files:
- [x] `config/templates/jacuzzi/jacuzzi_sensors.yaml` — `sensor.jacuzzi_effective_standby_temp` state + mode attribute updated with EV priority check
- [x] yamllint passes

## HA Version
Targeting Home Assistant 2026.2+. Use `action:` not `service:`, `triggers:` not `trigger:` (list format), `conditions:` and `actions:` (plural).
