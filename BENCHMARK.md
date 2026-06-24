# Company Brain Eval (CBE) — Methodology & Scorecard

**The category should be judged on governed correctness, not recall.** Agent-memory
products compete on recall (Zep ~63.8%, Hindsight ~91% on LongMemEval). The Company
Brain serves *executable, governed skills*, so the questions a buyer deploying agents
against Stripe actually asks are: when an agent uses a skill, does the brain reach the
correct decision, does it ever leak a guardrail, and can an agent see something its role
shouldn't?

**The benchmark has two parts, by design.** They answer different questions and earn
trust in different ways, so we keep them separate rather than blending them into one
hand-wavy score:

- **Part 1 — Exact governance (deterministic).** The governance metrics run on a
  deterministic, offline provider (`LLM_PROVIDER=fixture`, the default). They drive the
  real `GovernedExecutor` / `VisibilityFilter` with programmatic pass/fail, so they are
  **exact, reproducible, and un-gameable** — an exact `n`, not a noisy model score. This
  is the published headline and the CI gate.
- **Part 2 — Measured NLP (model-graded).** Extraction quality genuinely depends on the
  model, so we measure it on the **real model** and publish it as `mean ± 95% CI` over
  N≥5 runs with the model snapshot attached — graded by the LLM judge on **semantic
  equivalence**, not substring overlap. It is honest (expected below 100%), it is **not**
  part of the CI gate, and it is reported *next to* the governance number, never folded
  into it.

## Published scorecard (deterministic, fixture, `test` split, DATASET_VERSION v0.4)

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

## Part 2 — Measured NLP quality (model-graded extraction)

Extraction is the one stage whose quality genuinely depends on the model, so we measure it
*on the model* rather than omit it. The harness for this is `apps/api/evals/extraction_live.py`
(`make eval-extraction-live`). It is separate from the deterministic suite on purpose.

**Method (integrity-first):**

1. **Trust the judge first.** Extraction is graded by an LLM judge for *semantic
   equivalence* against a canonical `statement` per golden unit (never substring overlap —
   that's the deterministic gate's job). Before any extraction number is computed, the judge
   is validated against a 32-pair human-labeled set (`validate_judge.py`) including numeric
   near-misses (20% vs 25%, $500 vs $5000, 30 vs 60 days, flipped comparators, added
   negation) → **Cohen's κ**. **κ < 0.7 ⇒ the whole measurement is stamped low-trust and is
   not published.** A number graded by an untrusted judge is not a number.
2. **Precision *and* recall.** We report micro precision, recall, and F1 — false positives
   the extractor invents count against precision; missed units count against recall. F1
   alone hides both.
3. **N≥5 runs, `mean ± 95% CI`,** with the model id + snapshot stamped on the result. A live
   point estimate without its CI and snapshot is not reportable.
4. **Per source kind.** F1 + noise rejection broken out across all 8 connector kinds, so a
   regression in one source isn't averaged away.
5. **Cost + provenance.** Real token spend is reported; provenance accuracy = fraction of
   extracted spans found verbatim in the source.

```bash
LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=sk-... \
    python -m apps.api.evals.extraction_live --n 5 --split test
# or: make eval-extraction-live
```

The published result lands in `apps/api/evals/published/extraction_live.json` (committed
next to this file, attributable by commit + dataset + model snapshot) and surfaces in the
console under **"NLP quality — measured"**, beside — never blended into — the governance
tiles.

### Result (measured, `claude-opus-4-8` snapshot `2026-06`, commit `c1cea04`, dataset v0.4, `test` split, N=5)

| Metric | Value (mean ± 95% CI) |
|---|---|
| **Extraction F1** | **74.8% ± 2.7** |
| Precision | 59.8% ± 3.6 |
| Recall | 100.0% |
| Noise rejection | 92.0% ± 9.6 |
| Provenance accuracy | 100.0% |
| **Judge trust (Cohen's κ)** | **1.0** (n=32, observed agreement 1.0) — cleared the κ≥0.7 bar |

Real cost: **$10.62** · 1068 model calls (347k/73k in/out tokens). Artifact committed at
`apps/api/evals/published/extraction_live.{json,md}`.

**How to read this — and why it is honest.** Recall is **100%**: on the `test` split the
extractor misses **no** real rule. Precision is **59.8%**, so F1 is dragged to **74.8%** —
the model *over-extracts*, emitting ~1.5× the golden units, and the extras are scored as
false positives. A material share of those "false positives" are arguably **valid units the
goldens simply don't enumerate** (each source lists only its headline rule), so the *true*
precision is plausibly higher than 59.8% — but we score against the goldens as written and
do **not** hand-wave the number upward. This is the credible production picture: the brain
captures everything and is slightly over-eager, which is the safe failure direction for a
review-gated knowledge layer (a human prunes extras; a missed guardrail is the dangerous
case, and recall is 100%). The number publishes *only* because the judge grading it scored
**κ=1.0** against the human set first; a number from an untrusted judge would not appear here.

Per-source-kind F1 (last run) is in the committed artifact — the small-source kinds (one
case each) swing between 0.5 and 1.0, which is sampling noise at n=1 per kind, disclosed
rather than averaged away.

Publishing a deterministic, exact governance number next to an honestly-measured (or
honestly-pending) extraction number — and never conflating the two — is the whole point: we
claim only what we can prove, and we prove the rest on a real model.

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

## Appendix — the model seam

The LLM sits behind one interface (`apps/api/llm/base.py`); the real provider is
`anthropic_client.py`, selected by `LLM_PROVIDER=anthropic`. The deterministic Part 1
benchmark and everything else in the repo run on the fixture provider with **no key and no
network**. Only Part 2 (model-graded extraction, above) needs the model — and it is
cost-guarded, kept out of the CI gate, and refuses to emit a number without a real run.
