# Company Brain Eval (CBE) — Methodology & Scorecard

**The category should be judged on governed correctness, not recall.** Agent-memory
products compete on recall (Zep ~63.8%, Hindsight ~91% on LongMemEval). The Company
Brain serves *executable, governed skills*, so the questions a buyer deploying agents
against Stripe actually asks are: when an agent uses a skill, does the brain reach the
correct decision, does it ever leak a guardrail, and can an agent see something its role
shouldn't?

Two of CBE's three headline metrics are **deterministic** — they drive the real
`GovernedExecutor` / `VisibilityFilter` with programmatic pass/fail, so they are exact
rates with a disclosed `n`, **independent of any model**. The model-dependent metrics
(extraction, the judge κ) get genuine `mean ± 95% CI` from `make eval-live`. We never
dress a deterministic metric in a fake CI, and we never publish a fixture-easy number as
if it were the real one.

## Two scorecards, never confused

| | Published (headline) | CI gate |
|---|---|---|
| Run | `make eval-live` (real model) | `make eval` (fixture, deterministic) |
| Deterministic metrics (GAR/PER/SEC) | identical — exact, with n | identical — exact, with n |
| Model metrics (extraction F1, κ) | **real, mean ± 95% CI** | 100%/proxy "by construction" — **not publishable** |
| Purpose | the number you publish | always-green regression gate |

> **Run `make eval-live` (with `ANTHROPIC_API_KEY`) to populate the model-dependent rows
> below.** Until then those rows show the fixture placeholder and are explicitly marked
> not-publishable. The deterministic governance headline is already the real number.

## Headline — deterministic governance (real now, exact with n)

Measured on the `test` split, commit-attributed, identical in fixture and live because
they don't touch the extraction model:

| Metric | Value | n | Gate |
|---|---|---|---|
| **Guardrail Adherence Rate (GAR)** | **100%** | 18 | 100% required (hard) |
| **Permission Enforcement Rate (PER)** | **100%** | 17 | 100% required (hard) |
| **Skill-Execution Correctness (SEC)** | **100%** | 23 | ≥90% |
| Determinism | 100% | — | 1.0 required (hard) |

The adversarial GAR set (n=18 test) includes fact-spoof, over-charge, self-approve,
replay, no-scope, prompt-injection (incl. unicode/format), too-old, **approval
parameter-swap** (resuming an approval must execute the *approved* args, not the agent's
re-sent ones), and **cross-principal idempotency**. PER (n=17) covers the role matrix +
aggregation / existence / default-deny / revocation / provenance / private-repo
cross-source leaks. The harness's own sensitivity is tested: weakening a guardrail drops
GAR below 100%, and widening visibility drops PER below 100% — both turn CI red.

## Calibration — resolver confidence (Part B)

The resolver's confidence used to be a raw heuristic score with **ECE 0.68** (wrong by
68%). It is now Platt-calibrated (fit on a held-out `calib` split, INT-2; ranking — and
therefore top-1 — unchanged, INT-8):

```
ECE = 0.077   95% CI [0.052, 0.103]   n=26 committed   10 bins (bootstrap)
```

The point estimate is ≤ 0.10; the CI upper bound (0.103) sits right at the line, which we
disclose rather than hide — at n≈26 the estimate still has real uncertainty. A reliability
diagram (confidence vs empirical accuracy) is emitted on every scorecard.

## Supporting (deterministic in fixture; model-measured live)

| Metric | Fixture (gate) | Live (publish via `eval-live`) |
|---|---|---|
| Routing top-1 | 84% (n=31) | same (deterministic resolver) |
| Routing abstention | 100% (n=14) | same |
| Extraction F1 | 100% *by construction* — **not publishable** | real, ± CI |
| Noise rejection | 100% | real, ± CI |
| Provenance accuracy | 100% | real, ± CI |
| Synthesis / Compilation | 100% / 100% | deterministic |
| Judge κ (vs 32 human pairs) | −0.06 *(token-overlap proxy)* — **not publishable** | real model, target ≥ 0.7 |

Routing top-1 is **84%** on the grown, harder set (n=31) — the honest number, down from a
fixture-easy 90.9% on 20 cases. The resolver is keyword+embedding (no LLM tie-break in
fixture mode); oblique phrasings legitimately miss. The fixture **judge κ is negative on
purpose**: a token-overlap proxy cannot distinguish numeric near-misses ("above 20%" vs
"above 25%"), which is exactly why the published κ requires the real model.

## Statistical rigor (§7)

- **Bootstrap 95% CIs** for ECE and rates — no normal-approx at n≈20–45.
- **Every metric carries n.** "100% (n=18)" not bare "100%".
- **Power note:** at n≈18–31, differences under ~10–12 points are within noise; do not
  over-read run-to-run wiggle. The deterministic 100%s are exact (no sampling noise), but
  their *strength as a claim* is bounded by n — which is why we grew the sets and keep
  growing them.
- **No over-claim.** "GAR 100% / PER 100% (deterministic, n disclosed), including under
  adversarial input" is strong and true. "Best-in-class" is not something this n supports.

## Datasets (`test` / `dev` / `calib` split, DATASET_VERSION v0.3)

- adversarial 26 · execution 31 · routing 45 (+24 calib) · permission 20 · extraction 22
  (per-kind F1 + noise across 8 connector source kinds) · synthesis 4 · compilation 3.
- Contamination check green (no golden strings in prompts/templates, INT-1/INT-3).

## Running it

```bash
make eval        # fixture, deterministic, free — the CI gate
make eval-ci     # gate mode (nonzero exit on a failing threshold)
make eval-live   # real model: genuine CIs + model-measured κ (needs ANTHROPIC_API_KEY)
python -m apps.api.resolver.calibration   # refit the calibrator on the calib split
```

### What `make eval-live` changes (and how to read it)

- Deterministic metrics (GAR/PER/SEC) are unchanged — exact with n.
- Extraction F1, noise rejection, provenance, and judged checks become real `mean ± 95%
  CI` over N≥5 (INT-5/INT-6). **Expect extraction F1 below 100%** — that is the
  measurement, not a regression; we do not tune on `test` to recover it.
- Judge κ is measured by the real model (3× self-consistency) against ≥30 human pairs and
  published with the model id; κ ≥ 0.7 marks judged metrics "trusted".
- Attribution records model id + snapshot + seed; re-running reproduces headline numbers
  within the reported CIs.

## Honest limitations (kept and updated — this is credibility, not weakness)

- **The published model-dependent rows require `eval-live`.** This repo's CI runs fixture
  mode, whose extraction F1 (100%) and judge κ (proxy) are **not** publishable; they are
  the regression gate, not the number. Run live with a key to publish them.
- **Routing cases are author-generated**, not sampled from production traffic, and the
  resolver is keyword+embedding. The 84% reflects coverage of authored phrasings; real
  traffic will differ, and live mode can add an LLM tie-break.
- **ECE CI upper bound (0.103) grazes 0.10** at n≈26 — disclosed, not hidden. Growing the
  routing/calib sets will tighten it.
- **Dataset sizes**, while grown (GAR 26, SEC 31, routing 45), are still small;
  "100% (n=18)" is honest and strong but not a claim of statistical certainty — n is
  always on the card so a reader can judge.
