import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { GeoMapProps } from './GeoMap';
import { toCardModel } from '../api/presenters';
import IndicatorCard from './IndicatorCard';
import ReferenceChart from './ReferenceChart';
import ResultsView, { groupProblems } from './ResultsView';
import {
  failedEntry,
  fullDetailFixture,
  partialReportFixture,
  scenarioDetailFixture,
  skippedEntry,
  soilEntryOk,
  spiEntryOk,
  tempEntryOkWithFallback,
} from '../test/fixtures';

vi.mock('./GeoMap', () => ({
  default: ({ center, markers, mapLabel }: GeoMapProps) => (
    <div data-testid="geomap-stub" data-center={center.join(',')} aria-label={mapLabel}>
      {markers.map((marker) => (
        <span key={marker.id} data-testid={`geomap-marker-${marker.id}`}>
          {marker.popupTitle}: {marker.position.join(',')}
        </span>
      ))}
    </div>
  ),
}));

function goToTab(label: string): void {
  fireEvent.click(screen.getByRole('tab', { name: label }));
}

describe('IndicatorCard', () => {
  it('renders values, reference, source, limitations, and provenance', () => {
    render(<IndicatorCard model={toCardModel(spiEntryOk())} />);
    expect(screen.getByText('Rainfall · SPI (CHIRPS)')).toBeInTheDocument();
    expect(screen.getByText('-0.517')).toBeInTheDocument();
    expect(screen.getByText('76.87 mm')).toBeInTheDocument();
    // The reference line appears in the card meta and again under the chart.
    expect(screen.getAllByText(/Reference 1991–2020/)).toHaveLength(2);
    expect(screen.getByText(/CHIRPS v3.0/)).toBeInTheDocument();
    expect(screen.getByText(/Precipitation only/)).toBeInTheDocument();
    expect(screen.getByText(/Funk et al/)).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /Target value/ })).toBeInTheDocument();
  });

  it('shows the backend method note on SPI cards and the anomaly note otherwise', () => {
    const { unmount } = render(<IndicatorCard model={toCardModel(spiEntryOk())} />);
    expect(screen.getByText(/Gamma distribution/)).toBeInTheDocument();
    unmount();

    render(<IndicatorCard model={toCardModel(tempEntryOkWithFallback())} />);
    expect(screen.getByText(/Day-weighted window mean/)).toBeInTheDocument();
  });

  it('surfaces fallback and cell-edge warnings', () => {
    render(<IndicatorCard model={toCardModel(tempEntryOkWithFallback())} />);
    expect(screen.getByText(/Land fallback was used/)).toBeInTheDocument();

    render(<IndicatorCard model={toCardModel(spiEntryOk())} />);
    expect(screen.getAllByText(/grid-cell edge/)[0]).toBeInTheDocument();
  });

  it('renders failed and skipped states without values', () => {
    const { unmount } = render(<IndicatorCard model={toCardModel(failedEntry())} />);
    expect(screen.getByText(/No observations exist/)).toBeInTheDocument();
    expect(screen.getByText(/data_not_available/)).toBeInTheDocument();
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    unmount();

    render(<IndicatorCard model={toCardModel(skippedEntry())} />);
    expect(screen.getByText('Not requested in this scenario.')).toBeInTheDocument();
  });

  it('renders soil units and layer', () => {
    render(<IndicatorCard model={toCardModel(soilEntryOk())} />);
    expect(screen.getByText('-0.0505 m³/m³')).toBeInTheDocument();
    expect(screen.getByText('0–7 cm')).toBeInTheDocument();
  });
});

describe('ReferenceChart', () => {
  it('labels target, mean, spread, and the per-year caveat', () => {
    const model = toCardModel(tempEntryOkWithFallback()).chart;
    if (!model) {
      throw new Error('expected chart data');
    }
    render(<ReferenceChart model={model} referenceLabel="Reference 1991–2020" />);
    expect(screen.getByRole('img', { name: /Window mean 18.5/ })).toBeInTheDocument();
    expect(screen.getByText(/mean ± 1 std dev/)).toBeInTheDocument();
    expect(screen.getByText(/per-year values are not returned/)).toBeInTheDocument();
  });

  it('handles a missing spread without a band claim', () => {
    render(
      <ReferenceChart
        model={{
          target: 1,
          targetLabel: 'Target',
          mean: 0,
          sd: null,
          unit: 'x',
          nYears: 30,
          percentilePct: null,
        }}
        referenceLabel={null}
      />,
    );
    expect(screen.getByText(/No reference spread reported/)).toBeInTheDocument();
  });
});

