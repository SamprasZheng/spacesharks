# Product Pages

The demo should feel like an agent workbench, not a generic satellite tracker. More pages are useful only if each page shows a different part of the agent loop.

## Page 1: Fleet

Purpose: show the 50-object Starlink sample and the current triage state.

Required elements:

- Starlink fleet count
- green / yellow / red / abstain counts
- top red objects
- latest refresh time
- model cost estimate for the latest run

## Page 2: Red Queue

Purpose: show what the agent thinks needs attention.

Required elements:

- ranked red and yellow objects
- reason codes
- confidence
- model disagreement
- escalation status

## Page 3: Satellite Detail

Purpose: prove that each label is evidence-backed.

Required elements:

- public object name and NORAD catalog ID
- latest public orbit snapshot
- relevant environmental context
- local knowledge snippets used by the models
- five-model vote breakdown
- `Nemotron` arbitration result when used

## Page 4: Briefs

Purpose: show useful outputs without making the report generator the product.

Required elements:

- today brief
- 7-day brief
- 30-day brief
- source links
- model cost estimate
- abstained cases

## Page 5: Sources

Purpose: make trust visible.

Required elements:

- source URL
- parser version
- last successful refresh
- latest evidence hash
- error count

## Page 6: Model Panel

Purpose: show the hackathon AI contribution.

Required elements:

- five primary models
- backup models
- online / offline status
- average latency
- cost estimate
- recent vote agreement

## Navigation rule

The default first screen is `Fleet`. The demo path is:

```text
Fleet -> Red Queue -> Satellite Detail -> Briefs -> Model Panel
```
