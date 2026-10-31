import { describe, expect, it } from 'vitest';
import {
  echoDisplay,
  evidenceChips,
  evidenceIndex,
  evidenceLevelName,
  formatPlatformNumber,
  formatScore,
  isPlatformReport,
  scoreBreakdown,
  scoreInputsOf,
} from './reportPresenters';
import {
  evidenceItemFixture,
  rankedOptionFixture,
  reportFixtureFull,
  statementFixture,
} from '../test/fixtures';

describe('evidenceIndex / evidenceChips', () => {
  it('numbers evidence in order and keeps unknown ids visible', () => {
    const first = evidenceItemFixture();
    const second = evidenceItemFixture({
      chunk_id: 'other-doc:00007',
      doc_id: 'other-doc',
    });
    const index = evidenceIndex([first, second]);
    expect(index.get(first.chunk_id)).toBe(1);
    expect(index.get(second.chunk_id)).toBe(2);

    const chips = evidenceChips(
      statementFixture('x', { evidence_ids: [second.chunk_id, 'missing:1'] }),
      index,
    );
    expect(chips).toEqual([
      { n: 2, chunkId: second.chunk_id, resolved: true },
      { n: null, chunkId: 'missing:1', resolved: false },
    ]);
  });
});

describe('isPlatformReport', () => {
  it('treats fallback reports as platform-written', () => {
    expect(isPlatformReport(reportFixtureFull(true))).toBe(true);
    expect(isPlatformReport(reportFixtureFull(false))).toBe(false);
  });
});

describe('scoreBreakdown', () => {
  it('returns stable rows with weight × value contributions', () => {
    const rows = scoreBreakdown(rankedOptionFixture());
    expect(rows.map((row) => row.component)).toEqual([
      'constraint_fit',
      'evidence_strength',
      'indicator_relevance',
    ]);
    expect(rows).toContainEqual({
      component: 'evidence_strength',
      value: 1.0,
      weight: 0.5,
      contribution: 0.5,
    });
    const total = rows.reduce((sum, row) => sum + row.contribution, 0);
    expect(total).toBeCloseTo(1.0, 9);
  });
});

describe('evidenceLevelName', () => {
  it('names the three rubric levels and passes the rest through raw', () => {
    expect(evidenceLevelName(0)).toBe('needs_evidence');
    expect(evidenceLevelName(1)).toBe('single_source');
    expect(evidenceLevelName(2)).toBe('multi_source');
    expect(evidenceLevelName(7)).toBe('level 7');
  });
});

describe('echoDisplay', () => {
  it('marks only the exact backend unknown', () => {
    expect(echoDisplay('unknown')).toEqual({ text: 'Unknown', unknown: true });
    expect(echoDisplay('Unknown').unknown).toBe(false);
    expect(echoDisplay('saves 20% water').unknown).toBe(false);
  });
});

describe('scoreInputsOf', () => {
  it('narrows the open-typed inputs and sorts statuses', () => {
    const inputs = scoreInputsOf(
      rankedOptionFixture({
        score_inputs: {
          evidence_level: 1,
          evidence_doc_ids: ['b-doc', 'a-doc'],
          indicator_statuses: { era5_spi: 'ok', chirps_spi: 'failed' },
          exclusion_reasons: 0,
        },
      }),
    );
    expect(inputs.evidenceLevel).toBe(1);
    expect(inputs.evidenceDocIds).toEqual(['b-doc', 'a-doc']);
    expect(inputs.indicatorStatuses).toEqual([
      { indicator: 'chirps_spi', status: 'failed' },
      { indicator: 'era5_spi', status: 'ok' },
    ]);
    expect(inputs.exclusionReasons).toBe(0);
  });

  it('degrades malformed inputs to empty values without throwing', () => {
    const inputs = scoreInputsOf(
      rankedOptionFixture({
        score_inputs: {
          evidence_level: null,
          evidence_doc_ids: 'not-a-list',
          indicator_statuses: ['not-a-dict'],
          exclusion_reasons: 'zero',
        },
      }),
    );
    expect(inputs).toEqual({
      evidenceLevel: null,
      evidenceDocIds: [],
      indicatorStatuses: [],
      exclusionReasons: null,
    });
  });
});

describe('formatters', () => {
  it('rounds scores but keeps platform numbers verbatim', () => {
    expect(formatScore(0.1 + 0.2)).toBe('0.300');
    expect(formatScore(Number.NaN)).toBe('not a number');
    expect(formatPlatformNumber(-0.517141160387881)).toBe('-0.517141160387881');
    expect(formatPlatformNumber(Number.POSITIVE_INFINITY)).toBe('not a number');
  });
});
