---
title: Thermal & mechanical posture advisor
type: research
category: roadmap-phase-2
status: ingested
ingested: 2026-05-24
sources:
  - file://D:/career/ee/衛星機械系統/熱控設計.pdf                  # NSPO-marked, private
  - file://D:/career/ee/衛星機械系統/06_衛星熱環境介紹 _Homework.pdf  # NSPO-marked, private
  - file://D:/career/ee/衛星機械系統/Rosetta羅賽塔/                # case-study source folder
  - https://en.wikipedia.org/wiki/Stefan%E2%80%93Boltzmann_law
  - https://en.wikipedia.org/wiki/View_factor
  - Gilmore, D. G. (ed.) — Spacecraft Thermal Control Handbook, vol. I (AIAA, 2002) — textbook reference, public
  - Wertz, J. R. (ed.) — Space Mission Engineering: The New SMAD (Microcosm, 2011) — public
private_material:
  - 熱控設計.pdf, 06_衛星熱環境介紹.pdf bear NSPO proprietary markings. Cite by file path only.
  - Do not redistribute slide content. Equations below are textbook-grade (Gilmore / SMAD) and are not derived from those slides.
---

# Thermal & mechanical posture advisor — Phase 2 reference

> Post-MVP roadmap reference. Local expertise: Sampras's satellite-mechanical-systems coursework (NTU/NTUT, NSPO-sourced slides) plus a Rosetta case study. This file is the operational crystal for **model E (thermal posture)** and **model F (attitude-to-thermal pre-check)** as introduced in [`../ROADMAP.md`](../ROADMAP.md).
>
> All equations here are textbook-grade (Gilmore *Spacecraft Thermal Control Handbook* / SMAD). The NSPO slides are referenced only as private background — never quoted.

---

## 1. What this advisor is for

Many operator actions look like attitude or scheduling decisions but are actually thermal-mechanical decisions:

- A momentum dump scheduled at the wrong attitude can spike radiator temperatures.
- An eclipse transition can drop a battery into a low-voltage band that disables a heater string.
- A long sun-pointing for downlink can over-soak a payload past its qualification limit.
- An unplanned maneuver can drive a deployable / gimbal outside its slewed envelope.

The MVP has no read on any of this. Phase 2 adds a small advisor that, for any recommended attitude or scheduling change, predicts the thermal/mechanical state across the next *N* orbits and either confirms, downgrades, or rejects the recommendation. **It is allowed only to downgrade or veto** — thermal data alone never argues for *more* action.

---

## 2. Thermal environment model (LEO baseline)

LEO satellites see four heat-flux contributions plus radiative emission to deep space. The textbook decomposition (Gilmore §2):

```
Q_solar  = α_s · A_proj_solar · J_solar                         # direct solar
Q_albedo = α_s · A_proj_earth · a · J_solar · F_view_earth      # Earth-reflected
Q_IR     = ε   · A_proj_earth · σ · T_earth^4 · F_view_earth    # Earth IR
Q_int    = internal dissipation (electronics, payload)
Q_emit   = ε   · A_total      · σ · T_sat^4                     # to deep space
```

Symbols and reference values (for a generic LEO bus; tune per mission):

| Symbol | Meaning | Typical value |
|---|---|---|
| `J_solar` | Solar constant | 1361 W/m² (vary ±3.4% over a year) |
| `α_s` | Solar absorptance | 0.2 – 0.95 (paint dependent) |
| `ε` | IR emittance | 0.05 (polished Al) – 0.92 (white paint) |
| `a` | Earth albedo | 0.30 – 0.35 |
| `T_earth` | Earth effective IR temp | ~255 K |
| `σ` | Stefan–Boltzmann constant | 5.670374419 × 10⁻⁸ W/m²/K⁴ |
| `F_view_earth` | View factor to Earth | depends on altitude; `(R_e / (R_e + h))²` for a flat plate at nadir |
| `A_proj_*` | Projected area in flux direction | geometry-dependent |

The instantaneous balance is `m · c_p · dT/dt = Q_solar + Q_albedo + Q_IR + Q_int − Q_emit`. The advisor does **not** solve this finely. It uses a coarse lumped model (Section 3) tuned against published mission data and the bus-specific config.

### 2.1 Solar β-angle and eclipse fraction

The β-angle is the angle between the orbit plane and the sun vector. For a circular orbit, the eclipse fraction per orbit (Gilmore §2.4):

```
β_crit = arcsin( R_e / (R_e + h) )

eclipse_fraction(β, h) =
    0                                                if |β| ≥ β_crit
    (1/π) · arccos( sqrt(h² + 2·R_e·h) / ((R_e + h)·cos β) )   otherwise
```

For `h = 600 km`, `R_e = 6378 km`: `β_crit ≈ 66°`; eclipse fraction at `β = 0` is `(1/π)·arccos(sqrt(h²+2·R_e·h)/(R_e+h)) ≈ 0.36` (~35 minutes of a ~96-minute orbit).

