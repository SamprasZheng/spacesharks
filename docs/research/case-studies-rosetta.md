---
title: Rosetta / Philae case study — corpus seed
type: research
category: roadmap-phase-4
status: ingested
ingested: 2026-05-24
sources:
  - file://D:/career/ee/衛星機械系統/Rosetta羅賽塔/reference/Rosetta_Lander_Philae_Investigations.pdf
  - file://D:/career/ee/衛星機械系統/Rosetta羅賽塔/reference/Glassmeieretal-2007.pdf
  - file://D:/career/ee/衛星機械系統/Rosetta羅賽塔/reference/reference website.txt
  - file://D:/career/ee/衛星機械系統/Rosetta羅賽塔/20200319_羅賽塔.docx     # private writeup
  - file://D:/career/ee/衛星機械系統/Rosetta羅賽塔/Rosetta.stl                # CAD mesh, visual aid
  - https://www.esa.int/Science_Exploration/Space_Science/Rosetta
  - Glassmeier, K.-H. et al. (2007) — The Rosetta Mission — Space Sci Rev 128:1–21
  - Biele, J. et al. (2015) — The landing(s) of Philae and inferences about comet surface mechanical properties — Science 349:aaa9816
private_material:
  - 20200319_羅賽塔.docx — Sampras's own coursework writeup; use as tone/structure model, not as authoritative citation.
  - Causal-chain claims in §3 below must be re-verified against the Philae Investigations PDF before the corpus entry ships.
---

# Rosetta / Philae case study — Phase 4 corpus seed

> Post-MVP roadmap reference. Phase 4 is the **lessons-learned corpus** — a small, hand-curated set of real prior incidents that Nemotron can cite when it escalates. The corpus has to start narrow; this file seeds it with the Rosetta / Philae landing anomaly because the source material is already on `D:\`, the causal chain is multi-causal in instructive ways, and Sampras has hands-on coursework familiarity with it.
>
> Nothing in this file is a substitute for reading [`Rosetta_Lander_Philae_Investigations.pdf`](file://D:/career/ee/衛星機械系統/Rosetta羅賽塔/reference/Rosetta_Lander_Philae_Investigations.pdf). The causal-chain summary in §3 is *to be verified* on ingest, not to be relied on as the citation itself.

---

## 1. Why this case is the first corpus entry

Phase 4 only earns its slot in Spacesharks if every Nemotron escalation can cite at least one *real, traceable* prior incident. Rosetta/Philae fits four hard criteria:

1. **Documented in primary literature.** Biele et al. 2015 (*Science*) and the Philae Investigations report give a peer-reviewed causal chain — we do not have to paraphrase rumor.
2. **Multi-cause.** Anchoring failure + thruster non-firing + post-bounce thermal shadowing. Each cause maps onto a *different* Spacesharks advisor (Phase 2 thermal, Phase 2 mechanical envelope, Phase 4 itself).
3. **Local familiarity.** Sampras's own coursework folder (`D:\career\ee\衛星機械系統\Rosetta羅賽塔\`) contains a writeup, a `.stl` mesh, and a curated reference list. The corpus entry can be authored without secondhand summarisation.
4. **The lessons transfer to LEO.** The mission was deep-space, but the failure modes (thermal envelope violation after an unplanned attitude change, mechanical hold-down not verified before commit) are universal.

---

## 2. Corpus entry schema

Every corpus entry is a Markdown file with YAML frontmatter. The Phase 4 loader (`spacesharks/corpus/loader.py`, to be built) returns entries by `class` or `phase`.

```yaml
---
case_id: rosetta-philae-2014
mission: Rosetta / Philae
event_date: 2014-11-12
ingested: 2026-05-24
classes:
  - thermal_shadowing
  - mechanical_anchoring
  - harpoon_failure
  - post-event_power_loss
maps_to_phase: [2, 4]
sources:
  - Biele, J. et al. (2015), Science 349:aaa9816
  - Glassmeier, K.-H. et al. (2007), Space Sci Rev 128:1–21
  - https://www.esa.int/Science_Exploration/Space_Science/Rosetta
