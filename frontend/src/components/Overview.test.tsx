import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Mock } from 'vitest';
import type { GeoMapProps } from './GeoMap';
import Overview from './Overview';
import {
  demoFileFixture,
  demoListFixture,
  demoSummaryFixture,
  scenarioDetailFixture,
  scenarioListFixture,
  scenarioSummaryFixture,
} from '../test/fixtures';

vi.mock('./GeoMap', () => ({
  default: ({ markers, mapLabel }: GeoMapProps) => (
    <div data-testid="geomap-stub" aria-label={mapLabel}>
      {markers.map((marker) => (
        <span key={marker.id} data-testid={`geomap-marker-${marker.id}`}>
          {marker.popupTitle}: {marker.position.join(',')}
        </span>
      ))}
    </div>
  ),
}));

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

/** Route stubbed fetches by URL: demo list, one demo file, history list. */
function routeFetch(): Mock {
  return vi.fn().mockImplementation((input: RequestInfo | URL) => {
    const url =
      typeof input === 'string'
        ? input
        : input instanceof URL
          ? input.href
          : (input as Request).url;
    if (url.endsWith('/v1/demo/snapshots')) {
      return Promise.resolve(
        jsonResponse(demoListFixture([demoSummaryFixture()])),
      );
    }
    if (url.includes('/v1/demo/snapshots/')) {
      return Promise.resolve(
        jsonResponse(demoFileFixture(scenarioDetailFixture())),
      );
    }
    if (url.includes('/v1/scenarios')) {
      return Promise.resolve(
        jsonResponse(
          scenarioListFixture([scenarioSummaryFixture({ scenario_id: 'sc-9' })], 1),
        ),
      );
    }
    return Promise.reject(new Error(`unexpected fetch ${url}`));
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('Overview', () => {
  it('shows the purpose, entry actions, and documented coverage', () => {
    vi.stubGlobal('fetch', routeFetch());
    render(<Overview />);

    expect(
      screen.getByRole('heading', {
        name: 'From satellite archives to a citable adaptation report',
      }),
    ).toBeInTheDocument();
    expect(screen.getByText(/validates statement by statement/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Start an analysis' })).toHaveAttribute(
      'href',
      '#/new',
    );
    expect(screen.getByRole('link', { name: 'Open the demo' })).toHaveAttribute(
      'href',
      '#/demo',
    );
    expect(screen.getByText(/Land 60°S–60°N/)).toBeInTheDocument();
    expect(screen.getByText(/Global · 1950–present/)).toBeInTheDocument();
    expect(
      screen.getByText(/UC Santa Barbara Climate Hazards Center/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Copernicus Climate Change Service/),
    ).toBeInTheDocument();
  });

  it('marks real demo snapshots and history analyses from the APIs', async () => {
    vi.stubGlobal('fetch', routeFetch());
    render(<Overview />);

    await waitFor(() =>
      expect(
        screen.getByTestId('geomap-marker-demo-reference-morocco'),
      ).toHaveTextContent('Captured real run: 30.43,-9.61'),
    );
    expect(screen.getByTestId('geomap-marker-history-sc-9')).toHaveTextContent(
      'Your analysis: 30.43,-9.61',
    );
    expect(screen.getByTestId('overview-counts')).toHaveTextContent(
      '1 demo snapshot · 1 recent analysis on this map.',
    );
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('links each pipeline stage to the captured demo', () => {
    vi.stubGlobal('fetch', routeFetch());
    render(<Overview />);

    for (const label of [
      'Archives',
      'Indicators',
      'Cited evidence',
      'Ranked options',
      'Validated report',
    ]) {
      expect(
        screen.getByRole('link', { name: new RegExp(label) }),
      ).toHaveAttribute('href', '#/demo');
    }
  });

  it('shows unavailable states without placeholder numbers', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((input: RequestInfo | URL) => {
        const url =
          typeof input === 'string'
            ? input
            : input instanceof URL
              ? input.href
              : (input as Request).url;
        if (url.includes('/v1/demo/')) {
          return Promise.resolve(
            jsonResponse(
              {
                detail: [{ loc: [], msg: 'off', type: 'demo_mode_disabled' }],
              },
              404,
            ),
          );
        }
        return Promise.reject(new TypeError('down'));
      }),
    );
    render(<Overview />);

    await waitFor(() =>
      expect(screen.getByText('Demo snapshots unavailable')).toBeInTheDocument(),
    );
    expect(screen.getByText(/Demo mode is disabled/)).toBeInTheDocument();
    expect(screen.getByText('Your analyses unavailable')).toBeInTheDocument();
    expect(screen.getByText(/could not be reached/)).toBeInTheDocument();
    // The map still renders (coverage band + legend), with honest zero counts.
    expect(screen.getByTestId('geomap-stub')).toBeInTheDocument();
    expect(screen.getByTestId('overview-counts')).toHaveTextContent(
      '0 demo snapshots · 0 recent analyses on this map.',
    );
  });
});
