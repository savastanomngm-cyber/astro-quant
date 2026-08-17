# Full 3-Stage Rectification — Zoller's Method (Implemented)

Status of the event-driven rectification rebuild, per *A Rectification Manual*
(3rd ed.).  Update the standing "Stage III only" state to the FULL method.

## The three stages (as the manual orders them)

| Stage | Technique | Precision | Module |
|-------|-----------|-----------|--------|
| I | Fidaria (Persian chronocrators, Table B-2) | coarse ±hours | `rectify_stages.stage1_score` |
| II | Solar arcs (direct + converse `c.s.a.`) + secondary progressions (`prog. Moon/Sun`) + outer-planet transits (Saturn/Uranus) | ±1–2h at 0.5° partile | `rectify_stages.stage2_score` |
| III | Placidus PT primary directions | ±minutes ("fine sandpaper") | `placidian_pd.direction` (validated, see below) |

`rectify_full.py` runs all three as a **vote over the full 24h grid** (not a
hard cut-off funnel), so Stage III can override a weak Stage II — the manual's
"corroboration" intent.  `mission_control.action_rectify()` (menu option 8) now
wires to this.

## Why Stage II matters (the answer to "how do you rectify a 25-year-old?")

The manual rectifies young charts routinely.  It never relies on primary
directions alone.  A 30-year-old instrument has only ~16 Placidus PD dates but
~30° of solar arc and ~360° of progressed-Moon motion — Stage II provides the
*dense* timing signal that Stage III then refines.  That was the missing
mechanism; it is now built.

## Stage II is disciplined, not a broad sweep

Ch.14's warning (against manufacturing spurious near-matches) is respected:
- Partile orbs (0.5°), not multi-degree.
- Only the manual's cited signatures: `c.s.a.` (converse solar arc) of Sun/Moon
  and the event's own planet to ASC/MC; `prog.` Moon/Sun to ASC/MC; Saturn &
  Uranus transits to the event planet/angles.
- An event is timed by its OWN semantic planet (Mars crash → Mars contact,
  etc.), same discipline as Stage III.

## Current results (15-min grid, full method, 2026-08-17)

| Ticker | Time (UTC) | Fid | SA/prog/tr | PD | Combined | Power |
|--------|-----------|-----|------------|-----|----------|-------|
| GC | 16:00 | 5.0 | 7.3 | 2.2 | 0.608 | **LOW** |
| ES | 22:00 | 5.5 | 9.3 | 4.5 | 0.915 | **MODERATE** |
| NQ | 17:00 | 4.0 | 10.0 | 4.5 | 0.744 | **LOW** |

Persisted in `rectified_times_v3.json` with explicit `power` + `status` flags.

## Honest conclusion (not to be lost)

The engine and all three stages are **correct** (Placidus PT validated to
within a day on the manual's worked examples).  But the **statistical power
remains modest** for 30-year-old instruments: the winner-vs-runner-up gap is
narrow (0.02–0.16), so these are **provisional priors, not verdicts**.  The
manual assumes 70–90yr lifespans with 8–15 tightly-dated *personal* events;
futures contracts born in 1974–1997 with 20+ noisy *market* events sit at the
low end of the method's range.  Times are fit for use as a weak prior in
downstream work, not as a lit rectification.
