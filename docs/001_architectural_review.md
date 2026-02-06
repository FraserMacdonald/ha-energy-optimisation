# 001 – Architectural Review & Conventions

**Date:** 2026-02-05
**HA OS:** 2026.2.0 – Mini PC
**Status:** PROPOSAL – Awaiting Approval

---

## 1. Review of Phase 1 Summary Document

The Phase 1 summary is thorough and identifies the right problems. This review focuses on what needs to change *before* implementation begins — naming conventions, numbering schemes, file structure adjustments, and scalability concerns for the systems listed on the roadmap.

### 1.1 What the Summary Gets Right

- Correct identification of the race condition between jacuzzi and EV solar claims
- Package-based helper architecture (EV pattern) as the standard
- Shadow-mode deployment for the orchestrator — low risk
- The 3×5×3 scenario matrix is well-defined and implementable
- Phased rollout with rollback plans at each stage

### 1.2 What Needs Revision Before Implementation

| # | Issue | Detail |
|---|-------|--------|
| 1 | **Automation numbering doesn't scale** | The EV system uses `00–79` (80 slots for one subsystem). The orchestrator uses `80–89`. This leaves zero room for 6+ future systems. A prefix-based scheme is required. |
| 2 | **No domain prefix on entity names** | Helpers like `input_boolean.orchestrator_jacuzzi_heat_allowed` mix domain concerns. A consistent `[system]_[function]` convention is needed across all entities. |
| 3 | **File structure is flat** | All automations in one directory becomes unmanageable at 10+ systems. Subdirectories per system are needed. |
| 4 | **No `.gitignore` or secrets strategy** | The proposal mentions GitHub but doesn't address secrets, tokens, or API keys. These must never be committed. |
| 5 | **Dashboard files in wrong location** | HA dashboards defined via YAML go in the main config or a `dashboards/` dir referenced by `configuration.yaml`, not alongside automations. The current proposal is correct in structure but the include mechanism needs specifying. |
| 6 | **Missing automation metadata** | No standard for `description`, `mode`, or `trace` configuration on automations. These are essential for debugging a system this complex. |
| 7 | **Future systems not accounted for in orchestrator design** | The orchestrator currently only handles jacuzzi vs EV. The design should define how new loads (grow tent, greenhouse) plug in without rewriting the orchestrator. |

---

## 2. Naming Conventions

Every entity, automation, script, and file in the system must follow these conventions. No exceptions.

### 2.1 Entity Naming

**Pattern:** `[domain].[system]_[function]_[qualifier]`

| System | Prefix | Examples |
|--------|--------|----------|
| Energy Orchestrator | `energy_` | `sensor.energy_solar_surplus_w`, `sensor.energy_tariff_current` |
| Jacuzzi | `jacuzzi_` | `input_number.jacuzzi_target_temp`, `binary_sensor.jacuzzi_solar_available` |
| Tesla EV | `ev_` | `input_boolean.ev_solar_charge_enabled`, `sensor.ev_solar_available_amps` |
| Security Cameras | `security_` | `binary_sensor.security_front_door_motion` |
| Smart Lighting | `lighting_` | `input_boolean.lighting_circadian_enabled` |
| Grow Tent | `growtent_` | `sensor.growtent_humidity`, `input_number.growtent_target_vpd` |
| Greenhouse | `greenhouse_` | `sensor.greenhouse_soil_moisture_zone_1` |
| Hardware Storage | `hardware_` | `sensor.hardware_bin_a1_stock_level` |

**Rules:**
- All lowercase, underscores only — no hyphens, no camelCase
- System prefix is mandatory on every helper and template sensor
- Physical device entities (integrations) keep their default names but get **entity_id overrides** to match convention where possible
- Boolean helpers: name describes the ON state — `jacuzzi_manual_override` means "manual override is active"
- Number helpers: include unit hint where ambiguous — `jacuzzi_target_temp` (°C implied by context), `energy_solar_surplus_w` (watts explicit)

### 2.2 Automation Naming & Numbering

**Pattern:** `auto_[system]_[nnn]_[description]`

