"""Evidence-linked intervention catalog with deterministic constraints and ranking."""

from climateadapt.recommend.constraints import (
    CROP_NOT_APPLICABLE,
    NEEDS_EVIDENCE,
    NO_IRRIGATION_EQUIPMENT,
    NO_WATER_SOURCE,
    PRODUCTION_SYSTEM_MISMATCH,
    ConstraintResult,
    evaluate,
    evaluate_all,
)
from climateadapt.recommend.evidence import (
    MAX_EVIDENCE_LEVEL,
    evidence_level,
    evidence_score,
    format_evidence_reference,
)
from climateadapt.recommend.loader import load_catalog, packaged_catalog_path
from climateadapt.recommend.ranking import (
    CONSTRAINT_FIT_WEIGHT,
    EVIDENCE_WEIGHT,
    INDICATOR_WEIGHT,
    SCORE_WEIGHTS,
    indicator_relevance,
    rank,
)
from climateadapt.recommend.schema import (
    CATALOG_VERSION,
    UNKNOWN,
    Applicability,
    EvidenceLink,
    EvidenceReference,
    ExcludedOption,
    ExclusionReason,
    Intervention,
    InterventionCatalog,
    RankedOption,
    RecommendationResponse,
    ScenarioContext,
)
from climateadapt.recommend.service import LIMITATIONS, recommend
from climateadapt.recommend.validate import (
    IngestedDocInfo,
    ValidationIssue,
    ValidationReport,
    validate_catalog,
)

__all__ = [
    "CATALOG_VERSION",
    "CONSTRAINT_FIT_WEIGHT",
    "CROP_NOT_APPLICABLE",
    "EVIDENCE_WEIGHT",
    "INDICATOR_WEIGHT",
    "LIMITATIONS",
    "MAX_EVIDENCE_LEVEL",
    "NEEDS_EVIDENCE",
    "NO_IRRIGATION_EQUIPMENT",
    "NO_WATER_SOURCE",
    "PRODUCTION_SYSTEM_MISMATCH",
    "SCORE_WEIGHTS",
    "UNKNOWN",
    "Applicability",
    "ConstraintResult",
    "EvidenceLink",
    "EvidenceReference",
    "ExcludedOption",
    "ExclusionReason",
    "Intervention",
    "InterventionCatalog",
    "IngestedDocInfo",
    "RankedOption",
    "RecommendationResponse",
    "ScenarioContext",
    "ValidationIssue",
    "ValidationReport",
    "evaluate",
    "evaluate_all",
    "evidence_level",
    "evidence_score",
    "format_evidence_reference",
    "indicator_relevance",
    "load_catalog",
    "packaged_catalog_path",
    "rank",
    "recommend",
    "validate_catalog",
]
