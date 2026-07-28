# Milestone 6A.4 Breadth Replication

This directory contains the frozen development comparison between compiled adaptation and an
independently maintained strong static profile across eight fresh tasks and four source families.

The protocol, evidence stages, condition construction receipts, task fixtures, reference
solutions, anonymous run artifacts, and final bounded result are versioned here. Secret
randomization, raw traces, ephemeral configuration, and encryption keys remain outside the
repository. The deferred Milestone 6 external-validation study is not used.

Run the deterministic local checks with:

```bash
uv run python -m scripts.render_breadth_compiled_materials \
  --root development_benchmark_breadth_replication --check
uv run pytest -q tests/unit/benchmark/test_breadth_replication.py \
  tests/integration/test_breadth_replication.py
```