The advisor watches β as a slow-moving driver: β trends across days/weeks govern thermal-stress envelopes more than any single recommendation does.

### 2.2 Conduction reference

Fourier's law (1D steady):

```
Q_cond = k · A · (T_hot − T_cold) / L
```

Used by the advisor only as a sanity check between adjacent nodes (e.g., payload-to-radiator strap). Treat `k`, `A`, `L` as per-link config.

---

## 3. Three-node lumped bus model

The advisor uses three thermal nodes — payload, battery, radiator — connected by conductances `G_ij` (W/K) and exchanging radiation with the environment computed in Section 2. This is the *minimum* model that lets the advisor reason about the operational failure modes listed in Section 1.

```python
# spacesharks/thermal/lumped_three_node.py  (Phase 2 sketch)
from dataclasses import dataclass

SIGMA = 5.670374419e-8  # W/m²/K⁴

@dataclass(frozen=True)
class Node:
    name: str          # "payload" | "battery" | "radiator"
    m_cp: float        # J/K (thermal capacitance)
    alpha_s: float     # solar absorptance of its external face (0 if internal)
    eps: float         # IR emittance
    A_ext: float       # external area, m²
    A_proj_sun: callable  # f(attitude_quat, t) -> projected area to sun, m²
    A_proj_earth: callable # f(attitude_quat, t) -> projected area to Earth, m²
    T_qual: tuple[float, float]  # (T_low_K, T_high_K) qualification band

@dataclass(frozen=True)
class Bus:
    nodes: list[Node]
    G: dict[tuple[str, str], float]  # conductance W/K between node pairs
    Q_int: dict[str, callable]       # f(t, mode) -> internal dissipation W

def dT_dt(bus, T, attitude, t, mode, env):
    # env exposes J_solar, T_earth, albedo, eclipse(t)
    out = {}
    for n in bus.nodes:
        in_eclipse = env.eclipse(t)
        A_sun = 0.0 if in_eclipse else n.A_proj_sun(attitude, t)
        A_e   = n.A_proj_earth(attitude, t)
        Q_sol = n.alpha_s * A_sun * env.J_solar
        Q_alb = 0.0 if in_eclipse else n.alpha_s * A_e * env.albedo * env.J_solar
        Q_ir  = n.eps * A_e * SIGMA * env.T_earth**4
        Q_emt = n.eps * n.A_ext * SIGMA * T[n.name]**4
        Q_cnd = sum(bus.G[(n.name, m)] * (T[m] - T[n.name])
                    for (a, m) in bus.G if a == n.name)
        Q_int = bus.Q_int[n.name](t, mode)
        out[n.name] = (Q_sol + Q_alb + Q_ir + Q_int + Q_cnd - Q_emt) / n.m_cp
    return out
```

A naive forward Euler integration with a 10-second step is good enough for the next-N-orbits posture call. The advisor is not a thermal sim — it is a guard rail.

---

## 4. Feature outputs

| Feature | How it is computed |
|---|---|
| `posture` ∈ {`nominal`, `watch`, `violate`} | For each node, distance of predicted T to `T_qual` over next N orbits. `nominal` = always inside band with > 5 K margin; `watch` = ≤ 5 K margin; `violate` = predicted outside band at any time. Worst-case across nodes wins. |
| `subsystem` | Name of node driving the worst case. |
| `predicted_band_K` | `(min T over horizon, max T over horizon)` for that node. |
| `eclipse_transition_risk` | `True` if predicted battery node drops below `T_low + 2 K` *and* SoC proxy < 40% during eclipse. SoC proxy is operator-supplied; advisor never owns SoC. |
| `attitude_to_thermal_check` | For the *proposed* attitude (model F), recompute `posture`. If new posture is worse than current, advisor returns `veto` with reason. |
| `appendage_envelope_check` | Pure config + geometry. `True` if the recommended action would slew a deployable/gimbal across its locked envelope. |
| `lessons_learned_link` | At least one `case_id` from the Phase 4 corpus when posture ≠ `nominal`. |

The arbitration rule:

```
posture = nominal  → no action; advisor returns confidence 0.9, evidence card minimal
posture = watch    → downgrade any "execute" to "monitor"; evidence card lists worst node
posture = violate  → downgrade to "defer"; evidence card cites lesson; escalate to Nemotron
```

---

## 5. Interface contract

Compatible with the Phase 0 ensemble (`docs/research/small-model-ensemble-arbiter.md`):

```python
@dataclass(frozen=True)
class ThermalPostureOutput:
    responded: bool
    confidence: float
    latency_ms: int
    model_id: str = "thermal-posture/v1"
    posture: Literal["nominal", "watch", "violate"]
    subsystem: str | None
    predicted_band_K: tuple[float, float] | None
    eclipse_transition_risk: bool
    lessons_learned: list[str]           # corpus case_ids
    evidence: dict
```

