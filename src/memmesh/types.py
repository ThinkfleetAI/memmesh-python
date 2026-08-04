"""Shared types and small helpers for the MemMesh SDK.

Responses come back as plain ``dict`` objects (typed as ``MemoryItem`` etc.)
so you always have access to the full server payload. Enums + the
``subject`` helper exist to keep call sites readable and typo-proof.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, TypedDict, Union


class MemoryType(str, Enum):
    FACT = "fact"
    PREFERENCE = "preference"
    EVENT = "event"
    INSIGHT = "insight"
    OBSERVATION = "observation"
    RULE = "rule"
    CORRECTION = "correction"
    SUMMARY = "summary"
    #: A reusable procedure — how a job is done here (goal + steps + failure
    #: modes). Injected as a how-to exemplar, not a fact. Author with
    #: ``memory.create_procedure(...)``.
    PROCEDURE = "procedure"
    BEHAVIOR_PATTERN = "behavior_pattern"
    CONSENT = "consent"


class MemoryReviewReason(str, Enum):
    """Why a memory is in the adjudication queue (highest-priority reason wins)."""

    PENDING = "pending"
    FLAGGED = "flagged"
    LOW_CONFIDENCE = "low_confidence"
    STALE = "stale"


class MemoryProvenanceTier(str, Enum):
    """Origin tier used to resolve conflicts. Default order strongest→weakest."""

    HUMAN_VERIFIED = "human_verified"
    LOCAL = "local"
    LICENSED_BRAIN = "licensed_brain"
    BASE = "base"


class MemoryScope(str, Enum):
    PLATFORM = "platform"
    PROJECT = "project"
    LOCATION = "location"
    AGENT = "agent"
    USER = "user"
    SESSION = "session"


class FeedbackRating(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


class Subject(TypedDict):
    """The entity a memory or prediction is about.

    ``kind`` is free-form (``"contact"``, ``"user"``, ``"patient"``,
    ``"workspace"``, ...); ``externalId`` is your stable id for it.
    """

    kind: str
    externalId: str


def subject(kind: str, external_id: str) -> Subject:
    """Build a :class:`Subject` with the API's camelCase shape.

    >>> subject("contact", "sarah-pizza")
    {'kind': 'contact', 'externalId': 'sarah-pizza'}
    """
    return {"kind": kind, "externalId": external_id}


class SeekPage(TypedDict):
    """One page of a cursor-paginated list — the wire shape the API returns for
    cursor endpoints. Mirrors the TS ``SeekPage<T>``.

    ``next`` / ``previous`` are opaque cursors (``None`` at the ends). Walk every
    page transparently with :func:`memmesh.paginate` / :func:`memmesh.apaginate`.
    """

    data: List[Any]
    next: Optional[str]
    previous: Optional[str]


# Server payloads are returned verbatim as dicts.
MemoryItem = Dict[str, Any]
SearchResult = Dict[str, Any]
IngestMediaResult = Dict[str, Any]
MemoryFeedback = Dict[str, Any]
Prediction = Dict[str, Any]


@dataclass
class ObserveResponse:
    """What :meth:`memory.observe` returns — mirrors the TS ``ObserveResponse``.

    ``saved`` is the memories the engine chose to keep after running the raw
    turn through its noise filter (extract → dedupe → budget). It is **empty
    when the turn was filler** — that's success, not an error. ``candidate_count``
    is how many candidates the extractor found before the dedupe/budget pass, so
    ``len(saved) <= candidate_count``.
    """

    saved: List[MemoryItem]
    candidate_count: int


class ExplainResult(TypedDict):
    """Provenance bundle returned by ``memory.explain(...)`` — mirrors the TS
    ``{ memory, sourceMemories }`` shape.

    ``memory`` is the item asked about; ``sourceMemories`` are the raw items it
    was derived from (resolved from ``metadata.sourceMemoryIds``). Empty for a
    non-derived item.
    """

    memory: MemoryItem
    sourceMemories: List[MemoryItem]


def enum_value(x: Any) -> Any:
    """Return ``x.value`` for enums, else ``x`` — lets callers pass either
    the enum or a raw string."""
    return x.value if isinstance(x, Enum) else x


def render_procedure_content(
    goal: str,
    steps: List[Dict[str, str]],
    *,
    when_to_use: Optional[str] = None,
    failure_modes: Optional[List[str]] = None,
) -> str:
    """Render a procedure into the injectable ``content`` string — identical to
    the engine-side renderer, so client-authored content matches the server.

    ``steps`` is a list of ``{"text": ..., "pitfall"?: ...}`` dicts.
    """
    lines = [f"Goal: {goal.strip()}"]
    if when_to_use and when_to_use.strip():
        lines.append(f"When: {when_to_use.strip()}")
    lines.append("Steps:")
    for i, step in enumerate(steps, start=1):
        pitfall = step.get("pitfall")
        suffix = f" (watch out: {pitfall.strip()})" if pitfall and pitfall.strip() else ""
        lines.append(f"{i}. {step['text'].strip()}{suffix}")
    failures = [f.strip() for f in (failure_modes or []) if f.strip()]
    if failures:
        lines.append("Avoid:")
        lines.extend(f"- {f}" for f in failures)
    return "\n".join(lines)


# ── Lattice: behavioral pattern intelligence ─────────────────────────────────
#
# Typed result models mirroring ``thinkfleet-memory-sdk``'s ``types/lattice.ts``.
# Responses still arrive as plain ``dict``s at runtime (TypedDicts are dicts);
# these annotations exist so call sites get autocomplete + type-checking on the
# server payloads. Wire keys are camelCase, matching the API exactly.

#: Behavioral pattern kinds the extractor emits (free string on the wire).
BehaviorPatternKind = str

#: Target types the v2 general-prediction engine can predict — drives model
#: selection ("event_occurrence" | "numeric" | "event_time" | "anomaly").
TargetKind = str


class Cadence(TypedDict, total=False):
    """Inter-event rhythm attached to a behavior pattern."""

    periodDays: int
    dayOfWeek: int
    timeOfDayLocal: str
    timezone: str


class _BehaviorPatternMetadataRequired(TypedDict):
    patternKind: BehaviorPatternKind
    contactId: str
    confidence: float
    observationCount: int
    observationWindowDays: int
    lastObservedAt: str
    active: bool


class BehaviorPatternMetadata(_BehaviorPatternMetadataRequired, total=False):
    entityExternalIds: List[str]
    entityKind: str
    eventType: str
    cadence: Cadence
    nextExpectedAt: str
    toleranceMinutes: int


class BehaviorPatternRecord(TypedDict):
    """A mined behavior pattern, as stored (mirrors the underlying memory item)."""

    id: str
    projectId: Optional[str]
    contactId: str
    summary: str
    metadata: BehaviorPatternMetadata
    active: bool
    confidence: float
    created: str
    updated: str


class ContactExtractError(TypedDict):
    contactId: str
    eventType: str
    error: str


class _ExtractPatternsResultRequired(TypedDict):
    contactsProcessed: int
    patternsCreated: int
    patternsRefreshed: int
    patternsDeactivated: int
    durationMs: int


class ExtractPatternsResult(_ExtractPatternsResultRequired, total=False):
    """Outcome of a pattern (re-)extraction / memory-mining run."""

    errors: List[ContactExtractError]


class ListContactPatternsResponse(TypedDict):
    """One cursor-paginated page of a contact's behavior patterns."""

    data: List[BehaviorPatternRecord]
    nextCursor: Optional[str]


