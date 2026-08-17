# Full 3-Stage Rectification — corrected to the manual's TRUE structure

Prior status (commit df458a9) misplaced solar-arcs/progressions/transits as
"Stage II".  The project canon (notes "The Source Manual", "Rectification
Audit", "Rectification Rebuild") establishes the manual's REAL stages.  This is
now corrected.

## The manual's three stages (authoritative)

| Stage | Goal | Tools |
|-------|------|-------|
| **I** | Ascendant **SIGN** | Fidaria (diurnal vs nocturnal culls ~50% of hours in one step) + Moon sign/application + config + physiognomy |
| **II** | Ascendant **1–4° range** | Rising decan physiognomy + **Arabic Parts + profections** |
| **III** | Ascendant **degree/minute** | Primary Directions + Primary Direction Sequence + **Solar Arc Directions** + arcus vitae |

Predictive hierarchy (highest → lowest): Primary Directions → PD Sequence →
Solar Arcs → Fidaria → Transits/Progressions/Profections.

**Note:** Solar Arcs are a Stage-III tool ("equally accurate"), not Stage II.
Stage II is Arabic Parts + profections.  This module now reflects that.

## Modules

- `rectify_stages.py` — `stage1_score` (sign-level Fidaria sect-cull + Moon
  config), `stage2_score` (Arabic Parts + profections), `solar_arc_hits`
  (Stage III solar-arc directions), `arcus_vitae` (hyleg/kadukhadah).
- `rectify_full.py` — chains I→II→III over the full grid as a vote.
- `placidian_pd.py` — Stage III primary directions (unchanged, validated to
  within a day on the manual's worked examples).
- `mission_control.action_rectify` — menu option 8, now wired to `rectify_full`.

## Current results (15-min grid, 2026-08-17)

| Ticker | Time (UTC) | ASC sign | Sect | Fidaria match | Power |
|--------|-----------|----------|------|---------------|-------|
| GC | 05:15 | Sagittarius | Nocturnal | 6/16 | MODERATE |
| ES | 00:15 | Cancer | Nocturnal | 7/23 | LOW |
| NQ | 05:45 | Libra | Nocturnal | 6/21 | LOW |

All three resolve Nocturnal — the manual's sect-cull working as intended.

## Honest positioning (carried forward, not to be lost)

1. **Stage I + II are the defensible output** — they are the manual's "robust
   level" (sign + 1–4° range).  The codebase already had Fidaria / bounds /
   POF-POS / hyleg / profections (astro_core_v2), so this is a faithful
   assembly, not new math.

2. **Stage III is CORROBORATION ONLY for instruments.**  Prior finding
   (note o1pbi80d): the primary-direction event-match does NOT converge for
   assets (best ±700–1019 days vs the manual's "within 48h"), because market
   events are sparse and continuous, not discrete personal events.

3. Therefore rectified_times_v3.json carries the times as **provisional
   priors**, with Stage I/II support spelled out and Stage III explicitly
   labelled low-power.  Not a lit rectification.
