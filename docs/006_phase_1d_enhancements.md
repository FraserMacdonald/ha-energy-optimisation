# Phase 1D – Enhancements

**Date:** 2026-02-06
**Branch:** `feature/phase-1d-enhancements`
**Depends on:** Phase 1A–1C complete

## Overview

Four targeted enhancements to improve safety, user experience, and efficiency. Three new automations plus one modification to an existing automation.

## 1. Jacuzzi Pipe Freeze Pump Cycling

**Automation:** `auto_jacuzzi_091_pipe_freeze_cycling`
**File:** `automations/jacuzzi/jacuzzi_automations.yaml`

**Problem:** In extreme cold, water in jacuzzi pipes can freeze even when the main body is above 5°C (the existing freeze protection threshold). Pipes are exposed and cool faster than the insulated tub.

**Solution:** When outdoor temperature (`sensor.la_dole_temperature`) drops below 0°C and the jacuzzi is in standby (not actively heating for an event), cycle the pump for 5 minutes every 30 minutes by temporarily raising the target temperature.

**Safety classification:** Tier 0 — bypasses the orchestrator entirely. The `jacuzzi_automation_enabled` switch is still respected for emergency shutdown capability.

**Trigger:** `time_pattern: /30`
**Conditions:** Automation enabled, outdoor < 0°C, target at standby (not heating)
**Actions:** Raise target to `max(current_temp + 2, standby_temp)` for 5 minutes, then restore standby.

## 2. Jacuzzi Not Ready Warning

**Automation:** `auto_jacuzzi_061_not_ready_warning`
**File:** `automations/jacuzzi/jacuzzi_automations.yaml`

**Problem:** The existing `jacuzzi_060_event_reminder` only notifies when the jacuzzi IS ready. If it's not ready 30 minutes before an event, the user gets no warning.

**Solution:** Companion to 060 that fires under the inverse condition (temp < 38°C). Includes the current temperature and estimated time to ready from `sensor.jacuzzi_heat_up_time_required`.

**Trigger:** Template — 30 minutes before calendar event (same trigger as 060)
**Condition:** Water temperature < 38°C
**Action:** Notification with current temp and estimated heating time

## 3. Solar Off Fallback

**Automation:** `auto_jacuzzi_022_solar_off_fallback`
**File:** `automations/jacuzzi/jacuzzi_automations.yaml`

**Problem:** When `jacuzzi_020` starts solar opportunistic heating and then clouds roll in, the jacuzzi continues heating on grid power (expensive and wasteful). There's no mechanism to revert when solar disappears.

**Solution:** Monitors `sensor.energy_solar_surplus_w` and reverts to standby if surplus drops below 3500W for more than 10 minutes while the jacuzzi is actively heating.

**Safety guard:** Does NOT revert during calendar-driven preheat windows. Checks `sensor.jacuzzi_smart_start_time` to distinguish between solar-opportunistic and calendar-scheduled heating.

**Trigger:** `sensor.energy_solar_surplus_w` below 3500 for 10 minutes
**Conditions:** Automation enabled, solar priority on, target at 40°C, NOT in calendar preheat window
**Action:** Set target back to standby temperature

## 4. EV Climate Optimization

**Automation:** `auto_ev_050_climate_prep` (modified)
**File:** `automations/ev/ev_automations.yaml`

**Problem:** The original 1-minute `time_pattern` trigger fires 1440 times/day. Each evaluation reads Tesla sensor values which can wake the car from sleep, draining the 12V battery and increasing API rate limit usage.

**Solution:**
1. Replaced `/1` time_pattern with a **departure proximity template trigger** (fires when any departure enters the 45-minute window) plus a `/5` time_pattern for re-evaluation during the window
2. Added a **condition** that gates the `/5` trigger — only processes when a departure is within 45 minutes
3. Widened fire windows from 60s to 300s (matching the 5-minute check interval)
4. Changed mode from `parallel: 4` to `single` (both drivers handled in same run)

**Impact:** Reduces evaluations from ~1440/day to ~18/day (only during the 45-minute pre-departure windows). Tesla API wake-ups drop proportionally.

**Fire window change:**
- Before: `now_ts >= defrost_ts and now_ts < (defrost_ts + 60)` (1-minute window)
- After: `now_ts >= defrost_ts and now_ts < (defrost_ts + 300)` (5-minute window)

The `last_defrost_ts` / `last_preheat_ts` guards still prevent duplicate firings within the same departure.

## Files Modified

| File | Change |
|------|--------|
| `automations/jacuzzi/jacuzzi_automations.yaml` | Added 022, 061, 091 (3 new automations) |
| `automations/ev/ev_automations.yaml` | Modified 050 (trigger, condition, fire windows, mode) |

## Files Created

| File | Purpose |
|------|---------|
| `docs/006_phase_1d_enhancements.md` | This file |

## Validation Checklist

- [ ] `jacuzzi_091`: Verify pump cycles when outdoor < 0°C and jacuzzi in standby
- [ ] `jacuzzi_091`: Verify it does NOT fire when jacuzzi is actively heating (target 40°C)
- [ ] `jacuzzi_061`: Verify notification fires 30 min before event when temp < 38°C
- [ ] `jacuzzi_061`: Verify it does NOT fire when temp >= 38°C (060 handles that)
- [ ] `jacuzzi_022`: Verify fallback triggers when solar drops below 3500W for 10 min
- [ ] `jacuzzi_022`: Verify it does NOT revert during a calendar preheat window
- [ ] `ev_050`: Verify climate prep only evaluates within 45 min of departure
- [ ] `ev_050`: Verify defrost fires ~30 min before departure when temp < 0°C
- [ ] `ev_050`: Verify preheat fires ~15 min before departure
- [ ] `ev_050`: Verify no duplicate firings (last_defrost/preheat guards)
- [ ] yamllint passes on all modified files