# ── Context bundle ───────────────────────────────────────────────────────────


class _LatticeContextContactRequired(TypedDict):
    id: str


class LatticeContextContact(_LatticeContextContactRequired, total=False):
    displayName: str
    email: str
    phone: str
    segment: str
    tags: List[str]
    lifetimeValue: float
    lastInteractionAt: str


class _LatticeContextEventRequired(TypedDict):
    id: str
    eventType: str
    title: str
    occurredAt: str


class LatticeContextEvent(_LatticeContextEventRequired, total=False):
    data: Dict[str, Any]


class LatticeContextMemory(TypedDict):
    id: str
    content: str
    importance: float
    scope: str
    type: str
    created: str


class LatticeContextEntity(TypedDict):
    id: str
    kind: str
    name: str
    metadata: Dict[str, Any]


class _LatticeContextEdgeRequired(TypedDict):
    id: str
    sourceEntityId: str
    targetEntityId: str
    kind: str


class LatticeContextEdge(_LatticeContextEdgeRequired, total=False):
    weight: float


class _LatticeContextBundleRequired(TypedDict):
    contactId: str
    contact: LatticeContextContact
    activePatterns: List[BehaviorPatternRecord]
    recentEvents: List[LatticeContextEvent]
    recentMemories: List[LatticeContextMemory]


class LatticeContextBundle(_LatticeContextBundleRequired, total=False):
    """Full retrieval bundle for a contact — the single payload an AI message
    step needs to render a personalized response."""

    entities: List[LatticeContextEntity]
    edges: List[LatticeContextEdge]


# ── Monitor ──────────────────────────────────────────────────────────────────


class MonitorTickFailure(TypedDict):
    patternId: str
    error: str


class MonitorTickResult(TypedDict):
    patternsChecked: int
    patternsBroken: int
    breaksEmitted: int
    durationMs: int
    capped: bool
    failures: List[MonitorTickFailure]


class MonitorStatus(TypedDict):
    lastTickAt: Optional[str]
    lastTickDurationMs: Optional[float]
    patternsDue: int
    activePatternCount: int


# ── Predict (pattern projection + v2 declared target) ────────────────────────


class _PredictionTargetRequired(TypedDict):
    kind: TargetKind


class PredictionTarget(_PredictionTargetRequired, total=False):
    """A declaratively-specified prediction target (v2). Declare *what* to
    predict; the engine selects the model family from ``kind``."""

    eventType: str
    attributeKey: str
    lookbackDays: int


class _PredictedEventRequired(TypedDict):
    patternId: str
    patternKind: str
    description: str
    expectedAt: str
    confidence: float
    windowMinutes: int
    sourceMemoryIds: List[str]


class PredictedEvent(_PredictedEventRequired, total=False):
    """One projected event derived from one active behavior pattern."""

    confidenceLower: float
    confidenceUpper: float


class TargetPrediction(TypedDict):
    """The single calibrated estimate for a declared ``target``. Always check
    ``abstained`` first — an abstention means "unknown", never "low risk"."""

    targetKind: TargetKind
    eventType: str
    probability: float
    probabilityLower: float
    probabilityUpper: float
    value: float
    valueLower: float
    valueUpper: float
    expectedAt: str
    expectedAtLower: str
    expectedAtUpper: str
    daysUntil: float
    anomalyScore: float
    isAnomaly: bool
    abstained: bool
    abstentionReason: str
    explanation: str
    evidenceMemoryIds: List[str]


class _PredictResultRequired(TypedDict):
    subject: Subject
    predictions: List[PredictedEvent]
    activePatternCount: int
    generatedAt: str
    durationMs: int


class PredictResult(_PredictResultRequired, total=False):
    """Result of :meth:`LatticeResource.predict`. ``targetPrediction`` is set
    instead of ``predictions`` when the request carried a declarative target."""

    eventsEmitted: int
    abstained: bool
    abstentionReason: str
    targetPrediction: Optional[TargetPrediction]


