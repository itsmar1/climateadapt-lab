/**
 * Pure geography helpers for the map UI. No Leaflet import here, so this
 * module is unit-testable in jsdom without DOM mocks. No severity language.
 */

import type { BundleIndicatorResult } from './client';

/** Verified dataset fact (backend coverage + CHIRPS docs): 60°S–60°N. */
export const CHIRPS_LAT_MIN = -60;
export const CHIRPS_LAT_MAX = 60;

export const TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
export const TILE_ATTRIBUTION =
  '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

export interface MapPoint {
  lat: number;
  lon: number;
}

export interface LocationPreset extends MapPoint {
  key: string;
  label: string;
}

/** One-click presets matching the captured snapshots (docs/DEMO_RUNS.md). */
export const LOCATION_PRESETS: LocationPreset[] = [
  { key: 'reference-morocco', label: 'Morocco (reference)', lat: 30.43, lon: -9.61 },
  { key: 'punjab-india', label: 'Punjab, India', lat: 30.9, lon: 75.8 },
  { key: 'trondelag-norway', label: 'Trøndelag, Norway', lat: 63.4, lon: 10.4 },
  { key: 'atlantic-ocean', label: 'Atlantic (masked point)', lat: 30.43, lon: -15.5 },
];

export function isInChirpsBand(lat: number): boolean {
  return Number.isFinite(lat) && lat >= CHIRPS_LAT_MIN && lat <= CHIRPS_LAT_MAX;
}

/** Parse the form's lat/lon strings; null unless both are finite and in range. */
export function parseLatLon(latRaw: string, lonRaw: string): MapPoint | null {
  if (latRaw.trim() === '' || lonRaw.trim() === '') {
    return null;
  }
  const lat = Number(latRaw);
  const lon = Number(lonRaw);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
    return null;
  }
  if (lat < -90 || lat > 90 || lon < -180 || lon > 180) {
    return null;
  }
  return { lat, lon };
}

/** Tidy two-decimal display for map-picked coordinates (grid cells are coarser). */
export function formatCoord(value: number): string {
  return value.toFixed(2);
}

export interface FallbackPoint {
  indicator: string;
  requested: MapPoint;
  /** Grid point actually used (fallback selection, never the requested one). */
  used: MapPoint;
  /** Backend-reported great-circle distance, when the backend states it. */
  distanceKm: number | null;
}

function asRecord(value: unknown): Record<string, unknown> {
  if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/**
 * Collect one marker per entry whose ERA5 land fallback was used. Entries
 * without a used fallback (or without usable coordinates) contribute nothing.
 * Same requested/used pair across indicators is returned once per indicator.
 */
export function fallbackPoints(entries: BundleIndicatorResult[]): FallbackPoint[] {
  const points: FallbackPoint[] = [];
  for (const entry of entries) {
    const result = asRecord(entry.result as unknown);
    const fallback = asRecord(result.land_fallback);
    if (fallback.used !== true) {
      continue;
    }
    const usedLat = asNumber(fallback.selected_grid_point_latitude);
    const usedLon = asNumber(fallback.selected_grid_point_longitude);
    const reqLat = entry.requested_latitude;
    const reqLon = entry.requested_longitude;
    if (usedLat === null || usedLon === null) {
      continue;
    }
    if (typeof reqLat !== 'number' || typeof reqLon !== 'number') {
      continue;
    }
    points.push({
      indicator: entry.indicator,
      requested: { lat: reqLat, lon: reqLon },
      used: { lat: usedLat, lon: usedLon },
      distanceKm: asNumber(fallback.distance_km),
    });
  }
  return points;
}
