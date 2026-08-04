"""Behaviors resource — emergent behavior discovery.

Where :meth:`LatticeResource.predict` answers "what will this subject do?" and
``profile`` answers "who is this subject?", :meth:`discover` answers a
project-wide question: **"what behaviors exist in my data that nobody defined?"**
It clusters subjects by their feature vectors and surfaces the dense, cohesive
groups as behaviors — each with prevalence, stability, members, and explainable
evidence. Mirrors ``thinkfleet-memory-sdk``'s ``resources/behaviors.ts``.
"""

from __future__ import annotations

from typing import Any, Optional

from ..types import DiscoverResult


def _discover_body(
    sim_threshold: Optional[float],
    min_cluster_size: Optional[int],
    min_stability: Optional[float],
    max_members: Optional[int],
) -> dict:
    raw = {
        "simThreshold": sim_threshold,
        "minClusterSize": min_cluster_size,
        "minStability": min_stability,
        "maxMembers": max_members,
    }
    return {k: v for k, v in raw.items() if v is not None}


class BehaviorsResource:
    """Synchronous emergent-behavior discovery."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    def discover(
        self,
        *,
        sim_threshold: Optional[float] = None,
        min_cluster_size: Optional[int] = None,
        min_stability: Optional[float] = None,
        max_members: Optional[int] = None,
        project_id: Optional[str] = None,
    ) -> DiscoverResult:
        """Discover emergent behaviors across the project. Returns clusters of
        like-behaving subjects, sorted most-common-and-cohesive first. All tuning
        params are optional (the engine clamps to safe ranges): ``sim_threshold``
        (default 0.75), ``min_cluster_size`` (3), ``min_stability`` (0.6),
        ``max_members`` (50).

        An empty ``behaviors`` means the engine abstained — not enough signal to
        assert any behavior — never "there are no behaviors"."""
        body = _discover_body(sim_threshold, min_cluster_size, min_stability, max_members)
        return self._t.post("/lattice/discover", body, project_id)


class AsyncBehaviorsResource:
    """Asynchronous mirror of :class:`BehaviorsResource`."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    async def discover(
        self,
        *,
        sim_threshold: Optional[float] = None,
        min_cluster_size: Optional[int] = None,
        min_stability: Optional[float] = None,
        max_members: Optional[int] = None,
        project_id: Optional[str] = None,
    ) -> DiscoverResult:
        body = _discover_body(sim_threshold, min_cluster_size, min_stability, max_members)
        return await self._t.post("/lattice/discover", body, project_id)