# ── Profile ──────────────────────────────────────────────────────────────────


class RiskIndicator(TypedDict):
    kind: str
    description: str
    severity: float
    sourcePatternId: str


class SubjectProfile(TypedDict):
    """Behavioral profile snapshot — "who is this subject" view; the
    non-temporal counterpart to :class:`PredictResult`."""

    subject: Subject
    rfmSegment: Optional[str]
    recencyScore: Optional[float]
    frequencyScore: Optional[float]
    monetaryScore: Optional[float]
    topEntity: Optional[str]
    cadenceSummary: Optional[str]
    risks: List[RiskIndicator]
    contributingPatternIds: List[str]
    generatedAt: str
    durationMs: int


# ── Estimate (deterministic estimators, e.g. PhenoAge bio-age) ───────────────


class ScoreContributor(TypedDict):
    signal: str
    contribution: float


class EstimateResult(TypedDict):
    """A wellness estimate — never a diagnosis. Check ``ok`` before reading
    ``value``; ``missingSignals`` explains ``ok=False``."""

    subject: Subject
    estimatorId: str
    ok: bool
    value: float
    unit: str
    contributors: List[ScoreContributor]
    confidence: float
    provenance: List[str]
    framing: str
    disclaimer: str
    missingSignals: List[str]


# ── Calibration (prediction reliability) ─────────────────────────────────────


class CalibrationBucket(TypedDict):
    lower: float
    upper: float
    patterns: int
    predictions: int
    hits: int
    misses: int
    realizedHitRate: float
    hasData: bool


class CalibrationReport(TypedDict):
    """Confidence buckets mapped to realized hit-rates."""

    buckets: List[CalibrationBucket]
    totalPatterns: int
    totalPredictions: int


# ── Cohort ───────────────────────────────────────────────────────────────────


class CohortMember(TypedDict):
    subject: Subject
    similarity: float
    rfmSegment: str
    patternKinds: List[str]


class GetCohortResponse(TypedDict):
    target: Subject
    members: List[CohortMember]
    candidateCount: int
    generatedAt: str
    durationMs: int


class CohortPrediction(TypedDict):
    patternKind: str
    description: str
    expectedAt: str
    confidence: float
    windowMinutes: int
    supportingSubjects: List[Subject]
    sourceMemoryIds: List[str]


class PredictByCohortResponse(TypedDict):
    """Cohort-aware predictions — "people like this subject also did X." Every
    prediction carries ``supportingSubjects`` + ``sourceMemoryIds`` for
    traceability."""

    target: Subject
    cohort: List[CohortMember]
    predictions: List[CohortPrediction]
    generatedAt: str
    durationMs: int


# ── Learning: the closed-loop decision → action → outcome primitive ──────────
#
# Typed result models mirroring ``thinkfleet-memory-sdk``'s ``resources/learning.ts``.


class _ProvenanceRefRequired(TypedDict):
    memoryId: str


class ProvenanceRef(_ProvenanceRefRequired, total=False):
    """A causal input to a decision — the pattern/prediction/observation the
    actor was reacting to. ``weight`` splits credit across multiple inputs
    (0/unset is treated as 1.0)."""

    refType: str
    weight: float


class DecisionRecord(TypedDict):
    """A recorded decision and its causal provenance."""

    decisionId: str
    subject: Optional[Subject]
    actor: str
    decisionType: str
    policy: str
    informedBy: List[ProvenanceRef]
    actionType: str
    status: str
    occurredAt: str
    created: str


class RecordDecisionResult(TypedDict):
    decision: Optional[DecisionRecord]


class CalibrationUpdate(TypedDict):
    """One informing ref re-weighted by an outcome (before/after confidence)."""

    refId: str
    refType: str
    priorConfidence: float
    posteriorConfidence: float
    hits: int
    misses: int


class RecordOutcomeResult(TypedDict):
    """Result of recording an outcome — which informing refs were re-weighted,
    and by how much."""

    outcomeId: str
    updates: List[CalibrationUpdate]


class OutcomeRecord(TypedDict):
    """A recorded outcome linked back to its decision."""

    outcomeId: str
    decisionId: str
    subject: Optional[Subject]
    decisionType: str
    actionType: str
    outcomeType: str
    result: str
    reward: float
    occurredAt: str
    realizedAt: str


#: Dimension to roll up "what worked" by
#: ("action_type" | "decision_type" | "policy" | "pattern_kind").
EffectivenessGroupBy = str


class EffectivenessRow(TypedDict):
    """One "what worked" aggregation row."""

    groupKey: str
    #: Support: outcome count in this group.
    n: int
    #: Fraction with result="success".
    successRate: float
    avgReward: float
    #: Beta-Binomial posterior mean of the success rate.
    confidence: float


# ── Behaviors: emergent behavior discovery ───────────────────────────────────


class DiscoveredBehavior(TypedDict):
    """One emergent behavior — a cohesive cluster of subjects the engine grouped
    because they behave alike, with the statistics that justify treating it as
    real. Discovered from the data, not chosen from a fixed menu."""

    label: str
    #: Fraction of the analyzed cohort in this cluster, [0,1] — how common it is.
    prevalence: float
    #: Cohesion: mean pairwise similarity within the cluster, [0,1].
    stability: float
    #: Total subjects in the cluster (may exceed ``memberSubjects`` when capped).
    size: int
    memberSubjects: List[Subject]
    exemplarEvidence: List[str]


class DiscoverResult(TypedDict):
    """Result of a behavior-discovery run. An empty ``behaviors`` means the
    engine abstained — not enough signal — never "there are no behaviors"."""

    behaviors: List[DiscoveredBehavior]
    #: Total subjects analyzed (the prevalence denominator).
    subjectsAnalyzed: int
    generatedAt: str
    durationMs: int


