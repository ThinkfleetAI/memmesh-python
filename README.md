# MemMesh Python SDK

Memory **+ prediction** for AI agents. MemMesh remembers across sessions,
forecasts what happens next with a calibrated confidence score, and stays
compliant — everything mem0 does, plus a prediction layer it has no answer for.

```bash
pip install thinkfleet-memmesh   # the import name is still `memmesh`
```

## Quickstart

```python
from memmesh import MemMesh, subject

mm = MemMesh(api_key="sk-...", project_id="proj_...")

# 1 — Observe: feed it anything; the engine decides what to keep
mm.observe(
    "Moved to the annual plan, prefers email over SMS.",
    subject=subject("contact", "user_42"),
)

# 2 — Recall: hybrid semantic + keyword search
hits = mm.search("billing preferences", limit=5)

# 3 — Predict: what mem0 can't — what happens next, with provenance
result = mm.predict(subject("contact", "user_42"), horizon_days=30)
for p in result["predictions"]:
    print(p["expectedAt"], p["description"], p["confidence"])

# How honest is that confidence? Ask the calibration report.
print(mm.calibration())
```

## Async

```python
import asyncio
from memmesh import AsyncMemMesh, subject

async def main():
    async with AsyncMemMesh(api_key="sk-...", project_id="proj_...") as mm:
        await mm.observe("...", subject=subject("user", "ryan"))
        preds = await mm.predict(subject("user", "ryan"))

asyncio.run(main())
```

## What's here

| Area | Methods |
|------|---------|
| **Memory** | `observe` · `create` · `search` · `list` · `update` · `delete` · `stats` · `feedback` |
| **Prediction** (`mm.lattice`) | `predict` · `mine` · `profile` · `predict_by_cohort` · `calibration` |

Every method accepts an optional `project_id=` to override the client default,
and raises a typed error (`AuthenticationError`, `RateLimitError`,
`ValidationError`, …) on failure. 429 and 5xx are retried with backoff.

## Configuration

```python
MemMesh(
    api_key="sk-...",
    project_id="proj_...",
    base_url="https://app.memmesh.ai",  # or your self-hosted engine
    timeout=30.0,
    max_retries=2,
)
```

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check . && mypy src/memmesh
```

Apache-2.0 · built by [ThinkFleet](https://thinkfleet.ai) · https://memmesh.ai
