# Job Hunter Evaluations

Evaluation assets are versioned separately from production Domain State:

- `datasets/` contains runtime-validated inputs and human annotations.
- `rubrics/` defines annotation meaning and review rules.
- `reports/` is reserved for explicitly generated, content-safe result artifacts.

Run the deterministic seed replay from the repository root:

```text
./scripts/eval-replay
```

`smoke-v1` is deliberately small. It verifies loader, baseline, and metric mechanics only; it does not satisfy AC-DATA-001 and cannot support product-quality claims.

`hybrid-synthetic-v1` contains 20 non-sensitive semantic-paraphrase cases for the Synthetic Edge Case gate. After explicit `./scripts/semantic-setup`, run `./scripts/hybrid-eval` to regenerate its content-safe report. The report must keep `promoted=false`: the fixture has no human-confirmed No-Evidence labels, no cases above the fixed 1,200-token large-context threshold, and is not an independently annotated Frozen Holdout.

Hybrid reports separate retrieval-selection token reduction from final ContextPackage token reduction. The former is diagnostic only. AC-RAG-002 promotion uses the latter after the shared deterministic ContextBuilder projection includes protected entries, redaction, chunk overlap, and packaging overhead. Recall and No-Evidence degradation are paired against an eligible Full Context reference for the same large-context cases; missing large relevant or large No-Evidence denominators makes promotion ineligible rather than assuming a perfect baseline.

`context-runtime-synthetic-v1` exercises deterministic compaction, protected-entry preservation, exact provenance, and typed ArtifactReference rehydration. Run `./scripts/context-eval` to regenerate its content-safe report. Its Evidence metric is lineage coverage, not effective recall. Effective Evidence recall and workflow-completion degradation remain explicitly unavailable until a paired downstream consumption path exists. This fixture measures mechanics only; it contains no real Candidate data and makes no downstream model or workflow-quality claim.