# ── Brains: the marketplace registry ─────────────────────────────────────────
#
# A Brain is a publishable/consumable unit of memory: a Brain Card manifest plus
# a stable ``externalId`` slug the Mesh Router addresses it by. This resource
# covers the registry (create / list / get / update / delete). Consumption of a
# published brain happens over the hosted MCP endpoint, which an MCP client
# connects to directly — it is not a REST call. Mirrors ``types/brain.ts``.

#: Brain visibility on the marketplace ("PUBLIC" | "UNLISTED" | "PRIVATE").
BrainVisibility = str

#: Brain lifecycle status ("DRAFT" | "PUBLISHED" | "ARCHIVED").
BrainStatus = str


class _BrainProvenanceRequired(TypedDict):
    source: str
    license: str


class BrainProvenance(_BrainProvenanceRequired, total=False):
    """Provenance of the facts in a brain — where they came from and under what
    license."""

    url: str


class BrainReasoningCoverage(TypedDict, total=False):
    """Coverage the induced reasoning layer advertises on a Brain Card — the
    procedure/checklist/decomposition memories that make a brain worth more than
    a plain dataset. A facts-only brain reports ``total: 0``."""

    procedures: int
    checklists: int
    decompositions: int
    total: int


class BrainCardCoverage(TypedDict, total=False):
    subjects: int
    facts: int
    reasoning: BrainReasoningCoverage
    freshness: str


class BrainCardEvaluation(TypedDict, total=False):
    benchmark: str
    score: float


class BrainCardPricing(TypedDict, total=False):
    model: str
    unit: str


class BrainCard(TypedDict, total=False):
    """The Brain Card manifest (stored on the brain, surfaced in the catalog)."""

    ontologyRef: str
    provenance: List[BrainProvenance]
    changelogRef: str
    coverage: BrainCardCoverage
    evaluation: BrainCardEvaluation
    predictEnabled: bool
    pricing: BrainCardPricing


class Brain(TypedDict):
    """A registered brain, as stored (mirrors the TS ``Brain``)."""

    id: str
    created: str
    updated: str
    projectId: str
    #: Stable slug the Router addresses the brain by (unique per project).
    externalId: str
    name: str
    domain: Optional[str]
    #: Brain Interface contract version the brain conforms to (e.g. "v1").
    brainInterface: str
    version: str
    visibility: BrainVisibility
    status: BrainStatus
    rightsAttested: bool
    card: Optional[BrainCard]


class _CreateBrainRequestRequired(TypedDict):
    externalId: str
    name: str


class CreateBrainRequest(_CreateBrainRequestRequired, total=False):
    """Body for :meth:`BrainsResource.create`."""

    domain: str
    version: str
    visibility: BrainVisibility
    rightsAttested: bool
    card: BrainCard


class UpdateBrainRequest(TypedDict, total=False):
    """Body for :meth:`BrainsResource.update` — every field optional."""

    name: str
    domain: str
    version: str
    visibility: BrainVisibility
    status: BrainStatus
    rightsAttested: bool
    card: BrainCard


class ListBrainsParams(TypedDict, total=False):
    """Query params for :meth:`BrainsResource.list`."""

    limit: int
    cursor: str


# ── Consent: subject-level opt-out / opt-in ──────────────────────────────────
#
# Consent decisions are recorded as memory items of ``type='consent'`` so the
# audit log captures every change; the Rust mining engine honors opt-outs at the
# start of every mine pass. Mirrors ``resources/consent.ts``.


class ConsentSubject(TypedDict):
    """The subject a consent decision is about (person / team / workspace)."""

    kind: str
    externalId: str


class ConsentStatus(TypedDict):
    """Current consent status for a subject. ``optedOut=False`` is the default
    when no consent record exists."""

    subject: ConsentSubject
    optedOut: bool
    #: ISO timestamp of the opt-out, or ``None`` if never opted out.
    optedOutAt: Optional[str]
    reason: Optional[str]
    #: Id of the underlying consent memory item (for audit linking).
    memoryId: Optional[str]


# ── Events: the durable memory event log (Phase 3i) ──────────────────────────
#
# The engine emits durable events on interesting state changes — pattern
# emergence, risk firing, segment shift, consent change. Mirrors
# ``thinkfleet-memory-sdk``'s ``resources/events.ts`` + the emit types from
# ``types/lattice.ts``. Wire keys are camelCase.

#: Severity tier emitted on every event ("info" | "warn" | "critical").
EventSeverity = str


class EventSubject(TypedDict):
    """The entity an event is about (``None`` on the wire for project-wide events)."""

    kind: str
    externalId: str


class MemoryEvent(TypedDict):
    """One row from the memory event log. Provenance pointers
    (``sourceMemoryIds`` / ``sourcePatternId``) let consumers call
    ``memory.explain()`` to drill down to the raw memories that produced it."""

    id: str
    eventType: str
    subject: Optional[EventSubject]
    severity: EventSeverity
    payload: Dict[str, Any]
    sourceMemoryIds: List[str]
    sourcePatternId: Optional[str]
    emittedByPack: Optional[str]
    occurredAt: str


class _EmitEventRequestRequired(TypedDict):
    eventType: str


class EmitEventRequest(_EmitEventRequestRequired, total=False):
    """Body for :meth:`EventsResource.emit` — append an event to the durable
    log. Matching alert rules fire synchronously."""

    subject: Subject
    #: info | warn | critical. Defaults to "info".
    severity: str
    #: Free-form JSON payload (can include "value", "channel", etc.).
    payloadJson: str
    sourceMemoryIds: List[str]
    sourcePatternId: str


