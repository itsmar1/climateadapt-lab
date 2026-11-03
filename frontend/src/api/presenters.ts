/**
 * Presenters: pure mapping from bundle entries to indicator-card view models.
 * All narrowing is defensive (`unknown` in, strings out) so a future backend
 * field never crashes the UI. No severity language anywhere in this module.
 */

import type { BundleIndicatorResult } from './client';
import { messageForCode } from './errors';

export interface HeadlineRow {
  label: string;
  value: string;
}

export interface ChartModel {
  target: number;
  targetLabel: string;
  mean: number;
  sd: number | null;
  unit: string;
  nYears: number;
  percentilePct: number | null;
}

export interface IndicatorCardModel {
  key: string;
  title: string;
  status: 'ok' | 'undefined' | 'failed' | 'skipped';
  headlines: HeadlineRow[];
  reference: string | null;
  dataSource: string;
  coverage: string;
  requestedPoint: string;
  usedPoint: string | null;
  limitations: string[];
  citation: string | null;
  doi: string | null;
  license: string | null;
  warnings: string[];
  errorType: string | null;
  errorMessage: string | null;
  chart: ChartModel | null;
  method: string | null;
}

type ResultRecord = Record<string, unknown>;

function asRecord(value: unknown): ResultRecord {
  if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
    return value as ResultRecord;
  }
  return {};
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null;
}

function asBool(value: unknown): boolean {
  return value === true;
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === 'string');
}

function asYearList(value: unknown): number[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const years: number[] = [];
  for (const item of value) {
    if (typeof item === 'number') {
      years.push(item);
    } else if (typeof item === 'object' && item !== null && !Array.isArray(item)) {
      const year = (item as Record<string, unknown>).year;
      if (typeof year === 'number') {
        years.push(year);
      }
    }
  }
  return years;
}

const TITLES: Record<string, string> = {
  chirps_spi: 'Rainfall · SPI (CHIRPS)',
  era5_spi: 'Rainfall · SPI (ERA5-Land)',
  era5_temperature_anomaly: 'Temperature anomaly (ERA5-Land)',
  era5_soil_moisture_anomaly: 'Soil moisture anomaly (ERA5-Land)',
};

// Verified method note for window anomalies (backend indicators/window_anomaly.py:
// day-weighted window mean minus the mean of same-calendar-month reference
// windows; a difference in the variable's units, never a percentage).
const ANOMALY_METHOD =
  'Day-weighted window mean minus the mean of same-calendar-month reference '
  + 'windows (a difference in native units, not a percentage); incomplete '
  + 'reference years are excluded, never filled in.';

function methodFor(indicator: string, result: ResultRecord): string | null {
  if (indicator === 'chirps_spi' || indicator === 'era5_spi') {
    return asString(result.method);
  }
  if (
    indicator === 'era5_temperature_anomaly' ||
    indicator === 'era5_soil_moisture_anomaly'
  ) {
    return ANOMALY_METHOD;
  }
  return null;
}

// Verified dataset facts (backend coverage + dataset docs).
export const CHIRPS_COVERAGE = 'Land 60°S–60°N · 1981–present · 0.05° grid';
export const ERA5_COVERAGE = 'Global · 1950–present · 0.1° grid';
export const CHIRPS_SOURCE = 'UC Santa Barbara Climate Hazards Center';
export const ERA5_SOURCE = 'Copernicus Climate Change Service (CDS)';

function coverageFor(indicator: string): string {
  if (indicator === 'chirps_spi') {
    return CHIRPS_COVERAGE;
  }
  if (indicator.startsWith('era5_')) {
    return ERA5_COVERAGE;
  }
  return 'See the data source record';
}

function fmt(value: number | null, digits: number): string | null {
  if (value === null) {
    return null;
  }
  return value.toFixed(digits);
}

