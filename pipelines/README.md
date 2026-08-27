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
(Phases 4–8), `footystats/` (Phase 14, only after the real API schema has been
profiled), `identity_resolution/` (Phases 3 and 15), `quality/` and `load/`
alongside.

If validation fails, the previous production data stays live. Corrupted data is
never published.
