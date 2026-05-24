# Trust Model

The system should be trusted because it is observable, calibrated, and willing to abstain.

## Trust layers

### 1. Source trust

- Every event stores its source URL
- Every event stores its timestamp
- Every parser version is recorded
- Every derived field keeps an evidence trail

### 2. Model trust

- Use multiple small models for different sub-tasks
- Require confidence scores from each model
- Treat disagreement as a signal, not noise
- Escalate to `Nemotron` when the case is uncertain or high risk

### 3. Decision trust

- Never output a recommendation without evidence
- Include confidence and disagreement level with the answer
- Prefer abstention over a forced guess
- Degrade to "monitor only" when the ensemble is not aligned

### 4. System trust

- Keep all actions inside `NemoClaw`
- Keep the runtime alive in `OpenClaw`
- Log all outputs, failures, and escalations
- Make the full event chain replayable

## Ensemble policy

A simple version:

| Condition | Action |
|---|---|
| High agreement and moderate risk | Recommend |
| Low agreement | Abstain |
| High risk and low confidence | Escalate to Nemotron |
| No clear evidence | Monitor only |

## What to show reviewers

- The system can explain itself
- The system can reject uncertain cases
- The system can run cheaply enough to be practical
- The system improves trust through evidence, not through hype

## Suggested metrics

- source coverage
- latency
- abstention rate
- escalation rate
- recommendation acceptance rate
- replay completeness
