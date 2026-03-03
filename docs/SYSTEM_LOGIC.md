# How The Energy System Works

This document describes every decision the system makes, from the top-level triggers down to the individual actions. Written for Fraser and Heather — no YAML, no code.

---

## The Big Picture

Every 30 seconds, the **Energy Orchestrator** looks at three things:

1. **What does the jacuzzi need?** (freeze protection / standby heating / event heating / nothing)
2. **What do the cars need?** (trip-critical charge / top-up / nothing)
3. **What power is available?** (solar surplus / low tariff grid / high tariff grid)

It then walks down a priority list, giving power to the most important thing first, then the next, and so on until everything is served or power runs out.

---

## Tariff Schedule

| When | Rate | Name |
|------|------|------|
| Mon–Fri 17:00–22:00 | 0.38 CHF/kWh | **High** (peak) |
| All other hours | 0.26 CHF/kWh | **Low** (off-peak) |
| Solar used instead of exported | 0.06 CHF/kWh | **Opportunity cost** |

**Key rule:** The system avoids using grid power during peak hours unless there's a safety reason or enough solar to make it worthwhile.

---

## Priority Waterfall

Power is allocated in this strict order. Higher tiers always get served first.

### Tier 0 — Safety (always, any power source)

- Jacuzzi water below 5°C → heat immediately (freeze protection)
- Any car below 10% SOC → charge immediately
- Greenhouse lights on during photoperiod

These override everything. They don't "use up" solar — they just happen.

### Tier 1 — Trip-Critical EV Charging

**When:** A driver has a trip in the next 48 hours and their assigned car doesn't have enough charge to make it.

- Uses solar if available (needs at least 3,450W to start the charger)
- **Also uses grid at any tariff** — getting to a trip on time is more important than saving money
- Whatever solar this tier uses is subtracted from what's available for lower tiers

### Tier 2 — Home Battery Evening Charge (future, not yet installed)

Placeholder for when a home battery is added.

### Tier 3 — Jacuzzi Event Heating

**When:** There's a jacuzzi calendar event within 48 hours and the water is below 39.5°C.

- Uses any solar surplus (even 500W helps — partial solar + grid is cheaper than pure grid)
- Grid rules during different tariffs:
  - **Low tariff:** grid allowed
  - **High tariff:** grid allowed ONLY if:
    - The event is happening right now and the water is dropping below 39°C, OR
    - There's at least 2,250W of solar (blended cost is then cheaper than waiting for low tariff)
  - **Otherwise during peak:** wait — don't heat on expensive grid alone

### Tier 4 — Greenhouse Dimming (future placeholder)

### Tier 5 — Car Buffer Charging (top-up to 80%)

**When:** A car is plugged in at home and below its charge limit (80%), but there's no urgent trip need.

- Uses leftover solar (after jacuzzi event gets its share)
- Grid only during low tariff
- This is the "fill up when it's cheap" tier

### Tier 6 — Jacuzzi Standby / Banking

**When:** No event coming, but the water has dropped below the current standby target (which might be elevated by banking or boost mode).

- Uses leftover solar
- Grid only during low tariff
- Lower priority than event heating or car charging

### Tier 7 — Home Battery Additional (future)

### Tier 8 — Export

Whatever solar is left goes to the grid at 0.06 CHF/kWh.

---

## Jacuzzi Decision Logic

### What temperature is the system trying to maintain?

The **effective standby temperature** is chosen by priority:

1. **Banking target** (e.g. 35°C) — if the banking calculator has determined it's worth pre-heating for an upcoming event during cheap energy. During peak hours, this drops to banking minus 2°C to avoid wasting expensive grid power.

2. **Boosted standby** (34°C) — if the boost toggle is on and cheap energy is available (solar > 500W or low tariff).

3. **Normal standby** (20°C) — the default idle temperature.

4. **Readiness floor** — if the physics model calculates that the water must be above a certain temperature to guarantee reaching 40°C within the maximum heat-up window (6 hours), this overrides everything above. This prevents a situation where the water cools so much overnight that 40°C becomes unreachable.

The system always picks the highest applicable value.

### When does heating start for an event?

The **smart start time** is calculated in three steps:

1. **Base calculation:** Event time minus heating duration minus 30-minute buffer. The heating duration comes from the physics model (not a fixed rate — it accounts for outdoor temperature, learned heater power, and thermal losses).