The old pure-numeric scheme (`ev_00`, `ev_01`, … `ev_79`) is replaced with a **three-digit number per system**, giving each system 000–999 slots.

| System | Range | Example ID |
|--------|-------|------------|
| Energy Orchestrator | `auto_energy_0nn` | `auto_energy_001_evaluate_scenario` |
| Jacuzzi | `auto_jacuzzi_0nn` | `auto_jacuzzi_001_calendar_scheduler` |
| Tesla EV | `auto_ev_0nn` | `auto_ev_001_trip_planner_schedule` |
| Security | `auto_security_0nn` | `auto_security_001_motion_alert` |
| Lighting | `auto_lighting_0nn` | `auto_lighting_001_circadian_adjust` |
| Grow Tent | `auto_growtent_0nn` | `auto_growtent_001_vpd_control` |
| Greenhouse | `auto_greenhouse_0nn` | `auto_greenhouse_001_irrigation_cycle` |
| Hardware Storage | `auto_hardware_0nn` | `auto_hardware_001_stock_alert` |

**Sub-ranges within each system (recommended):**
- `001–019`: Core / lifecycle automations
- `020–039`: Solar / energy-related automations
- `040–059`: Scheduling / calendar automations
- `060–079`: Notifications / alerts
- `080–099`: Safety / override automations

**Every automation must include:**
```yaml
- id: auto_jacuzzi_001_calendar_scheduler
  alias: "Jacuzzi 001 – Calendar Event Scheduler"
  description: >
    Monitors the selected calendar for jacuzzi events. When an event is found
    within the heat-up window, sets the target temperature to 40°C.
    Gated by orchestrator_jacuzzi_heat_allowed.
  mode: single  # or queued/restart/parallel — be explicit
  trace:
    stored_traces: 10
```

### 2.3 File Naming

**Pattern:** `[system]_[type].yaml`

| Type | Convention | Example |
|------|-----------|---------|
| Package (helpers) | `[system]_system.yaml` | `jacuzzi_system.yaml` |
| Automations | `[system]_automations.yaml` | `jacuzzi_automations.yaml` |
| Template sensors | `[system]_sensors.yaml` | `jacuzzi_sensors.yaml` |
| Binary sensors | `[system]_binary_sensors.yaml` | `jacuzzi_binary_sensors.yaml` |
| Scripts | `[system]_scripts.yaml` | `jacuzzi_scripts.yaml` |
| Dashboard | `[system]_dashboard.yaml` | `jacuzzi_dashboard.yaml` |

**Shared/cross-system files use the `energy_` prefix:**
- `energy_shared_sensors.yaml`
- `energy_orchestrator_automations.yaml`

### 2.4 Script Naming

**Pattern:** `script.[system]_[action]`

Examples:
- `script.jacuzzi_set_heating_mode`
- `script.ev_start_solar_charge`
- `script.energy_force_rebalance`

### 2.5 Scene Naming

**Pattern:** `scene.[system]_[state_description]`

Examples:
- `scene.jacuzzi_party_mode`
- `scene.lighting_evening_relax`

---

## 3. Revised File Structure

This structure is designed for 8+ systems. Each system is self-contained in its subdirectory under `automations/` and `templates/`. Packages remain flat because HA requires direct `!include` paths.

