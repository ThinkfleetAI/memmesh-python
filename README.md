# MemMesh Python SDK

Memory **+ prediction** for AI agents. MemMesh remembers across sessions,
forecasts what happens next with a calibrated confidence score, and stays
compliant — everything mem0 does, plus a prediction layer it has no answer for.

```bash
pip install memmesh
```

## Quickstart

```python
from memmesh import MemMesh, subject

mm = MemMesh(api_key="sk-...", project_id="proj_...")

# 1 — Observe: feed it the raw turn; the engine's noise filter decides what to keep
res = mm.observe(
    text="Moved to the annual plan, prefers email over SMS.",
    user_id="user_42",       # provenance on whatever the engine keeps
    session_id="thread_7",   # keeps a conversation's turns linkable
)
print(res.saved, res.candidate_count)  # filler comes back as saved == []

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
| **Knowledge graph** (`mm.memory.graph`) | `stats` · `list_entities` · `get_entity` · `list_edges` · `traverse` |
| **Prediction** (`mm.lattice`) | `predict` · `mine` · `profile` · `predict_by_cohort` · `calibration` |

Every method accepts an optional `project_id=` to override the client default,
and raises a typed error (`AuthenticationError`, `RateLimitError`,
`ValidationError`, …) on failure. 429 and 5xx are retried with backoff.

## Knowledge graph

Observing doesn't only produce embeddable rows — extraction also resolves
entities and writes typed edges between them. That graph reaches facts no single
memory states outright.

```python
# How much of what you remember made it into the graph?
st = mm.memory.graph.stats()
print(st["entityCount"], st["edgeCount"], st["memoriesWithEdges"])

# Multi-hop: who does Sarah ultimately report to?
sarah, = mm.memory.graph.list_entities(search="Sarah", limit=1)
chain = mm.memory.graph.traverse(sarah["id"], hops=2, predicates=["member_of", "led_by"])
```

Use `stats()` — not `len(list_entities())` — for any "how big is it" question:
the list routes page, so their length is the page size, not the total.

Read-only. Entities and edges are written by extraction during `observe()`; a
hand-maintained graph is the work the engine exists to do for you.

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