class EmitEventInsertedEvent(TypedDict):
    id: str
    eventType: str
    severity: str
    occurredAt: str


class EmitEventResult(TypedDict):
    """Result of :meth:`EventsResource.emit`."""

    #: False when a dedupe collision suppressed the insert.
    emitted: bool
    event: Optional[EmitEventInsertedEvent]
    #: Number of alert rules that matched + dispatched.
    alertDispatches: int


# ── Alerts: user-defined alert rules (Phase 3j) ──────────────────────────────
#
# "Tell me when X happens, this way" rules that hook into the engine event
# stream. Mirrors ``thinkfleet-memory-sdk``'s ``resources/alerts.ts``.


class EngineEventTrigger(TypedDict):
    """Fire when the engine emits one of ``eventTypes``."""

    kind: str  # "engine-event"
    eventTypes: List[str]


#: Fire when a subject's segment transitions ``from`` -> ``to``. Defined with
#: the functional :func:`TypedDict` syntax because ``from`` is a Python keyword
#: (illegal as a class attribute). ``from`` is optional; ``kind`` + ``to`` are
#: the discriminant and target.
SegmentChangeTrigger = TypedDict(
    "SegmentChangeTrigger",
    {"kind": str, "from": str, "to": str},
    total=False,
)


class PatternEmergedTrigger(TypedDict):
    """Fire when a new pattern of ``patternKind`` emerges."""

    kind: str  # "pattern-emerged"
    patternKind: str


#: A discriminated trigger union (``kind`` selects the shape). Because
#: ``segment-change`` carries a ``from`` field (a Python keyword), build
#: triggers as plain dicts, e.g. ``{"kind": "segment-change", "from": "vip",
#: "to": "at_risk"}``.
AlertTrigger = Union[EngineEventTrigger, SegmentChangeTrigger, PatternEmergedTrigger, Dict[str, Any]]


class AlertFilter(TypedDict, total=False):
    """Narrows which events a trigger matches."""

    subjectKind: str
    #: Glob pattern. Use ``*`` for wildcards: ``vip-*`` matches any externalId
    #: starting with ``vip-``.
    subjectExternalIdPattern: str
    categories: List[str]
    #: Dot-path keys; equality match against event payload.
    metadataMatch: Dict[str, Any]


class WebhookChannel(TypedDict, total=False):
    """Deliver the firing event to an HTTP webhook."""

    kind: str  # "webhook"
    url: str
    #: Shared secret for HMAC-SHA256 signing of the body. Sent as
    #: ``X-ThinkFleet-Signature``.
    secret: str


class MemoryWriteAs(TypedDict, total=False):
    """How a ``memory`` channel writes the firing event back as a memory item."""

    #: Template with ``{{event.eventType}}``, ``{{event.severity}}``,
    #: ``{{subject.kind}}``, ``{{subject.externalId}}``, ``{{rule.name}}``.
    content: str
    scope: str


class MemoryChannel(TypedDict):
    """Self-documenting alert: writes the firing event as an OBSERVATION memory
    item so the next ``context.build()`` for the subject surfaces it to the LLM
    automatically — no external orchestration needed."""

    kind: str  # "memory"
    writeAs: MemoryWriteAs


#: A notification channel — webhook or self-documenting memory write.
NotificationChannel = Union[WebhookChannel, MemoryChannel, Dict[str, Any]]


class ThrottleConfig(TypedDict, total=False):
    """Rate-limits how often a rule fires."""

    maxPerHour: int
    cooldownMinutes: int
    dedupOn: str  # "subject" | "subject+rule" | "rule"


class AlertRule(TypedDict):
    """A stored alert rule."""

    id: str
    projectId: str
    name: str
    description: Optional[str]
    enabled: bool
    trigger: AlertTrigger
    filter: Optional[AlertFilter]
    notify: List[NotificationChannel]
    throttle: Optional[ThrottleConfig]
    created: str
    updated: str


class _CreateAlertRuleRequestRequired(TypedDict):
    name: str
    trigger: AlertTrigger
    notify: List[NotificationChannel]


class CreateAlertRuleRequest(_CreateAlertRuleRequestRequired, total=False):
    """Body for :meth:`AlertsResource.create`."""

    description: str
    enabled: bool
    filter: AlertFilter
    throttle: ThrottleConfig


class UpdateAlertRuleRequest(TypedDict, total=False):
    """Body for :meth:`AlertsResource.update` — every field optional."""

    name: str
    description: Optional[str]
    enabled: bool
    trigger: AlertTrigger
    filter: Optional[AlertFilter]
    notify: List[NotificationChannel]
    throttle: Optional[ThrottleConfig]


class AlertDeliveryResult(TypedDict, total=False):
    channel: str
    ok: bool
    error: str


class AlertFire(TypedDict):
    """One recorded firing of an alert rule."""

    id: str
    alertRuleId: str
    eventId: Optional[str]
    dedupeKey: str
    deliveryResults: List[AlertDeliveryResult]
    firedAt: str


# ── Typed attributes: structured/numeric data the engine reasons over ────────
#
# Register an attribute's schema once, then ingest observations — each is
# validated (accepted or quarantined) and accepted numeric values are folded
# into per-subject accumulators. Mirrors ``thinkfleet-memory-sdk``'s
# ``resources/typed.ts``.

#: The declared type of an attribute
#: ("numeric" | "categorical" | "temporal" | "boolean").
AttributeDataType = str

#: Acceptance status of an ingested observation ("accepted" | "quarantined").
ObservationStatus = str


class _AttributeDefRequired(TypedDict):
    id: str
    attributeKey: str
    dataType: AttributeDataType
    required: bool


