import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { toCardModel } from '../api/presenters';
import IndicatorCard from './IndicatorCard';
import ReferenceChart from './ReferenceChart';
import ResultsView from './ResultsView';
import {
  failedEntry,
  scenarioDetailFixture,
  skippedEntry,
  soilEntryOk,
  spiEntryOk,
  tempEntryOkWithFallback,
} from '../test/fixtures';

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
});