```
homeassistant/
├── configuration.yaml
├── secrets.yaml                          # API keys, tokens — NEVER committed
├── .gitignore
│
├── packages/
│   ├── energy_orchestrator_system.yaml   # Shared energy helpers
│   ├── jacuzzi_system.yaml              # Jacuzzi helpers
│   ├── ev_system.yaml                   # EV helpers
│   ├── security_system.yaml             # [FUTURE]
│   ├── lighting_system.yaml             # [FUTURE]
│   ├── growtent_system.yaml             # [FUTURE]
│   ├── greenhouse_system.yaml           # [FUTURE]
│   └── hardware_system.yaml             # [FUTURE]
│
├── automations/
│   ├── energy/
│   │   └── energy_orchestrator_automations.yaml
│   ├── jacuzzi/
│   │   └── jacuzzi_automations.yaml
│   ├── ev/
│   │   └── ev_automations.yaml
│   ├── security/                        # [FUTURE]
│   ├── lighting/                        # [FUTURE]
│   ├── growtent/                        # [FUTURE]
│   ├── greenhouse/                      # [FUTURE]
│   └── hardware/                        # [FUTURE]
│
├── templates/
│   ├── energy/
│   │   └── energy_shared_sensors.yaml
│   ├── jacuzzi/
│   │   ├── jacuzzi_sensors.yaml
│   │   └── jacuzzi_binary_sensors.yaml
│   └── ev/
│       └── ev_sensors.yaml
│
├── scripts/
│   ├── jacuzzi_scripts.yaml
│   └── ev_scripts.yaml
│
├── python_scripts/
│   ├── compute_elevation.py
│   ├── get_elevation.py
│   └── ev_text_store.py
│
├── dashboards/
│   ├── energy_overview_dashboard.yaml
│   ├── jacuzzi_dashboard.yaml
│   └── ev_dashboard.yaml
│
└── scenes/
    └── (as needed)
```

### 3.1 configuration.yaml Include Strategy

```yaml
homeassistant:
  packages:
    energy_orchestrator: !include packages/energy_orchestrator_system.yaml
    jacuzzi:            !include packages/jacuzzi_system.yaml
    ev:                 !include packages/ev_system.yaml
    # Future systems added here as single lines

# Automations — merge all system automation files
automation: !include_dir_merge_list automations/

# Templates — merge all system template files
template: !include_dir_merge_list templates/

# Scripts
script: !include_dir_merge_named scripts/
```

**Key point:** Using `!include_dir_merge_list` with subdirectories means we can add a new system by simply creating a new subdirectory and dropping files into it. No changes to `configuration.yaml` required for new systems.

### 3.2 Why Subdirectories Under automations/ and templates/

The original proposal had flat files (`automations/jacuzzi_automations.yaml`). This works for 3 systems but becomes unwieldy at 8+. Subdirectories allow:
- Each system to have multiple automation files if needed (e.g., `ev/ev_trip_automations.yaml`, `ev/ev_charge_automations.yaml`)
- `!include_dir_merge_list` to recursively pick up all YAML files
- Clean `git diff` output — changes scoped to system directories

---

## 4. Helpers: YAML-Only Policy

**All helpers must be defined in package YAML files. No helpers created via the UI.**

This is critical for:
- Version control (UI-created helpers exist only in `.storage/` which is gitignored)
- Reproducibility (rebuild from repo alone)
- Review (all changes visible in PRs)

### 4.1 Package File Template

Every `packages/[system]_system.yaml` follows this structure:

```yaml
# packages/jacuzzi_system.yaml
# Jacuzzi System – Helper Definitions
# All helpers for the jacuzzi subsystem. Do not create helpers via UI.

input_boolean:
  jacuzzi_manual_override:
    name: "Jacuzzi Manual Override"
    icon: mdi:hand-back-right
  jacuzzi_boost_mode:
    name: "Jacuzzi Boost Mode"
    icon: mdi:rocket-launch

input_number:
  jacuzzi_target_temp:
    name: "Jacuzzi Target Temperature"
    min: 10
    max: 40
    step: 0.5
    unit_of_measurement: "°C"
    icon: mdi:thermometer
  jacuzzi_standby_temp:
    name: "Jacuzzi Standby Temperature"
    min: 10
    max: 30
    step: 0.5
    unit_of_measurement: "°C"
    icon: mdi:thermometer-low

input_select:
  jacuzzi_calendar_entity:
    name: "Jacuzzi Calendar Entity"
    options:
      - calendar.jacuzzi
      - calendar.family
    icon: mdi:calendar

input_datetime:
  jacuzzi_last_heated:
    name: "Jacuzzi Last Heated"
    has_date: true
    has_time: true
```

### 4.2 Migrating Existing UI Helpers

Any helpers currently in `.storage/core.config_entries` or `.storage/core.restore_state` must be:
1. Identified via HA Developer Tools → States
2. Recreated in the appropriate package YAML
3. Deleted from the UI
4. HA restarted to confirm the YAML version takes over

