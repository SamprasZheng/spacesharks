# Fleet Strategy

## Primary focus

Spacesharks is Starlink-first.

The hackathon demo should not monitor every object in orbit. It should monitor a representative Starlink sample, find the few objects that need attention, and produce a short evidence-backed fleet brief.

## Initial sample

- Start with 50 Starlink satellites
- Keep the pipeline expandable to 100
- Select from public Starlink TLE data
- Refresh at a practical cadence, not sub-minute realtime
- Treat MEO and GEO satellites as optional benchmarks, not the core product

## Reference objects

The product can include a small reference strip for popular non-LEO objects, but this is not the core mission.

| Orbit class | Suggested sample | Purpose |
|---|---|---|
| LEO | 50 Starlink objects, expandable to 100 | Main fleet triage target |
| MEO | 5 to 10 GNSS objects, such as GPS or Galileo | Show how Starlink LEO differs from navigation-orbit assets |
| GEO | 5 to 10 recognizable GEO communication or weather objects | Show slower-changing baseline behavior |

The UI should label MEO/GEO as reference objects. They should not compete with Starlink for the main risk queue.

## Why Starlink

- Starlink is the most visible LEO megaconstellation
- Public TLE data makes a demo feasible
- Fleet scale makes triage meaningful
- Public interest makes the story easy to understand
- The sample can show how an agent reduces noise by highlighting only the objects that matter
- Lower update cadence is acceptable because the user value is triage and reporting, not second-by-second tracking

## Why not full LEO / MEO / GEO

Full orbit-class coverage creates a different product. LEO megaconstellation triage, MEO navigation satellites, and GEO communications satellites have different operating assumptions, cadences, and risk models.

For the hackathon, mixing all of them equally would dilute the claim. The clean version is:

- Starlink = main fleet
- MEO/GEO = optional comparison objects
- Public evidence = hard boundary

## Report cadence

The system should support:

- today brief
- 7-day brief
- 30-day brief

The report is not the product. The product is the agent's triage: deciding which satellites deserve attention and why.

## Demo target

Show a 50-satellite Starlink fleet where:

- most objects remain green
- a small number become yellow
- one or two objects become red
- red objects include evidence, confidence, disagreement, and a recommendation
- disputed red cases route to `Nemotron`
