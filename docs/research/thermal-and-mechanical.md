# Thermal & mechanical advisory (Phase 2)

> Post-MVP design note. Local expertise: Sampras's satellite-mechanical-systems coursework (NTU/NTUT) covering spacecraft thermal environment, thermal control design, and a Rosetta lander case study.

## Why this module belongs in Spacesharks

Many "weird" operator decisions are actually thermal-mechanical decisions in disguise:

- A momentum dump scheduled at the wrong attitude can spike radiator temperatures.
- An eclipse transition can drop a battery into a low-voltage band that disables a heater string.
- A long sun-pointing for a downlink can over-soak a payload past its qualification limit.
- An unplanned maneuver can move a moving-mass appendage (deployable, gimbal) outside its slewed envelope.

The MVP loop has no read on any of this. Phase 2 adds a small "posture advisor" that asks: *given the maneuver the system is about to recommend, what does the thermal/mechanical state look like in the following N orbits, and is it inside the safe envelope?*

## What we already have locally

`D:\career\ee\衛星機械系統\` is a complete starter library:

- **`熱控設計.pdf`** — thermal control design notes. Covers passive (MLI, paint, radiators) and active (heaters, loop heat pipes) control. Includes worked thermal-balance examples — the equations to lift into the model.
- **`06_衛星熱環境介紹 _Homework.pdf`** — spacecraft thermal environment homework. Solar flux, albedo, IR, eclipse fraction as a function of orbit geometry. Direct inputs to a thermal posture model.
- **`Rosetta羅賽塔\`** — Rosetta case study folder, including Sampras's own `20200319_羅賽塔.docx` writeup, an `.stl` mesh, an `HW1 CHECK LIST.xlsx`, and a reference folder with primary literature (see [`case-studies-rosetta.md`](case-studies-rosetta.md)).
- **`satellite general survey\各國衛星整理\`** — placeholder for a multi-mission survey; currently empty, intentionally left in the catalog to be refilled once Phase 4 (lessons-learned corpus) gets serious.

Full catalog: [`INDEX.md`](INDEX.md).

## Feature set this can produce

| Feature | How the local material supports it |
|---|---|
| `thermal_envelope_state` | Solar/albedo/IR inputs (homework PDF) + a coarse box model of the bus (thermal control PDF) → predicted temperature band per major subsystem over the next N orbits. |
| `eclipse_transition_risk` | Eclipse-fraction equations from the homework PDF + battery state-of-charge proxy → flag windows where heater duty cycle would exceed available power. |
| `attitude_to_thermal_check` | For any recommended attitude change, compare predicted hot-/cold-side temperatures vs. configured qualification limits. Veto or flag if exceeded. |
| `appendage_envelope_check` | Static config of deployable/gimbal envelopes + maneuver delta → boolean "inside / outside envelope". Crude is fine; the point is to abstain rather than approve. |
| `lessons_learned_link` | Whenever a flag fires, attach at least one citation from the Phase 4 corpus (start with Rosetta/Philae). |

## Where this plugs into the architecture

Same ensemble pattern as Phase 0 and Phase 1:

```
OpenClaw → small model E (Phase 2: thermal/mechanical posture)   ← new
        → small model F (Phase 2: attitude-to-thermal pre-check) ← new
        → Nemotron (escalate if E or F vetos a Phase 0/1 recommendation)
```

Output contract: `{posture: "nominal"|"watch"|"violate", subsystem: str, predicted_band_C: [low, high], evidence: [file-ref, ...]}`.

A "violate" from model E or F is allowed to *downgrade* a Phase 0/1 "execute" to "defer" or "monitor only". It is not allowed to *upgrade* anything — thermal data alone never argues for more action.

## What to actually build (Phase 2 checklist)

- [ ] Pick a single reference bus (LEO smallsat, sun-pointing default). Hard-code geometry first.
- [ ] Extract the solar / albedo / IR flux equations from `06_衛星熱環境介紹 _Homework.pdf` into a `thermal_env.py` helper.
- [ ] Extract the box-model thermal-balance form from `熱控設計.pdf` into a `thermal_model.py` helper. Three nodes is enough (payload, battery, radiator).
- [ ] Express qualification limits as a YAML config keyed by subsystem.
- [ ] Implement model E deterministically. Confidence comes from how close the predicted band is to a configured limit, *not* from an LLM.
- [ ] Add appendage envelope check (model F) as a pure config + geometry lookup.
- [ ] Write a demo replay where a recommended attitude maneuver is downgraded to "defer" because model E predicts payload > qualification high temp during the next 2 orbits, and Nemotron's evidence card cites the Rosetta thermal-shadowing lesson.
- [ ] Add one negative test: nominal sun-pointing must produce `posture: "nominal"` with no flags.

## Out of scope for Phase 2

- Real FEM thermal simulation. The point is fast, interpretable, conservative — not accurate-to-the-Kelvin.
- Multi-bus generalisation. Pick one bus, do it well, document the assumptions.
- Structural dynamics (modal analysis, jitter). Out of scope until there is a clear operator question that needs it.

## Related notes

- The Rosetta/Philae case study that seeds the lessons-learned corpus: [`case-studies-rosetta.md`](case-studies-rosetta.md).
- Link margin during/after thermal transitions can interact with Phase 1: [`rf-ground-segment.md`](rf-ground-segment.md).
- Roadmap context: [`../ROADMAP.md`](../ROADMAP.md).
