# Energy Optimisation System — User Guide

This system manages three things in your home: the jacuzzi, the two Teslas (Horace and Horatio), and solar energy allocation. It watches your calendars, electricity prices, and solar production to heat the jacuzzi and charge the cars at the lowest possible cost — automatically.

---

## Contents

1. [System Overview](#system-overview)
2. [Jacuzzi](#jacuzzi)
3. [EV Charging](#ev-charging)
4. [Energy Orchestrator](#energy-orchestrator)
5. [Solar Forecast](#solar-forecast)
6. [Notifications You'll Receive](#notifications-youll-receive)
7. [Dashboards](#dashboards)
8. [Settings You Can Change](#settings-you-can-change)
9. [Quick Actions](#quick-actions)

---

## System Overview

The system has three subsystems that work together:

- **Jacuzzi** — Heats the jacuzzi before calendar events using the cheapest energy available (solar first, then low-tariff overnight/weekend power, then grid as a last resort).
- **EV Charging** — Keeps Horace and Horatio charged for tomorrow's trips, assigns the right car to each driver, and tops up from solar during the day.
- **Energy Orchestrator** — Decides who gets solar power when both the jacuzzi and a car want it at the same time.

### Electricity Tariff Schedule

| Period | Rate |
|--------|------|
| **Low tariff** — Mon-Thu 22:00-06:00, Fri from 22:00 through entire weekend until Mon 06:00 | 0.25 CHF/kWh |
| **Main tariff** — all other hours | 0.35 CHF/kWh |
| **Solar** — when panels produce more than the house uses | ~0.10 CHF/kWh opportunity cost |

### Solar Setup

23 kWp of panels split between east-facing and west-facing roof slopes at 35-degree tilt. The system forecasts production 48 hours ahead and uses that to plan heating and charging.

---

## Jacuzzi

### How Scheduling Works

Create an event in the **Jacuzzi Schedule** calendar (synced via CalDAV). The event title doesn't matter — only the start and end times are used. The system will:

1. Calculate how long heating will take based on the current water temperature, outdoor conditions, and learned heater performance
2. Add a 30-minute safety buffer
3. Work backward from your event to find the best time to start heating
4. Prefer starting during cheap energy windows (solar or low tariff) when possible

### Smart Start

The system uses a physics-based model to predict heating time. It accounts for:

- Current water temperature
- Weather forecast for the outdoor temperature during heating
- Learned heater power (starts at 5.7 kW, refines itself over time)
- Heat loss rate (the system learns separate rates for cold, mild, and warm weather)

The first week uses conservative estimates. After about 20 heating sessions, the model is fully calibrated and predictions become noticeably more accurate.

### Solar and Low-Tariff Heating

When a jacuzzi event is coming up within 24 hours:

- **Solar heating** kicks in when the panels produce more than 6 kW of surplus. If clouds roll in and surplus drops for more than 10 minutes, the system stops heating (it won't quietly switch to expensive grid power).
- **Low-tariff heating** starts automatically at the beginning of cheap-rate windows if there's enough time to finish before the event.

Both of these can be toggled with the **Solar Priority** setting. When solar priority is on, the system tries to wait for sun before using overnight power.

### Thermal Banking

When you have an event coming up and cheap energy is available well before it, the system can pre-heat the water beyond the normal standby temperature. This is called "banking" — storing heat energy while it's cheap, so less expensive grid heating is needed closer to the event.

The banking algorithm:

- Looks at the hours between now and your event
- Identifies which hours have cheap energy (solar or low tariff) and which don't
- Works backward from the event to figure out the optimal pre-heat temperature
- Caps pre-heating at 37 degrees (going higher has diminishing returns)
- Only banks if it actually saves money compared to heating later

Banking requires the **Standby Boost** setting to be enabled.

### Standby Temperature

When no event is scheduled, the water sits at the **standby temperature** (default 20 degrees). This is the baseline.

When standby boost is enabled and cheap energy is available, the system raises the standby to the **boosted standby temperature** (default 34 degrees). When cheap energy ends, it drops back to normal standby.

If banking is active, the banking target overrides the boost temperature.

The system also enforces a **minimum standby** — the lowest temperature from which it can guarantee reaching 40 degrees within the maximum heat-up time (default 6 hours). If the minimum is higher than your standby setting, the minimum wins.

### Weather Forecast

The system fetches hourly weather forecasts from Met.no. It uses the predicted outdoor temperature (not just the current reading) when calculating heating time. This makes a real difference for sessions that take several hours — the outdoor temperature at 3 PM when the event starts may be very different from the temperature at 9 AM when heating begins.

### Freeze Protection

Two automatic safety systems run regardless of all other settings:

- **Emergency heating** — If water drops below 5 degrees, the heater fires immediately to reach 10 degrees. Overrides everything, including manual override and maintenance mode.
- **Pipe cycling** — When outdoor temperature is below 0 degrees, the pump runs for 5 minutes every 30 minutes to prevent pipes from freezing. Only activates during standby (not while event heating is running).

### During an Event

While a calendar event is active, the system maintains 40 degrees. If the heater stops unexpectedly (power blip, safety cutoff), it automatically restarts within 2 minutes as long as the water is below 39.5 degrees.

When the event ends, the system drops back to standby temperature.

---

## EV Charging

### The Two Cars

| | Horace | Horatio |
|---|---|---|
| Battery | 70 kWh | 90 kWh |
| Efficiency | 180 Wh/km | 215 Wh/km |
| Range at 100% | ~389 km | ~419 km |

The system treats both cars equally — neither is permanently assigned to a driver. Assignment happens automatically based on tomorrow's trips.

### Trip Planning from Calendar

The system reads **Fraser's calendar** and **Heather's calendar** three times a day (07:00, 14:00, 20:00) plus whenever a calendar event changes. For each event with a location:

1. It builds a trip chain: Home, then each event location in order, then Home
2. Uses Waze to calculate driving distance and time for each leg
3. Estimates how much battery each trip will use (accounting for each car's efficiency)
4. Computes the departure time (event start minus drive time minus 15-minute buffer)

### Car Assignment

The planner evaluates two scenarios — Fraser in Horace vs Fraser in Horatio — and picks the combination where both drivers can complete their trips with the most battery to spare. The driver with the longer trip generally gets the car with more charge.

If elevation data is available for the route, the system adjusts battery estimates accordingly.

### Overnight Charging

When tomorrow's trips require more charge than a car currently has:

1. The planner identifies which car needs charging and to what level
2. During the low-tariff window, the system wakes the car, checks it's plugged in, and starts charging
3. The Tesla's own charge limit is set to the target level, so the car stops itself when done
4. If the car is asleep and not responding, the system retries up to three times with increasing wait periods

The target is set so the driver arrives home with at least 20% remaining (with a hard floor of 10% — the system won't plan a trip that would drain below that).

### Solar Surplus Charging

During the day, when solar panels produce more than the house uses:

- The system calculates how many amps of charging the surplus can support
- If it's at least 5 amps, charging begins on whichever car is plugged in
- Charging current adjusts dynamically as solar production changes
- If surplus drops below the minimum, charging pauses until it recovers

### Maintenance Charging (Always-Ready)

Regardless of trips, tariffs, or time of day, the system ensures at least one car has **50% charge** at all times. This guarantees about 100-150 km of range for unplanned trips or emergencies.

Every 30 minutes, it checks whether any home car is below 50%. If so, it picks the car with the lowest charge, wakes it, and tops it up. If the car isn't plugged in, you'll get a notification asking you to plug it in.

### Climate Prep

On mornings with a planned trip:

- **Defrost** activates 30 minutes before departure when outside temperature is below 0 degrees
- **Cabin preheat** to 21 degrees activates 15 minutes before departure

Both run automatically using the departure time calculated from your calendar.

---

## Energy Orchestrator

The orchestrator is the referee between the jacuzzi and the EVs. When both want power at the same time and there isn't enough solar for everyone, it decides who gets priority.

### How It Works

Every 30 seconds, the orchestrator evaluates the situation using three inputs:

- **Solar production** — Is there enough surplus for one load? Both loads? Neither?
- **Jacuzzi demand** — Is it in freeze protection? Heating for an imminent event? Just topping up standby?
- **EV demand** — Does a car need charge for tomorrow's trip? Is it a casual top-up? No demand?

### Priority Tiers

When there's a conflict, higher-priority needs win:

| Priority | What | Examples |
|----------|------|---------|
| **Safety** (always runs) | Freeze protection, pipe cycling | Water below 5 degrees, pipes at risk |
| **Critical** | Trip-critical EV charging, emergency heating | Car won't make tomorrow's trip without charging tonight |
| **Time-sensitive** | Jacuzzi pre-heat for an imminent event, maintenance charging | Event starts in 4 hours, car below 50% |
| **Opportunistic** | Solar top-ups for jacuzzi or EV | Surplus available, no deadline pressure |

### Scenario Codes

The orchestrator labels each evaluation with a three-part code like `2-D-Y`:

- **First part (1/2/3)** — Solar tier. 1 = not enough for anything useful. 2 = enough for one load. 3 = enough for both.
- **Second part (A-E)** — Jacuzzi state. A = freeze risk. B = below standby. C = solar pre-heat for upcoming event. D = imminent event, must heat now. E = satisfied or off.
- **Third part (X/Y/idle)** — EV state. X = trip-critical, must charge. Y = could top up. idle = no demand.

You can see the current scenario code on the Energy dashboard.

### Shadow Mode vs Active Mode

The orchestrator defaults to **off** (shadow mode). In this mode, it evaluates every scenario and logs decisions, but doesn't actually control the jacuzzi or EVs — they run independently as they always have.

When you turn the orchestrator **on** (active mode), it gates the subsystems: the jacuzzi and EV automations check with the orchestrator before heating or charging. This is useful during peak solar season when conflicts happen more often.

---

## Solar Forecast

### What It Predicts

Every 30 minutes between 04:00 and 22:00, the system generates a 48-hour solar production forecast. It uses:

- Sun position calculations (altitude, azimuth) for your location
- Your panel layout (east and west slopes at 35-degree tilt)
- Cloud cover forecast from Met.no
- A calibration factor learned from your actual production history

### How It Learns

Every Sunday evening, the system reviews the last 90 days to find clear-sky days (less than 20% average cloud cover). It compares what the panels actually produced against what the model predicted for those clear days, then adjusts the calibration factor. This accounts for panel soiling, inverter losses, and local atmospheric conditions.

### How It's Used

- **Thermal banking** uses the forecast to identify upcoming cheap solar windows and calculate how much heat gain to expect
- **EV charging** uses it to estimate whether solar surplus will be available for topping up
- **Conflict alerts** use it to warn you when both loads will compete for limited solar

### Forecast Quality

The system tracks its own accuracy with a quality score (0-100) and letter rating. You can see this on the Energy dashboard along with the error percentages for near-term and 24-hour-ahead forecasts.

---

## Notifications You'll Receive

### Jacuzzi Notifications

| Notification | When | Who |
|---|---|---|
| **Daily plan** | When an event is detected, or at 07:00 if one is scheduled today | Fraser and Heather |
| **Feasibility warning** | If there isn't enough time to reach 40 degrees before the event | Fraser and Heather |
| **Heating started** | When the target is raised to 40 degrees | Fraser and Heather |
| **Progress update** | Every 60 minutes during heating | Fraser |
| **Halfway there** | When water reaches the midpoint between start and 40 degrees | Fraser and Heather |
| **Ready** | When water crosses 39.5 degrees during heating for an event | Fraser and Heather |
| **Readiness reminder** | 30 minutes before the event, if water is above 38 degrees | Fraser and Heather |
| **Not ready warning** | 30 minutes before the event, if water is below 38 degrees (with ETA) | Fraser and Heather |
| **Won't be ready** | 60 minutes before the event, if water is below 37 degrees | Fraser and Heather |
| **Session over** | When the calendar event ends | Fraser |
| **Rate anomaly** | If heating is less than 70% of expected speed (possible heater issue) | Fraser |
| **Pipe freeze cycling** | When outdoor temperature triggers pipe protection | Fraser |

### EV Notifications

| Notification | When | Who |
|---|---|---|
| **Morning briefing** | 06:30 daily — car status, today's trips, overnight charging summary, climate note | Fraser and Heather (personalised) |
| **Departure reminder** | 1.5 hours before departure — trip distance, assigned car, drive time, required charge | The driver with the trip |
| **Solar charge started** | When solar surplus charging begins | The assigned driver |
| **Solar charge stopped** | When solar drops too low to continue | The assigned driver |
| **Solar target reached** | When the car reaches its charge limit from solar | The assigned driver |
| **Night charge started** | When overnight cheap-tariff charging begins | Fraser and Heather |
| **Night charge complete** | When the car reaches its overnight target | Fraser and Heather |
| **Charging progress** | Every 60 minutes during any charging session | The assigned driver |
| **Charging session ended** | When charging stops (any reason), with source breakdown | The assigned driver |
| **Trip complete** | When a car returns home after a trip, with battery used | Fraser |
| **Evening trip digest** | 20:00 daily — summary of today's trips and overnight charging plan | Fraser and Heather |
| **Plug-in reminder** | 20:00 if the overnight car isn't plugged | The relevant driver |
| **Arrival plug-in reminder** | 10 minutes after arriving home if not plugged in | The driver who arrived |
| **Always-one-plugged nag** | Every 30 minutes if no car is plugged in at home | Fraser (and Heather if home) |
| **Unexpected disconnect** | When a car is unplugged while below target | Fraser |
| **Morning SOC check** | 06:00 if overnight charging didn't reach its target | Fraser |

### Energy / Orchestrator Notifications

| Notification | When | Who |
|---|---|---|
| **Morning summary** | 07:00 daily — jacuzzi event, EV trips, orchestrator status, solar forecast | Fraser |
| **Daily summary** | 21:00 daily — what happened today (heating, charging, surplus) | Fraser |
| **Weekly summary** | Sunday 20:00 — week overview | Fraser |
| **Mode changed** | When the orchestrator is turned on or off | Fraser and Heather |
| **Conflict detail** | When jacuzzi and EV both need solar but there isn't enough | Fraser |
| **Surplus wasted** | When more than 3 kW goes unused for 30+ minutes | Fraser |

---

## Dashboards

### Jacuzzi Dashboard

The main view shows:

- **Current temperature** and target, with climate control
- **Current mode** — Heating, Standby, Ready, Manual Override, Maintenance, or Disabled
- **Event status** (when an event is upcoming) — Smart start time, hours needed, readiness prediction (On Track / Marginal / At Risk)
- **Standby boost status** (when boost is active) — Which mode (solar or low tariff) and effective temperature
- **Banking status** (when banking is active) — Target temperature, strategy, expected solar hours and temperature gain
- **Weather forecast** (when available) — Predicted outdoor temperature at event time vs current
- **Temperature graphs** — 6-hour and 48-hour views of water and ambient temperature
- **Heating rate** and current tariff
- **Thermal model info** — Learned heater power, heat loss rate, observation count, model status (Bootstrapping / Learning / Calibrated)
- **Quick action buttons** and settings (see below)

### EV Dashboard

- **Car status cards** — Horace and Horatio each show charge level (colour-coded gauge), location, and plug status
- **Trip cards** (when trips are planned) — Fraser's and Heather's trip distances, assigned car, departure time, drive duration, required charge
- **Charging plan** — Which car charges tonight, target level, solar mode toggle
- **Today's charging** — Solar and grid kWh for each car
- **Settings** — Charge limits, trip mode, charger configuration

### Energy Dashboard

- **Orchestrator status** — On/off, current scenario code and decision
- **Tariff and surplus** — Current rate, net solar balance (surplus/importing/balanced)
- **Solar production** — 12-hour graph of actual output
- **System status** — Jacuzzi temperature, Horace and Horatio charge levels (tap to navigate to their dashboards)
- **Solar forecast** — Today's forecast vs actual kWh, current and peak hour power, cloud cover, tomorrow's forecast
- **Forecast quality** — Accuracy rating, error percentages, calibration factor
- **Forecast vs actual graph** — 24-hour comparison of predicted vs real production

---

## Settings You Can Change

### Jacuzzi Settings

| Setting | Default | What It Does |
|---|---|---|
| Smart Heating Enabled | Off | Master switch for all jacuzzi automations |
| Solar Priority | On | Prefer solar over low-tariff for pre-heating |
| Standby Temperature | 20 degrees | Water temperature when no event is scheduled |
| Standby Boost Enabled | Off | Allow pre-heating to boosted level during cheap energy |
| Boosted Standby Temperature | 34 degrees | Target when boost is active and cheap energy is available |
| Preheat Buffer | 30 min | Extra time added to heating calculations as safety margin |
| Max Heat-Up Time | 6 hours | Maximum time the system plans for reaching 40 degrees |
| Use Weather Forecast | On | Use predicted outdoor temperature instead of current reading |
| Manual Override | Off | Temporarily disable all automations (expires at set time) |

### EV Settings

| Setting | Default | What It Does |
|---|---|---|
| Solar Mode Enabled | On | Allow solar surplus charging |
| Minimum SOC | 50% | Maintenance charging threshold — at least one car stays above this |
| Horace Charge Limit | 80% | Default maximum charge for Horace (overridden by trip planner when needed) |
| Horatio Charge Limit | 80% | Default maximum charge for Horatio |
| Horace Trip Mode | Off | Force charge Horace to 100% for a long trip (auto-resets after 8 hours) |
| Horatio Trip Mode | Off | Force charge Horatio to 100% for a long trip (auto-resets after 8 hours) |
| Charger Max Amps | 16 A | Home charger's maximum current |
| Minimum Amps | 5 A | Lowest useful current for solar charging |

### Energy / Orchestrator Settings

| Setting | Default | What It Does |
|---|---|---|
| Orchestrator Enabled | Off | When on, the orchestrator actively gates jacuzzi and EV decisions. When off, systems run independently. |
| Solar Forecast Enabled | On | Run the 48-hour solar production forecast |

---

## Quick Actions

### Jacuzzi Quick Actions

| Button | What It Does |
|---|---|
| **4h Override** | Activates manual mode and heats to 40 degrees for 4 hours. Use for a quick unscheduled soak. |
| **Heat Now** | Immediate heating for 8 hours, bypassing all scheduling. For last-minute events or testing. |
| **Reset to Standby** | Cancels any override and returns to normal standby temperature. |

### EV Quick Actions

| Button | What It Does |
|---|---|
| **Plug Horace** / **Plug Horatio** | Sends a notification to available drivers asking them to plug in that car. |
| **Emergency Charge Both** | Overrides all logic and charges both cars at maximum current. For urgent situations. |
| **Stop All Charging** | Immediately stops all EV charging. |