---

## 5. Orchestrator Scalability Design

The current proposal designs the orchestrator for 2 loads (jacuzzi + EV). With 6+ future systems, several of which are energy-consuming (grow tent lights, greenhouse heating, etc.), the orchestrator needs a **load priority queue** rather than hardcoded if/else logic.

### 5.1 Load Priority Tiers

| Tier | Priority | Loads | Rule |
|------|----------|-------|------|
| 0 – Safety | Absolute | Freeze protection, security cameras | Always powered. Bypasses orchestrator entirely. |
| 1 – Critical | High | EV charging when trip-critical (State X), Jacuzzi below minimum (State A) | Must be met. Use grid if solar insufficient. |
| 2 – Time-Sensitive | Medium-High | Jacuzzi event imminent (State D), Grow tent light schedule | Solar preferred, grid fallback in low tariff. |
| 3 – Opportunistic | Medium | EV topping up (State Y), Jacuzzi solar heating (State C), Greenhouse heating | Solar only. No grid import. |
| 4 – Background | Low | EV above required SOC, Hardware storage inventory scan | Excess solar only, after all other loads satisfied. |

### 5.2 Orchestrator Decision Algorithm (Generalised)

Instead of a hardcoded 45-scenario matrix, the generalised orchestrator:

1. Calculates `solar_surplus_w`
2. Builds a sorted list of active load requests, each with: `system`, `priority_tier`, `power_demand_w`, `can_use_grid`, `can_use_low_tariff`
3. Iterates through the list from highest to lowest priority, allocating surplus until exhausted
4. Any remaining unmet Tier 1 loads get grid allocation
5. Tier 2 loads check if low tariff is active before using grid
6. Tier 3+ loads wait for solar

This means adding a new system (e.g., grow tent) requires only:
- Creating its package, automations, and templates
- Registering a `sensor.growtent_demand_scenario` and a `input_number.growtent_power_demand_w`
- Adding a line to the orchestrator's load list

The orchestrator itself doesn't change — it just processes the priority queue.

### 5.3 Backward Compatibility

The 45-scenario matrix from the summary document remains valid as a **verification tool**. We can generate expected outcomes from the matrix and compare against the generalised algorithm's decisions to ensure correctness during shadow mode.

---

## 6. Git Repository Strategy

### 6.1 Repository Structure

```
ha-energy-optimisation/           # GitHub repo root
├── .gitignore
├── README.md
├── LICENSE
│
├── docs/
│   ├── 001_architectural_review.md        # This document
│   ├── 002_naming_conventions.md          # Extracted quick-reference
│   ├── 003_phase_1a_bugfixes.md           # Phase 1A implementation notes
│   ├── 004_phase_1b_shared_sensors.md     # Phase 1B implementation notes
│   ├── 005_phase_1c_orchestrator.md       # Phase 1C implementation notes
│   ├── 006_phase_1d_enhancements.md       # Phase 1D implementation notes
│   └── diagrams/
│       └── orchestrator_flow.md           # Mermaid diagrams
│
├── config/                                # Maps to /homeassistant/ on the HA instance
│   ├── configuration.yaml
│   ├── packages/
│   ├── automations/
│   ├── templates/
│   ├── scripts/
│   ├── python_scripts/
│   ├── dashboards/
│   └── scenes/
│
└── tools/
    ├── validate.sh                        # Runs HA config check
    └── deploy.sh                          # Syncs repo to HA instance
```

### 6.2 .gitignore

```gitignore
# Secrets — NEVER commit
secrets.yaml
*.secret
.env

# HA internal storage
.storage/
*.log
*.db
*.db-shm
*.db-wal
home-assistant_v2.db*

# OS files
.DS_Store
Thumbs.db
__pycache__/
*.pyc

# Backup files
*.bak
*.backup

# IDE
.vscode/
.idea/
```

### 6.3 Branching Strategy

