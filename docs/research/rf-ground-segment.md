---
title: RF ground-segment & link-margin advisor
type: research
category: roadmap-phase-1
status: ingested
ingested: 2026-05-24
sources:
  - file://D:/Beamformer_RF/Driver/TXBFIC_source.py        # F5288 TX driver
  - file://D:/Beamformer_RF/Driver/RXBFIC.py               # F6212 RX driver
  - file://D:/Beamformer_RF/Driver/regmap.txt              # F6212 init / per-channel RX_ch_set
  - file://D:/Beamformer_RF/Thesis_0850193.pdf             # Sampras MSc thesis, private
  - file://D:/Beamformer_RF/Hybrid X-band Phased Array Transmitter.pdf  # private paper
  - https://en.wikipedia.org/wiki/Friis_transmission_equation
  - ITU-R P.618-13                                        # rain attenuation, Earth-space paths
  - ITU-R P.531-14                                        # ionospheric scintillation, S4 index
  - arXiv:2104.07379                                       # phased-array calibration survey, ref only
private_material:
  - F5288 / F6212 datasheets (Renesas / REN) — confidential; do not redistribute.
  - NSPO / NTU course content — local reference only.
---

# RF ground-segment & link-margin advisor — Phase 1 reference

> Post-MVP roadmap reference. The MVP does not consume any RF feature. This file is the operational crystal for the **link-margin advisor (model D)** described in [`../ROADMAP.md`](../ROADMAP.md). Local expertise: Sampras's MSc work on an X-band phased-array beamformer using Renesas F5288 (TX) and F6212 (RX) BFICs hosted on a CORA-Z7 (Zynq-7) with a Yaskawa scan rig.
>
> Treat vendor datasheets and the MSc thesis as **private references** — cite the file paths, never quote. Everything below is derived from Sampras's own driver code, public physics, and the ITU-R / Wikipedia citations above.

---

## 1. What this advisor is for

The MVP loop (Phase 0 in `ARCHITECTURE.md`) recommends operator actions (slew, defer, hand-off) on the basis of space-weather and conjunction signals. It implicitly assumes that the next ground-station pass can carry the resulting command and telemetry traffic. In practice the *link* is the bottleneck more often than the spacecraft is:

- rain fade and gaseous absorption at X-band,
- ionospheric scintillation during geomagnetic storms (NOAA SWPC `S` scale ≥ S1, ITU-R P.531 `S4 > 0.3`),
- per-element calibration drift in a phased array,
- silent element failure that distorts the array pattern.

The link-margin advisor produces an honest `link_margin_dB ± σ` for the next *N* passes, with a typed evidence trail, and feeds that into the Phase 0 ensemble. It is allowed to *downgrade* a recommendation; it is never allowed to *upgrade* one.

---

## 2. Hardware substrate (what is actually on `D:\Beamformer_RF\`)

