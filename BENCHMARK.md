# Company Brain Eval (CBE) — Methodology & Scorecard

**The category should be judged on governed correctness, not recall.** Agent-memory
products compete on recall (Zep ~63.8%, Hindsight ~91% on LongMemEval). The Company
Brain serves *executable, governed skills*, so the questions a buyer deploying agents
against Stripe actually asks are: when an agent uses a skill, does the brain reach the
correct decision, does it ever leak a guardrail, and can an agent see something its role
shouldn't?

**This benchmark is deterministic by design.** The whole system — and the eval harness —
runs on a deterministic, offline provider (`LLM_PROVIDER=fixture`, the default). No
external model is required or used. The advantage: the published headline metrics are
**exact, reproducible, and un-gameable** — they drive the real `GovernedExecutor` /
`VisibilityFilter` with programmatic pass/fail, so they carry an exact `n`, not a noisy
model score. We report exactly what we can measure rigorously, and we explicitly do **not**
publish numbers that would require a model we don't run (see "Not published", below).

## Published scorecard (deterministic, fixture, `test` split, DATASET_VERSION v0.3)

Reproduce with `make eval` (free, offline, ~5s). Every number is exact with a disclosed n;
re-running is bit-identical.

### Headline — governance

| Metric | Value | n | Gate |
|---|---|---|---|
| **Guardrail Adherence Rate (GAR)** | **100%** | 18 | 100% required (hard) |
| **Permission Enforcement Rate (PER)** | **100%** | 17 | 100% required (hard) |
| **Skill-Execution Correctness (SEC)** | **100%** | 23 | ≥90% |
| Determinism | 100% | — | 1.0 required (hard) |

GAR (n=18 test) includes fact-spoof, over-charge, self-approve, replay, no-scope,
prompt-injection (incl. unicode/format), too-old, **approval parameter-swap** (resuming an
approval must execute the *approved* args, not the agent's re-sent ones), and
**cross-principal idempotency**. PER (n=17) covers the role matrix + aggregation /
existence / default-deny / revocation / provenance / private-repo cross-source leaks. The
harness's own sensitivity is tested: weakening a guardrail drops GAR below 100%, widening
visibility drops PER below 100% — both turn CI red.

### Supporting — routing & pipeline logic (all deterministic)

| Metric | Value | n |
|---|---|---|
| Routing top-1 | 84% | 31 |
| Routing abstention | 100% | 14 |
| Calibration (ECE) | 0.077 · 95% CI [0.052, 0.103] | 26 |
| Synthesis correctness | 100% | 4 |
| Compilation fidelity | 100% | 3 |
| End-to-end | 100% | 3 |

Routing top-1 is **84%** on the grown, harder set (down from a fixture-easy 90.9% on 20
cases) — the resolver is keyword+embedding and oblique phrasings legitimately miss; this is
the honest number. A reliability diagram is emitted on every scorecard.

## Calibration — resolver confidence (Part B)

The resolver's confidence used to be a raw heuristic score with **ECE 0.68** (wrong by
68%). It is now Platt-calibrated, **fit on a held-out `calib` split** (never `test`,
INT-2). Ranking — and therefore top-1 — is unchanged (INT-8, asserted in a test); only the
confidence magnitude is calibrated:

```
ECE = 0.077   95% CI [0.052, 0.103]   n=26 committed   10 bins (bootstrap)
```

The point estimate is ≤ 0.10; the CI upper bound (0.103) grazes the line, which we disclose
rather than hide — at n≈26 the estimate still has real uncertainty. `python -m
apps.api.resolver.calibration` refits it; the params are version-stamped in
`calibration.json`.

## Not published (would require a model we don't run)

Two stages can't be honestly scored without an LLM, so in this fixture-only configuration
we **do not publish them as accuracy numbers**:

- **Extraction F1 / noise-rejection / provenance.** The fixture extractor is rule-based, so
  it matches the goldens *by construction* (F1 = 100%). That is a **regression gate on the
  pipeline's correctness**, not a measure of NLP quality — so we report it as a gate, never
  as a published accuracy claim. A real extraction-quality number would require running the
  extractor on a model (an optional path; see appendix) and would honestly score below 100%.
- **Judge κ.** The semantic-equivalence judge is only needed for model-graded checks, which
  we don't run here. The fixture judge is a token-overlap proxy (κ is intentionally low on
  numeric near-misses) — a *flag*, not a published number.

Publishing a deterministic 100% governance number next to an honestly-omitted extraction
number is the point: we claim only what we can prove.

## Statistical rigor (§7)

- **Bootstrap 95% CIs** for ECE (and available for rates) — no normal-approx at n≈20–45.
- **Every metric carries n.** "100% (n=18)" not bare "100%".
- **Power note:** at n≈18–31, a real difference under ~10–12 points is within sampling
  noise of the case set. The deterministic 100%s are exact (no run-to-run variance), but
  their *strength as a claim* is bounded by n — which is why we grew the sets and keep
  growing them.
- **No over-claim.** "GAR 100% / PER 100% (deterministic, n disclosed), under adversarial
  input" is strong and true. "Best-in-class accuracy" is not something this n supports.

## Datasets (`test` / `dev` / `calib` split)

adversarial 26 · execution 31 · routing 45 (+24 calib) · permission 20 · extraction 22
(per-kind across 8 connector source kinds) · synthesis 4 · compilation 3. Contamination
check green — no golden strings in prompts/templates (INT-1/INT-3). Grown and iterated on
`dev`/`calib`; published on `test`; nothing tuned on `test`.

## Running it

```bash
make eval        # the published, deterministic scorecard (fixture, free, offline)
make eval-ci     # gate mode: nonzero exit on a failing threshold (GAR/PER 100%, etc.)
python -m apps.api.resolver.calibration   # refit the resolver calibrator on the calib split
```

## Honest limitations (kept — this is credibility, not weakness)

- **Extraction quality is not benchmarked here.** By choice, this configuration is
  model-free; the extraction metrics are pipeline-correctness gates, not NLP-accuracy
  claims. That's a real gap a buyer should know — it's disclosed, not hidden.
- **Routing cases are author-generated**, not sampled from production traffic, and the
  resolver is keyword+embedding. The 84% reflects coverage of authored phrasings; real
  traffic will differ.
- **ECE CI upper bound (0.103) grazes 0.10** at n≈26 — growing the routing/calib sets will
  tighten it.
- **Dataset sizes**, though grown (GAR 26, SEC 31, routing 45), are still small; n is always
  on the card so a reader can judge the strength of each claim.

## Appendix — optional model-graded extraction (not the published config)

The LLM sits behind one interface (`apps/api/llm/base.py`); a model provider can be added
in one file if you ever want a model-graded extraction/κ number. That path is **not** part
of the published deterministic benchmark and is not required to run anything in this repo.
