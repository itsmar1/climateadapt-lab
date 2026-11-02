import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import ReportView from './ReportView';
import {
  evidenceItemFixture,
  partialReportFixture,
  reportFixtureFull,
  statementFixture,
} from '../test/fixtures';

describe('ReportView', () => {
  it('shows all sections with the platform label for the fallback', () => {
    render(<ReportView report={reportFixtureFull(true)} />);
    expect(screen.getByText('Computed by the platform')).toBeInTheDocument();
    expect(screen.getByText('Deterministic fallback')).toBeInTheDocument();
    for (const heading of [
      'Summary',
      'Environmental findings',
      'Ranked recommendations',
      'Excluded options',
      'Evidence',
      'Limitations',
      'Assumptions',
      'Data coverage',
      'Provenance',
    ]) {
      expect(screen.getByRole('heading', { name: heading })).toBeInTheDocument();
    }
    expect(screen.getByText('Synthetic limitation.')).toBeInTheDocument();
  });

  it('labels model drafts as AI narrative', () => {
    render(<ReportView report={reportFixtureFull(false)} />);
    expect(screen.getByText('AI-generated narrative')).toBeInTheDocument();
    expect(screen.queryByText('Computed by the platform')).not.toBeInTheDocument();
  });

  it('marks each statement with its authorship on mixed reports', () => {
    render(<ReportView report={partialReportFixture()} />);
    expect(
      screen.getByText('Mixed: 6/7 statements model-written'),
    ).toBeInTheDocument();
    expect(screen.queryByText('AI-generated narrative')).not.toBeInTheDocument();
    expect(screen.queryByText('Computed by the platform')).not.toBeInTheDocument();
    expect(screen.getAllByText('AI-written')).toHaveLength(6);
    expect(screen.getAllByText('Platform-written')).toHaveLength(1);
  });

  it('links claims to evidence with chips, pages, and platform values', () => {
    render(<ReportView report={reportFixtureFull(true)} />);
    const chips = screen.getAllByRole('button', { name: 'E1' });
    expect(chips).toHaveLength(2);
    expect(chips[0]).toHaveAttribute(
      'title',
      'fao-iddp66-crop-yield-response-to-water:00001',
    );
    fireEvent.click(chips[0] as HTMLElement);
    expect(
      screen.getByText(
        'Steduto et al. (2012). Crop yield response to water. FAO. ' +
          'PDF p. 22 (printed p. 22).',
      ),
    ).toBeInTheDocument();
    const link = screen.getByRole('link', { name: 'https://example.invalid/fao-iddp66' });
    expect(link).toHaveAttribute('href', 'https://example.invalid/fao-iddp66');
    expect(screen.getByText(/licence verified_in_record/)).toBeInTheDocument();
    expect(screen.getByText('-0.517 SPI')).toBeInTheDocument();
    expect(screen.getByText('chirps_spi.spi')).toBeInTheDocument();
  });

  it('flags unverified metadata', () => {
    const report = reportFixtureFull(true);
    report.evidence = [evidenceItemFixture({ license_status: 'unverified' })];
    render(<ReportView report={report} />);
    expect(screen.getByText('Metadata unverified')).toBeInTheDocument();
  });

  it('keeps unresolved evidence ids visible instead of dropping them', () => {
    const report = reportFixtureFull(true);
    report.environmental_findings = [
      statementFixture('Claim with a bad id.', { evidence_ids: ['ghost:1'] }),
    ];
    render(<ReportView report={report} />);
    expect(screen.getByText('unresolved evidence')).toBeInTheDocument();
  });

  it('renders empty sections honestly with limitations always visible', () => {
    const report = reportFixtureFull(true);
    report.ranked_recommendations = [];
    report.excluded_options = [];
    report.evidence = [];
    report.assumptions = [];
    render(<ReportView report={report} />);
    expect(screen.getByText('No ranked recommendations.')).toBeInTheDocument();
    expect(screen.getByText('No excluded options.')).toBeInTheDocument();
    expect(screen.getByText('No cited evidence.')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Assumptions' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Limitations' })).toBeInTheDocument();
  });
});