2. **Solar delay:** If solar priority is on and the event is more than 8 hours away, and the calculated start is before 9:00 AM, push it to 9:00 AM. Why waste grid power at 4 AM when the sun will be helping at 9?

3. **Peak avoidance:** If the calculated start falls during Mon–Fri 17:00–22:00, shift it earlier so heating completes by 17:00. Better to start at 14:00 on low tariff than at 18:00 on high tariff.

### What triggers jacuzzi heating?

| Automation | Trigger | What it does |
|---|---|---|
| **040 — Calendar Scheduler** | Every 5 min + calendar changes | Main controller. If we're in the smart-start window: heat to 40°C (unless peak with no solar, then wait). If event is happening now: maintain 40°C. Otherwise: revert to effective standby. |
| **020 — Solar Opportunistic** | Solar available for 5 min, or low tariff starts | If solar is available and there's an event within 48h and water < 38°C: heat to 40°C. If low tariff and water is below standby: heat to standby. Blocked during peak unless solar > 2,250W. |
| **021 — Low Tariff Standby** | Low tariff starts, or every 15 min | If water is below effective standby and it's low tariff: heat to standby. |
| **022 — Solar Off Fallback** | Solar drops below 500W for 10 min | If we were heating to 40°C on solar and it drops: during low tariff, keep going (grid is cheap). During peak, revert to standby (don't pay 0.38/kWh). Does NOT revert if we're in the smart-start window or during an event. |
| **041 — Heating Persistence** | Every 2 min when target is 40°C | If the Balboa controller drops out of heat mode while we're trying to reach 40°C: force it back on. Safety net for unreliable hardware. |
| **001 — Temperature Loop** | Every 2 min + temp/target changes | Basic thermostat: if water < target - 0.5°C, heat. If water ≥ target, stop. |

### Safety automations

| Automation | Trigger | What it does |
|---|---|---|
| **090 — Freeze Protection** | Water drops below 5°C | Heat to 10°C immediately. Alerts both users. |
| **091 — Pipe Freeze Cycling** | Every 30 min when outdoor < 0°C | If the jacuzzi is just sitting at standby (not heating for an event), bump the target up 2°C for 5 minutes to cycle the pump and prevent pipe freeze. |

### How does the system learn?

Every 15 minutes (**automation 095**), the thermal model takes a reading:

- **When heating:** Measures how fast the water is warming. Calculates the effective heater power (accounting for heat losses to the air). Updates the learned power value, nudging 10% toward the new observation.

- **When idle and cooling:** Measures how fast the water is losing heat. Calculates the heat loss coefficient for the current outdoor temperature band (cold/mild/warm). Updates the learned coefficient, nudging 10% toward the new observation.

This means the system gets more accurate over time. After about 20 heating observations and 20 cooling observations, it's considered "calibrated."

---

## EV Decision Logic

### How does the system know what trips are coming?

**EV 010 — Calendar Sync** runs at 07:00, 14:00, 20:00, and whenever a calendar changes.

For each driver (Fraser and Heather):
1. Fetches all calendar events with a location in the next 48 hours
2. Builds a driving route: home → event 1 → home (overnight) → event 2 → home
3. **Overnight return-home rule:** If two events are on different calendar dates, the system assumes you drive home between them. Exception: a multi-day event (e.g. Monday 09:00 – Tuesday 17:00) bridges without a return home.
4. Calls Waze for each leg to get real driving distance and time
5. Stores total 48-hour km and first departure time

### How are cars assigned to drivers?

**EV 030 — Planner** runs when trip data changes, at 06:00/14:00/20:30, or when Fraser manually selects a car.

**Manual override:** If Fraser selects a car on the dashboard, he gets it. Heather gets the other one. The override clears after one use.

**Automatic optimisation:** The planner tests two scenarios:
- **A:** Horace takes the longer trip, Horatio takes the shorter one
- **B:** The reverse

For each scenario, it calculates whether either car would need overnight charging, and how far each car would be from a comfortable margin (25% SOC) after the trip. It picks the scenario that either needs no charging, or has the smallest shortfall.

The car with the largest deficit becomes the **night charge car** — the one that gets plugged in overnight.

If the total charging needed exceeds what one night can deliver (88 kWh = 11kW for 8 hours), the system flags that external charging (e.g. at a public charger) is required.

### When do the cars charge?

| Automation | When it runs | What it does |
|---|---|---|
| **041 — Overnight Charging** | Every 10 min during low tariff | Charges the planner's chosen car to the target SOC. Wakes the Tesla, checks the plug, sets the charge limit on the car (so it stops itself at the target), then turns on the charge switch. |
| **040 — Solar Charging** | Solar power or plug changes | Matches available solar surplus to charging amps. Trip-critical cars get max amps regardless. Normal top-up gets whatever amps the sun provides (minimum 5A to start). During low tariff with demand but no sun: charges at minimum amps. |
| **044 — Maintenance Charging** | Every 30 min + when peak starts | Keeps at least one car charged. **Blocked during peak** (Mon–Fri 17:00–22:00) unless a car is below 10% (critical). Skips waking cars if any home car is already above 50%. Picks the car closest to 50% (fastest path to readiness). Charges to 80%. |

**Priority order:** Trip-critical (any tariff) > overnight planner (low tariff) > solar surplus > maintenance buffer (low tariff only)

### What about the plug-in reminders?

The system tries to make sure a car is always plugged in:

| Automation | Trigger | Who gets notified |
|---|---|---|
| **EV 030 plug-in** | Planner decides a car needs overnight charging | Fraser always, Heather if at home |
| **EV 044 nag** | Maintenance check finds unplugged car below 50% | Fraser (if home), Heather (if home). Suppressed if another car is already above 50%. |
| **080 — Always Plugged** | Every 30 min, both home cars unplugged | Both (if home). Suppressed if any home car ≥ 50% and no car < 10%. |
| **081 — Arrival Reminder** | Car arrives home, still unplugged after 10 min | The driver who owns the car |
| **082 — Unexpected Disconnect** | Car is unplugged while below target | Fraser (time-sensitive) |

### SOC tracking and trip accuracy

**EV 020 — SOC Tracker** (every 30 min):
- Reads each car's battery level from Tesla
- If the car is away from home: estimates what SOC it will have when it returns (using Waze distance + energy consumption rate)
- Detects external charging: if SOC jumped up while the car was away and not plugged in at home, someone charged it elsewhere

**EV 045 — Consumption Correction** (when a car returns home):
- Compares predicted vs actual SOC drop for the trip
- Nudges the correction factor 10% toward reality (clamped to 0.5–2.0x)
- Over time, trip predictions become more accurate

### Climate prep (defrost and preheat)

**EV 050** watches for departure times approaching:
- **30 minutes before departure** (if outdoor < 0°C): Turns on defrost
- **15 minutes before departure**: Sets cabin to 21°C

Only fires if the car is at home. Re-evaluates every 5 minutes.

---

## Solar Forecast and Banking

### Forecast pipeline

| Time | What happens |
|---|---|
| Every 30 min (04:00–22:00) | **020:** Predict solar production for next 48h using sun position + Met.no cloud forecast |
| Every 30 min | **021:** Log actual production from SolarEdge |
| :05 past each hour (05:00–22:00) | **022:** Compare prediction vs actual for this hour |
| Sunday 23:30 | **023:** Weekly calibration — nudge the model's calibration factor toward reality |
| Every 30 min | **024:** Banking calculator (see below) |

### How banking works

The banking calculator looks at the next jacuzzi event (up to 48 hours away) and asks: *"Is it cheaper to pre-heat the water now while energy is cheap, even though we'll lose some heat before the event?"*

1. Builds an hourly timeline from now to the event
2. Marks each hour as "cheap" (solar forecast > 6kW or low tariff) or "expensive" (peak grid)
3. Works backward from the event: starting at 40°C, calculates how much the water cools during expensive gaps (when we don't want to heat)
4. Determines what temperature we'd need to reach during cheap hours so that after cooling through the expensive gaps, we still arrive at 40°C
5. Checks the cost: only pre-heats if the cheap energy cost is less than what we'd pay heating through the expensive period
6. Caps the banking target at 37°C (diminishing returns above this — heat losses accelerate)

The banking target feeds into the effective standby temperature, which the jacuzzi automations then maintain automatically.

---

## Notifications

### Who gets what

**Both Fraser and Heather receive:**
- Jacuzzi ready / not ready / feasibility warnings
- Jacuzzi heating started / halfway / won't be ready
- EV night charge started / complete
- EV morning briefing (personalised per driver)
- Orchestrator mode changes

**Fraser only receives:**
- Jacuzzi progress updates (hourly), rate anomalies, session over
- Energy morning/daily/weekly summaries
- Conflict alerts, surplus wasted alerts
- Unexpected EV disconnect
- All orchestrator-level decisions

**Heather receives (when relevant):**
- EV plug-in reminders (when she's at home)
- EV charging updates for her assigned car
- Morning briefing with her trip details and plug-in warnings

**Personalised EV notifications** (solar charge start/stop, target reached, charging ended) go to whichever driver is assigned to that car.

### Notification timing

| Notification | When |
|---|---|
| Morning briefing | 06:30 |
| Energy morning summary | 07:00 |
| Departure reminders | As departure time approaches |
| Jacuzzi daily plan | When calendar event detected or 07:00 |
| Jacuzzi 30-min warnings | 30 minutes before event |
| Jacuzzi 60-min warning | 60 minutes before event (only if temp < 37°C) |
| Evening trip digest | 20:00 |
| Daily summary | 21:00 |
| Weekly summary | Sunday 20:00 |
| Plug-in nags | Every 30 minutes (with suppression logic) |

### Suppressed / disabled notifications

- **Source changed** (jacuzzi 065): Disabled — was firing every time solar fluctuated
- **Decision change** (energy 063): Disabled — fired on every 30-second orchestrator cycle
- **Plug-in nags**: Suppressed when any home car is already above 50% SOC (the readiness goal is met)
- **Maintenance nags**: Suppressed when readiness goal is met, unless a car is critically low (< 10%)

---

## Configurable Settings

### Jacuzzi

| Setting | Default | What it does |
|---|---|---|
| Standby temp | 20°C | Idle temperature when no event is coming |
| Boosted standby | 34°C | Pre-heating target during cheap energy (when boost toggle is on) |
| Preheat buffer | 30 min | Extra time added before calculated heat-up duration |
| Max heat-up hours | 6h | Readiness guarantee — standby will be raised if 40°C can't be reached in this time |
| Solar priority | On | Delays early-morning starts to wait for sun; enables solar-first heating |
| Boost enabled | Off | Whether to use boosted standby during cheap energy |
| Use forecast | On | Whether to use Met.no weather in heat-up calculations |

### EV

| Setting | Default | What it does |
|---|---|---|
| Charger max amps | 16A | Wallbox limit |
| Min amps | 5A | Minimum current to start solar charging |
| Solar margin | 500W | Buffer before offering surplus to charger |
| Minimum SOC | 50% | Readiness goal — at least one car should be above this |
| Charge limits | 80% each | Normal charge target per car |
| Trip mode | Off | Override to charge to 100% (auto-resets after 8 hours) |
| Requested vehicle | None | Fraser manually picks a car (one-time override) |

### Energy

| Setting | Default | What it does |
|---|---|---|
| Orchestrator enabled | Off | Shadow mode (calculates but doesn't control) vs active mode |
| Buffer target SOC | 80% | Maintenance charging target |
| Solar forecast enabled | On | Run solar prediction engine |
| Calibration factor | 0.75 | Solar model tuning (learned weekly) |

---

## Thermal Physics (How Heat-Up Time is Calculated)

The system uses Newton's law of cooling to predict heating and cooling. This is more accurate than a fixed "X degrees per hour" because:

- Heating slows down as the water gets hotter (the temperature difference with the air increases, so heat losses increase)
- The heater has a fixed output (6kW rated, ~5.7kW effective) but losses are proportional to the temperature gap
- Outdoor temperature matters — heating on a cold winter night is slower than a warm summer evening

The key numbers (all learned automatically, nudged 10% per observation):

| Parameter | Cold (<5°C) | Mild (5–15°C) | Warm (>15°C) |
|---|---|---|---|
| Heat loss rate | 0.040 kW/°C | 0.035 kW/°C | 0.025 kW/°C |

| Parameter | Value |
|---|---|
| Effective heater power | ~5.7 kW (learning from 6.0 rated) |
| Water volume | 3,200 litres |
| Thermal capacity | 3.72 kWh/°C |

**Example:** On a 10°C day, heating from 20°C to 40°C:
- Heat loss at 40°C = 0.035 × (40 - 10) = 1.05 kW
- Net heating power at 40°C = 5.7 - 1.05 = 4.65 kW
- But at 20°C: loss = 0.035 × 10 = 0.35 kW, net = 5.35 kW
- So heating starts fast (~1.4°C/h) and slows to ~1.25°C/h near the target
- The physics formula accounts for this curve; a flat rate estimate would be wrong by 30+ minutes
