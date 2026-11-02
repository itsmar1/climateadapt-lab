import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { GeoMapProps } from './GeoMap';
import DemoView from './DemoView';

vi.mock('./GeoMap', () => ({
  default: ({ mapLabel }: GeoMapProps) => (
    <div data-testid="geomap-stub" aria-label={mapLabel} />
  ),
}));
import {
  demoFileFixture,
  demoListFixture,
  demoSummaryFixture,
  fullDetailFixture,
  mockFetch,
} from '../test/fixtures';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('DemoView', () => {
  it('lists snapshots and opens one with the snapshot banner', async () => {
    const list = demoListFixture([demoSummaryFixture()]);
    const file = demoFileFixture(fullDetailFixture());
    vi.stubGlobal('fetch', mockFetch([{ body: list }, { body: file }]));
    const onOpen = vi.fn();
    const { rerender } = render(<DemoView snapshotKey={null} onOpen={onOpen} />);

    await waitFor(() =>
      expect(screen.getByText('Reference: Souss-Massa, Morocco')).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Open' }));
    expect(onOpen).toHaveBeenCalledWith('reference-morocco');

    rerender(<DemoView snapshotKey="reference-morocco" onOpen={onOpen} />);
    await waitFor(() =>
      expect(screen.getByText('Cached real-data snapshot')).toBeInTheDocument(),
    );
    expect(screen.getByText(/Stored results, not a live run/)).toBeInTheDocument();
    expect(screen.getByText('Rainfall · SPI (CHIRPS)')).toBeInTheDocument();
  });

  it('maps the disabled error to its message', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch([
        {
          body: { detail: [{ loc: [], msg: 'off', type: 'demo_mode_disabled' }] },
          status: 404,
        },
      ]),
    );
    render(<DemoView snapshotKey={null} onOpen={() => undefined} />);

    await waitFor(() =>
      expect(screen.getByText(/Demo mode is disabled/)).toBeInTheDocument(),
    );
  });

  it('shows unknown snapshots with a way back', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch([
        {
          body: { detail: [{ loc: [], msg: 'gone', type: 'demo_snapshot_not_found' }] },
          status: 404,
        },
      ]),
    );
    const onOpen = vi.fn();
    render(<DemoView snapshotKey="ghost" onOpen={onOpen} />);

    await waitFor(() =>
      expect(screen.getByText('Could not load this snapshot')).toBeInTheDocument(),
    );
    expect(screen.getByText(/unknown or was deleted/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Back to snapshots' }));
    expect(onOpen).toHaveBeenCalledWith(null);
  });

  it('shows the empty state', async () => {
    vi.stubGlobal('fetch', mockFetch([{ body: demoListFixture([]) }]));
    render(<DemoView snapshotKey={null} onOpen={() => undefined} />);

    await waitFor(() =>
      expect(screen.getByText('No snapshots stored on this server.')).toBeInTheDocument(),
    );
  });
});
