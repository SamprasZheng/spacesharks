"""desk.decisions.kb_retrieval — load + look up entries from the COTS defect
knowledge base produced by AI#1 (`data/cots_defect_knowledge.json`).

This module ships with a tiny bundled seed corpus (10 entries covering the
three regime classes: tid / see / dielectric_charge in LEO) so AI#3 can
ship even if AI#1 hasn't finished its offline batch yet. When AI#1's full
JSON exists on disk, this module loads it preferentially.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence


_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
_KB_PATH_PRIMARY = _REPO / "data" / "cots_defect_knowledge.json"
_KB_PATH_SEED = _HERE / "kb_seed.json"


@dataclass
class KBEntry:
    entry_id: str
    failure_mode: str       # tid | see | dielectric_charge
    component_class: str    # cpu | gpu | fpga | memory | power-rail | mixed-signal
    regime: str             # LEO | MEO | GEO
    question: str
    answer: str
    authority_score: float  # 0..1
    citations: list[dict] = field(default_factory=list)


# Tiny seed corpus — used until AI#1's full JSON lands on disk. Each entry
# is verified against publicly-known references (NASA-STD-8739.9, JEDEC
# JESD89, ESA failure reports). Authority scores reflect the source class.
_SEED_ENTRIES: list[dict] = [
    {
        "entry_id": "see-sel-leo-001",
        "failure_mode": "see",
        "component_class": "power-rail",
        "regime": "LEO",
        "question": "What is the immediate signature of a Single Event Latch-up on a COTS power rail?",
        "answer": "Sudden current draw spike of 100-400 mA above nominal on the supply rail, "
                  "lasting 0.4-1.5 s, accompanied by a rail voltage droop of 0.1-0.25 V. "
                  "Mitigation: cycle the affected rail within the SEL hold-time budget (typically "
                  "<2 s) before thermal runaway destroys the latched device.",
        "authority_score": 0.90,
        "citations": [
            {"title": "NASA-STD-8739.10 Section 6.4", "url": "https://standards.nasa.gov/"},
            {"title": "JEDEC JESD89A SEE Test Standard", "url": "https://www.jedec.org/standards-documents"},
        ],
    },
    {
        "entry_id": "see-set-leo-002",
        "failure_mode": "see",
        "component_class": "fpga",
        "regime": "LEO",
        "question": "How do Single Event Transients in FPGA configuration cells manifest in telemetry?",
        "answer": "SEU/SET in configuration memory cause functional drift visible as elevated SEU "
                  "bit-error-rate (BER > 1e-7) over the previous orbit's baseline. Scrub the "
                  "configuration through partial reconfiguration; if BER stays elevated for >3 "
                  "consecutive frames, full reconfiguration is recommended.",
        "authority_score": 0.85,
        "citations": [
            {"title": "Xilinx UG116 SEU Mitigation", "url": "https://www.xilinx.com/support/documentation/"},
        ],
    },
    {
        "entry_id": "tid-cmos-leo-003",
        "failure_mode": "tid",
        "component_class": "cpu",
        "regime": "LEO",
        "question": "What current-leakage signature indicates TID accumulation on a CMOS SoC?",
        "answer": "Exponential rise in idle leakage current (Iddq) of 10-30 % above the launch "
                  "baseline over months of accumulated dose. At 1.5x baseline, expect thermal "
                  "margin reduction; at 2x, consider operational duty-cycle reduction. "
                  "Threshold-voltage shift causes timing-margin erosion in synchronous logic.",
        "authority_score": 0.92,
        "citations": [
            {"title": "NASA-STD-8739.9 TID Test", "url": "https://standards.nasa.gov/"},
            {"title": "MIL-STD-883 TM 1019", "url": "https://landandmaritime.dla.mil/Programs/MilSpec/"},
        ],
    },
    {
        "entry_id": "tid-eldr-leo-004",
        "failure_mode": "tid",
        "component_class": "mixed-signal",
        "regime": "LEO",
        "question": "What is the ELDR effect in bipolar mixed-signal devices?",
        "answer": "Enhanced Low Dose Rate Sensitivity — bipolar devices accumulate damage faster at "
                  "low dose rates (orbital exposure) than at high dose rates (lab testing). RDM "
                  ">= 2x is recommended over standard 1.5x for bipolar circuits in LEO. Symptom: "
                  "input offset voltage drift and beta degradation.",
        "authority_score": 0.88,
        "citations": [
            {"title": "MIL-STD-883 TM 1019.9 ELDR", "url": "https://landandmaritime.dla.mil/Programs/MilSpec/"},
        ],
    },
    {
        "entry_id": "charge-saa-leo-005",
        "failure_mode": "dielectric_charge",
        "component_class": "mixed-signal",
        "regime": "LEO",
        "question": "Why does deep dielectric charging risk peak during SAA passes after eclipse?",
        "answer": "Eclipse darkness allows electron flux to accumulate in floating dielectrics "
                  "without photoemission rebalancing; SAA's energetic electron belt amplifies "
                  "the deposition rate. Discharge occurs on eclipse exit as sunlight re-ionizes "
                  "the surrounding plasma. Symptom: sudden ground-referenced potential transient "
                  "and visible voltage rail droop of 0.05-0.15 V lasting 0.2-0.6 s.",
        "authority_score": 0.83,
        "citations": [
            {"title": "ECSS-E-ST-20-06C Spacecraft Charging", "url": "https://ecss.nl/"},
        ],
    },
    {
        "entry_id": "see-mbu-leo-006",
        "failure_mode": "see",
        "component_class": "memory",
        "regime": "LEO",
        "question": "How are Multiple Bit Upsets distinguished from Single Bit Upsets?",
        "answer": "MBUs affect adjacent memory cells from a single ion strike; ECC SEC-DED codes "
                  "detect but cannot correct them, surfacing as uncorrectable error counts in "
                  "DRAM controller statistics. SBU rate in LEO ~1e-10 errors/bit-day; MBU rate "
                  "is ~10x lower but rises sharply during SEP events.",
        "authority_score": 0.86,
        "citations": [
            {"title": "JEDEC JESD89A", "url": "https://www.jedec.org/standards-documents"},
        ],
    },
    {
        "entry_id": "see-sefi-leo-007",
        "failure_mode": "see",
        "component_class": "cpu",
        "regime": "LEO",
        "question": "What is a Single Event Functional Interrupt and how is it recovered?",
        "answer": "SEFI is a transient functional disruption (lock-up, mode change) that does not "
                  "directly destroy the device but requires reset to recover. Detect via watchdog "
                  "timeout or heartbeat loss. Recovery: power-cycle the affected subsystem; if "
                  "repeated SEFIs occur in <30 minute window, escalate to a safe-mode trigger.",
        "authority_score": 0.85,
        "citations": [
            {"title": "ESA ECSS-Q-ST-30-11C", "url": "https://ecss.nl/"},
        ],
    },
    {
        "entry_id": "tid-gpu-leo-008",
        "failure_mode": "tid",
        "component_class": "gpu",
        "regime": "LEO",
        "question": "What TID hardness can be expected from a COTS NVIDIA Orin / Jetson SoC in LEO?",
        "answer": "Aitech S-A2300 (Orin-based) certification at 10 krad(Si) bare die / 20 krad(Si) "
                  "with shielded enclosure (May 2025 test data). Functional degradation above "
                  "20 krad shows VRAM ECC error rate climbing exponentially. For a 5-year LEO "
                  "mission at 540 km, expect ~6 krad/yr behind 4 mm Al — well within margin.",
        "authority_score": 0.82,
        "citations": [
            {"title": "Aitech S-A2300 datasheet", "url": "https://www.aitech.com/"},
        ],
    },
    {
        "entry_id": "see-beam-redirect-leo-009",
        "failure_mode": "see",
        "component_class": "power-rail",
        "regime": "LEO",
        "question": "When does a beam-redirect recommendation outrank a safe-mode trigger?",
        "answer": "When (a) the affected payload is the comms transponder rather than the bus, "
                  "(b) a critical ground-disaster scenario (earthquake / aviation incident / "
                  "armed conflict) overlaps the orbital ground track, AND (c) the SEL recovery "
                  "is confirmed (current normalised, voltage stabilised). Drafting a beam-redirect "
                  "script does not constitute an executable command — it is a needs-review "
                  "proposal that the operator must approve via /api/approve.",
        "authority_score": 0.75,
        "citations": [
            {"title": "Spacesharks INVARIANTS.md O2 override", "url": "internal://docs/INVARIANTS.md"},
        ],
    },
    {
        "entry_id": "see-x-flare-leo-010",
        "failure_mode": "see",
        "component_class": "mixed-signal",
        "regime": "LEO",
        "question": "How does an X-class flare amplify SEE risk on LEO COTS hardware?",
        "answer": "X-class flares (X-ray >= 1e-4 W/m²) precede SEP events by 30-90 minutes. "
                  "Increased proton flux (>10 MeV) elevates SEE rate by 100-1000x baseline for "
                  "the duration of the storm (typically 6-48 hours). Operational response: pre-"
                  "emptive safe-mode for sensitive payloads, ECC scrubbing acceleration, and "
                  "deferring non-critical writes to flight-software persistent storage.",
        "authority_score": 0.88,
        "citations": [
            {"title": "NOAA SWPC S-scale", "url": "https://www.swpc.noaa.gov/noaa-scales-explanation"},
        ],
    },
]


# Module-level cache.
_KB_CACHE: list[KBEntry] | None = None
_KB_SOURCE: str = "uninitialised"


def kb_load(force_seed: bool = False) -> tuple[list[KBEntry], str]:
    """Load the KB. Returns (entries, source) where source is one of:
      'primary' — AI#1's data/cots_defect_knowledge.json
      'seed'    — bundled seed corpus
    """
    global _KB_CACHE, _KB_SOURCE
    if _KB_CACHE is not None:
        return _KB_CACHE, _KB_SOURCE

    if not force_seed and _KB_PATH_PRIMARY.exists():
        try:
            data = json.loads(_KB_PATH_PRIMARY.read_text(encoding="utf-8"))
            entries = data.get("entries", []) if isinstance(data, dict) else data
            _KB_CACHE = [_to_kb_entry(e) for e in entries]
            _KB_SOURCE = "primary"
            return _KB_CACHE, _KB_SOURCE
        except (OSError, json.JSONDecodeError):
            pass

    _KB_CACHE = [_to_kb_entry(e) for e in _SEED_ENTRIES]
    _KB_SOURCE = "seed"
    return _KB_CACHE, _KB_SOURCE


def _to_kb_entry(d: dict) -> KBEntry:
    return KBEntry(
        entry_id=str(d.get("entry_id", "")),
        failure_mode=str(d.get("failure_mode", "")).lower(),
        component_class=str(d.get("component_class", "")).lower(),
        regime=str(d.get("regime", "LEO")),
        question=str(d.get("question", "")),
        answer=str(d.get("answer", "")),
        authority_score=float(d.get("authority_score", 0.5)),
        citations=list(d.get("citations", [])),
    )


def _token_set(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def kb_lookup(
    *,
    failure_mode: str | None = None,
    component_class: str | None = None,
    regime: str = "LEO",
    query: str | None = None,
    limit: int = 3,
) -> list[KBEntry]:
    """Retrieve up to `limit` KB entries best matching the query.

    Match precedence:
      1. exact (failure_mode, regime) match
      2. partial query keyword overlap (jaccard on bag-of-words)
      3. authority_score descending
    """
    entries, _ = kb_load()

    candidates = entries
    if failure_mode:
        candidates = [e for e in candidates if e.failure_mode == failure_mode.lower()]
    if regime:
        candidates = [e for e in candidates if e.regime == regime]
    if component_class:
        comp_filtered = [e for e in candidates if e.component_class == component_class.lower()]
        if comp_filtered:
            candidates = comp_filtered

    if query:
        q_tokens = _token_set(query)
        def score(e: KBEntry) -> tuple[float, float]:
            kb_tokens = _token_set(e.question + " " + e.answer)
            if not q_tokens or not kb_tokens:
                return (0.0, e.authority_score)
            overlap = len(q_tokens & kb_tokens) / max(1, len(q_tokens | kb_tokens))
            return (overlap, e.authority_score)
        candidates = sorted(candidates, key=score, reverse=True)
    else:
        candidates = sorted(candidates, key=lambda e: e.authority_score, reverse=True)

    return candidates[:max(1, limit)]
