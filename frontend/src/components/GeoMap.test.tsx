import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import GeoMap from './GeoMap';

interface Captured {
  click?: (event: { latlng: { lat: number; lng: number } }) => void;
  dragend?: (event: {
    target: { getLatLng: () => { lat: number; lng: number } };
  }) => void;
}

const captured: Captured = {};

vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }: { children?: ReactNode }) => (
    <div data-testid="map">{children}</div>
  ),
  TileLayer: ({ url, attribution }: { url: string; attribution: string }) => (
    <div data-testid="tiles" data-url={url} data-attribution={attribution} />
  ),
  Rectangle: ({ bounds }: { bounds: [[number, number], [number, number]] }) => (
    <div data-testid="band" data-bounds={JSON.stringify(bounds)} />
  ),
  Marker: ({
    children,
    position,
    draggable,
    icon,
    eventHandlers,
  }: {
    children?: ReactNode;
    position: [number, number];
    draggable?: boolean;
    icon: { options: { className?: string } };
    eventHandlers?: Captured;
  }) => {
    captured.dragend = eventHandlers?.dragend;
    return (
      <div
        data-testid="marker"
        data-position={position.join(',')}
        data-draggable={draggable === true ? 'yes' : 'no'}
        data-icon={icon.options.className ?? ''}
      >
        <button
          type="button"
          data-testid="drag-marker"
          onClick={() =>
            eventHandlers?.dragend?.({
              target: { getLatLng: () => ({ lat: 1.5, lng: 2.5 }) },
            })
          }
        >
          drag
        </button>
        {children}
      </div>
    );
  },
  Popup: ({ children }: { children?: ReactNode }) => (
    <div data-testid="popup">{children}</div>
  ),
  useMap: () => ({ setView: vi.fn(), getZoom: () => 3, fitBounds: vi.fn() }),
  useMapEvents: (handlers: Captured) => {
    captured.click = handlers.click;
    return null;
  },
}));

const MARKER = {
  id: 'point',
  position: [30.43, -9.61] as [number, number],
  popupTitle: 'Requested point',
  popupLines: ['30.43°, -9.61°'],
  tone: 'request' as const,
  draggable: true,
};

describe('GeoMap', () => {
  it('uses the policy tile URL and attribution, and shades the CHIRPS band', () => {
    render(
      <GeoMap
        mapLabel="Test map"
        center={[30.43, -9.61]}
        zoom={3}
        markers={[MARKER]}
        showChirpsBand
      />,
    );
    expect(screen.getByTestId('tiles')).toHaveAttribute(
      'data-url',
      'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    );
    const attribution = screen.getByTestId('tiles').getAttribute('data-attribution') ?? '';
    expect(attribution).toContain('OpenStreetMap');
    expect(attribution).toContain('https://www.openstreetmap.org/copyright');
    const bands = screen.getAllByTestId('band').map((node) =>
      JSON.parse(node.getAttribute('data-bounds') ?? '[]'),
    );
    expect(bands).toEqual([
      [
        [60, -180],
        [90, 180],
      ],
      [
        [-90, -180],
        [-60, 180],
      ],
    ]);
  });

  it('omits the band rectangles when not asked', () => {
    render(
      <GeoMap mapLabel="Test map" center={[0, 0]} zoom={3} markers={[]} />,
    );
    expect(screen.queryByTestId('band')).not.toBeInTheDocument();
  });

  it('wires click picks and marker drags to callbacks', () => {
    const onPick = vi.fn();
    const onMarkerMove = vi.fn();
    render(
      <GeoMap
        mapLabel="Test map"
        center={[30.43, -9.61]}
        zoom={3}
        markers={[MARKER]}
        onPick={onPick}
        onMarkerMove={onMarkerMove}
      />,
    );
    expect(screen.getByTestId('marker')).toHaveAttribute('data-position', '30.43,-9.61');
    expect(screen.getByTestId('marker').getAttribute('data-icon')).toContain('request');
    captured.click?.({ latlng: { lat: 63.4, lng: 10.4 } });
    expect(onPick).toHaveBeenCalledWith(63.4, 10.4);
    fireEvent.click(screen.getByTestId('drag-marker'));
    expect(onMarkerMove).toHaveBeenCalledWith('point', 1.5, 2.5);
  });

  it('labels the map region and lists markers for screen readers', () => {
    render(
      <GeoMap
        mapLabel="Pick the analysis location"
        center={[30.43, -9.61]}
        zoom={3}
        markers={[MARKER]}
      />,
    );
    expect(
      screen.getByRole('region', { name: 'Pick the analysis location' }),
    ).toBeInTheDocument();
  });
});
