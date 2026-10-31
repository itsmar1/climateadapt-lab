import { describe, expect, it } from 'vitest';
import { reportToMarkdown } from './export';
import {
  fullDetailFixture,
  reportFixtureFull,
  scenarioDetailFixture,
} from '../test/fixtures';

describe('reportToMarkdown', () => {
  it('exports every section with citations, scores, unknowns, and limitations', () => {
    const text = reportToMarkdown(fullDetailFixture());

    expect(text).toContain('# ClimateAdapt Lab report — scenario `sc-test`');
    expect(text).toContain('Computed by the platform');
    expect(text).toContain('Deterministic fallback: Model output rejected (test)');
    expect(text).toContain('## Summary');
    expect(text).toContain('Synthetic summary.');
    expect(text).toContain('## Environmental findings');
    expect(text).toContain('Synthetic finding with a traced value.');
    expect(text).toContain('Evidence: E1.');
    expect(text).toContain('Deterministic outputs: chirps_spi.');
    expect(text).toContain('- Platform value: -0.517 SPI (from chirps_spi.spi).');

    expect(text).toContain('## Ranked recommendations');
    expect(text).toContain('### Deficit irrigation (`deficit-irrigation`)');
    expect(text).toContain('Deterministic score: 1.000');
    expect(text).toContain('| evidence_strength | 1.000 | 0.500 | 0.500 |');
    expect(text).toContain(
      'Evidence strength: level 2 (fao-iddp66-crop-yield-response-to-water).',
    );
    expect(text).toContain('- Unknown: soil type at the farm');
    expect(text).toContain('- Benefit: Unknown');
    expect(text).toContain('Synthetic recommendation narrative.');

    expect(text).toContain('## Excluded options');
    expect(text).toContain('Reason codes: needs_evidence.');
    expect(text).toContain('Evidence status: needs_evidence.');

    expect(text).toContain('## Evidence');
    expect(text).toContain('### E1 — `fao-iddp66-crop-yield-response-to-water:00001`');
    expect(text).toContain('Steduto et al. (2012). Crop yield response to water.');
    expect(text).toContain('Landing page: https://example.invalid/fao-iddp66');
    expect(text).toContain('Licence: CC BY-NC-SA 3.0 IGO (status: verified_in_record).');

    expect(text).toContain('## Limitations');
    expect(text).toContain('- Synthetic limitation.');
    expect(text).toContain('## Assumptions');
    expect(text).toContain('## Data coverage');
    expect(text).toContain('## Provenance');
    expect(text).toContain('References: bundle, chirps_spi.');

    expect(text).not.toMatch(/\bsevere\b|\bseverity\b|extreme drought|drought categor/i);
  });

  it('labels model-written reports as AI narrative', () => {
    const modelReport = reportFixtureFull(false);
    const text = reportToMarkdown(
      fullDetailFixture({
        report: { ...modelReport, fallback: false, generator: 'test-model' },
      }),
    );
    expect(text).toContain('AI-generated narrative');
    expect(text).not.toContain('Computed by the platform');
  });

  it('is honest when no report was stored', () => {
    const text = reportToMarkdown(
      scenarioDetailFixture({ status: 'failed', report: null, ranking: null, bundle: null }),
    );
    expect(text).toContain('No report was produced for this run.');
  });
});
