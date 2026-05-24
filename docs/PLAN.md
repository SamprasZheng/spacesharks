# Hackathon Plan

This plan is intentionally narrow. The goal is to prove one trustworthy loop, not to build the full satellite lifecycle platform in four days.

## Outcome to prove

Deliver a working satellite operations copilot that:

- runs safely in `NemoClaw`
- stays alive in `OpenClaw` for 24 hours
- uses a small-model ensemble for low-cost reasoning
- escalates uncertain cases to `Nemotron`
- produces traceable recommendations with event-level provenance

## Build sequence

### Day 1

- Lock the scope to one core ops scenario
- Define the event schema
- Connect the first public sources
- Stand up the runtime boundary and logging path

### Day 2

- Implement the ensemble loop
- Add arbitration and abstain rules
- Wire one decision action end to end
- Verify the event log can be replayed

### Day 3

- Build the demo narrative
- Add a failure case and show how the system degrades safely
- Capture screenshots, logs, and a short storyboard

### Day 4

- Polish the README and diagrams
- Validate the live 24h behavior
- Package the submission and record the retrospective

## Deliverables

- One clear demo loop
- One architecture diagram
- One trust / confidence explanation
- One replayable event log
- One concise submission narrative

## Non-goals

- No full lifecycle coverage
- No automated real-world actuation
- No trading or investment framing
- No large source crawl on day one
- No dependency on the most expensive model for every step
