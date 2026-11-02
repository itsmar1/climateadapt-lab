import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { GeoMapProps } from './GeoMap';
import ScenarioForm from './ScenarioForm';
import { mockFetch, scenarioCreatedFixture } from '../test/fixtures';

vi.mock('./GeoMap', () => ({
  default: ({ center, markers, onPick, onMarkerMove, mapLabel }: GeoMapProps) => (
    <div data-testid="geomap-stub" data-center={center.join(',')} aria-label={mapLabel}>
      {markers.map((marker) => (
        <span key={marker.id} data-testid={`geomap-marker-${marker.id}`}>
          {marker.position.join(',')}
        </span>
      ))}
      {onPick && (
        <button
          type="button"
          data-testid="geomap-pick"
          onClick={() => onPick(63.4, 10.4)}
        >
          pick
        </button>
      )}
      {onMarkerMove && (
        <button
          type="button"
          data-testid="geomap-drag"
          onClick={() => onMarkerMove('picker', 1.5, 2.5)}
        >
          drag
        </button>
      )}
    </div>
  ),
}));

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ScenarioForm', () => {
  it('shows coverage hints and the fallback explanation', () => {
    render(<ScenarioForm onCreated={() => undefined} />);
    expect(screen.getByText(/CHIRPS covers 60°S–60°N/)).toBeInTheDocument();
    expect(screen.getByText(/falls back to the nearest land grid point/)).toBeInTheDocument();
  });

  it('syncs the map marker both ways with the coordinate inputs', () => {
    render(<ScenarioForm onCreated={() => undefined} />);
    expect(screen.getByTestId('geomap-stub')).toHaveAttribute(
      'data-center',
      '30.43,-9.61',
    );

    fireEvent.change(screen.getByLabelText('Latitude'), { target: { value: '51.5' } });
    fireEvent.change(screen.getByLabelText('Longitude'), { target: { value: '0.12' } });
    expect(screen.getByTestId('geomap-stub')).toHaveAttribute('data-center', '51.5,0.12');
    expect(screen.getByTestId('geomap-marker-picker')).toHaveTextContent('51.5,0.12');

    fireEvent.click(screen.getByTestId('geomap-pick'));
    expect(screen.getByLabelText('Latitude')).toHaveValue('63.40');
    expect(screen.getByLabelText('Longitude')).toHaveValue('10.40');

    fireEvent.click(screen.getByTestId('geomap-drag'));
    expect(screen.getByLabelText('Latitude')).toHaveValue('1.50');
    expect(screen.getByLabelText('Longitude')).toHaveValue('2.50');
  });

  it('offers one-click presets matching the captured snapshots', () => {
    render(<ScenarioForm onCreated={() => undefined} />);
    fireEvent.click(screen.getByRole('button', { name: 'Trøndelag, Norway' }));
    expect(screen.getByLabelText('Latitude')).toHaveValue('63.4');
    expect(screen.getByLabelText('Longitude')).toHaveValue('10.4');
    expect(screen.getByText(/outside the CHIRPS band/)).toBeInTheDocument();
    expect(screen.getByText('outside_coverage')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Morocco (reference)' }));
    expect(screen.getByLabelText('Latitude')).toHaveValue('30.43');
    expect(screen.queryByText(/outside the CHIRPS band/)).not.toBeInTheDocument();
  });

  it('blocks invalid coordinates without calling the backend', () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    render(<ScenarioForm onCreated={() => undefined} />);

    fireEvent.change(screen.getByLabelText('Latitude'), { target: { value: 'north' } });
    fireEvent.click(screen.getByRole('button', { name: 'Run analysis' }));

    expect(screen.getByText('Enter a latitude between -90 and 90.')).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('requires at least one indicator', () => {
    vi.stubGlobal('fetch', vi.fn());
    render(<ScenarioForm onCreated={() => undefined} />);

    for (const label of [
      'CHIRPS rainfall (SPI)',
      'ERA5-Land rainfall (SPI)',
      'ERA5-Land temperature',
      'ERA5-Land soil moisture',
    ]) {
      fireEvent.click(screen.getByLabelText(label));
    }
    fireEvent.click(screen.getByRole('button', { name: 'Run analysis' }));

    expect(screen.getByText('Select at least one indicator.')).toBeInTheDocument();
  });

  it('submits parsed values and reports the created id', async () => {
    const fetchMock = mockFetch([{ body: scenarioCreatedFixture(), status: 202 }]);
    vi.stubGlobal('fetch', fetchMock);
    const onCreated = vi.fn();
    render(<ScenarioForm onCreated={onCreated} />);

    fireEvent.click(screen.getByRole('button', { name: 'Run analysis' }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith('sc-new'));
    const [request] = fetchMock.mock.calls[0] as [Request];
    const body = (await request.json()) as Record<string, unknown>;
    expect(body.latitude).toBe(30.43);
    expect(body.timescale_months).toBe(3);
    expect(body.land_fallback_max_km).toBe(15);
    expect(body.has_water_source).toBe(true);
    expect(body.indicators).toHaveLength(4);
  });

  it('maps a 422 body onto fields', async () => {
    const fetchMock = mockFetch([
      {
        body: {
          detail: [{ loc: ['body', 'query'], msg: 'field required', type: 'missing' }],
        },
        status: 422,
      },
    ]);
    vi.stubGlobal('fetch', fetchMock);
    render(<ScenarioForm onCreated={() => undefined} />);

    fireEvent.click(screen.getByRole('button', { name: 'Run analysis' }));

    await waitFor(() => expect(screen.getByText('field required')).toBeInTheDocument());
    expect(screen.getByText(/server rejected some fields/)).toBeInTheDocument();
  });

  it('maps a typed server error to its message', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch([
        { body: { detail: [{ loc: [], msg: 'busy', type: 'server_busy' }] }, status: 503 },
      ]),
    );
    render(<ScenarioForm onCreated={() => undefined} />);

    fireEvent.click(screen.getByRole('button', { name: 'Run analysis' }));

    await waitFor(() => expect(screen.getByText(/server is at capacity/)).toBeInTheDocument());
  });
});