trigger_conditions:
  # Each entry is a boolean predicate over Phase-1/2/3 features.
  - phase: 2
    feature: posture
    value: violate
    extra: subsystem == "payload" and predicted_shadowing_min > 60
  - phase: 2
    feature: appendage_envelope_check
    value: true
limits_of_analogy:
  - Comet surface mechanics ≠ LEO debris environment.
  - Deep-space comm cadence ≠ LEO pass cadence — recovery timelines do not transfer.
  - Philae was a lander; Spacesharks today reasons about orbiting platforms only.
---
```

The frontmatter is the load-bearing part. The body is for operators; it has three required sections (§3 below).

---

## 3. Body sections (required)

### 3.1 What happened (one paragraph, neutral)

> *To be filled on ingest, against `Rosetta_Lander_Philae_Investigations.pdf` and Biele et al. 2015.* Draft outline only:
>
> On 2014-11-12, the Philae lander separated from Rosetta and descended to comet 67P/Churyumov–Gerasimenko. The active anchoring sub-system (harpoons) did not fire on touchdown, and the cold-gas thruster intended as a backup hold-down did not activate. Philae bounced twice and came to rest in a final attitude where solar illumination was substantially reduced relative to the planned site, eventually leading to loss of power once the primary battery was exhausted. Partial recovery occurred in 2015 as the comet approached perihelion and illumination improved.

### 3.2 Causal chain (each bullet ends with a citation pointer)

> *Each bullet to be verified against the source PDF with page numbers on ingest.* Draft outline only:
>
> - Harpoon anchoring system did not fire on touchdown — *[src: Biele 2015 §2; Philae Investigations §X]*
> - Cold-gas thruster intended as a backup hold-down did not activate — *[src: Philae Investigations §X]*
> - Lander bounced; final resting site exposed Philae to reduced solar flux relative to the planned site — *[src: Biele 2015 §3]*
> - Reduced illumination dropped solar-array power below threshold for sustained science operations — *[src: Biele 2015 §4]*
> - Recovery depended on seasonal illumination, which arrived too late and too weakly for full mission objectives — *[src: ESA mission summary]*

### 3.3 Decision points that mattered

This is the operator-relevant payload. From the public literature:

- **Pre-commit verification of the anchoring sub-system.** The harpoons were known to be a single-shot, hard-to-test mechanism; the criticality of their firing was high but the pre-commit verification was constrained by environment.
- **Backup hold-down enablement.** The cold-gas thruster was an available fallback; its non-activation was a contributing factor and a reminder that fallbacks must be exercised on the day, not just designed for.
- **Site selection vs descent uncertainty.** The chosen site optimised illumination; the bounce envelope exceeded the design margin.

Each of these maps onto a class of Phase 2 / Phase 4 check Spacesharks should make on a *different* mission before approving an analogous action.

### 3.4 Trigger conditions in Spacesharks (formal)

Reproduced from the frontmatter, expanded:

| Spacesharks signal | Trigger | Reason for citing this case |
|---|---|---|
| `model E (thermal): posture = violate` with `subsystem = payload` and predicted shadow > 60 min | Recommended action would put payload in extended shadow | "Reduced illumination → power loss" sub-chain. |
| `model F (attitude-to-thermal): veto` for an attitude change that crosses an envelope | Hold-down / deployable analog | "Anchoring not verified before commit" lesson. |
| Phase 0 model A returns `CONJUNCTION` with `risk ≥ 7` and a maneuver is proposed | Pre-commit verification analogue | Reminder that "designed-for" ≠ "exercised on the day". |

The loader returns at most three Rosetta-tagged entries per call; the operator must see §3.3 and §3.5.

### 3.5 Limits of analogy (required)

This is the section most likely to be skipped, which is why it is the most important.

- **Comet surface mechanics ≠ LEO debris environment.** Anchoring on a low-gravity body is not the same as orbital attitude hold; bouncing dynamics do not apply.
- **Deep-space comm cadence ≠ LEO pass cadence.** Philae's recovery timeline was bounded by communication windows that have no LEO analogue. Do not infer LEO recovery timing from this case.
- **Lander ≠ orbiter.** Spacesharks today reasons about orbiting platforms only; the corpus entry exists to inform thermal/mechanical reasoning patterns, not to suggest landing decisions.
- **Single-shot mechanisms vs continuously controllable subsystems.** Philae's harpoons were single-shot; most LEO actuators are not. Lessons about pre-commit testing transfer; lessons about "what to do after the action" do not.

---

## 4. Loader contract

```python
# spacesharks/corpus/loader.py (Phase 4 sketch)
from dataclasses import dataclass

