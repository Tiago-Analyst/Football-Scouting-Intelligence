# Pipelines

Batch ingestion and transformation. Nothing here runs yet.

The application never calls a data provider during a web request: providers are
read on a schedule, transformed, quality-checked, and only then loaded into
PostgreSQL for the API to serve.

```
Provider → Raw snapshot → Validation → Identity resolution
        → Derived metrics → Percentiles → Scores → Roles
        → Similarity features → PostgreSQL
```

Build order: `transfermarkt/` (Phase 1B), `transformations/` and `metrics/`
(Phases 4–8), `identity_resolution/` (Phase 3), `quality/` and `load/`
alongside.

`quality/` reports on the loaded data rather than on a load. `coverage.py`
measures which canonical metrics are populated and what their absence would
disable — the dependency graph is discovered by blanking a field and seeing what
stops computing, not by a hand-written table that would drift. `report.py` runs
the checks and exits 1 on any failure, so it can gate a deployment:

```bash
python -m pipelines.quality.report            # print
python -m pipelines.quality.report --persist  # and record in fact_data_quality
```

`footystats/` holds the validation apparatus, not an ingestion pipeline. `probe`
records real API responses and `profile` describes them; neither interprets a
field. An ingestion pipeline may only be written after a person has read the
profile and filled in `config/footystats_mapping.yaml`, and both scripts refuse
to run — writing nothing, exit code 2 — until there is something real to work
from.

If validation fails, the previous production data stays live. Corrupted data is
never published — and that is enforced rather than intended. `--verify` runs the
serving quality suite inside the load transaction, so a failing check rolls the
whole load back:

```bash
python -m pipelines.load.load_providers --source transfermarkt --replace --verify
```

`.github/workflows/pipeline.yml` runs this on the cadence set in
`config/competitions.yaml`.