| Branch | Purpose |
|--------|---------|
| `main` | Stable, tested config. Matches what's running on the HA instance. |
| `develop` | Integration branch. Merges here before `main`. |
| `feature/phase-1a-bugfixes` | Phase 1A work |
| `feature/phase-1b-shared-sensors` | Phase 1B work |
| `feature/phase-1c-orchestrator` | Phase 1C work |
| `feature/phase-1d-enhancements` | Phase 1D work |
| `feature/[system]-initial` | Future system branches (e.g., `feature/security-initial`) |

**Workflow:**
1. Create feature branch from `develop`
2. Make changes, commit with descriptive messages
3. Test on HA instance
4. Merge to `develop`
5. After validation period, merge `develop` → `main`
6. Tag releases: `v1.0.0-phase1a`, `v1.1.0-phase1b`, etc.

### 6.4 Commit Message Convention

```
[system] action: brief description

Examples:
[jacuzzi] fix: correct entity name solar_available_jacuzzi → solar_available_for_jacuzzi
[ev] fix: update solaredge entity reference to sensor.solaredge_solar_power
[energy] feat: add shared solar surplus and tariff sensors
[orchestrator] feat: implement 45-scenario decision engine
[config] refactor: migrate jacuzzi helpers from standalone to package format
[docs] add: phase 1A implementation notes
```

---

## 7. Automation Renumbering Map

### 7.1 Jacuzzi System (Current → New)

| Current | Current Name | New ID | New Alias |
|---------|-------------|--------|-----------|
| #1 | Calendar Scheduler | `auto_jacuzzi_040_calendar_scheduler` | Jacuzzi 040 – Calendar Event Scheduler |
| #2 | Solar Opportunistic Heating | `auto_jacuzzi_020_solar_opportunistic` | Jacuzzi 020 – Solar Opportunistic Heating *(RETIRE in Phase 1C)* |
| #3 | Temperature Control | `auto_jacuzzi_001_temperature_control` | Jacuzzi 001 – Temperature Control Loop |
| #4 | Manual Override | `auto_jacuzzi_080_manual_override` | Jacuzzi 080 – Manual Override Handler |
| #5 | Low Tariff Preference | `auto_jacuzzi_021_low_tariff_heating` | Jacuzzi 021 – Low Tariff Heating *(RETIRE in Phase 1C)* |
| #6 | Freeze Protection | `auto_jacuzzi_090_freeze_protection` | Jacuzzi 090 – Freeze Protection |
| #7 | Event Reminder | `auto_jacuzzi_060_event_reminder` | Jacuzzi 060 – Event Readiness Reminder |
| NEW | — | `auto_jacuzzi_091_pipe_freeze_cycling` | Jacuzzi 091 – Pipe Freeze Pump Cycling |
| NEW | — | `auto_jacuzzi_022_solar_off_fallback` | Jacuzzi 022 – Solar Off Fallback to Standby |
| NEW | — | `auto_jacuzzi_061_not_ready_warning` | Jacuzzi 061 – Event Not Ready Warning |

### 7.2 EV System (Current → New)

The EV system currently uses `ev_00` through `ev_79`. These need the `auto_ev_` prefix and three-digit numbering. Full mapping will be completed in Phase 1A, but the key automations:

| Current | Current Name | New ID |
|---------|-------------|--------|
| ev_00 | Trip Planner Schedule | `auto_ev_001_trip_planner_schedule` |
| ev_10 | SOC Monitor | `auto_ev_002_soc_monitor` |
| ev_20 | Night Charge Scheduler | `auto_ev_040_night_charge_scheduler` |
| ev_30 | Departure Climate | `auto_ev_003_departure_climate` |
| ev_40 | Solar Surplus Charging | `auto_ev_020_solar_surplus_charge` |
| ev_41 | Cheap Tariff Charging | `auto_ev_021_cheap_tariff_charge` |
| ev_42 | Solar Surplus Alert | `auto_ev_060_solar_surplus_alert` |
| ev_43 | Energy Logger | `auto_ev_004_energy_logger` |
| ev_50 | Climate Control | `auto_ev_005_climate_control` |

### 7.3 Energy Orchestrator (New)