describe('ResultsView', () => {
  it('shows one card per indicator for a complete run', () => {
    const detail = scenarioDetailFixture({
      bundle: {
        indicator: 'environmental_bundle',
        latitude: 30.43,
        longitude: -9.61,
        target_end_month: '2024-03',
        timescale_months: 3,
        reference_start_year: 1991,
        reference_end_year: 2020,
        entries: [spiEntryOk(), failedEntry()],
      },
    });
    render(<ResultsView detail={detail} onNew={() => undefined} />);
    expect(screen.getByText('Rainfall · SPI (CHIRPS)')).toBeInTheDocument();
    expect(screen.getByText('Rainfall · SPI (ERA5-Land)')).toBeInTheDocument();
    expect(screen.queryByText(/Deterministic fallback/)).not.toBeInTheDocument();
  });

  it('banners the deterministic fallback and lists problems', () => {
    const detail = scenarioDetailFixture({
      status: 'partial',
      report: { ...scenarioDetailFixture().report!, fallback: true },
      problems: ['[drought-label] banned vocabulary'],
      warnings: ['[retrieval-empty] No passages retrieved.'],
    });
    render(<ResultsView detail={detail} onNew={() => undefined} />);
    expect(screen.getByText(/Deterministic fallback report/)).toBeInTheDocument();
    goToTab('Provenance & methods');
    expect(screen.getByText('drought-label')).toBeInTheDocument();
    expect(screen.getByText('retrieval-empty')).toBeInTheDocument();
  });

  it('shows failed runs with explanations and no fabricated values', () => {
    const detail = scenarioDetailFixture({
      status: 'failed',
      bundle: null,
      ranking: null,
      report: null,
      trace: null,
      problems: ['[outside_coverage] Point outside CHIRPS coverage.'],
    });
    render(<ResultsView detail={detail} onNew={() => undefined} />);
    expect(screen.getByText(/This run failed/)).toBeInTheDocument();
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });

  it('shows ranking, report, and export for a full run', () => {
    render(<ResultsView detail={fullDetailFixture()} onNew={() => undefined} />);
    goToTab('Evidence & options');
    expect(screen.getByRole('heading', { name: 'Recommendations' })).toBeInTheDocument();
    expect(screen.getAllByText('Computed by the platform')).toHaveLength(1);
    goToTab('Report');
    expect(screen.getByRole('heading', { name: 'Report' })).toBeInTheDocument();
    expect(screen.getByText('Deficit irrigation')).toBeInTheDocument();
    expect(screen.getAllByText('Computed by the platform')).toHaveLength(1);
    expect(
      screen.getByRole('button', { name: 'Export report (Markdown)' }),
    ).toBeInTheDocument();
  });

  it('badges AI-accepted versus platform-fallback reports in the strip', () => {
    const accepted = scenarioDetailFixture({ status: 'complete' });
    const { unmount } = render(<ResultsView detail={accepted} onNew={() => undefined} />);
    expect(screen.getByText('AI report accepted')).toBeInTheDocument();
    const meta = screen.getByTestId('result-strip-meta');
    expect(meta).toHaveTextContent('30.43°, -9.61°');
    expect(meta).toHaveTextContent('2024-03');
    expect(meta).toHaveTextContent('3-month window');
    expect(meta).toHaveTextContent('1991–2020');
    unmount();

    const fallback = scenarioDetailFixture({
      status: 'partial',
      report: { ...scenarioDetailFixture().report!, fallback: true },
    });
    render(<ResultsView detail={fallback} onNew={() => undefined} />);
    expect(screen.getByText('Platform fallback report')).toBeInTheDocument();
    expect(screen.queryByText('AI report accepted')).not.toBeInTheDocument();
  });

  it('badges ai-partial reports with counts and lists replaced statements', () => {
    const detail = scenarioDetailFixture({
      status: 'complete',
      report: partialReportFixture(),
    });
    render(<ResultsView detail={detail} onNew={() => undefined} />);
    expect(
      screen.getByText('AI report: 6/7 statements model-written (validated)'),
    ).toBeInTheDocument();
    expect(screen.queryByText('AI report accepted')).not.toBeInTheDocument();
    expect(screen.queryByText('Platform fallback report')).not.toBeInTheDocument();
    expect(screen.getByText('Why 1 statement is platform-written')).toBeInTheDocument();
    expect(screen.getByText('limitations[0]')).toBeInTheDocument();
    expect(screen.getByText(/replaced \(/)).toBeInTheDocument();
    expect(screen.getByText(/undeclared-number/)).toBeInTheDocument();
  });

  it('groups problems by code with counts under a collapsed summary', () => {
    expect(
      groupProblems(['[b-code] second', '[a-code] first', '[b-code] third', 'plain note']),
    ).toEqual([
      { code: 'a-code', items: ['first'] },
      { code: 'b-code', items: ['second', 'third'] },
      { code: 'note', items: ['plain note'] },
    ]);
    const detail = scenarioDetailFixture({
      status: 'partial',
      report: { ...scenarioDetailFixture().report!, fallback: true },
      problems: ['[b-code] second', '[a-code] first', '[b-code] third'],
    });
    render(<ResultsView detail={detail} onNew={() => undefined} />);
    goToTab('Provenance & methods');
    expect(
      screen.getByText(/Why this is the platform fallback · 3 problems in 2 groups/),
    ).toBeInTheDocument();
    expect(screen.getByText('a-code')).toBeInTheDocument();
    expect(screen.getByText('b-code')).toBeInTheDocument();
  });

  it('maps the requested point and the grid point actually used', () => {
    const entry = {
      ...tempEntryOkWithFallback(),
      result: {
        ...(tempEntryOkWithFallback().result as Record<string, unknown>),
        land_fallback: {
          ...((tempEntryOkWithFallback().result as Record<string, unknown>)
            .land_fallback as Record<string, unknown>),
          distance_km: 11.1,
        },
      },
    };
    const detail = scenarioDetailFixture({
      bundle: {
        indicator: 'environmental_bundle',
        latitude: 30.43,
        longitude: -9.61,
        target_end_month: '2024-03',
        timescale_months: 3,
        reference_start_year: 1991,
        reference_end_year: 2020,
        entries: [entry],
      },
    });
    render(<ResultsView detail={detail} onNew={() => undefined} />);
    expect(screen.getByTestId('geomap-marker-requested')).toHaveTextContent(
      'Requested point: 30.43,-9.61',
    );
    expect(
      screen.getByTestId('geomap-marker-used-era5_temperature_anomaly'),
    ).toHaveTextContent('Grid point used (era5_temperature_anomaly): 30.5,-9.6');
    expect(screen.getByText(/11\.1 km from requested/)).toBeInTheDocument();
  });

  it('is honest when ranking and report are missing', () => {
    const detail = scenarioDetailFixture({
      status: 'partial',
      bundle: null,
      ranking: null,
      report: null,
      trace: null,
    });
    render(<ResultsView detail={detail} onNew={() => undefined} />);
    goToTab('Evidence & options');
    expect(screen.getByText('No ranking stored for this run.')).toBeInTheDocument();
    goToTab('Report');
    expect(screen.getByText('No report stored for this run.')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Export report (Markdown)' }),
    ).not.toBeInTheDocument();
  });

  it('shows one workspace panel at a time', () => {
    render(<ResultsView detail={fullDetailFixture()} onNew={() => undefined} />);
    expect(screen.getByText('Rainfall · SPI (CHIRPS)')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Report' })).not.toBeInTheDocument();

    goToTab('Report');
    expect(screen.getByRole('heading', { name: 'Report' })).toBeInTheDocument();
    expect(screen.queryByText('Rainfall · SPI (CHIRPS)')).not.toBeInTheDocument();
    // Report limitations stay visible without clicking anything.
    expect(screen.getByRole('heading', { name: 'Limitations' })).toBeInTheDocument();

    goToTab('Indicators');
    expect(screen.getByText('Rainfall · SPI (CHIRPS)')).toBeInTheDocument();
  });

  it('shows the run trace in Provenance & methods', () => {
    const detail = scenarioDetailFixture({
      trace: {
        agent_version: 1,
        component_versions: { model: 'baseten:meta-models/muse-spark-open-1026' },
        draft_text: '',
        duration_ms_total: 101781,
        ended_at: '2026-11-02T20:22:27+00:00',
        outcome: 'complete',
        repair_text: '',
        run_id: 'abc123',
        started_at: '2026-11-02T20:20:45+00:00',
        stages: [
          {
            detail: '4/4 ok',
            duration_ms: 16547,
            error_code: null,
            name: 'bundle',
            started_at: '2026-11-02T20:20:45+00:00',
            status: 'ok',
          },
          {
            detail: 'finish=length',
            duration_ms: 58594,
            error_code: null,
            name: 'draft',
            started_at: '2026-11-02T20:21:05+00:00',
            status: 'ok',
          },
        ],
        usage: { llm_calls: 2, prompt_tokens: 61385, completion_tokens: 23296 },
        validator_verdicts: ['[invalid-json] truncated', '[repair-accepted]'],
      },
    });
    render(<ResultsView detail={detail} onNew={() => undefined} />);
    goToTab('Provenance & methods');
    expect(
      screen.getByText('baseten:meta-models/muse-spark-open-1026'),
    ).toBeInTheDocument();
    expect(screen.getByText(/101781 ms/)).toBeInTheDocument();
    expect(screen.getByText('bundle')).toBeInTheDocument();
    expect(screen.getByText(/61385 prompt/)).toBeInTheDocument();
    expect(screen.getByText('[repair-accepted]')).toBeInTheDocument();
  });

  it('says so when no run trace is stored', () => {
    const detail = scenarioDetailFixture({ trace: null });
    render(<ResultsView detail={detail} onNew={() => undefined} />);
    goToTab('Provenance & methods');
    expect(screen.getByText('No run trace stored for this run.')).toBeInTheDocument();
  });
});
