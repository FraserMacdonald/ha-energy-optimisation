# Phase 1D – Notification Implementation

**Date:** 2026-02-06
**Depends on:** Phase 1A–1D complete

## Overview

Comprehensive notification system across all three subsystems: jacuzzi, EV, and energy orchestrator. Includes a critical bug fix, 23 new notification automations in 3 new files, and enhancements to 3 existing notifications.

## Critical Bug Fix

**File:** `templates/jacuzzi/jacuzzi_sensors.yaml`

`sensor.jacuzzi_heat_up_time_required` was calculating temperature difference using `input_number.jacuzzi_target_temp` (which holds the standby temp ~30°C until an automation changes it). This caused `sensor.jacuzzi_smart_start_time` to always underestimate heating time.

**Fix:** Hardcoded target to 40°C (the event temperature). Added `calculation_breakdown` attribute showing the full calculation chain.

## Notification Targets

| Target | Service |
|--------|---------|
| Fraser | `notify.mobile_app_fraser_s_iphone` |
| Heather | `notify.mobile_app_heather_s_iphone` |
| Both | Call both services |
| Dashboard | `persistent_notification.create` |
| Logbook | `logbook.log` |

## iOS Push Priority

| Level | Use case |
|-------|----------|
| `critical` | Freeze protection, safety only |
| `time-sensitive` | Won't be ready, morning SOC short, feasibility warning |
| normal (default) | Everything else |

## New Files Created

### 1. `automations/jacuzzi/jacuzzi_notification_automations.yaml`

| ID | Alias | Code | Trigger | Target |
|----|-------|------|---------|--------|
| auto_jacuzzi_062_daily_plan | Jacuzzi 062 – Daily Plan | P1 | Calendar event or 07:00 | Both |
| auto_jacuzzi_063_feasibility_warning | Jacuzzi 063 – Feasibility Warning | P2 | Smart start past or time short | Both (time-sensitive) |
| auto_jacuzzi_064_heating_started | Jacuzzi 064 – Heating Started | A1 | Target temp rises to 40 | Both |
| auto_jacuzzi_065_source_changed | Jacuzzi 065 – Source Changed | A2 | Solar crosses 3500W while heating | Fraser |
| auto_jacuzzi_066_progress_update | Jacuzzi 066 – Progress Update | R1 | /30 time pattern while heating | Fraser |
| auto_jacuzzi_067_halfway | Jacuzzi 067 – Halfway | R2 | Temp crosses midpoint | Both |
| auto_jacuzzi_068_wont_be_ready_60 | Jacuzzi 068 – Won't Be Ready (60 min) | X1 | 60 min before event, temp < 37 | Both (time-sensitive) |
| auto_jacuzzi_069_pipe_cycling_notify | Jacuzzi 069 – Pipe Cycling Notify | X4 | 091 fires | Fraser |
| auto_jacuzzi_070_rate_anomaly | Jacuzzi 070 – Rate Anomaly | X9 | /30, rate < 70% expected | Fraser |
| auto_jacuzzi_071_session_over | Jacuzzi 071 – Session Over | C2 | Calendar event ends | Fraser |

### 2. `automations/ev/ev_notification_automations.yaml`

| ID | Alias | Code | Trigger | Target |
|----|-------|------|---------|--------|
| auto_ev_065_solar_charge_started | EV 065 – Solar Charge Started | A4 | Allow charging boolean turns on | Driver |
| auto_ev_066_solar_charge_stopped | EV 066 – Solar Charge Stopped | A5 | Allow charging boolean turns off | Driver |
| auto_ev_067_night_charge_started | EV 067 – Night Charge Started | A6 | Charge switch on during low tariff | Fraser |
| auto_ev_068_night_charge_complete | EV 068 – Night Charge Complete | A7 | SOC reaches target during low tariff | Both |
| auto_ev_069_charging_progress | EV 069 – Charging Progress | R3 | /30 while charging | Driver |
| auto_ev_077_trip_complete | EV 077 – Trip Complete | C4 | Device tracker → home | Fraser |

### 3. `automations/energy/energy_notification_automations.yaml`

| ID | Alias | Code | Trigger | Target |
|----|-------|------|---------|--------|
| auto_energy_062_morning_summary | Energy 062 – Morning Summary | P4 | 07:00 | Fraser |
| auto_energy_063_decision_change | Energy 063 – Decision Change | A8 | Decision sensor changes (5min cooldown) | Fraser |
| auto_energy_064_mode_changed | Energy 064 – Mode Changed | A9 | Orchestrator enabled toggle | Both |
| auto_energy_065_conflict_detail | Energy 065 – Conflict Detail | X7 | Both loads + production 1/2 | Fraser |
| auto_energy_066_surplus_wasted | Energy 066 – Surplus Wasted | X8 | Surplus > 3000W for 30min unused | Fraser |
| auto_energy_067_daily_summary | Energy 067 – Daily Summary | S1 | 21:00 | Fraser + dashboard |
| auto_energy_068_weekly_summary | Energy 068 – Weekly Summary | S2 | Sunday 20:00 | Fraser + dashboard |

## Helpers Added

**File:** `packages/energy_orchestrator_system.yaml`

| Entity | Type | Purpose |
|--------|------|---------|
| `input_number.energy_jacuzzi_heating_start_temp` | number (0-45) | Records temp when heating starts (for halfway calc) |
| `input_number.energy_jacuzzi_last_progress_temp` | number (0-45) | Records temp at last progress check (for rate calc) |
| `input_datetime.energy_jacuzzi_last_progress_time` | datetime | Records time of last progress check |

## Existing Notification Enhancements

### auto_jacuzzi_060_event_reminder

**Before:** Generic `notify.notify` with simple message.
**After:** Sends to both users via specific mobile services. Message includes heating start temp, source (solar/tariff/grid), and event time.

### auto_jacuzzi_061_not_ready_warning

**Before:** Generic `notify.notify` with estimated heat minutes.
**After:** Sends to both users with `time-sensitive` priority. Message includes actual heating rate, ETA time, and minutes late.

### auto_ev_064_morning_soc_check

Already had `interruption-level: time-sensitive` — no changes needed.

## Validation Checklist

- [ ] yamllint passes on all new and modified files
- [ ] Heat-up time sensor uses hardcoded 40°C (not input_number.jacuzzi_target_temp)
- [ ] Smart start time reads corrected heat-up sensor
- [ ] P1: Daily plan fires at 07:00 with event today
- [ ] P2: Feasibility warning fires when not enough time
- [ ] A1: Heating started records start temp in helper
- [ ] R1: Progress update shows delta and on-track status
- [ ] R2: Halfway fires at midpoint between start and 40
- [ ] X1: 60-min warning fires with time-sensitive priority
- [ ] X9: Rate anomaly fires when actual < 70% expected
- [ ] A4/A5: Solar charge start/stop routes to correct driver
- [ ] A6/A7: Night charge notifications fire during low tariff
- [ ] R3: Charging progress routes to correct driver
- [ ] C4: Trip complete fires when car arrives home
- [ ] P4: Morning summary includes all systems
- [ ] A8: Decision change has 5-minute cooldown
- [ ] X7: Conflict detail shows priority winner
- [ ] X8: Surplus wasted has 2-hour cooldown
- [ ] S1/S2: Summaries create persistent notifications
- [ ] Enhanced 060: Shows source and start temp
- [ ] Enhanced 061: Shows rate, ETA, and minutes late