| ID | Alias | Purpose |
|----|-------|---------|
| `auto_energy_001_evaluate_scenario` | Energy 001 – Evaluate Scenario | Main 30-second evaluation loop |
| `auto_energy_002_dispatch_commands` | Energy 002 – Dispatch Commands | Sets output helpers based on decision |
| `auto_energy_060_decision_log` | Energy 060 – Decision Logger | Logs orchestrator decisions for audit |
| `auto_energy_061_conflict_alert` | Energy 061 – Conflict Alert | Notifies if orchestrator detects conflicting demands it cannot resolve |

---

## 8. Revised Implementation Phases

The phases from the original document are sound. The revisions below add the naming/numbering migration and Git workflow:

### Phase 1A – Bug Fixes, Structural Alignment & Naming Migration
**Branch:** `feature/phase-1a-bugfixes`
**Est:** 3–4 hours (increased from 2–3 to include renumbering)

1. Initialise Git repo with current config as baseline commit on `main`
2. Create `feature/phase-1a-bugfixes` branch
3. Fix all 6 bugs identified (4 jacuzzi + 2 EV)
4. Migrate `jacuzzi_helpers.yaml` → `packages/jacuzzi_system.yaml`
5. Rename all entity IDs to match naming convention (Section 2.1)
6. Rename all automation IDs to match numbering convention (Section 7)
7. Create subdirectory structure under `automations/` and `templates/`
8. Update `configuration.yaml` includes
9. Update all dashboards with new entity names
10. Run `ha core check` to validate config
11. Test both systems work independently
12. Commit, merge to `develop`, deploy, validate, merge to `main`
13. Tag `v1.0.0-phase1a`

### Phase 1B – Shared Sensors
**Branch:** `feature/phase-1b-shared-sensors`
**Est:** 1–2 hours (unchanged)

### Phase 1C – Energy Orchestrator
**Branch:** `feature/phase-1c-orchestrator`
**Est:** 3–4 hours (unchanged)

### Phase 1D – Enhancements
**Branch:** `feature/phase-1d-enhancements`
**Est:** 2–3 hours (unchanged)

---

## 9. Recommended Immediate Actions

Before writing any YAML, these decisions need confirming:

| # | Decision | Recommendation | Needs Confirmation |
|---|----------|---------------|--------------------|
| 1 | Naming convention as defined in Section 2 | Adopt as-is | ✅ / ❌ |
| 2 | Three-digit automation numbering with sub-ranges | Adopt as-is | ✅ / ❌ |
| 3 | Subdirectory structure under `automations/` and `templates/` | Adopt as-is | ✅ / ❌ |
| 4 | Generalised priority-queue orchestrator (Section 5.2) vs hardcoded 45-scenario matrix | Priority queue (more scalable) | ✅ / ❌ |
| 5 | Git branching strategy | Adopt as-is | ✅ / ❌ |
| 6 | Commit message convention | Adopt as-is | ✅ / ❌ |
| 7 | Start with Phase 1A (bug fixes + renaming) | Yes | ✅ / ❌ |

---

## 10. Future System Roadmap (For Planning Only)

These systems are not in scope for Phase 1 but the architecture must accommodate them:

| System | Key Sensors/Devices | Energy Load | Orchestrator Tier |
|--------|-------------------|-------------|-------------------|
| **Security AI Cameras** | Motion sensors, NVR, AI inference | ~100W constant (NVR) | Tier 0 (Safety) |
| **Smart Lighting** | Zigbee/Z-Wave bulbs, circadian schedules | ~50–500W variable | Tier 3 (Opportunistic) |
| **Grow Tent** | Lights, fans, humidifier, pH/EC sensors | ~400–1000W (lights on schedule) | Tier 2 (Time-Sensitive) |
| **Greenhouse** | Soil sensors, irrigation valves, heating | ~500–2000W (heating) | Tier 2–3 (varies) |
| **Hardware Storage** | Barcode/RFID, inventory DB, reorder triggers | Negligible | Tier 4 (Background) |

Each system will follow the same pattern: package → automations → templates → dashboard → orchestrator registration.

---

*End of document. Proceed to Phase 1A upon confirmation of decisions in Section 9.*