@dataclass(frozen=True)
class CaseEntry:
    case_id: str
    mission: str
    event_date: str
    classes: frozenset[str]
    maps_to_phase: frozenset[int]
    body_path: Path
    sources: list[str]
    has_limits_of_analogy: bool   # True only if §3.5 is non-empty

class CorpusLoader:
    def __init__(self, root: Path): ...
    def lookup_by_class(self, klass: str, limit: int = 3) -> list[CaseEntry]: ...
    def lookup_by_phase(self, phase: int, limit: int = 3) -> list[CaseEntry]: ...
    def assert_shippable(self, entry: CaseEntry) -> None:
        """Raises if §3.5 is missing or if any source URL has not been re-archived."""
```

The Arbiter consults `CorpusLoader.lookup_by_class()` whenever it constructs a Nemotron escalation payload (see arbiter §7). `assert_shippable` is the mechanism that enforces the "limits-of-analogy must be populated" guarantee from the Trust Model.

---

## 5. Re-archiving discipline

Open-web sources rot. The `reference website.txt` file in the Rosetta folder is a curated link list that may not survive a decade. On ingest:

1. Save the current HTML / PDF of each URL into Spacesharks's own evidence log (write-once, content-hashed).
2. Record the archive hash on the `source:` line, alongside the URL.
3. Periodically re-fetch and verify the hash; flag drift, do not silently update.

This is not optional. A corpus that cites dead links is worse than no corpus.

---

## 6. What to actually build (Phase 4 checklist)

- [ ] Author `corpus/rosetta-philae-2014.md` with frontmatter from §2 and body sections from §3, after re-verifying each bullet against the source PDFs. Add explicit page numbers.
- [ ] Implement `CorpusLoader` per §4.
- [ ] Implement the re-archive job per §5. Persist into `spacesharks/evidence/` (write-once).
- [ ] Wire the loader into the Arbiter's Nemotron-escalation payload construction. The payload must include `case_id` and `limits_of_analogy`.
- [ ] Add a UI / log toggle: every cited case must be dismissable by the operator; record dismissals as drift signal for re-tuning trigger conditions.
- [ ] **Do not** declare the corpus "live" with one entry. Pick a second mission/regime (suggested: a LEO momentum-management incident with thermal coupling) before promoting the loader into production.

---

## 7. Non-goals for Phase 4

- No auto-generated cases. Every entry is human-curated against primary sources.
- No mass translation. Bilingual on a per-entry basis is fine.
- No corpus that grows by lowering the bar. Better to ship two entries with full §3.5 sections than ten without.

---

## 8. Open uncertainties

- Whether `event_date` should be the touchdown (2014-11-12) or the loss-of-contact date for the post-bounce shutdown. Touchdown is more decision-relevant; record both in the body.
- Trigger conditions in §3.4 use `predicted_shadowing_min` which is not yet a Phase 2 feature. Add to the Phase 2 backlog before Phase 4 ships, or remove from the trigger.
- Whether to attach the `.stl` mesh to the operator-facing evidence card. Visual aid value is real, but it increases storage cost. Default off for now.

---

## 9. Related notes

- Roadmap context: [`../ROADMAP.md`](../ROADMAP.md).
- Phase 0 arbiter (the consumer of the corpus): [`small-model-ensemble-arbiter.md`](small-model-ensemble-arbiter.md).
- Phase 2 thermal posture (provides `posture = violate` triggers): [`thermal-and-mechanical.md`](thermal-and-mechanical.md).
- Phase 3 classifiers whose firings cause corpus lookup: [`signal-processing.md`](signal-processing.md).
- Source-of-truth catalog: [`INDEX.md`](INDEX.md).
