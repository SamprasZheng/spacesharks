# Hackathon Plan

This plan is intentionally narrow. The goal is to prove one trustworthy Starlink fleet triage loop, not to build a full satellite lifecycle platform.

## Outcome to prove

Deliver a working Starlink fleet triage agent that:

- runs safely in `NemoClaw`
- stays alive in `OpenClaw` for 24 hours
- monitors 50 public Starlink objects, expandable to 100
- uses a small-model ensemble for low-cost daily triage
- escalates red, disputed, or low-confidence cases to `Nemotron`
- produces traceable today, 7-day, and 30-day fleet briefs

## Build sequence

### Day 1

- Lock the fleet sample to 50 Starlink satellites
- Define the satellite snapshot and fleet brief schemas
- Stand up the `NemoClaw` policy boundary and event log
- Connect CelesTrak Starlink orbit data
- Add one space-environment context source

### Day 2

- Implement the small-model ensemble
- Add red/yellow/green risk scoring
- Add abstain and escalation rules
- Route disputed red cases to `Nemotron`
- Generate the first today brief from logged events

### Day 3

- Build the demo screen flow:
  - 100-object-ready fleet overview
  - top red satellites
  - satellite detail with evidence
  - today / 7-day / 30-day brief
- Stage one low-confidence case to show abstention
- Stage one `NemoClaw` denied action to show auditability

### Day 4

- Freeze schemas and demo flow
- Validate the 24-hour run
- Polish README, diagrams, and submission language
- Record the walkthrough
- Package the submission

## Deliverables

- One Starlink-first demo loop
- One fleet overview
- One red satellite detail view
- One today / 7-day / 30-day report flow
- One replayable event log
- One trust and confidence explanation

## Non-goals

- No full satellite lifecycle coverage
- No attempt to monitor every Starlink object
- No full MEO/GEO product scope
- No private SpaceX telemetry claim
- No real spacecraft actuation
- No trading or investment framing
- No dependency on the largest model for every step
