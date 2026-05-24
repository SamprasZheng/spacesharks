# Event Schema

This is the row contract every ingestor, every model, every scoreboard component, and every publisher in Spacesharks conforms to. The design is **provenance-first**: every row carries a source URL, an ingest fingerprint, and a parser version so any claim can be traced back to its raw source.

The schema is the long-term commercial product. The agent is its continuous ingest engine.

> Canonical version: `yxz/wiki/concepts/spacesharks-mission-desk-event-schema.md`. This file is the build-side reference.

## Minimum row contract

Every row carries these fields, regardless of phase.

| Field | Type | Required | Notes |
|---|---|---|---|
| `schema_version` | string | yes | `vMAJOR.MINOR`, e.g. `v1.0` |
| `event_id` | string | yes | `<phase>-<sat_id>-<event_time>-<short_hash>` |
| `sat_id` | string | yes | NORAD CAT ID preferred; fallback to operator name |
| `phase` | enum | yes | `pre-launch \| launch-ascent \| commissioning \| on-orbit-ops \| eol-deorbit` |
| `event_time` | string | yes | ISO-8601 UTC; the event itself, not ingest time |
| `source_type` | enum | yes | `tle \| space-weather \| cdm \| notam \| regulatory \| press-release \| operator-telemetry \| derived \| manual` |
| `source_url` | string | yes* | Canonical retrievable URL; `null` only when `source_type = manual` |
| `confidence` | enum | yes | `high \| medium \| low` |
| `evidence_hash` | string | yes | SHA-256 of the raw payload at ingest |
| `parser_version` | string | yes | semver tag or git SHA of the ingestor parser |
| `recommendation` | object\|null | no | `{action_type, target_t, parameters}` or `null` |
| `recommended_by` | string | no | `<agent_id>@<version>`; required when `recommendation` is non-null |
| `review_status` | enum | yes | `auto-published \| draft \| internal-log-only \| needs-human-review \| dismissed` |

`source_url` is required except for `manual` rows. `recommended_by` is required when `recommendation` is non-null.

## Why provenance is split out

The audit trail is what lets us recover from parser bugs without rewriting history.

- `source_url` points to the raw, publicly retrievable artifact
- `evidence_hash` is the immutable fingerprint of the source at ingest time
- `parser_version` identifies which ingestor produced the row
- Discover a bug? Every affected row is selectable by `parser_version`; replay deterministically against the same `evidence_hash` blob

## `review_status` state machine

```
                 confidence: low  → internal-log-only
                 confidence: med  → draft
                 confidence: high → auto-published (*)

      auto-published is terminal for publishing,
      but outcome fields stay mutable for evaluation backfill.

      Any state → needs-human-review when:
        - evidence_hash mismatches on nightly re-hash
        - the row contradicts a prior wiki/doc claim
        - human operator raises a flag

      Any state → dismissed
        only by explicit human action.
        Dismissed rows are kept; never deleted.
```

(\*) `auto-published` from `high` confidence also requires crossing a significance threshold (unusual magnitude, novel sat/phase combination, or decision confidence ≥ 0.85). Full policy in [GOVERNANCE.md](GOVERNANCE.md).

## Per-phase extras

Each phase appends its own fields on top of the core.

- **pre-launch**: `launch_id`, `vehicle`, `pad`, `scheduled_t`, `predicted_slip_prob`, `actual_t`, `slip_reason`
- **launch-ascent**: `vehicle`, `flight_id`, `event`, `measured_envelope`, `historical_envelope`, `anomaly_score`, `affected_payload_ids`
- **commissioning**: `class`, `day_n`, `baseline_anomalies`, `observed_anomalies`, `deviation_z`, `recommended_hold`
- **on-orbit-ops**: `event_type`, `environmental_inputs`, `decision`, `operator_action_taken`, `outcome`
- **eol-deorbit**: `predicted_decay_t`, `actual_decay_t`, `footprint_polygon`, `casualty_risk`, `passivation_status`

The MVP only ships **on-orbit-ops** with full depth. Other phases use the core fields plus the first one or two extras as schema-conformant stubs.

## Storage layout

```
data/
  lifecycle-events/
    <phase>/YYYY-MM.jsonl       append-only JSONL, one row per line
  evidence-blobs/
    <hash[:2]>/<full-hash>.raw  content-addressed raw source payload
  lifecycle-events.sqlite       SQLite mirror; rebuildable from JSONL
```

- JSONL is the source of truth. SQLite is a derived index.
- Blobs are write-once. No blob is deleted or overwritten.
- The hot path writes inside the `NemoClaw` sandbox; the storage roots must be in the sandbox's allowlist.

## Schema versioning

- MAJOR: any breaking change (rename, type change, enum removal)
- MINOR: additive only
- Hackathon ships `v1.0`. `v1.x` reserved for additive changes during the build window. No MAJOR bump expected before submission.
- Ingestors must reject rows whose `schema_version` MAJOR is higher than their compiled version.

## Example row

```json
{
  "schema_version": "v1.0",
  "event_id": "on-orbit-ops-25544-20260524T0612Z-a3f7c819",
  "sat_id": "25544",
  "phase": "on-orbit-ops",
  "event_time": "2026-05-24T06:12:00Z",
  "source_type": "space-weather",
  "source_url": "https://services.swpc.noaa.gov/products/alerts.json",
  "confidence": "high",
  "evidence_hash": "a3f7c819e6d2b4f1c8e3a7d509c26f3b8e1d4a72c9b5f0e3827d641c4b9e2f7a",
  "parser_version": "0.1.0",
  "recommendation": {
    "action_type": "safe-mode-trigger",
    "target_t": "2026-05-24T08:00:00Z",
    "parameters": {"kp_threshold": 7}
  },
  "recommended_by": "spacesharks-mission-desk@0.1.0",
  "review_status": "auto-published"
}
```