class AttributeDef(_AttributeDefRequired, total=False):
    """A registered attribute definition — drives input validation on ingest."""

    platformId: str
    projectId: str
    unit: str
    #: Inclusive plausibility bounds; values outside are quarantined.
    minValid: float
    maxValid: float
    metadataJson: str


class _RegisterAttributeRequestRequired(TypedDict):
    attributeKey: str
    dataType: AttributeDataType


class RegisterAttributeRequest(_RegisterAttributeRequestRequired, total=False):
    """Body for :meth:`TypedAttributesResource.register_attribute`."""

    unit: str
    minValid: float
    maxValid: float
    required: bool
    metadata: Any


class _TypedObservationInputRequired(TypedDict):
    attributeKey: str
    subjectKind: str
    subjectExternalId: str
    #: ISO-8601 observation time.
    observedAt: str


class TypedObservationInput(_TypedObservationInputRequired, total=False):
    """One typed measurement of an attribute for a subject at a point in time."""

    id: str
    valueNumeric: float
    valueText: str
    valueBool: bool
    #: ISO-8601 for temporal values.
    valueTs: str
    source: str
    #: Source-trust weight in 0..1 (default 1).
    trust: float


class TypedObservation(TypedObservationInput, total=False):
    """A stored typed observation (input shape plus server-assigned fields)."""

    platformId: str
    projectId: str
    qualityScore: float
    status: ObservationStatus


class IngestReport(TypedDict):
    """Outcome of a batch ingest."""

    accepted: int
    quarantined: int
    duplicates: int
    #: observationId -> quarantine reason
    quarantineReasons: Dict[str, str]


class EnqueueResult(TypedDict):
    """Outcome of an asynchronous ingest enqueue."""

    enqueued: int


class _AccumulatorRequired(TypedDict):
    subjectKind: str
    subjectExternalId: str
    attributeKey: str
    count: int
    sum: float
    sumSq: float
    cumulative: float


class Accumulator(_AccumulatorRequired, total=False):
    """Per-(subject, attribute) running statistics."""

    minVal: float
    maxVal: float
    lastVal: float
    lastObservedAt: str
    ewma: float
    ewmaVar: float
    #: Derived on read.
    mean: float
    variance: float
    stddev: float


# ── Health vertical ──────────────────────────────────────────────────────────
#
# Typed models mirroring ``thinkfleet-memory-sdk``'s ``types/health.ts``.
# Health data IS memory data: you record biomarkers / demographics / diagnoses
# as memory items (see ``HealthResource.record*``) and the engine derives a
# biological age + condition predictions from them. Read shapes are returned by
# ``/lattice/health/{profile,cohort-risk}``. Gated behind the
# ``@thinkfleet/pack-healthcare`` pack. Wire keys are camelCase.

#: Canonical biomarker keys the engine understands. Free string on the wire so
#: new markers don't break the contract; recognized values include the PhenoAge
#: panel (albumin, creatinine, glucose_fasting, crp, lymphocyte_pct, mcv, rdw,
#: alkaline_phosphatase, wbc) and cardiometabolic markers (hba1c, ldl, hdl,
#: total_cholesterol, triglycerides, systolic_bp, diastolic_bp).
Biomarker = str

#: "male" | "female" | "unknown".
Sex = str

#: "sedentary" | "low" | "moderate" | "high".
ActivityLevel = str

#: "active" | "resolved" | "historical".
ConditionStatus = str


class DemographicsInput(TypedDict, total=False):
    """Subject demographics — latest values win."""

    ageYears: float
    sex: Sex
    weightKg: float
    heightCm: float
    activity: ActivityLevel


class _ConditionInputRequired(TypedDict):
    #: ICD-10 code, e.g. "E11.9".
    icd10: str


class ConditionInput(_ConditionInputRequired, total=False):
    """An ICD-10 diagnosis to record for a subject."""

    status: ConditionStatus
    #: ISO timestamp.
    onsetAt: str


class HealthAgeComponent(TypedDict):
    label: str
    yearsDelta: float


class _BiologicalAgeRequired(TypedDict):
    biologicalAgeYears: float
    chronologicalAgeYears: float
    deltaYears: float
    #: "phenoage_hybrid" | "composite".
    method: str
    confidence: float
    components: List[HealthAgeComponent]


class BiologicalAge(_BiologicalAgeRequired, total=False):
    #: 10-year mortality score (0..1) from PhenoAge, when available.
    mortalityScore: Optional[float]


class _PredictedHealthConditionRequired(TypedDict):
    #: Canonical key, e.g. "type2_diabetes".
    condition: str
    label: str
    #: "above_threshold_now" | "threshold_projection".
    basis: str
    biomarker: str
    currentValue: float
    threshold: float
    confidence: float
    rationale: str
    sourceMemoryIds: List[str]


class PredictedHealthCondition(_PredictedHealthConditionRequired, total=False):
    #: ISO timestamp; set only for threshold_projection.
    projectedOnsetAt: Optional[str]


class BiomarkerReading(TypedDict):
    biomarker: str
    value: float
    unit: str
    observedAt: str


class _HealthProfileRequired(TypedDict):
    subject: Subject
    predictedConditions: List[PredictedHealthCondition]
    #: ICD-10 codes already diagnosed (active) on record.
    diagnosedConditions: List[str]
    latestBiomarkers: List[BiomarkerReading]
    #: Always populated — screening indicators, not a diagnosis.
    disclaimer: str
    generatedAt: str


class HealthProfile(_HealthProfileRequired, total=False):
    """Biological-age estimate + condition predictions + latest biomarkers."""

    biologicalAge: Optional[BiologicalAge]


