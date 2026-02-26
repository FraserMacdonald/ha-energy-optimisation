# Home Assistant – Energy Optimisation System

Unified solar energy optimisation for Home Assistant, managing load priority across multiple subsystems.

## Current Systems
- **Energy Orchestrator** – Central decision engine evaluating solar surplus, tariff, and demand scenarios
- **Jacuzzi Smart Heating** – Calendar-driven heating with solar opportunistic mode
- **Tesla EV Charging** – Trip-aware charging with solar surplus and low-tariff scheduling

## Planned Systems
- Security AI Cameras
- Smart Lighting
- Automated Grow Tent (with data tracking & reporting)
- Automated Greenhouse
- Hardware Storage & Reordering

## Architecture
All configuration lives in `config/` and maps to `/homeassistant/` on the HA instance.

```
config/
├── configuration.yaml
├── packages/          # Helper definitions (YAML-only, no UI helpers)
├── automations/       # Subdirectory per system
├── templates/         # Subdirectory per system
├── scripts/
├── python_scripts/
├── dashboards/
└── scenes/
```

See `docs/001_architectural_review.md` for full conventions and design decisions.

## Branching
| Branch | Purpose |
|--------|---------|
| `main` | Stable config running on HA instance |
| `develop` | Integration branch |
| `feature/*` | Per-phase or per-system work |

## HA Environment
- **HA OS:** 2026.2.0
- **Hardware:** Mini PC
- **Solar:** SolarEdge inverter
- **EV:** Tesla (multi-car)
- **Jacuzzi:** Smart-switched heater (6000W)
