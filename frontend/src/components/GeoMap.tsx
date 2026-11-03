import { useEffect, useMemo } from 'react';
import L from 'leaflet';
import {
  MapContainer,
  Marker,
  Popup,
  Rectangle,
  TileLayer,
  useMap,
  useMapEvents,
} from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import { CHIRPS_LAT_MAX, CHIRPS_LAT_MIN, TILE_ATTRIBUTION, TILE_URL } from '../api/geo';

export interface GeoMarker {
  id: string;
  position: [number, number];
  popupTitle: string;
  popupLines: string[];
  /** Requested point (turquoise) vs grid point actually used (ochre).
   * Overview reuse: 'demo' (captured real run) vs 'history' (your analysis). */
  tone: 'request' | 'used' | 'demo' | 'history';
  draggable?: boolean;
}

export interface GeoMapProps {
  mapLabel: string;
  center: [number, number];
  zoom: number;
  markers: GeoMarker[];
  showChirpsBand?: boolean;
  /** Fit all markers instead of tracking the center prop. */
  fitMarkers?: boolean;
  className?: string;
  onPick?: (lat: number, lon: number) => void;
  onMarkerMove?: (id: string, lat: number, lon: number) => void;
}

const reducedMotion =
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

function dotIcon(tone: GeoMarker['tone']): L.DivIcon {
  return L.divIcon({
    className: `geo-dot geo-dot-${tone}`,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
    popupAnchor: [0, -10],
  });
}

const ICONS: Record<GeoMarker['tone'], L.DivIcon> = {
  request: dotIcon('request'),
  used: dotIcon('used'),
  demo: dotIcon('demo'),
  history: dotIcon('history'),
};

const BAND_STYLE: L.PathOptions = {
  stroke: false,
  fillColor: '#b98a2f',
  fillOpacity: 0.22,
  interactive: false,
};

function ClickPicker({ onPick }: { onPick?: (lat: number, lon: number) => void }) {
  useMapEvents({
    click(event) {
      onPick?.(event.latlng.lat, event.latlng.lng);
    },
  });
  return null;
}

/** Keep the view on the prop-driven position without fighting user pans. */
function ViewSync({
  center,
  markers,
  fitMarkers,
}: {
  center: [number, number];
  markers: GeoMarker[];
  fitMarkers: boolean;
}) {
  const map = useMap();
  const key = useMemo(
    () =>
      fitMarkers
        ? markers.map((marker) => marker.position.join(',')).join('|')
        : center.join(','),
    [fitMarkers, markers, center],
  );
  useEffect(() => {
    if (fitMarkers && markers.length > 0) {
      map.fitBounds(
        L.latLngBounds(markers.map((marker) => marker.position)),
        { padding: [32, 32], maxZoom: 8 },
      );
      return;
    }
    if (!fitMarkers) {
      map.setView(center, map.getZoom());
    }
    // `key` is the serialized view target: depending on it (not on the raw
    // arrays) keeps unrelated parent re-renders from resetting a user pan.
  }, [map, key]);
  return null;
}

export default function GeoMap({
  mapLabel,
  center,
  zoom,
  markers,
  showChirpsBand = false,
  fitMarkers = false,
  className = 'geo-map',
  onPick,
  onMarkerMove,
}: GeoMapProps) {
  return (
    <div className="geo-wrap" role="region" aria-label={mapLabel}>
      <MapContainer
        center={center}
        zoom={zoom}
        minZoom={2}
        maxZoom={18}
        scrollWheelZoom={false}
        zoomAnimation={!reducedMotion}
        fadeAnimation={!reducedMotion}
        className={className}
      >
        <TileLayer url={TILE_URL} attribution={TILE_ATTRIBUTION} />
        {showChirpsBand && (
          <>
            <Rectangle
              bounds={[
                [CHIRPS_LAT_MAX, -180],
                [90, 180],
              ]}
              pathOptions={BAND_STYLE}
            />
            <Rectangle
              bounds={[
                [-90, -180],
                [CHIRPS_LAT_MIN, 180],
              ]}
              pathOptions={BAND_STYLE}
            />
          </>
        )}
        {markers.map((marker) => (
          <Marker
            key={marker.id}
            position={marker.position}
            icon={ICONS[marker.tone]}
            draggable={marker.draggable === true}
            eventHandlers={
              marker.draggable === true
                ? {
                    dragend: (event: L.LeafletEvent) => {
                      const point = (event.target as L.Marker).getLatLng();
                      onMarkerMove?.(marker.id, point.lat, point.lng);
                    },
                  }
                : undefined
            }
          >
            <Popup>
              <strong>{marker.popupTitle}</strong>
              {marker.popupLines.map((line) => (
                <span key={line}>
                  <br />
                  {line}
                </span>
              ))}
            </Popup>
          </Marker>
        ))}
        <ClickPicker onPick={onPick} />
        <ViewSync center={center} markers={markers} fitMarkers={fitMarkers} />
      </MapContainer>
      <ul className="visually-hidden">
        {markers.map((marker) => (
          <li key={marker.id}>
            {marker.popupTitle}: {marker.position[0].toFixed(3)}°,{' '}
            {marker.position[1].toFixed(3)}°. {marker.popupLines.join(' ')}
          </li>
        ))}
      </ul>
    </div>
  );
}