class CohortConditionRisk(TypedDict):
    condition: str
    #: Fraction of the cohort carrying this condition (0..1).
    cohortPrevalence: float
    cohortSize: int
    countWith: int
    meanSimilarity: float
    confidence: float
    rationale: str


class CohortHealthRisk(TypedDict):
    """Condition prevalence among the patients most similar to a subject."""

    subject: Subject
    cohortSize: int
    populationSize: int
    risks: List[CohortConditionRisk]
    disclaimer: str
    generatedAt: str


# ── Financial vertical ───────────────────────────────────────────────────────
#
# Typed models mirroring ``thinkfleet-memory-sdk``'s ``types/financial.ts``.
# Financial data IS memory data: you ingest price bars, fundamentals, holdings,
# and news as memory items (see ``FinancialResource.ingest*``) and the engine
# derives indicators, portfolio risk, and a self-calibrating directional signal
# loop. Read shapes are returned by ``/lattice/financial/*``. Gated behind the
# ``@thinkfleet/pack-financial`` pack. Everything is informational only — NOT
# investment advice. Wire keys are camelCase.

#: "buy" | "sell" | "hold".
Direction = str


class _PriceInputRequired(TypedDict):
    ticker: str
    close: float


class PriceInput(_PriceInputRequired, total=False):
    """One price bar (daily close). Emit one per trading day to build history."""

    currency: str
    volume: float
    #: ISO timestamp of the bar; defaults to ingestion time.
    asOf: str


class _FundamentalInputRequired(TypedDict):
    ticker: str


class FundamentalInput(_FundamentalInputRequired, total=False):
    """Latest-wins fundamentals for a ticker."""

    peRatio: float
    marketCap: float
    dividendYield: float
    eps: float
    debtToEquity: float
    #: Vendor-reported beta. The engine also computes beta from price history.
    beta: float
    asOf: str


class _HoldingInputRequired(TypedDict):
    ticker: str
    shares: float


class HoldingInput(_HoldingInputRequired, total=False):
    """A portfolio position. Restated, not summed — the latest record wins."""

    costBasis: float
    #: "equity" | "bond" | "cash" | "crypto" | ... Defaults to "equity".
    assetClass: str


class _NewsInputRequired(TypedDict):
    headline: str


class NewsInput(_NewsInputRequired, total=False):
    """A news event. Tag one ticker or many; supply a sentiment in [-1, 1]."""

    ticker: str
    tickers: List[str]
    #: [-1, 1]; omit to let the engine score the headline.
    sentiment: float
    source: str
    publishedAt: str


class _TechnicalIndicatorsRequired(TypedDict):
    ticker: str
    lastClose: float
    asOf: str
    #: "none" | "computed" (from price history) | "reported" (vendor).
    betaSource: str
    sampleSize: int
    sourceMemoryIds: List[str]


class TechnicalIndicators(_TechnicalIndicatorsRequired, total=False):
    sma20: Optional[float]
    sma50: Optional[float]
    sma200: Optional[float]
    ema12: Optional[float]
    ema26: Optional[float]
    rsi14: Optional[float]
    macd: Optional[float]
    macdSignal: Optional[float]
    macdHistogram: Optional[float]
    bollingerUpper: Optional[float]
    bollingerMid: Optional[float]
    bollingerLower: Optional[float]
    bollingerPctB: Optional[float]
    annualizedVolatility: Optional[float]
    trailingReturn: Optional[float]
    #: Negative fraction, e.g. -0.25 for a 25% peak-to-trough decline.
    maxDrawdown: Optional[float]
    sharpe: Optional[float]
    beta: Optional[float]


class _FundamentalSnapshotRequired(TypedDict):
    ticker: str
    asOf: str
    sourceMemoryId: str


class FundamentalSnapshot(_FundamentalSnapshotRequired, total=False):
    peRatio: Optional[float]
    marketCap: Optional[float]
    dividendYield: Optional[float]
    eps: Optional[float]
    debtToEquity: Optional[float]
    beta: Optional[float]


class _PortfolioPositionRequired(TypedDict):
    ticker: str
    shares: float
    lastClose: float
    marketValue: float
    #: Fraction of total portfolio value.
    weight: float
    assetClass: str


class PortfolioPosition(_PortfolioPositionRequired, total=False):
    costBasis: Optional[float]
    unrealizedPnl: Optional[float]


class AssetAllocation(TypedDict):
    assetClass: str
    value: float
    weight: float


class _PortfolioRiskRequired(TypedDict):
    totalValue: float
    #: Herfindahl index of position weights, [0, 1]. 1 = single name.
    concentrationHhi: float
    allocations: List[AssetAllocation]
    varMethod: str


class PortfolioRisk(_PortfolioRiskRequired, total=False):
    weightedBeta: Optional[float]
    weightedAnnualizedVolatility: Optional[float]
    #: Parametric 1-day 95% VaR in currency units (ignores correlation).
    valueAtRisk95_1d: Optional[float]


class _FinancialProfileRequired(TypedDict):
    subject: Subject
    indicators: List[TechnicalIndicators]
    fundamentals: List[FundamentalSnapshot]
    #: Empty in ticker mode (subject.kind === "ticker").
    positions: List[PortfolioPosition]
    #: Held tickers with no market data in the corpus (couldn't be priced).
    unpricedHoldings: List[str]
    #: Always populated — informational only, not investment advice.
    disclaimer: str
    generatedAt: str


class FinancialProfile(_FinancialProfileRequired, total=False):
    """Technical indicators + (for a portfolio subject) a risk rollup."""

    #: Absent in ticker mode or when the portfolio has no priced value.
    portfolioRisk: Optional[PortfolioRisk]


