"""S03 consumes versioned snapshot-bound TypeScript/Python observations.

The callable extension adds immutable lexical values and namespace member calls.
Dynamic callbacks and mutable object dispatch retain explicit outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from seremy.contracts import (
    PROFILE_ID,
    EvidenceRef,
    Span,
    canonical_bytes,
    sha256_hex,
)
from seremy.parsing import (
    CandidateRecord,
    DeclarationRecord,
    ParsedFileResult,
    artifact_digest as s02_artifact_digest,
)
from seremy.language_profiles import ECMASCRIPT_BINDING_PROFILE, ECMASCRIPT_PROFILE, parsed_profile

PRODUCER_RESOLVER = "seremy.resolver/0.2"
BINDING_PROFILE = "typescript-checker-v0.2"
CALLABLE_BINDING_PROFILE = "typescript-callable-checker-v0.1"
PYTHON_BINDING_PROFILE = "python-ast-static-v0.1"
EXPECTED_S02_PRODUCER = "seremy.parsing/0.1"

RESOLVED_SINGLE = "RESOLVED_SINGLE"
RESOLVED_TARGET_SET = "RESOLVED_TARGET_SET"
EXTERNAL = "EXTERNAL"
AMBIGUOUS = "AMBIGUOUS"
MISSING = "MISSING"
READINESS_UNKNOWN = "READINESS_UNKNOWN"
UNSUPPORTED = "UNSUPPORTED"
BINDER_FAILED = "BINDER_FAILED"
LINK_MISSING = "LINK_MISSING"
CANCELLED = "CANCELLED"
NOT_PROCESSED = "NOT_PROCESSED"
PENDING_LINK = "PENDING_LINK"  # internal, never final in this profile

TERMINAL_STATES = frozenset(
    {
        RESOLVED_SINGLE,
        RESOLVED_TARGET_SET,
        EXTERNAL,
        AMBIGUOUS,
        MISSING,
        READINESS_UNKNOWN,
        UNSUPPORTED,
        BINDER_FAILED,
        LINK_MISSING,
        CANCELLED,
        NOT_PROCESSED,
    }
)

# Declared relation-kind table (S03-R4): candidate kind + binding
# operation -> legal relation kinds for this profile.
RELATION_KIND_TABLE = {"call+definition": ("CALLS",), "member_call+definition": ("CALLS",)}
# Member calls require the profile's proven namespace/module target; mutable
# receiver calls still have explicit unsupported outcomes.

ATTEMPTED_KINDS = frozenset({"call", "member_call"})


@dataclass(frozen=True)
class Entity:
    """Snapshot-scoped declaration identity (declaration ID == entity ID)."""

    entity_id: str
    file_id: str
    kind: str
    name: str
    name_span: Span
    decl_span: Span

    def to_artifact_record(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "file_id": self.file_id,
            "kind": self.kind,
            "name": self.name,
            "name_span": [self.name_span.start, self.name_span.end],
            "decl_span": [self.decl_span.start, self.decl_span.end],
        }


@dataclass(frozen=True)
class Occurrence:
    candidate_id: str
    file_id: str
    span: Span
    evidence: EvidenceRef

    def to_artifact_record(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "file_id": self.file_id,
            "span": [self.span.start, self.span.end],
            "evidence": {
                "blob_sha256": self.evidence.blob_sha256,
                "span": [self.evidence.span.start, self.evidence.span.end],
                "producer": self.evidence.producer,
                "method": self.evidence.method,
                "method_version": self.evidence.method_version,
            },
        }


@dataclass
class ResolutionRecord:
    """One final record per candidate (S03-R1), observations included."""

    candidate_id: str
    file_id: str
    candidate_kind: str
    name: str
    candidate_span: Span
    outcome: str
    reason: Optional[str] = None
    target: Optional[str] = None  # entity ID, file ID or external URI
    target_type: Optional[str] = None  # entity_ref | file_ref | external_ref
    alternatives: Tuple[str, ...] = ()
    operation: str = "definition"
    occurrence: Optional[Occurrence] = None
    attempted: bool = False

    def to_artifact_record(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "file_id": self.file_id,
            "candidate_kind": self.candidate_kind,
            "name": self.name,
            "candidate_span": [self.candidate_span.start, self.candidate_span.end],
            "outcome": self.outcome,
            "reason": self.reason,
            "target": self.target,
            "target_type": self.target_type,
            "alternatives": list(self.alternatives),
            "operation": self.operation,
            "occurrence": self.occurrence.to_artifact_record() if self.occurrence else None,
            "attempted": self.attempted,
        }


@dataclass
class DirectRelation:
    """Deduplicated direct edge retaining every source occurrence (S03-R6)."""

    source: str
    source_type: str
    target: str
    target_type: str
    kind: str  # from RELATION_KIND_TABLE, e.g. CALLS
    origin: str  # binder_observation (syntax_candidate would overclaim binding)
    occurrences: List[Occurrence] = field(default_factory=list)

    def to_artifact_record(self) -> dict:
        return {
            "source": self.source,
            "source_type": self.source_type,
            "target": self.target,
            "target_type": self.target_type,
            "kind": self.kind,
            "origin": self.origin,
            "occurrences": [o.to_artifact_record() for o in self.occurrences],
        }


def _entity_id_for(file_id: str, declaration: DeclarationRecord) -> str:
    return f"ent:{file_id}#{declaration.kind}:{declaration.name}@{declaration.name_span.start}"


def _candidate_id_for(file_id: str, candidate: CandidateRecord) -> str:
    return f"cand:{file_id}#{candidate.kind}:{candidate.name}@{candidate.span.start}"


def _enclosing_declaration(
    declarations: List[DeclarationRecord], span: Span
) -> Optional[DeclarationRecord]:
    containing = [
        d
        for d in declarations
        if d.decl_span.start <= span.start and span.end <= d.decl_span.end
    ]
    if not containing:
        return None
    return max(containing, key=lambda d: d.decl_span.start)


class Resolver:
    """Static binder for the Milestone 1 slice."""

    def __init__(self, results: List[ParsedFileResult], *, expected_s02_digest: str, profile_id: Optional[str] = None):
        if not results:
            raise ValueError("resolver requires at least one parsed file result")
        self.profile_id=profile_id or parsed_profile(results)
        digest = s02_artifact_digest(results,profile_id=self.profile_id)
        if digest != expected_s02_digest:
            raise ValueError(
                "S02 artifact digest mismatch: results digest "
                f"{digest} != expected {expected_s02_digest}"
            )
        self.results = results
        self.by_file: Dict[str, ParsedFileResult] = {r.file_id: r for r in results}
        self.universe = frozenset(self.by_file)
        self.script_binding_profile=ECMASCRIPT_BINDING_PROFILE if self.profile_id==ECMASCRIPT_PROFILE else BINDING_PROFILE
        script_results=[result for result in results if not result.file_id.endswith(".py")]
        extensions={result.construct_coverage.get("binding_extension") for result in script_results}
        if CALLABLE_BINDING_PROFILE in extensions:
            if extensions!={CALLABLE_BINDING_PROFILE}:
                raise ValueError("mixed callable binding extensions in one script snapshot")
            self.script_binding_profile=CALLABLE_BINDING_PROFILE

    # -- helpers ------------------------------------------------------------

    def _entity(self, file_id: str, declaration: DeclarationRecord) -> Entity:
        return Entity(
            entity_id=_entity_id_for(file_id, declaration),
            file_id=file_id,
            kind=declaration.kind,
            name=declaration.name,
            name_span=declaration.name_span,
            decl_span=declaration.decl_span,
        )

    def _bind_call(self, file_id: str, candidate: CandidateRecord) -> ResolutionRecord:
        observation = candidate.attributes.get("binding")
        if not observation:
            return ResolutionRecord(
                candidate_id=_candidate_id_for(file_id, candidate), file_id=file_id,
                candidate_kind=candidate.kind, name=candidate.name, candidate_span=candidate.span,
                outcome=BINDER_FAILED, reason="missing_compiler_observation", attempted=True)
        context = observation.get("context", {})
        method = PYTHON_BINDING_PROFILE if file_id.endswith(".py") else self.script_binding_profile
        expected = sorted([r.file_id, r.analysis_sha256] for r in self.results
                          if r.file_id.endswith(".py") == file_id.endswith(".py"))
        if context.get("method") != method or context.get("snapshot_files") != expected:
            raise ValueError("compiler observation does not bind the parsed snapshot")
        record = ResolutionRecord(
            candidate_id=_candidate_id_for(file_id, candidate), file_id=file_id,
            candidate_kind=candidate.kind, name=candidate.name, candidate_span=candidate.span,
            outcome=observation["outcome"], reason=observation.get("reason"), attempted=True)
        if record.outcome == EXTERNAL:
            record.target = observation["target"]
            record.target_type = "external_ref"
        if record.outcome != RESOLVED_SINGLE:
            return record
        target = observation["target"]
        parsed = self.by_file.get(target["file_id"])
        if parsed is None or parsed.analysis_sha256 != target["content_sha256"]:
            raise ValueError("compiler target is outside the parsed snapshot")
        declarations = [d for d in parsed.declarations
                        if d.name == target["name"] and d.kind == target["kind"]
                        and [d.name_span.start, d.name_span.end] == target["name_byte"]]
        if len(declarations) != 1:
            record.outcome = UNSUPPORTED
            record.reason = "target_not_in_valid_parsed_declarations"
            return record
        record.target = _entity_id_for(parsed.file_id, declarations[0])
        record.target_type = "entity_ref"
        evidence = EvidenceRef(
            blob_sha256=self.by_file[file_id].analysis_sha256, span=candidate.span,
            producer=PRODUCER_RESOLVER, method=method, method_version="0.2" if method==BINDING_PROFILE else "0.1")
        record.occurrence = Occurrence(
            candidate_id=record.candidate_id, file_id=file_id, span=candidate.span, evidence=evidence)
        return record

    # -- main entry ----------------------------------------------------------

    def resolve(self) -> "ResolutionSet":
        resolutions: List[ResolutionRecord] = []
        for file_id in sorted(self.by_file):
            parsed = self.by_file[file_id]
            for candidate in parsed.candidates:
                if candidate.kind in ATTEMPTED_KINDS:
                    resolutions.append(self._bind_call(file_id, candidate))
                else:
                    # Not attempted in the calls-only profile; still
                    # accounted (S03-R1, S03-R6 conservation).
                    resolutions.append(
                        ResolutionRecord(
                            candidate_id=_candidate_id_for(file_id, candidate),
                            file_id=file_id,
                            candidate_kind=candidate.kind,
                            name=candidate.name,
                            candidate_span=candidate.span,
                            outcome=NOT_PROCESSED,
                            reason="jsx_runtime_semantics_outside_profile" if candidate.kind=="jsx_tag" else "not_attempted_calls_only_profile",
                            attempted=False,
                        )
                    )

        self._check_conservation(resolutions)
        return self._build_resolution_set(resolutions)

    @staticmethod
    def _check_conservation(resolutions: List[ResolutionRecord]) -> None:
        ids = [r.candidate_id for r in resolutions]
        if len(ids) != len(set(ids)):
            raise AssertionError("duplicate ResolutionRecord for a candidate")
        terminal = [r for r in resolutions if r.outcome in TERMINAL_STATES]
        if len(terminal) != len(resolutions):
            unresolved = sorted(
                r.candidate_id for r in resolutions if r.outcome not in TERMINAL_STATES
            )
            raise AssertionError(f"nonterminal outcomes at finalization: {unresolved}")

    def _build_resolution_set(self, resolutions: List[ResolutionRecord]) -> "ResolutionSet":
        entities = {
            _entity_id_for(file_id, d): self._entity(file_id, d)
            for file_id, parsed in self.by_file.items()
            for d in parsed.declarations
        }
        edges: Dict[Tuple[str, str, str], DirectRelation] = {}
        for record in resolutions:
            if record.outcome != RESOLVED_SINGLE or record.target_type != "entity_ref":
                continue
            source_entity = _enclosing_declaration(
                self.by_file[record.file_id].declarations, record.candidate_span
            )
            source_id = (
                _entity_id_for(record.file_id, source_entity)
                if source_entity
                else f"file:{record.file_id}"
            )
            source_type = "entity_ref" if source_entity else "file_ref"
            candidate = next(c for c in self.by_file[record.file_id].candidates
                             if _candidate_id_for(record.file_id,c)==record.candidate_id)
            if "source_owner" in candidate.attributes:
                source_id=candidate.attributes["source_owner"]
                if source_id not in entities and source_id!="file:"+record.file_id:
                    raise ValueError("invalid lexical source owner")
                source_type="entity_ref" if source_id in entities else "file_ref"
            key = (source_id, "CALLS", record.target)
            edge = edges.setdefault(
                key,
                DirectRelation(
                    source=source_id,
                    source_type=source_type,
                    target=record.target,
                    target_type="entity_ref",
                    kind="CALLS",
                    origin="binder_observation",
                ),
            )
            edge.occurrences.append(record.occurrence)

        profiles={PYTHON_BINDING_PROFILE if r.file_id.endswith(".py") else self.script_binding_profile for r in self.results}
        profile=next(iter(profiles)) if len(profiles)==1 else "mixed-callable-static-v0.1" if CALLABLE_BINDING_PROFILE in profiles else "mixed-ecmascript-static-v0.1" if ECMASCRIPT_BINDING_PROFILE in profiles else "mixed-static-v0.1"
        return ResolutionSet(
            entities=entities,
            resolutions=resolutions,
            edges=sorted(
                edges.values(),
                key=lambda e: (e.source, e.kind, e.target),
            ),
            binding_profile=profile,
            profile_id=self.profile_id,
        )


@dataclass
class ResolutionSet:
    """S03 handoff: entities, resolution records and deduplicated edges."""

    entities: Dict[str, Entity]
    resolutions: List[ResolutionRecord]
    edges: List[DirectRelation]
    binding_profile: str
    profile_id: str = PROFILE_ID

    def outcome_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for record in self.resolutions:
            counts[record.outcome] = counts.get(record.outcome, 0) + 1
        return counts

    def attempted_count(self) -> int:
        return sum(1 for r in self.resolutions if r.attempted)

    def to_artifact(self, *, manifest_digest: str, s02_digest: str) -> dict:
        return {
            "artifact": "s03-relations-slice",
            "profile": self.profile_id,
            "producer": PRODUCER_RESOLVER,
            "binding_profile": self.binding_profile,
            "binds": {"inventory_manifest_digest": manifest_digest, "s02_artifact_digest": s02_digest},
            "entities": [self.entities[k].to_artifact_record() for k in sorted(self.entities)],
            "resolutions": [r.to_artifact_record() for r in self.resolutions],
            "edges": [e.to_artifact_record() for e in self.edges],
            "coverage": {
                "candidate_count": len(self.resolutions),
                "attempted_count": self.attempted_count(),
                "outcome_counts": dict(sorted(self.outcome_counts().items())),
                "direct_edge_count": len(self.edges),
                "total_occurrences": sum(len(e.occurrences) for e in self.edges),
            },
        }


def artifact_digest(set_artifact: dict) -> str:
    return sha256_hex(canonical_bytes(set_artifact))
