# Extraction quality — measured (model-graded)

> **PUBLISHED** · claude-opus-4-8 (2026-06) · commit `c1cea04` · dataset v0.4 · **test** split · 5 runs · judge κ=1.0

| Metric | Value (mean ± 95% CI) |
|---|---|
| Precision | 59.8% ±3.6 |
| Recall | 100.0% |
| **F1** | **74.8% ±2.7** |
| Noise rejection | 92.0% ±9.6 |
| Provenance accuracy | 100.0% |

Judge-graded against canonical statements (semantic equivalence, not substring). Cohen's κ vs human labels = **1.0** (n=32, observed agreement 1.0).
Cost: $10.6206 · 1068 model calls (347290/73336 in/out tokens).

## Per source kind (F1, last run)
| Kind | F1 | Noise rej. | Cases |
|---|---|---|---|
| db_row | 1.000 | 1.000 | 2 |
| email | 1.000 | 1.000 | 2 |
| github_comment | — | 1.000 | 1 |
| github_doc | 0.667 | — | 1 |
| linear_issue | 0.667 | — | 1 |
| notion_page | 0.880 | — | 3 |
| slack_message | 0.667 | 1.000 | 3 |
| transcript | 0.500 | — | 1 |
| zendesk_ticket | 0.667 | — | 1 |

_Model-graded extraction quality, judge-matched (semantic equivalence). Honest production number — expected below the fixture gate's 100%._