class _FinancialSignalRequired(TypedDict):
    ticker: str
    strategy: str
    direction: Direction
    #: Blended sub-signal score in [-1, 1], bullish positive.
    score: float
    #: Raw model agreement before calibration.
    structuralConfidence: float
    #: The number to trust: structural × the strategy's realized reliability.
    reportedConfidence: float
    expectedReturn: float
    horizonDays: int
    basisClose: float
    #: ISO timestamp when the call becomes scoreable.
    dueAt: str
    rationale: List[str]
    newsUsed: bool
    sourceMemoryIds: List[str]


class FinancialSignal(_FinancialSignalRequired, total=False):
    #: Set when the call was persisted for later scoring.
    predictionId: Optional[str]


class PredictFinancialResult(TypedDict):
    signals: List[FinancialSignal]
    strategy: str
    #: Reliability multiplier applied this run (0 resolved → 1.0).
    strategyReliability: float
    resolvedSample: int
    disclaimer: str
    generatedAt: str


class ReconcileFinancialResult(TypedDict):
    #: Newly resolved this pass.
    scored: int
    hits: int
    misses: int
    #: Due-or-not, not yet scoreable.
    stillPending: int
    generatedAt: str


class FinancialCalibrationBucket(TypedDict):
    lower: float
    upper: float
    predictions: int
    hits: int
    misses: int
    realizedHitRate: float
    hasData: bool


class FinancialCalibrationReport(TypedDict):
    buckets: List[FinancialCalibrationBucket]
    #: "all" when unfiltered.
    strategy: str
    strategyReliability: float
    totalResolved: int
    generatedAt: str


class PredictOptions(TypedDict, total=False):
    """Option bag for ``FinancialResource.predict``."""

    #: Horizon in days; default 30, clamped [1, 365].
    horizonDays: int
    #: Persist each call for later scoring; default true.
    persist: bool


class CalibrationOptions(TypedDict, total=False):
    """Option bag for ``FinancialResource.get_calibration``."""

    #: Number of confidence bands; default 5, clamped [1, 20].
    bucketCount: int
    #: Filter to one strategy; omit for all.
    strategy: str


# ── Compliance vertical ──────────────────────────────────────────────────────
#
# Typed models mirroring ``thinkfleet-memory-sdk``'s ``resources/compliance.ts``.
# GDPR-grade subject export (Art. 15), right-to-erasure (Art. 17), the audit
# log, and compliance-pack management. Served under ``/memory-compliance/*`` and
# ``/memory-compliance-packs``. Wire keys are camelCase (except the export
# bundle's snake_case interior, which is returned verbatim by the engine).


class ComplianceSubject(TypedDict):
    """The subject an export / erasure / audit query is scoped to."""

    kind: str
    externalId: str


class ExportCounts(TypedDict):
    memories: int
    patterns: int
    observations: int
    events: int
    alertFires: int


class ExportSubjectBundle(TypedDict):
    """The Art. 15 data bundle — snake_case interior, returned verbatim."""

    subject: ComplianceSubject
    memories: List[Any]
    patterns: List[Any]
    observations: List[Any]
    events: List[Any]
    alert_fires: List[Any]
    generated_at: str


class ExportSubjectResponse(TypedDict):
    subject: ComplianceSubject
    export: Optional[ExportSubjectBundle]
    counts: ExportCounts
    generatedAt: str
    durationMs: float


class _HardDeleteSubjectRequestRequired(TypedDict):
    subject: ComplianceSubject
    #: Free-text reason for the audit log. Required — Art. 17 requests carry a
    #: case id.
    reason: str


class HardDeleteSubjectRequest(_HardDeleteSubjectRequestRequired, total=False):
    #: Preview-only when true; no rows touched.
    dryRun: bool


class HardDeleteSubjectResponse(TypedDict):
    subject: ComplianceSubject
    memoriesDeleted: int
    patternsDeleted: int
    observationsDeleted: int
    eventsDeleted: int
    alertFiresDeleted: int
    dryRun: bool
    auditEventId: Optional[str]
    generatedAt: str
    durationMs: float


class ListAuditParams(TypedDict, total=False):
    """Filters for ``ComplianceResource.list_audit_events``."""

    #: Restrict to events touching this subject.
    subject: ComplianceSubject
    #: Restrict to a specific actor (user or service key id).
    actor: str
    #: Event types to include. Empty = all.
    eventTypes: List[str]
    #: ISO-8601 lower bound. Newer events only.
    since: str
    #: Max events to return. Default 100, max 1000.
    limit: int


class AuditEvent(TypedDict):
    id: str
    created: str
    actor: str
    #: "read.search", "read.context", "read.predict", "read.profile",
    #: "read.export", "subject.hard_delete", etc.
    eventType: str
    query: Optional[str]
    memoryIds: Optional[str]
    resultCount: int
    metadata: Dict[str, Any]


class CompliancePack(TypedDict):
    #: Stable pack id — e.g. "hipaa", "gdpr".
    id: str
    #: Pack version — bump when redaction/consent rules change.
    version: str
    #: Human-readable description of what the pack enforces.
    description: str
    #: Memory classes the pack claims jurisdiction over (e.g. "phi", "pii").
    ownsClasses: List[str]
    #: Regulatory tags this pack maps to (e.g. "HIPAA", "GDPR-Art-9").
    regulatoryTags: List[str]


class ProjectPackEnablement(TypedDict):
    id: str
    packId: str
    enabled: bool
    config: Dict[str, Any]
    enabledByUserId: Optional[str]
    created: str
    updated: str


class _UpsertProjectPackRequestRequired(TypedDict):
    packId: str
    enabled: bool


class UpsertProjectPackRequest(_UpsertProjectPackRequestRequired, total=False):
    #: Pack-owned opaque config. Schema is the pack's responsibility.
    config: Dict[str, Any]
