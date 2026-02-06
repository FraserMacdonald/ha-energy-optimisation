# Phase 1C – Energy Orchestrator (Stage 1: Shadow Mode)

**Date:** 2026-02-06
**Branch:** `feature/phase-1c-orchestrator`
**Depends on:** Phase 1A (complete), Phase 1B shared sensors (complete)

## Overview

Stage 1 deploys the energy orchestrator in **shadow mode**. It evaluates scenario sensors every 30 seconds, applies the priority queue algorithm from the architectural review (section 5.2), sets output helpers, and logs decisions. Existing jacuzzi and EV automations continue to operate independently — the orchestrator does not control them yet.

The purpose of shadow mode is to validate the orchestrator's decisions against real-world conditions before wiring it into subsystem control in Stage 2.

## Files Created

| File | Purpose |
|------|---------|
| `packages/energy_orchestrator_system.yaml` | Output helpers (3 booleans, 1 number, 1 text store) |
| `automations/energy/energy_orchestrator_automations.yaml` | 3 automations (evaluate, log, conflict alert) |
| `templates/energy/energy_shared_sensors.yaml` | Added `sensor.energy_orchestrator_decision` (sensor #7) |

## Files Modified

| File | Change |
|------|--------|
| `configuration.yaml` | Uncommented `energy_orchestrator` package include |

## Output Helpers

| Entity | Type | Purpose |
|--------|------|---------|
| `input_boolean.energy_jacuzzi_heat_allowed` | boolean | Orchestrator grants/denies jacuzzi heating |
| `input_boolean.energy_ev_solar_charge_allowed` | boolean | Orchestrator grants/denies EV solar charging |
| `input_boolean.energy_ev_tariff_charge_allowed` | boolean | Orchestrator grants/denies EV low-tariff charging |
| `input_number.energy_ev_max_solar_amps` | number (0–32 A) | Max amps EV may draw during solar charging |
| `input_select.energy_last_decision` | select (text store) | Audit trail: scenario code + action + timestamp |

**Note:** `energy_last_decision` uses `input_select` with `set_options` (not `input_text`) because `input_text` was removed in HA 2026. This follows the same pattern as `ev_last_planner_decision` in the EV system.

## Automations

### auto_energy_001_evaluate_scenario — Energy 001 – Evaluate Scenario

**Trigger:** Time pattern, every 30 seconds.
**Condition:** All three scenario sensors available (not unknown/unavailable).

**Algorithm (priority queue from arch review section 5.2):**

1. Read scenario inputs:
   - `sensor.energy_production_scenario` (1/2/3)
   - `sensor.energy_jacuzzi_demand_scenario` (A/B/C/D/E)
   - `sensor.energy_ev_demand_scenario` (X/Y/idle)
   - `sensor.energy_solar_surplus_w`
   - `binary_sensor.energy_low_tariff_active`

2. Compute jacuzzi decision (priority order):
   - State E (no demand) → deny
   - State A (freeze, Tier 1) → always allow (grid fallback)
   - Surplus covers both loads → allow (no conflict)
   - Surplus covers jacuzzi AND jacuzzi has equal/higher priority → allow solar
   - State D (imminent, Tier 2) AND low tariff → allow (tariff fallback)
   - Otherwise → deny

3. Compute EV decisions:
   - Solar: deduct jacuzzi from surplus if jacuzzi has priority and is solar-powered; allow if remaining surplus covers min EV watts
   - Tariff: allow if state X (trip-critical)
   - Amps: calculate from EV's available surplus, clamped between min and max charger amps

4. Set all output helpers and log the decision.

### auto_energy_060_decision_log — Energy 060 – Decision Logger

**Trigger:** State change on `sensor.energy_orchestrator_decision`.
**Action:** Writes to HA logbook with entity attribution.

### auto_energy_061_conflict_alert — Energy 061 – Conflict Alert

**Trigger:** State change on any of the three scenario sensors.
**Condition:** Both jacuzzi and EV have active demand, AND production scenario is 1 or 2 (insufficient solar for both).
**Action:** Creates/updates a persistent notification (`notification_id: energy_orchestrator_conflict`) with scenario details.

## Template Sensor Added

### sensor.energy_orchestrator_decision

Human-readable string combining the scenario code with the orchestrator's recommended action.

**State format:** `{prod}-{jac}-{ev}: {action summary}`
**Examples:**
- `2-D-X: Heat jacuzzi, EV solar@8A`
- `1-E-Y: EV solar@12A`
- `3-B-idle: Heat jacuzzi`
- `1-E-idle: No action`

**Attributes:** `scenario_code`, `jacuzzi_allowed`, `ev_solar_allowed`, `ev_tariff_allowed`, `ev_max_solar_amps`, `last_decision`

## Priority Tier Reference

| Tier | Priority | Jacuzzi State | EV State | Power Source |
|------|----------|---------------|----------|--------------|
| 1 | Critical | A (freeze <5 C) | X (trip-critical) | Grid if needed |
| 2 | Time-sensitive | D (event imminent) | — | Solar preferred, low-tariff grid |
| 3 | Opportunistic | B (standby), C (event <24h) | Y (top-up) | Solar only |
| 99 | No demand | E (satisfied) | idle | — |

## Validation Checklist

- [ ] All three scenario sensors reporting (not unknown)
- [ ] `sensor.energy_orchestrator_decision` shows reasonable scenario code
- [ ] Output helpers changing in response to scenarios
- [ ] `input_select.energy_last_decision` updates every 30 seconds
- [ ] Logbook shows orchestrator entries (search "Energy Orchestrator")
- [ ] Conflict alert fires when both loads active with insufficient solar
- [ ] Existing jacuzzi and EV automations still work independently
- [ ] Compare orchestrator decisions against the 45-scenario matrix (arch review section 5.3)

## Stage 2 – Wired Mode

**Date:** 2026-02-06

### Overview

Stage 2 wires the orchestrator into existing subsystem automations via a master enable switch (`input_boolean.energy_orchestrator_enabled`). When the switch is OFF (default), all automations behave exactly as before (legacy mode). When ON, the orchestrator gates solar/tariff decisions.

**No automations were disabled or deleted.** The orchestrator adds a condition layer — it does not replace existing logic.

### Master Switch

| Entity | Default | Purpose |
|--------|---------|---------|
| `input_boolean.energy_orchestrator_enabled` | OFF | Legacy mode (off) = all systems independent. Orchestrator mode (on) = orchestrator gates solar/tariff access. |

Added to `packages/energy_orchestrator_system.yaml`.

### Gate Pattern

Every modified automation uses the same OR condition:

```yaml
# Orchestrator gate: legacy mode (off) OR orchestrator grants permission
- condition: or
  conditions:
    - condition: state
      entity_id: input_boolean.energy_orchestrator_enabled
      state: "off"
    - condition: state
      entity_id: input_boolean.energy_jacuzzi_heat_allowed  # (or ev_ variant)
      state: "on"
```

This means: **orchestrator OFF = pass through** (legacy), **orchestrator ON = check permission**.

### Modified Automations

#### Jacuzzi

| Automation | Change |
|------------|--------|
| `auto_jacuzzi_020_solar_opportunistic` | Added orchestrator gate (`energy_jacuzzi_heat_allowed`) to conditions |
| `auto_jacuzzi_021_low_tariff_heating` | Added orchestrator gate (`energy_jacuzzi_heat_allowed`) to conditions |
| `auto_jacuzzi_040_calendar_scheduler` | Added orchestrator gate to both `set 40°C` branches (preheat window + event ongoing). Standby/default branch unaffected. |

#### EV

| Automation | Change |
|------------|--------|
| `auto_ev_040_solar_charging` | Added orchestrator gate (`energy_ev_solar_charge_allowed`) to conditions. When orchestrator enabled, `target_amps` capped to `energy_ev_max_solar_amps` instead of hardcoded 16A. |
| `auto_ev_041_cheap_tariff` | Added orchestrator gate (`energy_ev_tariff_charge_allowed`) to the "should charge" choose branch. Stop-charging branches unaffected. |

### EV Solar Amps Capping (ev_040)

When the orchestrator is enabled, `ev_040` reads `input_number.energy_ev_max_solar_amps` as the upper bound for charging current instead of the hardcoded 16A. The orchestrator calculates this value based on available surplus after jacuzzi allocation, clamped between `ev_min_amps` and `ev_charger_max_amps`.

When the orchestrator is disabled (legacy mode), the original hardcoded 16A cap applies.

### Validation Checklist – Stage 2

- [ ] Turn orchestrator OFF: verify all 5 automations work exactly as before
- [ ] Turn orchestrator ON: verify jacuzzi 020/021 respect `energy_jacuzzi_heat_allowed`
- [ ] Turn orchestrator ON: verify jacuzzi 040 preheat respects orchestrator permission
- [ ] Turn orchestrator ON: verify EV 040 solar amps capped to `energy_ev_max_solar_amps`
- [ ] Turn orchestrator ON: verify EV 041 tariff charging respects `energy_ev_tariff_charge_allowed`
- [ ] Verify no automations were disabled or deleted
- [ ] Compare behaviour with orchestrator ON vs OFF during solar surplus
- [ ] Check logbook for correct orchestrator decisions matching actual automation behaviour
