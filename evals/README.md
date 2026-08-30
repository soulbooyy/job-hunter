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
