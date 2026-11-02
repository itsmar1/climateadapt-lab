/**
 * Presenters for the report + ranking sections: evidence numbering, statement
 * trace chips, score breakdowns, unknown handling. Pure mapping with defensive
 * narrowing (same style as presenters.ts). No severity language anywhere.
 */

import type { EvidenceItem, RankedOption, Report, Statement } from './client';

/** Number report evidence E1..En in payload order, keyed by chunk id. */
export function evidenceIndex(evidence: EvidenceItem[]): Map<string, number> {
  const index = new Map<string, number>();
  evidence.forEach((item, position) => {
    if (!index.has(item.chunk_id)) {
      index.set(item.chunk_id, position + 1);
    }
  });
  return index;
}

export interface EvidenceChip {
  n: number | null;
  chunkId: string;
  resolved: boolean;
}

/** Map a statement's evidence ids to chips; unresolved ids stay visible. */
export function evidenceChips(
  statement: Statement,
  index: Map<string, number>,
): EvidenceChip[] {
  return (statement.evidence_ids ?? []).map((chunkId) => {
    const n = index.get(chunkId);
    return { n: n ?? null, chunkId, resolved: n !== undefined };
  });
}

/** True when the report text itself is platform-written (never model prose). */
export function isPlatformReport(report: Report): boolean {
  return report.fallback || report.generator === 'deterministic-fallback';
}

export type Acceptance = 'ai-accepted' | 'ai-partial' | 'fallback';

/** How the report was accepted; legacy reports without stamps use the flag. */
export function acceptanceOf(report: Report): Acceptance {
  if (
    report.acceptance === 'ai-accepted' ||
    report.acceptance === 'ai-partial' ||
    report.acceptance === 'fallback'
  ) {
    return report.acceptance;
  }
  return isPlatformReport(report) ? 'fallback' : 'ai-accepted';
}

/** True when some statements are model-written and some platform-written. */
export function isPartialReport(report: Report): boolean {
  return acceptanceOf(report) === 'ai-partial';
}

/** Counted-statement locations in render order (backend vocabulary). */
export function statementLocations(report: Report): string[] {
  const locations = ['summary'];
  report.environmental_findings.forEach((_, index) => {
    locations.push(`environmental_findings[${index}]`);
  });
  (report.ranked_recommendations ?? []).forEach((_, index) => {
    locations.push(`ranked_recommendations[${index}]`);
  });
  (report.excluded_options ?? []).forEach((_, index) => {
    locations.push(`excluded_options[${index}]`);
  });
  (report.limitations ?? []).forEach((_, index) => {
    locations.push(`limitations[${index}]`);
  });
  (report.assumptions ?? []).forEach((_, index) => {
    locations.push(`assumptions[${index}]`);
  });
  locations.push('data_coverage');
  return locations;
}

/** (model-written, total) counted statements; legacy reports use the flag. */
export function modelStatementCounts(report: Report): { model: number; total: number } {
  const origins = report.statement_origins ?? {};
  const keys = Object.keys(origins);
  if (keys.length > 0) {
    return {
      model: keys.filter((key) => origins[key] === 'model').length,
      total: keys.length,
    };
  }
  const total = statementLocations(report).length;
  return isPlatformReport(report) ? { model: 0, total } : { model: total, total };
}

/** Authorship of one statement, or null when the report predates stamps. */
export function statementOrigin(
  report: Report,
  location: string,
): 'model' | 'platform' | null {
  const origin = (report.statement_origins ?? {})[location];
  if (origin === 'model' || origin === 'platform') {
    return origin;
  }
  return null;
}

export interface ChangedStatement {
  location: string;
  codes: string[];
}

/** Replaced statements (composite location) with the codes that forced it. */
export function replacedStatements(report: Report): ChangedStatement[] {
  return Object.entries(report.replaced_statements ?? {}).map(([location, codes]) => ({
    location,
    codes,
  }));
}

/** Dropped statements (model location) with their codes. */
export function droppedStatements(report: Report): ChangedStatement[] {
  return Object.entries(report.dropped_statements ?? {}).map(([location, codes]) => ({
    location,
    codes,
  }));
}

export interface ScoreRow {
  component: string;
  value: number;
  weight: number;
  contribution: number;
}

/** Score breakdown rows in stable component-name order. */
export function scoreBreakdown(option: RankedOption): ScoreRow[] {
  return Object.keys(option.score_components)
    .sort()
    .map((component) => {
      const value = option.score_components[component] ?? 0;
      const weight = option.score_weights[component] ?? 0;
      return { component, value, weight, contribution: weight * value };
    });
}

/** Backend rubric names (recommend/evidence.py LEVEL_NAMES); raw past level 2. */
export function evidenceLevelName(level: unknown): string {
  if (level === 0) {
    return 'needs_evidence';
  }
  if (level === 1) {
    return 'single_source';
  }
  if (level === 2) {
    return 'multi_source';
  }
  return `level ${String(level)}`;
}

export interface EchoDisplay {
  text: string;
  unknown: boolean;
}

/**
 * Render a benefit/cost/risk echo. The backend sends the literal "unknown"
 * unless a source states a value; unknowns render as "Unknown", never blank.
 */
export function echoDisplay(value: string): EchoDisplay {
  if (value === 'unknown') {
    return { text: 'Unknown', unknown: true };
  }
  return { text: value, unknown: false };
}

export interface IndicatorStatus {
  indicator: string;
  status: string;
}

export interface ScoreInputs {
  evidenceLevel: unknown;
  evidenceDocIds: string[];
  indicatorStatuses: IndicatorStatus[];
  exclusionReasons: number | null;
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === 'string');
}

/** Narrow the open-typed score_inputs dict without ever throwing. */
export function scoreInputsOf(option: RankedOption): ScoreInputs {
  const inputs = option.score_inputs as Record<string, unknown>;
  const statuses = inputs.indicator_statuses;
  const indicatorStatuses: IndicatorStatus[] = [];
  if (typeof statuses === 'object' && statuses !== null && !Array.isArray(statuses)) {
    for (const [indicator, status] of Object.entries(statuses)) {
      indicatorStatuses.push({
        indicator,
        status: typeof status === 'string' ? status : String(status),
      });
    }
  }
  indicatorStatuses.sort((a, b) => (a.indicator < b.indicator ? -1 : 1));
  const exclusionReasons = inputs.exclusion_reasons;
  return {
    evidenceLevel: inputs.evidence_level,
    evidenceDocIds: asStringArray(inputs.evidence_doc_ids),
    indicatorStatuses,
    exclusionReasons:
      typeof exclusionReasons === 'number' && Number.isFinite(exclusionReasons)
        ? exclusionReasons
        : null,
  };
}

/** Scores are display-rounded; platform numbers below are verbatim. */
export function formatScore(value: number): string {
  return Number.isFinite(value) ? value.toFixed(3) : 'not a number';
}

/** Verbatim rendering: ReportedNumber values were copied, never computed here. */
export function formatPlatformNumber(value: number): string {
  return Number.isFinite(value) ? String(value) : 'not a number';
}