function fmtSigned(value: number | null, digits: number): string | null {
  if (value === null) {
    return null;
  }
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(digits)}`;
}

function push(row: HeadlineRow[] | null, label: string, value: string | null): void {
  if (row && value !== null) {
    row.push({ label, value });
  }
}

function referenceLine(result: ResultRecord): string | null {
  const start = asNumber(result.reference_start_year);
  const end = asNumber(result.reference_end_year);
  if (start === null || end === null) {
    return null;
  }
  const windowEnd = asString(result.target_window_end);
  const timescale = asNumber(result.timescale_months);
  let line = `Reference ${start}–${end}`;
  if (timescale !== null && windowEnd !== null) {
    line += ` · ${timescale}-month window ending ${windowEnd}`;
  }
  return line;
}

function warningsFor(
  result: ResultRecord,
  entry: BundleIndicatorResult,
): { warnings: string[]; usedPoint: string | null } {
  const warnings: string[] = [];
  let usedPoint: string | null = null;

  const fallback = asRecord(result.land_fallback);
  const fallbackUsed = asBool(fallback.used);
  if (fallbackUsed) {
    const nearLat = asNumber(fallback.nearest_grid_point_latitude);
    const nearLon = asNumber(fallback.nearest_grid_point_longitude);
    const selLat = asNumber(fallback.selected_grid_point_latitude);
    const selLon = asNumber(fallback.selected_grid_point_longitude);
    const maxKm = asNumber(fallback.max_distance_km);
    usedPoint =
      selLat !== null && selLon !== null
        ? `${selLat.toFixed(2)}°, ${selLon.toFixed(2)}°`
        : null;
    warnings.push(
      `Land fallback was used: the nearest grid point` +
        (nearLat !== null && nearLon !== null
          ? ` (${nearLat.toFixed(2)}°, ${nearLon.toFixed(2)}°)`
          : '') +
        ` was masked, so the analysis used` +
        (usedPoint ? ` ${usedPoint}` : ' a nearby land point') +
        (maxKm !== null ? ` (allowed up to ${maxKm} km away)` : '') +
        '. Values describe the fallback point, not the requested one.',
    );
  }

  const cellLat = asNumber(result.grid_cell_center_latitude);
  const cellLon = asNumber(result.grid_cell_center_longitude);
  if (cellLat !== null && cellLon !== null && usedPoint === null) {
    usedPoint = `${cellLat.toFixed(2)}°, ${cellLon.toFixed(2)}°`;
  }
  if (!fallbackUsed) {
    const gridLat = entry.grid_point_latitude;
    const gridLon = entry.grid_point_longitude;
    if (typeof gridLat === 'number' && typeof gridLon === 'number') {
      usedPoint = `${gridLat.toFixed(2)}°, ${gridLon.toFixed(2)}°`;
    }
  }

  if (asBool(result.point_on_cell_boundary)) {
    warnings.push(
      'The requested point falls on a grid-cell edge; the value comes from the containing cell.',
    );
  }
  if (asBool(result.target_in_reference_period)) {
    warnings.push('The target window overlaps the reference period.');
  }
  const excluded = asYearList(result.reference_years_excluded);
  if (excluded.length > 0) {
    warnings.push(
      `${excluded.length} reference year${excluded.length === 1 ? '' : 's'} ` +
        `excluded for incomplete data (${excluded.join(', ')}); the rest were kept, nothing imputed.`,
    );
  }
  return { warnings, usedPoint };
}

function spiModel(
  base: IndicatorCardModel,
  result: ResultRecord,
): IndicatorCardModel {
  const headlines: HeadlineRow[] = [];
  push(headlines, 'SPI', fmt(asNumber(result.spi), 3));
  const total = fmt(asNumber(result.window_total_mm), 2);
  push(headlines, 'Window total', total === null ? null : `${total} mm`);
  push(headlines, 'Cumulative probability', fmt(asNumber(result.cumulative_probability), 3));
  const used = asNumber(result.reference_years_used);
  push(headlines, 'Reference years used', used === null ? null : String(Math.round(used)));
  base.headlines = headlines;

  const target = asNumber(result.spi);
  const mean = asNumber(result.reference_spi_mean);
  if (target !== null && mean !== null && used !== null) {
    base.chart = {
      target,
      targetLabel: 'Target value',
      mean,
      sd: asNumber(result.reference_spi_std),
      unit: 'SPI',
      nYears: Math.round(used),
      percentilePct: null,
    };
  }
  return base;
}

function temperatureModel(
  base: IndicatorCardModel,
  result: ResultRecord,
): IndicatorCardModel {
  const headlines: HeadlineRow[] = [];
  const anomaly = fmtSigned(asNumber(result.anomaly_c), 2);
  push(headlines, 'Anomaly', anomaly === null ? null : `${anomaly} °C`);
  const windowMean = fmt(asNumber(result.window_mean_c), 2);
  push(headlines, 'Window mean', windowMean === null ? null : `${windowMean} °C`);
  const refMean = fmt(asNumber(result.reference_mean_c), 2);
  push(headlines, 'Reference mean', refMean === null ? null : `${refMean} °C`);
  const pct = asNumber(result.percentile_rank);
  const used = asNumber(result.reference_years_used);
  if (pct !== null && used !== null) {
    headlines.push({
      label: 'Rank among reference years',
      value: `${(pct * 100).toFixed(1)}th percentile of ${Math.round(used)} years`,
    });
  }
  base.headlines = headlines;

  const target = asNumber(result.window_mean_c);
  const mean = asNumber(result.reference_mean_c);
  if (target !== null && mean !== null && used !== null) {
    base.chart = {
      target,
      targetLabel: 'Window mean',
      mean,
      sd: asNumber(result.reference_sd_c),
      unit: '°C',
      nYears: Math.round(used),
      percentilePct: pct === null ? null : pct * 100,
    };
  }
  return base;
}

function soilModel(
  base: IndicatorCardModel,
  result: ResultRecord,
): IndicatorCardModel {
  const headlines: HeadlineRow[] = [];
  const anomaly = fmtSigned(asNumber(result.anomaly_m3m3), 4);
  push(headlines, 'Anomaly', anomaly === null ? null : `${anomaly} m³/m³`);
  const windowMean = fmt(asNumber(result.window_mean_m3m3), 4);
  push(headlines, 'Window mean', windowMean === null ? null : `${windowMean} m³/m³`);
  const refMean = fmt(asNumber(result.reference_mean_m3m3), 4);
  push(headlines, 'Reference mean', refMean === null ? null : `${refMean} m³/m³`);
  push(headlines, 'Soil layer', asString(result.layer_depth));
  const used = asNumber(result.reference_years_used);
  push(headlines, 'Reference years used', used === null ? null : String(Math.round(used)));
  const pct = asNumber(result.percentile_rank);
  if (pct !== null && used !== null) {
    headlines.push({
      label: 'Rank among reference years',
      value: `${(pct * 100).toFixed(1)}th percentile of ${Math.round(used)} years`,
    });
  }
  base.headlines = headlines;

  const target = asNumber(result.window_mean_m3m3);
  const mean = asNumber(result.reference_mean_m3m3);
  if (target !== null && mean !== null && used !== null) {
    base.chart = {
      target,
      targetLabel: 'Window mean',
      mean,
      sd: asNumber(result.reference_sd_m3m3),
      unit: 'm³/m³',
      nYears: Math.round(used),
      percentilePct: pct === null ? null : pct * 100,
    };
  }
  return base;
}

export function toCardModel(entry: BundleIndicatorResult): IndicatorCardModel {
  const result = asRecord(entry.result as unknown);
  const { warnings, usedPoint } = warningsFor(result, entry);
  const base: IndicatorCardModel = {
    key: entry.indicator,
    title: TITLES[entry.indicator] ?? entry.indicator,
    status: entry.status,
    headlines: [],
    reference: referenceLine(result),
    dataSource: asString(result.data_source) ?? 'Unknown source',
    coverage: coverageFor(entry.indicator),
    requestedPoint: `${entry.requested_latitude.toFixed(3)}°, ${entry.requested_longitude.toFixed(3)}°`,
    usedPoint,
    limitations: asStringArray(result.limitations),
    citation: asString(result.citation),
    doi: asString(result.doi),
    license: asString(result.license_note),
    warnings,
    errorType: null,
    errorMessage: null,
    chart: null,
    method: methodFor(entry.indicator, result),
  };

  if (entry.status === 'failed') {
    const code =
      typeof entry.error_type === 'string' && entry.error_type.length > 0
        ? entry.error_type
        : 'internal';
    base.errorType = code;
    base.errorMessage = messageForCode(code);
    const raw =
      typeof entry.error_message === 'string' && entry.error_message.length > 0
        ? entry.error_message
        : null;
    if (raw !== null && raw !== base.errorMessage) {
      base.warnings = [...base.warnings, raw];
    }
    return base;
  }
  if (entry.status === 'skipped') {
    base.warnings = [...base.warnings, 'Not requested in this scenario.'];
    return base;
  }

  switch (entry.indicator) {
    case 'chirps_spi':
    case 'era5_spi':
      spiModel(base, result);
      break;
    case 'era5_temperature_anomaly':
      temperatureModel(base, result);
      break;
    case 'era5_soil_moisture_anomaly':
      soilModel(base, result);
      break;
    default:
      break;
  }

  if (entry.status === 'undefined') {
    const message = asString(result.message) ?? 'Indeterminate for this window.';
    base.warnings = [...base.warnings, message];
    base.chart = null;
  }
  return base;
}
