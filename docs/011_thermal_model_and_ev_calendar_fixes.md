# Phase 1D – Thermal Model Redesign & EV Calendar Bug Fix

**Date:** 2026-02-06
**Depends on:** Phase 1A–1D Notifications complete

## Overview

Two major changes: (1) Replace the jacuzzi's linear heating model with a physics-based thermal model that adapts from observations, and (2) fix the EV calendar sync bug that caused "Take None" departure notifications.

---

## Task 1: Jacuzzi Physics-Based Thermal Model

### Problem

The original linear model assumed 3–5°C/h heating rate. For a 3200L jacuzzi with a 3kW Balboa M7 heater, the real theoretical max is ~0.81°C/h (observed ~1.0°C/h with pump waste heat). The linear model gave wildly wrong heat-up time estimates.

### Solution: Physics-Based Model

Uses Newton's law of heating/cooling with adaptive parameter learning.

**Core equations:**
- Thermal capacity: `C = volume × 4.186 / 3600` (kWh/°C)
- Heat loss: `Q_loss = k × (T_water - T_ambient)` (kW)
- Heat-up time (integral): `t = -(C/k) × ln[(P/k - ΔT_target) / (P/k - ΔT_current)]`
- Max achievable temp: `T_max = T_ambient + P_net / k`

**Adaptive learning via EWM (α=0.1):**
- Heating observations → learn effective heater power (P_net)
- Cooling observations → learn heat loss coefficient (k) per outdoor temp band

### Part 1A: New Helpers

**File:** `packages/jacuzzi_system.yaml`

| Entity | Type | Purpose |
|--------|------|---------|
| `jacuzzi_volume_litres` | number (500-5000) | Water volume, default 3200 |
| `jacuzzi_heater_power_rated_kw` | number (1-12) | Rated heater power, default 3.0 |
| `jacuzzi_effective_power_kw` | number (0.5-12) | Learned net power, default 3.7 |
| `jacuzzi_k_cold` | number (0.005-0.2) | Loss coeff <5°C outdoor, default 0.040 |
| `jacuzzi_k_mild` | number (0.005-0.2) | Loss coeff 5-15°C outdoor, default 0.035 |
| `jacuzzi_k_warm` | number (0.005-0.2) | Loss coeff >15°C outdoor, default 0.025 |
| `jacuzzi_last_sample_temp` | number (0-50) | Last observed water temp |
| `jacuzzi_last_sample_ambient` | number (-20-45) | Last observed ambient temp |
| `jacuzzi_last_sample_time` | datetime | Last observation timestamp |
| `jacuzzi_last_sample_heater_state` | select | Last heater state (heating/idle/unknown) |
| `jacuzzi_model_observation_count` | number (0-100000) | Total observations |
| `jacuzzi_model_heating_observations` | number (0-100000) | Heating-only observations |
| `jacuzzi_model_cooling_observations` | number (0-100000) | Cooling-only observations |

### Part 1B: Physics-Based Sensors

**File:** `templates/jacuzzi/jacuzzi_sensors.yaml`

| Sensor | Purpose |
|--------|---------|
| `jacuzzi_thermal_capacity` | C_water in kWh/°C |
| `jacuzzi_current_k` | Active heat loss coefficient based on outdoor temp band |
| `jacuzzi_current_heat_loss_kw` | Instantaneous heat loss (kW) |
| `jacuzzi_net_heating_rate` | Rate of temperature change (°C/h) |
| `jacuzzi_max_achievable_temp` | Equilibrium temperature (°C) |
| `jacuzzi_standby_loss_rate` | Cooling rate when idle (°C/h) |
| `jacuzzi_predicted_temp_at_event` | Projected temperature at next calendar event |
| `jacuzzi_thermal_model_status` | bootstrapping / learning / calibrated |
| `jacuzzi_heat_up_time_required` | **Replaced** — now uses physics integral formula |
| `jacuzzi_smart_start_time` | **Replaced** — reads corrected heat-up time, adds achievability check |

### Part 1C: Adaptive Feedback Automations

**File:** `automations/jacuzzi/jacuzzi_automations.yaml`

| ID | Alias | Purpose |
|----|-------|---------|
| `auto_jacuzzi_095` | Thermal Model Update | 15-min observation loop. Heating: learns P_net via EWM. Cooling: learns k per temp band via EWM. Skips if duration <0.1h or >2h, or heater state changed mid-interval. |
| `auto_jacuzzi_096` | Thermal Model Reset Sample | Resets observation window immediately when heater transitions between heating/idle. |

---

## Task 2: EV Calendar Sync Today/Tomorrow Split

### Bug Report

Fraser received "Take **None** (80%)" departure notification on a Sunday morning when he had a valid trip.

### Root Cause Chain

1. Saturday 20:00: Calendar sync queries Sunday → `km_tomorrow=180`, `departure=Sunday 08:30`
2. Sunday 00:00: Daily reset clears `km_tomorrow=0`
3. Sunday 07:00: Calendar sync queries Monday (tomorrow) → `km_tomorrow=0`
4. Planner triggers: `km=0` → `assigned_car=None`
5. Sunday 08:00: Departure reminder fires with `assigned_car=None`

### Fix: Today/Tomorrow Data Split

**New helpers** (`packages/ev_system.yaml`):
- `input_number.ev_trip_km_fraser_today`
- `input_number.ev_trip_km_heather_today`

**Calendar sync** (`auto_ev_010`) restructured:
- Queries BOTH today and tomorrow for each driver
- Today section: computes trip km via Waze, sets departure time (only for future events)
- Tomorrow section: computes trip km + full legs/stops/JSON (for overnight planning)
- Tomorrow departure time only set if today has no future trip (prevents overwrite)

**Daily reset** (`auto_ev_002`):
- At midnight: copies `_tomorrow` km → `_today` km **before** clearing tomorrow

**Planner** (`auto_ev_030`):
- Reads both `_today` and `_tomorrow` km
- Uses `today if today > 0 else tomorrow` — morning: uses today (correct), evening: uses tomorrow (planning)
- Triggers on both `_today` and `_tomorrow` changes

**Departure reminders** (`auto_ev_061`, `auto_ev_062`):
- Added safety guard: `assigned_car not in ['None', 'none', 'unavailable', 'unknown']`
- Moved `assigned_car` variable before `should_fire` so it can be referenced

**Morning SOC check** (`auto_ev_064`):
- Condition changed from `_tomorrow > 0` to `_today > 0`

**Morning summary** (`energy_notification_automations.yaml`, `auto_energy_062`):
- Uses `_today` km for display

**EV demand scenario** (`energy_shared_sensors.yaml`):
- Uses `today if today > 0 else tomorrow` for trip detection

**Diagnostic dump** (`ev_scripts.yaml`, `ev_dump_state`):
- Shows both today and tomorrow km

---

## Validation Checklist

- [x] yamllint passes on all modified files
- [x] No remaining references to `start_iso` / `end_iso` in ev_010
- [x] All `_today` helpers defined in ev_system.yaml
- [x] Daily reset copies `_tomorrow` → `_today` before clearing
- [x] Planner uses today-first-else-tomorrow logic
- [x] Departure reminders guard against None car
- [x] Morning automations (064, energy 062) use `_today`
- [x] Orchestrator demand sensor uses today-first logic
- [x] Physics-based heat-up time uses integral formula
- [x] Adaptive model has EWM learning with sanity bounds
- [x] Thermal model status reflects observation count
