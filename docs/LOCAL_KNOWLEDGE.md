# Local Knowledge

Local knowledge is used to ground the models so they do not treat every orbit event as a generic text classification task.

## Goal

Give small models enough domain context to make better Starlink fleet triage decisions without sending every case to a larger model.

## Knowledge pack

The MVP knowledge pack should be small and explicit.

| Pack | Content | Use |
|---|---|---|
| `starlink-basics` | Starlink orbit shells, public constellation facts, naming conventions | Ground object selection and report wording |
| `leo-ops-basics` | LEO drag, decay, orbital altitude changes, update cadence expectations | Avoid overreacting to normal LEO behavior |
| `space-weather-basics` | Kp, solar wind, geomagnetic activity, radiation context | Explain environment-driven risk labels |
| `tle-limitations` | TLE freshness, propagation limitations, public-data uncertainty | Prevent false precision |
| `meo-geo-reference` | Basic MEO/GEO differences and slower update expectations | Keep comparison objects from polluting Starlink logic |

## Public data candidates

- CelesTrak Starlink GP / OMM data
- CelesTrak GNSS groups for MEO references
- CelesTrak GEO group for GEO references
- NOAA SWPC alerts and space-weather products
- SpaceX / Starlink public pages for non-operational context

## Local files

Suggested layout:

```text
data/
  knowledge/
    starlink-basics.md
    leo-ops-basics.md
    space-weather-basics.md
    tle-limitations.md
    meo-geo-reference.md
```

## Retrieval rule

Each model receives:

- the current satellite snapshot
- the relevant public source excerpt
- at most three local knowledge snippets

The system must log which snippets were used. If no local snippet is relevant, the model should say so rather than invent context.

## Trust boundary

Local knowledge improves reasoning. It does not create private telemetry. Any UI label that looks like "health" must be explained as public-data triage, not actual spacecraft health.
