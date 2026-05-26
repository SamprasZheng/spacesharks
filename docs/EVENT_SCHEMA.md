# Event Schema

This is the contract for the Starlink-first hackathon version. It is intentionally narrower than the long-term lifecycle dataset.

## Record types

The MVP writes two record types:

- `satellite_snapshot`: one normalized state for one Starlink object at one observation time
- `fleet_brief`: one generated report over a time window

## `satellite_snapshot`

| Field | Type | Required | Notes |
|---|---|---|---|
| `schema_version` | string | yes | Starts at `v0.1` |
| `record_type` | enum | yes | `satellite_snapshot` |
| `snapshot_id` | string | yes | `<norad_cat_id>-<observed_at>-<short_hash>` |
| `norad_cat_id` | string | yes | Public catalog ID |
| `object_name` | string | yes | Public object name, e.g. `STARLINK-####` |
| `operator` | string | yes | `SpaceX` for the MVP fleet |
| `orbit_class` | enum | yes | `LEO` for Starlink MVP |
| `observed_at` | string | yes | ISO-8601 UTC |
| `ingested_at` | string | yes | ISO-8601 UTC |
| `source_type` | enum | yes | `tle`, `space-weather`, `derived`, `manual` |
| `source_url` | string | yes | Public retrievable source |
| `evidence_hash` | string | yes | SHA-256 of the raw source payload |
| `parser_version` | string | yes | Parser semver or git SHA |
| `risk_label` | enum | yes | `green`, `yellow`, `red`, `abstain` |
| `risk_score` | number | yes | 0.0 to 1.0 |
| `confidence` | enum | yes | `high`, `medium`, `low` |
| `disagreement` | enum | yes | `none`, `low`, `medium`, `high` |
| `escalated_to_nemotron` | boolean | yes | True when the arbiter escalated |
| `reason_codes` | array | yes | Short machine-readable explanations |
| `recommendation` | object | no | Required for red items unless `risk_label = abstain` |
| `review_status` | enum | yes | `internal-log-only`, `brief-candidate`, `needs-review`, `dismissed` |

## `fleet_brief`

| Field | Type | Required | Notes |
|---|---|---|---|
| `schema_version` | string | yes | Starts at `v0.1` |
| `record_type` | enum | yes | `fleet_brief` |
| `brief_id` | string | yes | `<window>-<generated_at>-<short_hash>` |
| `window` | enum | yes | `today`, `7d`, `30d` |
| `generated_at` | string | yes | ISO-8601 UTC |
| `fleet_size` | integer | yes | 50 for MVP, 100 when expanded |
| `green_count` | integer | yes | Count in latest window |
| `yellow_count` | integer | yes | Count in latest window |
| `red_count` | integer | yes | Count in latest window |
| `abstain_count` | integer | yes | Count in latest window |
| `top_red_objects` | array | yes | Snapshot IDs and short reasons |
| `top_yellow_objects` | array | yes | Snapshot IDs and short reasons |
| `model_cost_estimate` | number | no | Optional cost estimate for the report |
| `source_urls` | array | yes | Sources used for the brief |
| `generated_by` | string | yes | Agent and version |

## Example `satellite_snapshot`

```json
{
  "schema_version": "v0.1",
  "record_type": "satellite_snapshot",
  "snapshot_id": "44713-20260524T120000Z-a3f7c819",
  "norad_cat_id": "44713",
  "object_name": "STARLINK-1007",
  "operator": "SpaceX",
  "orbit_class": "LEO",
  "observed_at": "2026-05-24T12:00:00Z",
  "ingested_at": "2026-05-24T12:03:10Z",
  "source_type": "tle",
  "source_url": "https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=json",
  "evidence_hash": "a3f7c819e6d2b4f1c8e3a7d509c26f3b8e1d4a72c9b5f0e3827d641c4b9e2f7a",
  "parser_version": "0.1.0",
  "risk_label": "yellow",
  "risk_score": 0.63,
  "confidence": "medium",
  "disagreement": "low",
  "escalated_to_nemotron": false,
  "reason_codes": ["orbit-drift-watch", "space-weather-context"],
  "recommendation": {
    "action_type": "review",
    "summary": "Include in today's fleet brief and compare with next refresh."
  },
  "review_status": "brief-candidate"
}
```

## Storage layout

```text
data/
  snapshots/YYYY-MM-DD.jsonl
  briefs/YYYY-MM-DD.jsonl
  evidence-blobs/<hash-prefix>/<full-hash>.raw
```

JSONL is the source of truth. Any dashboard, report, or SQLite index is derived from these records.
