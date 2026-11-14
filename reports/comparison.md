# Provider comparison

All metrics below are measured on the committed synthetic corpus.

| Provider | Model | Precision | Recall | F1 | Citation | Unverified | Mean ms | Max ms | Input tokens | Output tokens | USD / 100 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| replay:rules | simple-regex-v1 | 0.9697 | 0.8205 | 0.8889 | 1.0000 | 0.0000 | 0.12 | 0.47 | 0 | 0 | 0.0 |
| replay:fake | synthetic-rules-v1 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0.03 | 0.03 | 0 | 0 | 0.0 |

## Field accuracy (matched records)

- replay:rules: {"effective_from": 1.0, "effective_to": 0.9696969696969697, "operator": 1.0, "threshold": 1.0, "unit": 1.0}
  Top error categories: [{"type": "missed_step_down", "count": 4}, {"type": "effective_to", "count": 1}, {"type": "missed_amendment_override", "count": 1}]
  Pricing: Regex baseline, no model tokens; excludes compute/hosting costs.
- replay:fake: {"effective_from": 1.0, "effective_to": 1.0, "operator": 1.0, "threshold": 1.0, "unit": 1.0}
  Top error categories: []
  Pricing: Deterministic fake, no model tokens; excludes compute/hosting costs.

## Interpretation

Fake/rules results are deterministic baselines, not small/large LLM benchmarks. Their zero tokens and inference API cost do not imply free hosting or production readiness. Their latency measures local rules.
Replay returns original recorded usage, not replay execution time. Quality and provider failures must be assessed alongside human review needs. No production model is selected without a real-model evaluation.

See README for matching rules, dataset limitations, data residency, and reproduction commands.
