# Case study: Rosetta / Philae (Phase 4 seed)

> Post-MVP design note. Local material: `D:\career\ee\衛星機械系統\Rosetta羅賽塔\` — Sampras's own course writeup plus primary literature on the Philae lander.

## Why this is the first case study

Phase 4 ("lessons-learned corpus") only earns its place in Spacesharks if every Nemotron escalation can cite at least one *real, traceable* prior incident. The corpus has to start narrow. Rosetta / Philae is an ideal first entry because:

1. **It is real and well-documented.** The Philae investigation paper is the kind of primary source we can cite without paraphrasing rumor.
2. **It is multi-cause.** Cold-gas thruster anchoring failure + harpoon misfire + post-bounce thermal shadowing — every cause maps onto a different Phase 1–3 advisory path.
3. **Sampras has hands-on familiarity with it** from coursework (`20200319_羅賽塔.docx`, `HW1.pptx`, the `.stl` mesh, an `HW1 CHECK LIST.xlsx`), so the corpus entry can be written without secondhand summarisation.
4. **The lessons translate to LEO ops**, not just deep space — thermal envelope violations, mechanical envelope violations, and the cost of skipping a verification step before commit are universal.

## Sources to ingest

| File | Use |
|---|---|
| `D:\career\ee\衛星機械系統\Rosetta羅賽塔\reference\Rosetta_Lander_Philae_Investigations.pdf` | Primary source for the failure chain. Cite directly. |
| `D:\career\ee\衛星機械系統\Rosetta羅賽塔\reference\Glassmeieretal-2007.pdf` | Instrument-level context (RPC suite). Cite for thermal/EM environment around the lander. |
| `D:\career\ee\衛星機械系統\Rosetta羅賽塔\reference\reference website.txt` | Curated link list. Re-archive each URL into Spacesharks's own evidence log on ingest — don't trust the upstream URL to outlive the corpus. |
| `D:\career\ee\衛星機械系統\Rosetta羅賽塔\20200319_羅賽塔.docx` | Sampras's coursework summary. Use as a stylistic and structural model for other corpus entries. Do *not* cite as authoritative. |
| `D:\career\ee\衛星機械系統\Rosetta羅賽塔\Rosetta.stl` | Visual aid only. Optional asset for the demo card. |

Full catalog: [`INDEX.md`](INDEX.md).

## How a corpus entry should look

Each entry is a structured page that an advisory model can cite by ID. Suggested shape (YAML frontmatter + Markdown body):

```yaml
---
case_id: rosetta-philae-2014
mission: Rosetta / Philae
event_date: 2014-11-12
classes: [thermal_shadowing, mechanical_anchoring, post-event_power_loss]
maps_to_phase: [2, 4]
sources:
  - file: D:\career\ee\衛星機械系統\Rosetta羅賽塔\reference\Rosetta_Lander_Philae_Investigations.pdf
  - file: D:\career\ee\衛星機械系統\Rosetta羅賽塔\reference\Glassmeieretal-2007.pdf
---
```

Body sections:

1. **What happened** — one paragraph, neutral tone, no embellishment.
2. **Causal chain** — bulleted, each bullet ending with `[src: <file>]`.
3. **Decision points that mattered** — what the team did or did not check before commit; this is the operator-relevant payload.
4. **Trigger conditions in Spacesharks** — the specific signal patterns that should cause the advisor to surface this case (e.g., "predicted post-maneuver attitude leaves payload in shadow > 60 min AND battery SoC < 40%").
5. **Limits of analogy** — explicit list of where the analogy stops being useful (e.g., "deep-space comet landing dynamics do not map to LEO attitude control"). This is the most important section and the one most likely to be skipped.

## Causal chain (draft, to be verified against the PDF on ingest)

These are placeholders for the actual ingestion pass. They are *not* yet citations.

- Harpoon anchoring system did not fire on touchdown.
- Cold-gas thruster intended as a backup hold-down did not activate.
- Lander bounced; final resting site was in deep shadow.
- Reduced solar illumination dropped power below the threshold for sustained science ops.
- Recovery depended on later seasonal illumination, which arrived too late and too weakly.

Each bullet must be replaced with a verified citation on ingest, with the page number from the Philae Investigations PDF.

## What this seeds in the Spacesharks loop

When a Phase 2 thermal/mechanical advisor flags `attitude_to_thermal_check: violate` *and* the recommended action involves a hold-down or anchoring analog (deployable lock, gimbal stow), the Nemotron arbitration step should:

1. Pull the Rosetta-Philae entry.
2. Highlight specifically the "decision points that mattered" section.
3. Include the limits-of-analogy section in the evidence card so the operator can dismiss the citation if it is not actually relevant.

This is the test of whether the corpus is *useful* vs. *decorative*: an operator must be able to read the citation and decide in under 30 seconds whether it changes their mind.

## What to actually build (Phase 4 checklist)

- [ ] Define the `case_id` schema and write the first entry from the files listed above.
- [ ] Add a corpus loader that exposes `lookup_by_class(class_name)` and `lookup_by_phase(n)` to the Nemotron arbitration step.
- [ ] Add a "limits of analogy was read" toggle on the evidence card UI. If the operator dismisses a citation, log the dismissal as a signal that the trigger conditions need tuning.
- [ ] Refuse to ship a Nemotron escalation that cites a corpus entry without the limits-of-analogy section populated.
- [ ] Add one more entry from a *different* mission/regime before declaring the corpus "live" — one case is not a corpus.

## Out of scope for Phase 4

- Auto-generating cases from web crawls. Every entry must be human-curated against primary sources.
- Translating the corpus into other languages. Bilingual is fine on a per-entry basis; mass translation is not the value.
- Anything that would make the corpus larger faster but shallower.

## Related notes

- Phase 2 thermal/mechanical advisor that first triggers a citation: [`thermal-and-mechanical.md`](thermal-and-mechanical.md).
- Phase 3 classifiers whose firings drive corpus lookup: [`signal-processing.md`](signal-processing.md).
- Roadmap context: [`../ROADMAP.md`](../ROADMAP.md).
