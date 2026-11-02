import { describe, expect, it } from 'vitest';
import {
  CHIRPS_LAT_MAX,
  CHIRPS_LAT_MIN,
  LOCATION_PRESETS,
  TILE_ATTRIBUTION,
  TILE_URL,
  fallbackPoints,
  formatCoord,
  isInChirpsBand,
  parseLatLon,
} from './geo';
import { soilEntryOk, spiEntryOk, tempEntryOkWithFallback } from '../test/fixtures';

describe('geo', () => {
  it('pins the verified CHIRPS band to ±60°', () => {
    expect(CHIRPS_LAT_MIN).toBe(-60);
    expect(CHIRPS_LAT_MAX).toBe(60);
    expect(isInChirpsBand(60)).toBe(true);
    expect(isInChirpsBand(-60)).toBe(true);
    expect(isInChirpsBand(60.01)).toBe(false);
    expect(isInChirpsBand(-60.01)).toBe(false);
    expect(isInChirpsBand(Number.NaN)).toBe(false);
  });

  it('pins the tile source and attribution to the OSMF policy wording', () => {
    expect(TILE_URL).toBe('https://tile.openstreetmap.org/{z}/{x}/{y}.png');
    expect(TILE_ATTRIBUTION).toContain('OpenStreetMap');
    expect(TILE_ATTRIBUTION).toContain('https://www.openstreetmap.org/copyright');
  });

  it('pins the four presets to the captured snapshot coordinates', () => {
    expect(LOCATION_PRESETS).toEqual([
      { key: 'reference-morocco', label: 'Morocco (reference)', lat: 30.43, lon: -9.61 },
      { key: 'punjab-india', label: 'Punjab, India', lat: 30.9, lon: 75.8 },
      { key: 'trondelag-norway', label: 'Trøndelag, Norway', lat: 63.4, lon: 10.4 },
      { key: 'atlantic-ocean', label: 'Atlantic (masked point)', lat: 30.43, lon: -15.5 },
    ]);
  });

  it('parses and formats coordinates defensively', () => {
    expect(parseLatLon('30.43', '-9.61')).toEqual({ lat: 30.43, lon: -9.61 });
    expect(parseLatLon('north', '-9.61')).toBeNull();
    expect(parseLatLon('', '-9.61')).toBeNull();
    expect(parseLatLon('91', '0')).toBeNull();
    expect(parseLatLon('0', '181')).toBeNull();
    expect(formatCoord(30.428)).toBe('30.43');
    expect(formatCoord(-9.6)).toBe('-9.60');
  });

  it('extracts used fallback points with backend distances', () => {
    const withDistance = {
      ...tempEntryOkWithFallback(),
      result: {
        ...(tempEntryOkWithFallback().result as Record<string, unknown>),
        land_fallback: {
          ...((
            tempEntryOkWithFallback().result as Record<string, unknown>
          ).land_fallback as Record<string, unknown>),
          distance_km: 11.1,
        },
      },
    };
    expect(fallbackPoints([spiEntryOk(), withDistance, soilEntryOk()])).toEqual([
      {
        indicator: 'era5_temperature_anomaly',
        requested: { lat: 30.43, lon: -9.61 },
        used: { lat: 30.5, lon: -9.6 },
        distanceKm: 11.1,
      },
    ]);
  });

  it('skips entries without a usable fallback selection', () => {
    expect(fallbackPoints([spiEntryOk(), soilEntryOk()])).toEqual([]);
    const unused = {
      ...tempEntryOkWithFallback(),
      result: {
        ...(tempEntryOkWithFallback().result as Record<string, unknown>),
        land_fallback: {
          used: false,
          selected_grid_point_latitude: 30.5,
          selected_grid_point_longitude: -9.6,
        },
      },
    };
    expect(fallbackPoints([unused])).toEqual([]);
    const missingCoords = {
      ...tempEntryOkWithFallback(),
      result: {
        ...(tempEntryOkWithFallback().result as Record<string, unknown>),
        land_fallback: { used: true },
      },
    };
    expect(fallbackPoints([missingCoords])).toEqual([]);
  });

  it('emits no severity language', () => {
    const banned = /\bsevere\b|\bseverity\b|extreme drought|drought categor/i;
    expect(JSON.stringify(LOCATION_PRESETS)).not.toMatch(banned);
    expect(TILE_ATTRIBUTION).not.toMatch(banned);
  });
});
