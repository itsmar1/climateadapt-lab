import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { GeoMapProps } from './components/GeoMap';
import App from './App';

vi.mock('./components/GeoMap', () => ({
  default: ({ mapLabel }: GeoMapProps) => (
    <div data-testid="geomap-stub" aria-label={mapLabel} />
  ),
}));
import {
  demoListFixture,
  demoSummaryFixture,
  mockFetch,
  scenarioCreatedFixture,
  scenarioDetailFixture,
  scenarioListFixture,
  scenarioSummaryFixture,
} from './test/fixtures';

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = '';
});

describe('App', () => {
  // Spans two production poll cycles (2s each); needs more than the 5s default.
  it('runs form → progress → results end to end', async () => {
    window.location.hash = '#/new';
    const running = scenarioDetailFixture({ status: 'running' });
    const done = scenarioDetailFixture({ status: 'complete' });
    vi.stubGlobal(
      'fetch',
      mockFetch([
        { body: scenarioCreatedFixture(), status: 202 },
        { body: running },
        { body: done },
      ]),
    );

    render(<App />);

    fireEvent.click(
      screen.getByRole('button', { name: 'Evidence & indicators' }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Run analysis' }));

    await waitFor(() => expect(screen.getByText('Analysis running')).toBeInTheDocument());
    // The app polls on the production 2s interval; allow two poll cycles.
    await waitFor(() => expect(screen.getByText('Results')).toBeInTheDocument(), {
      timeout: 10000,
    });
    expect(window.location.hash).toBe('#/scenarios/sc-new');
    expect(screen.getByText('Rainfall · SPI (CHIRPS)')).toBeInTheDocument();
  }, 20000);

  it('opens a stored scenario directly from the hash', async () => {
    window.location.hash = '#/scenarios/sc-stored';
    const done = scenarioDetailFixture({ status: 'partial' });
    vi.stubGlobal('fetch', mockFetch([{ body: done }]));

    render(<App />);

    await waitFor(() => expect(screen.getByText('Results')).toBeInTheDocument());
    expect(screen.queryByText(/Deterministic fallback report/)).not.toBeInTheDocument();
  });

  it('shows load failures with a way back', async () => {
    window.location.hash = '#/scenarios/sc-missing';
    vi.stubGlobal(
      'fetch',
      mockFetch([
        {
          body: {
            detail: [{ loc: [], msg: 'Unknown scenario id.', type: 'scenario_not_found' }],
          },
          status: 404,
        },
      ]),
    );

    render(<App />);

    await waitFor(() => expect(screen.getByText('Polling failed')).toBeInTheDocument());
    expect(screen.getByText(/unknown or was deleted/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Back to form' }));
    expect(screen.getByRole('heading', { name: 'New analysis' })).toBeInTheDocument();
  });

  it('opens the history list from the hash', async () => {
    window.location.hash = '#/scenarios';
    vi.stubGlobal(
      'fetch',
      mockFetch([
        { body: scenarioListFixture([scenarioSummaryFixture()], 1) },
      ]),
    );

    render(<App />);

    await waitFor(() =>
      expect(screen.getByText('Scenario history')).toBeInTheDocument(),
    );
    expect(screen.getByText('sc-1')).toBeInTheDocument();
  });

  it('opens the demo list from the hash', async () => {
    window.location.hash = '#/demo';
    vi.stubGlobal(
      'fetch',
      mockFetch([{ body: demoListFixture([demoSummaryFixture()]) }]),
    );

    render(<App />);

    await waitFor(() =>
      expect(screen.getByText('Demo snapshots')).toBeInTheDocument(),
    );
    expect(screen.getByText('Reference: Souss-Massa, Morocco')).toBeInTheDocument();
  });

  it('lands on the overview by default', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch([
        { body: demoListFixture([]) },
        { body: scenarioListFixture([], 0) },
      ]),
    );

    render(<App />);

    expect(
      screen.getByRole('heading', {
        name: 'From satellite archives to a citable adaptation report',
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Start an analysis' })).toHaveAttribute(
      'href',
      '#/new',
    );
    await waitFor(() =>
      expect(screen.getByTestId('overview-counts')).toBeInTheDocument(),
    );
  });
});