Verified by reading [`Driver/TXBFIC_source.py`](file://D:/Beamformer_RF/Driver/TXBFIC_source.py), [`Driver/RXBFIC.py`](file://D:/Beamformer_RF/Driver/RXBFIC.py), and [`Driver/regmap.txt`](file://D:/Beamformer_RF/Driver/regmap.txt):

| Component | Visible facts (from driver source, not datasheet) |
|---|---|
| F5288 (TX BFIC) | 4×4 H/V dual-pol channels. SPI command word: `[0x28, ic_address, reg, hi, lo]`. Per-channel CTRL reg base `0x21/0x25/...` (stride 4), per-channel SET reg `0x22/0x26/...`. Gain code 8-bit, `gain_code = limit_range(int((gain / 30.47 + 1) * 255), 255, 0)` → linear coding over ≈ 30 dB. Phase code 6-bit, `phase_code = limit_range(int((phase/5.6) + 0.5), 0x3f, 0)` → **5.6°/LSB**, 360° coverage. Power-on word `0x05 0x80 0x93`. |
| F6212 (RX BFIC) | Mirror part. Per-channel RX address `register_address = 0x16 + channel*8 + subchannel*4`. Gain code 6-bit, `gain_code = limit_range(int((gain+1.4)/0.45+0.5), 0, 63)` → step **0.45 dB**, dynamic range ≈ −1.4 dB to +27 dB. Phase code 6-bit, `phase_code = int((phase%360)/5.6 + 0.5)` → **5.6°/LSB**. |
| CORA-Z7 host | Zynq-7 board (`f5288/CORA-Z7/Cora_Z7_measurement_tool_10.bit` + `..._7s.bit`). Tcl flows: `vivado_server_Lin.tcl`, `vivado_server_Win.tcl`. Python wrappers `JTAGDriver2.py`, `ToolDriver.py`. SPI bus name `SPI_0`. |
| NA / spectrum | `NA.py` drives a network analyzer for S-parameter / pattern capture. `P5026A_for_F5288_measurement.py` is the calibration host script. |
| Yaskawa robotic arm | `Yaskawa.py` + `roboticarm.py` — sweeps probe over the array under test for pattern capture. |
| Measurement archive | `f5288/Measurement/{0601,0604,0612,0613}` — raw captured patterns. Real, in-house, label-able ground-truth dataset. |

These three numbers — **5.6°/step phase**, **~30 dB linear gain range (TX)** or **0.45 dB step (RX)**, and **4×4 dual-pol channel grid** — are the only datasheet-adjacent figures used downstream. They are visible in the user's own code; we do not need the vendor PDFs to ship Phase 1.

---

## 3. Link-margin model — derivation

The link-margin advisor is a deterministic function before it is a "model". It returns `(margin_dB, sigma_dB, evidence)`. Confidence is computed from the standard-deviation budget, not from an LLM.

### 3.1 Free-space and atmospheric chain

Friis transmission equation (free-space path loss only):

```
FSPL_dB = 20·log10(4·π·d / λ)
        = 32.45 + 20·log10(f_MHz) + 20·log10(d_km)
```

Received power:

```
P_rx_dBm = P_tx_dBm + G_tx_dBi - L_tx_dB
        - FSPL_dB
        - L_atm_dB(f, elevation, weather)
        + G_rx_dBi - L_rx_dB
```

`G_tx_dBi`, `G_rx_dBi` come from the antenna pattern at the steering angle (Section 4). Atmospheric loss decomposes into:

```
L_atm = L_gas(ITU-R P.676)
      + L_rain(ITU-R P.618-13, depends on rain rate R_0.01% and elevation)
      + L_cloud(ITU-R P.840)
      + L_scint(ITU-R P.531, S4 index)
```

For X-band LEO downlink ground-station geometry typical of NSPO-class missions:

| Term | Typical clear-sky budget (X-band, elev ≥ 20°) |
|---|---|
| `L_gas` | 0.1 – 0.3 dB |
| `L_rain` (CCDF 0.01%) | 1 – 5 dB |
| `L_cloud` | < 0.5 dB |
| `L_scint` (quiet) | < 0.5 dB |
| `L_scint` (S4 = 0.5, storm-time) | 2 – 6 dB |

The numbers above are illustrative ranges from ITU-R recommendations, not hardcoded constants. The advisor takes them from the SWPC ingestor (`L_scint`) and a regional weather feed (`L_rain`, `L_cloud`).

### 3.2 Link margin

```
C_over_N0_dBHz = P_rx_dBm - 10·log10(k_B · T_sys) - 30
              = P_rx_dBm + 228.6 - 10·log10(T_sys_K)        # k_B·1 W/Hz/K reference

E_b_over_N0_dB = C_over_N0_dBHz - 10·log10(R_b)
Margin_dB     = E_b_over_N0_dB - E_b_over_N0_required_dB
```

`E_b_over_N0_required_dB` is the FEC threshold + implementation loss. For a CCSDS concatenated turbo at `R = 1/2`, threshold is around **0.5 – 1.5 dB** at BER 1e-6; add ~2 dB implementation loss to get ~3 dB required. Treat as config, not as constant.

### 3.3 Uncertainty (σ) budget

`Margin_dB` is reported with a 1σ uncertainty assembled in quadrature:

```
σ_margin² = σ_G_tx² + σ_G_rx² + σ_L_rain² + σ_L_scint² + σ_T_sys² + σ_cal²
```

Defaults for Phase 1 (revise once Day 14 of operation has produced statistics):

| Term | 1σ |
|---|---|
| `σ_G_tx` | 0.3 dB (per-element variation, post-calibration) |
| `σ_G_rx` | 0.3 dB |
| `σ_L_rain` | 0.5 dB (ITU CCDF uncertainty + nowcast lag) |
| `σ_L_scint` | 1.0 dB (S4 forecast uncertainty) |
| `σ_T_sys` | 0.3 dB (LNA temperature, antenna sky-noise variation) |
| `σ_cal` | from `calibration_drift_score` (Section 5) |

The 95% upper bound of `Margin_dB` is `mean - 1.645·σ` (one-sided). The advisor reports both `mean ± σ` and the one-sided 95% bound — the operator should make decisions on the bound, not the mean.

---

## 4. Array factor — beam pointing and element-loss penalty

For a uniformly-spaced rectangular planar array of `M × N` elements (the F5288 substrate is 4×4 dual-pol — treat each polarization as an independent `M=N=4` array for first-order modelling), the normalised array factor at steering angle `(θ_0, φ_0)` evaluated at observation `(θ, φ)` is:

```
AF(θ, φ) = (1/MN) Σ_m Σ_n w_{m,n} · exp(j·k·(m·d_x·(sinθ·cosφ - sinθ_0·cosφ_0)
                                       + n·d_y·(sinθ·sinφ - sinθ_0·sinφ_0)))
```

with `k = 2π/λ`, element spacing `d_x = d_y ≈ λ/2` at the design centre frequency, and `w_{m,n}` the complex weight applied per element (`mag_dB`, `phase_deg`) by the BFIC.

Two operational facts follow:

1. **Beam squint with frequency.** Because phase shifters are *true phase* (not true delay), the main-lobe angle changes with frequency: `Δθ_squint ≈ -(Δf/f_0)·tan(θ_0)`. The 5.6°/step phase resolution → quantisation lobe ≈ `−20·log10(M·N·sin(0.5·Δφ/2))` worse than ideal at large steering angles; for the 4×4 substrate this is ≈ 1 – 2 dB worst case at θ_0 ≥ 45°.
2. **Element-loss penalty.** With `k_fail` elements dead out of `M·N`, the bore-sight gain drops by `20·log10((MN - k_fail)/MN)` and the first sidelobe rises by approximately the same amount. For 4×4 dual-pol (16 elements/pol), a single dead element costs ≈ **0.56 dB**; two dead elements ≈ **1.16 dB**. The advisor uses this to convert `element_failure_count` into a gain delta.

The full pattern, sidelobe levels, and beamwidth come from `f5288/Code/antenna_plotter.ipynb` and `f6212/Analysis/array_factor.ipynb`. The advisor only needs scalar penalties from those notebooks, not the full pattern.

---

## 5. Calibration drift score

The per-element amplitude/phase calibration is the dominant non-environmental source of `σ_cal`. The reference calibration loop is the one in `f5288/Code/calibration.ipynb`, summarised:

1. For each element `(m, n)`:
   1. Drive only this element through the F5288, all others muted.
   2. Sweep the Yaskawa probe to peak.
   3. Record `mag_meas[m,n]_dB` and `phase_meas[m,n]_deg` via the NA / `P5026A_for_F5288_measurement.py`.
2. Subtract the array geometric phase (probe position → element position) to get the *intrinsic* per-element offset.
3. Store as `cal_baseline[m,n] = (mag_dB, phase_deg)`.

Drift score on a later capture:

```python
def calibration_drift_score(cal_baseline, cal_now) -> float:
    """
    Returns max element deviation in dB-equivalent.
    cal_baseline, cal_now: dict[(m,n) -> (mag_dB, phase_deg)]
    """
    max_dev = 0.0
    for key, (m_dB_0, p_deg_0) in cal_baseline.items():
        m_dB_1, p_deg_1 = cal_now[key]
        # Translate phase error into amplitude-equivalent loss
        # via the array-factor coherence penalty:  L_coh ≈ -20·log10(cos(Δφ))
        dphi = (p_deg_1 - p_deg_0 + 180) % 360 - 180
        amp_eq_loss_dB = abs(m_dB_1 - m_dB_0) + max(0.0, -20.0 * math.log10(math.cos(math.radians(dphi))))
        max_dev = max(max_dev, amp_eq_loss_dB)
    return max_dev
```

Thresholds:

| `calibration_drift_score` | Advisor behaviour |
|---|---|
| `< 0.5 dB` | nominal; `σ_cal = 0.2 dB` |
| `0.5 – 1.5 dB` | watch; `σ_cal = drift_score / 2`; flag element with max deviation in evidence |
| `> 1.5 dB` | violate; downgrade any "execute" recommendation to "defer" with reason `calibration_violate` and require operator acknowledgement before re-arm |

The advisor never demands a re-calibration — it only refuses to assume a tight margin.

---

## 6. Interface contract (Phase 0 ensemble compatibility)

The advisor is "model D" in the Phase 0 small-model ensemble (`docs/research/small-model-ensemble-arbiter.md`). It satisfies the same `ModelOutput` Protocol:

```python
@dataclass(frozen=True)
class LinkMarginOutput:
    responded: bool
    confidence: float          # 0.0..1.0; see below
    latency_ms: int
    model_id: str = "rf-link-margin/v1"
    # Domain-specific:
    margin_mean_dB: float
    margin_sigma_dB: float
    margin_p95_lower_dB: float
    dominant_term: str         # e.g. "L_scint", "L_rain", "calibration_drift"
    element_failure_count: int
    evidence: dict             # file refs + numeric inputs
```

`confidence` is *not* the link margin. It is the operator's *trust in the estimate*, computed as:

```python
def confidence_from_sigma(sigma_dB: float, cal_drift: float) -> float:
    # 1 - smooth-step over a sigma budget that operationally makes sense.
    # σ ≤ 0.5 dB  → 0.95
    # σ ≈ 1.5 dB  → 0.5
    # σ ≥ 3.0 dB  → 0.1
    x = max(0.0, sigma_dB - 0.5) / 2.5
    conf = 0.95 * math.exp(-x)
    if cal_drift > 1.5:
        conf = min(conf, 0.3)         # never claim confidence with stale calibration
    return max(0.05, conf)
```

Disagreement contribution to the Arbiter (`docs/research/small-model-ensemble-arbiter.md` §5):

```python
# When the action drafter (model C) proposes "execute downlink" but
#   margin_p95_lower_dB < 3 dB OR element_failure_count > 0:
# add +0.4 to the disagreement score and tag dominant_term in evidence.
```

The Arbiter then handles the rest by its existing rules — abstain on disagreement, escalate on high-risk classes.

---

## 7. What to actually build (Phase 1 checklist)

- [ ] Pick a single reference ground station. Hard-code `lat, lon, alt, G_rx_dBi, T_sys_K`.
- [ ] Stand up a `link_budget.py` module implementing Sections 3.1 – 3.2 as pure functions. No I/O. Unit-test with a synthetic pass.
- [ ] Add an `array_factor.py` helper for the gain penalty in Section 4. Lift the math from `array_factor.ipynb`; do not reimplement the whole notebook.
- [ ] Add a `calibration_baseline.json` loader. Seed with a stub of the most recent `f5288/Measurement/...` capture metadata. Real recalibrations are out of scope for Phase 1; we only consume them.
- [ ] Subscribe to two new fields from the Phase 0 SWPC ingestor (`docs/research/noaa-swpc-api.md`): `S` scale and `S4` index proxy. Map onto `L_scint` per Section 3.1.
- [ ] Stub a regional-weather feed for `L_rain`. Treat the feed as an opaque function returning `(rain_rate_mm_per_h, cloud_attenuation_dB)`; Phase 1 does not own that integration.
- [ ] Wire `model D` into the Arbiter (`spacesharks/core/arbiter.py`) via the existing `Protocol` injection. Do not modify the Arbiter logic; only add a new disagreement contribution.
- [ ] Build one replay where a Phase 0 "execute downlink" recommendation flips to "defer" because `model D` reports `margin_p95_lower_dB = 2.1 dB` with `dominant_term = "L_scint"` during a SWPC `S2` storm. The evidence card cites the SWPC URL + the calibration baseline file.
- [ ] Build one negative replay where calm conditions produce `margin_p95_lower_dB ≥ 6 dB, confidence ≥ 0.9` and the original recommendation passes unchanged.

---

## 8. Non-goals for Phase 1

- No real-time control of any ground station. Advisory only, never actuation.
- No multi-station scheduling — Phase 5 (fleet view) owns that.
- No Doppler/polarisation fine-tuning beyond what the link-budget already captures.
- No re-derivation of vendor register maps; cite Sampras's drivers as authoritative.
- No public release of measurement archive files. They stay on `D:\` until cleared.

---

## 9. Open uncertainties (to revisit before Phase 2 starts)

- Whether `σ_L_scint = 1.0 dB` is realistic for an S2 vs an S4 storm — Section 3.3 number is a placeholder. The first 30 days of operation should produce an empirical posterior.
- Whether the 4×4 dual-pol substrate should be modelled per-pol (two arrays) or jointly. Joint is more accurate but doubles model complexity.
- Element-failure detection rule. Section 4 gives the bore-sight penalty, but detection itself belongs in Phase 3 (`docs/research/signal-processing.md` — CFAR on per-element residual).

---

## 10. Related notes

- Roadmap context: [`../ROADMAP.md`](../ROADMAP.md).
- Phase 0 ensemble interface: [`small-model-ensemble-arbiter.md`](small-model-ensemble-arbiter.md).
- Source-of-truth catalog: [`INDEX.md`](INDEX.md).
- Phase 3 detection rules consume the same measurement archive: [`signal-processing.md`](signal-processing.md).
- Thermal posture can interact with calibration (PA temp drift): [`thermal-and-mechanical.md`](thermal-and-mechanical.md).