Disagreement contribution: any `posture in {"watch","violate"}` combined with a Phase 0 "execute" or Phase 1 "go" recommendation adds `+0.4` to the disagreement score (cf. arbiter §5) and tags `subsystem` in evidence.

---

## 6. Lessons-learned linkage (Rosetta seed)

Phase 4 (`docs/research/case-studies-rosetta.md`) seeds the corpus with Rosetta/Philae. The thermal advisor specifically queries the corpus by `class`:

| Phase 2 feature | Corpus classes to query |
|---|---|
| `posture = violate` on payload (thermal shadowing predicted) | `thermal_shadowing` |
| `eclipse_transition_risk = True` | `post-event_power_loss` |
| `appendage_envelope_check = True` | `mechanical_anchoring`, `harpoon_failure` |
| `attitude_to_thermal_check = veto` | combine all three above |

The corpus lookup returns at most three entries per evidence card. Operators must see the "limits of analogy" section of each.

---

## 7. Confidence calibration

`confidence` for `ThermalPostureOutput` is **not** a softmax. It is composed:

```python
def thermal_confidence(predicted_band_K, T_qual, model_uncertainty_K):
    T_min, T_max = predicted_band_K
    T_low, T_high = T_qual
    # Margin to nearest qualification limit
    margin_K = min(T_min - T_low, T_high - T_max)
    # 1σ uncertainty of the lumped model
    z = margin_K / max(model_uncertainty_K, 0.5)
    # Confidence drops smoothly as the band approaches limits
    if z >= 3:  return 0.95
    if z >= 1:  return 0.7
    if z >= 0:  return 0.4
    return 0.15
```

`model_uncertainty_K` is a per-bus-config number. Defaults: 3 K for payload, 5 K for battery, 8 K for radiator. Tune from the first 30 days of on-orbit telemetry.

The model **must never report confidence ≥ 0.9 in `watch` or `violate` states**. That guarantee is part of the Trust Model (`docs/TRUST.md`).

---

## 8. What to actually build (Phase 2 checklist)

- [ ] Pick a single reference bus (LEO smallsat, sun-pointing default). Hard-code geometry, mass, surface optical properties.
- [ ] Implement `thermal_env.py` with the equations in Section 2 and 2.1. Pure functions, unit-tested against published numbers (e.g., 600 km circular eclipse fraction at β=0 ≈ 0.36).
- [ ] Implement `lumped_three_node.py` per Section 3. Single forward-Euler integrator, no third-party ODE dep.
- [ ] Express `T_qual` per subsystem as YAML config keyed by node name.
- [ ] Implement model E as a deterministic posture call returning `ThermalPostureOutput`.
- [ ] Implement model F as a thin wrapper around model E that takes a proposed attitude and reports `veto` if posture worsens.
- [ ] Implement appendage envelope check as a pure config + quaternion lookup. No physics.
- [ ] Wire both models into the Phase 0 Arbiter via the existing `Protocol` injection. Reuse the arbiter; do not fork it.
- [ ] One replay: recommended attitude maneuver flips from "execute" to "defer" because model E predicts payload > qualification high temp during the next 2 orbits; Nemotron evidence card cites the Rosetta thermal-shadowing lesson.
- [ ] One negative replay: nominal sun-pointing produces `posture = nominal` with no flags.

---

## 9. Non-goals for Phase 2

- No FEM thermal simulation. The point is fast, interpretable, conservative — not accurate-to-the-Kelvin.
- No multi-bus generalisation. Pick one bus, do it well, document assumptions.
- No structural dynamics (modal analysis, jitter). Out of scope until there is a concrete operator question that needs it.
- No automated control. Advisory only.

---

## 10. Open uncertainties

- Conductance values `G_ij` are the largest unknown. Initial estimates from Gilmore-style scaling will be wrong by 30–50%; the model must be re-tuned against on-orbit telemetry before its veto power can be trusted.
- View-factor approximations break down for spinning or rapidly-slewing platforms; the LEO sun-pointing default keeps us safe. Flag explicitly when the proposed attitude implies high body rates.
- The `eclipse_transition_risk` rule assumes the operator supplies a SoC proxy. If they cannot, the rule must abstain rather than approve.

---

## 11. Related notes

- Roadmap context: [`../ROADMAP.md`](../ROADMAP.md).
- Phase 0 arbiter the advisor plugs into: [`small-model-ensemble-arbiter.md`](small-model-ensemble-arbiter.md).
- Phase 1 RF advisor whose link margin can be cross-coupled (PA temperature drift): [`rf-ground-segment.md`](rf-ground-segment.md).
- Phase 3 small-model classifiers consume the same Q internal trace: [`signal-processing.md`](signal-processing.md).
- Phase 4 seed corpus: [`case-studies-rosetta.md`](case-studies-rosetta.md).
- Source-of-truth catalog: [`INDEX.md`](INDEX.md).
