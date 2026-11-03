import { useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import type { AgentScenario } from '../api/client';
import { createScenario } from '../api/client';
import { ApiError, messageForCode, parseValidationErrors } from '../api/errors';
import type { LocationPreset } from '../api/geo';
import {
  LOCATION_PRESETS,
  formatCoord,
  isInChirpsBand,
  parseLatLon,
} from '../api/geo';
import GeoMap from './GeoMap';
import {
  CHIRPS_COVERAGE,
  CHIRPS_SOURCE,
  ERA5_COVERAGE,
  ERA5_SOURCE,
} from '../api/presenters';

const INDICATORS = [
  { id: 'chirps_spi', label: 'CHIRPS rainfall (SPI)' },
  { id: 'era5_spi', label: 'ERA5-Land rainfall (SPI)' },
  { id: 'era5_temperature_anomaly', label: 'ERA5-Land temperature' },
  { id: 'era5_soil_moisture_anomaly', label: 'ERA5-Land soil moisture' },
] as const;
const STEPS = ['Location', 'Crop & system', 'Time & reference', 'Evidence & indicators'];

/** Client-side error keys owned by each step (server errors jump to theirs). */
const STEP_FIELDS: string[][] = [
  ['latitude', 'longitude'],
  [],
  [
    'target_end_month',
    'timescale_months',
    'reference_start_year',
    'reference_end_year',
    'min_reference_years',
  ],
  ['query', 'top_k', 'land_fallback_max_km', 'indicators'],
];

const REFERENCE_TIP =
  'Baseline years each indicator is compared against. Years with incomplete data are excluded, never filled in.';

const FALLBACK_TIP =
  'When the point falls on a masked ERA5-Land cell, the nearest land cell within this distance is used instead, and the substitution is reported with its distance.';

type IndicatorId = AgentScenario['indicators'][number];

type TriState = 'unknown' | 'yes' | 'no';

interface FormState {
  latitude: string;
  longitude: string;
  targetEndMonth: string;
  timescaleMonths: string;
  referenceStartYear: string;
  referenceEndYear: string;
  minReferenceYears: string;
  crop: string;
  hasWaterSource: TriState;
  hasIrrigationEquipment: TriState;
  productionSystem: '' | 'irrigated' | 'rainfed';
  season: string;
  query: string;
  topK: string;
  excludeReference: boolean;
  allowFallback: boolean;
  fallbackKm: string;
  indicators: IndicatorId[];
}

const INITIAL: FormState = {
  latitude: '30.43',
  longitude: '-9.61',
  targetEndMonth: '2024-03',
  timescaleMonths: '3',
  referenceStartYear: '1991',
  referenceEndYear: '2020',
  minReferenceYears: '30',
  crop: 'wheat',
  hasWaterSource: 'yes',
  hasIrrigationEquipment: 'yes',
  productionSystem: 'irrigated',
  season: '2024-03',
  query: 'deficit irrigation scheduling',
  topK: '5',
  excludeReference: true,
  allowFallback: true,
  fallbackKm: '15',
  indicators: INDICATORS.map((entry) => entry.id),
};

function triToBool(value: TriState): boolean | null {
  if (value === 'yes') {
    return true;
  }
  if (value === 'no') {
    return false;
  }
  return null;
}

function parseNumber(raw: string): number | null {
  if (raw.trim() === '') {
    return null;
  }
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

function parseIntStrict(raw: string): number | null {
  if (!/^-?\d+$/.test(raw.trim())) {
    return null;
  }
  const value = Number(raw);
  return Number.isSafeInteger(value) ? value : null;
}

function validate(state: FormState): Record<string, string> {
  const errors: Record<string, string> = {};
  const lat = parseNumber(state.latitude);
  if (lat === null || lat < -90 || lat > 90) {
    errors.latitude = 'Enter a latitude between -90 and 90.';
  }
  const lon = parseNumber(state.longitude);
  if (lon === null || lon < -180 || lon > 180) {
    errors.longitude = 'Enter a longitude between -180 and 180.';
  }
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(state.targetEndMonth)) {
    errors.target_end_month = 'Use YYYY-MM, for example 2024-03.';
  }
  const timescale = parseIntStrict(state.timescaleMonths);
  if (timescale === null || timescale < 1 || timescale > 48) {
    errors.timescale_months = 'Enter a whole number of months from 1 to 48.';
  }
  const startYear = parseIntStrict(state.referenceStartYear);
  const endYear = parseIntStrict(state.referenceEndYear);
  const minYears = parseIntStrict(state.minReferenceYears);
  if (startYear === null || startYear < 1 || startYear > 9999) {
    errors.reference_start_year = 'Enter a valid start year.';
  }
  if (endYear === null || endYear < 1 || endYear > 9999) {
    errors.reference_end_year = 'Enter a valid end year.';
  }
  if (
    startYear !== null &&
    endYear !== null &&
    startYear >= 1 &&
    endYear >= 1 &&
    endYear < startYear
  ) {
    errors.reference_end_year = 'The end year must not be earlier than the start year.';
  }
  if (minYears === null || minYears < 10 || minYears > 100) {
    errors.min_reference_years = 'Enter a whole number from 10 to 100.';
  } else if (
    startYear !== null &&
    endYear !== null &&
    endYear >= startYear &&
    minYears > endYear - startYear + 1
  ) {
    errors.min_reference_years = 'Cannot exceed the number of reference years.';
  }
  if (state.query.trim().length === 0) {
    errors.query = 'Describe the evidence question.';
  } else if (state.query.length > 500) {
    errors.query = 'Keep the question under 500 characters.';
  }
  const topK = parseIntStrict(state.topK);
  if (topK === null || topK < 1 || topK > 20) {
    errors.top_k = 'Enter a whole number from 1 to 20.';
  }
  if (state.allowFallback) {
    const km = parseNumber(state.fallbackKm);
    if (km === null || km <= 0 || km > 25) {
      errors.land_fallback_max_km = 'Enter a distance from just above 0 to 25 km.';
    }
  }
  if (state.indicators.length === 0) {
    errors.indicators = 'Select at least one indicator.';
  }
  return errors;
}

function toBody(state: FormState): AgentScenario {
  const crop = state.crop.trim();
  const season = state.season.trim();
  return {
    latitude: Number(state.latitude),
    longitude: Number(state.longitude),
    target_end_month: state.targetEndMonth,
    timescale_months: Number(state.timescaleMonths),
    reference_start_year: Number(state.referenceStartYear),
    reference_end_year: Number(state.referenceEndYear),
    min_reference_years: Number(state.minReferenceYears),
    land_fallback_max_km: state.allowFallback ? Number(state.fallbackKm) : null,
    indicators: [...state.indicators],
    query: state.query.trim(),
    top_k: Number(state.topK),
    exclude_reference: state.excludeReference,
    crop: crop === '' ? null : crop,
    has_water_source: triToBool(state.hasWaterSource),
    has_irrigation_equipment: triToBool(state.hasIrrigationEquipment),
    production_system: state.productionSystem === '' ? null : state.productionSystem,
    season: season === '' ? null : season,
  };
}

export default function ScenarioForm({ onCreated }: { onCreated: (id: string) => void }) {
  const [state, setState] = useState<FormState>(INITIAL);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [step, setStep] = useState(0);
  const [doneSteps, setDoneSteps] = useState<boolean[]>([false, false, false, false]);
  const [fallbackOpen, setFallbackOpen] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);

  function set<K extends keyof FormState>(key: K, value: FormState[K]): void {
    setState((prev) => ({ ...prev, [key]: value }));
  }

  function toggleIndicator(id: IndicatorId): void {
    setState((prev) => ({
      ...prev,
      indicators: prev.indicators.includes(id)
        ? prev.indicators.filter((entry) => entry !== id)
        : [...prev.indicators, id],
    }));
  }

  /** Open any collapsed panel holding one of these errors so it is visible. */
  function revealErrors(found: Record<string, string>): void {
    if (found.land_fallback_max_km !== undefined) {
      setFallbackOpen(true);
    }
    if (found.top_k !== undefined) {
      setAdvancedOpen(true);
    }
  }

  function firstErrorStep(found: Record<string, string>): number {
    for (let index = 0; index < STEP_FIELDS.length; index += 1) {
      const keys = STEP_FIELDS[index] ?? [];
      if (keys.some((key) => found[key] !== undefined)) {
        return index;
      }
    }
    return step;
  }

  function pickStepErrors(
    found: Record<string, string>,
    index: number,
  ): Record<string, string> {
    const picked: Record<string, string> = {};
    for (const key of STEP_FIELDS[index] ?? []) {
      const message = found[key];
      if (message !== undefined) {
        picked[key] = message;
      }
    }
    return picked;
  }

  function goNext(): void {
    const found = pickStepErrors(validate(state), step);
    setErrors(found);
    revealErrors(found);
    if (Object.keys(found).length > 0) {
      return;
    }
    setDoneSteps((prev) => prev.map((done, index) => done || index === step));
    setStep(step + 1);
  }

  async function handleSubmit(event: FormEvent): Promise<void> {
    event.preventDefault();
    const local = validate(state);
    setErrors(local);
    revealErrors(local);
    setSubmitError(null);
    if (Object.keys(local).length > 0) {
      setStep(firstErrorStep(local));
      return;
    }
    setSubmitting(true);
    try {
      const created = await createScenario(toBody(state));
      onCreated(created.scenario_id);
    } catch (error: unknown) {
      if (error instanceof ApiError && error.status === 422) {
        const mapped = parseValidationErrors(error.body);
        setErrors(mapped);
        revealErrors(mapped);
        setStep(firstErrorStep(mapped));
        setSubmitError('The server rejected some fields; see the messages below.');
      } else if (error instanceof ApiError) {
        setSubmitError(error.message);
      } else {
        setSubmitError(messageForCode('internal'));
      }
    } finally {
      setSubmitting(false);
    }
  }
  function fieldError(name: string): ReactNode {
    const message = errors[name];
    if (!message) {
      return null;
    }
    return <p className="field-error">{message}</p>;
  }

  function applyPreset(preset: LocationPreset): void {
    setState((prev) => ({
      ...prev,
      latitude: String(preset.lat),
      longitude: String(preset.lon),
    }));
  }

  function applyPicked(lat: number, lon: number): void {
    setState((prev) => ({
      ...prev,
      latitude: formatCoord(lat),
      longitude: formatCoord(lon),
    }));
  }

  const picked = parseLatLon(state.latitude, state.longitude);
  const mapPoint = picked ?? { lat: 30.43, lon: -9.61 };
  const outsideBand = picked !== null && !isInChirpsBand(picked.lat);
  return (
    <form onSubmit={handleSubmit} noValidate aria-label="Scenario form">
      {submitError && (
        <div className="banner error" role="alert">
          <strong>Could not create the scenario</strong>
          {submitError}
        </div>
      )}
      <div className="summary-panel" data-testid="form-summary">
        <strong>Draft summary</strong>
        <dl>
          <div style={{ display: 'contents' }}>
            <dt>Location</dt>
            <dd>{picked ? `${formatCoord(picked.lat)}°, ${formatCoord(picked.lon)}°` : '—'}</dd>
          </div>
          <div style={{ display: 'contents' }}>
            <dt>Window</dt>
            <dd>{`${state.targetEndMonth.trim() || '—'} · ${state.timescaleMonths.trim() || '—'}-month`}</dd>
          </div>
          <div style={{ display: 'contents' }}>
            <dt>Reference</dt>
            <dd>{`${state.referenceStartYear.trim() || '—'}–${state.referenceEndYear.trim() || '—'} (min ${state.minReferenceYears.trim() || '—'})`}</dd>
          </div>
          <div style={{ display: 'contents' }}>
            <dt>Crop · system</dt>
            <dd>{`${state.crop.trim() === '' ? 'Any crop' : state.crop.trim()} · ${state.productionSystem === '' ? 'Unknown' : state.productionSystem}`}</dd>
          </div>
          <div style={{ display: 'contents' }}>
            <dt>Evidence</dt>
            <dd>{state.query.trim() === '' ? '—' : `“${state.query.trim()}” · top ${state.topK.trim() || '—'}`}</dd>
          </div>
          <div style={{ display: 'contents' }}>
            <dt>Indicators</dt>
            <dd>{`${state.indicators.length} selected`}</dd>
          </div>
          <div style={{ display: 'contents' }}>
            <dt>Land fallback</dt>
            <dd>
              {state.allowFallback
                ? state.fallbackKm.trim() === ''
                  ? 'On (distance unset)'
                  : `Up to ${state.fallbackKm.trim()} km`
                : 'Off'}
            </dd>
          </div>
        </dl>
      </div>

      <ol className="stepper" aria-label="Analysis steps">
        {STEPS.map((label, index) => (
          <li key={label}>
            <button
              type="button"
              className={doneSteps[index] === true && index !== step ? 'step step-done' : 'step'}
              aria-current={index === step ? 'step' : undefined}
              onClick={() => setStep(index)}
            >
              <span className="step-number" aria-hidden="true">
                {index + 1}
              </span>
              {label}
            </button>
          </li>
        ))}
      </ol>

      {step === 0 && (
        <div>
      <div className="field field-full">
        <span id="location-picker-label">Location picker</span>
        <div className="preset-row" role="group" aria-label="Demo locations">
          {LOCATION_PRESETS.map((preset) => (
            <button
              key={preset.key}
              type="button"
              className="ghost preset"
              onClick={() => applyPreset(preset)}
            >
              {preset.label}
            </button>
          ))}
        </div>
        <GeoMap
          mapLabel="Analysis location map"
          center={[mapPoint.lat, mapPoint.lon]}
          zoom={3}
          markers={[
            {
              id: 'picker',
              position: [mapPoint.lat, mapPoint.lon],
              popupTitle: 'Analysis location',
              popupLines: [`${formatCoord(mapPoint.lat)}°, ${formatCoord(mapPoint.lon)}°`],
              tone: 'request',
              draggable: true,
            },
          ]}
          showChirpsBand
          onPick={applyPicked}
          onMarkerMove={(_id, lat, lon) => applyPicked(lat, lon)}
        />
        <p className="hint">
          Click the map or drag the marker — or type coordinates below. Shaded
          bands lie outside 60°S–60°N: there, CHIRPS does not apply and
          ERA5-Land indicators still run.
        </p>
        {outsideBand && (
          <p className="band-note" role="note">
            Current latitude is outside the CHIRPS band: the CHIRPS indicator
            will report <code className="inline">outside_coverage</code>;
            ERA5-Land still runs.
          </p>
        )}
      </div>
          <div className="form-grid">
        <div className="field">
          <label htmlFor="latitude">Latitude</label>
          <input
            id="latitude"
            inputMode="decimal"
            value={state.latitude}
            onChange={(event) => set('latitude', event.target.value)}
            aria-invalid={errors.latitude ? true : undefined}
          />
          <p className="hint">CHIRPS covers 60°S–60°N; ERA5-Land is global.</p>
          {fieldError('latitude')}
        </div>
        <div className="field">
          <label htmlFor="longitude">Longitude</label>
          <input
            id="longitude"
            inputMode="decimal"
            value={state.longitude}
            onChange={(event) => set('longitude', event.target.value)}
            aria-invalid={errors.longitude ? true : undefined}
          />
          <p className="hint">Demo point 30.43, −9.61 (Souss-Massa, Morocco).</p>
          {fieldError('longitude')}
        </div>
          </div>
          <ul className="coverage-list" aria-label="Dataset coverage">
            <li>
              <strong>CHIRPS v3 Final</strong> — {CHIRPS_COVERAGE}.{' '}
              <span className="subtle">Source: {CHIRPS_SOURCE}.</span>
            </li>
            <li>
              <strong>ERA5-Land monthly means</strong> — {ERA5_COVERAGE}.{' '}
              <span className="subtle">Source: {ERA5_SOURCE}.</span>
            </li>
          </ul>
          <div className="actions">
            <button type="button" className="primary" onClick={goNext}>
              Next
            </button>
          </div>
        </div>
      )}
      {step === 1 && (
        <div>
          <div className="form-grid">
        <div className="field">
          <label htmlFor="crop">Crop (optional)</label>
          <input
            id="crop"
            value={state.crop}
            onChange={(event) => set('crop', event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="hasWaterSource">Water source available</label>
          <select
            id="hasWaterSource"
            value={state.hasWaterSource}
            onChange={(event) => set('hasWaterSource', event.target.value as TriState)}
          >
            <option value="unknown">Unknown</option>
            <option value="yes">Yes</option>
            <option value="no">No</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="hasIrrigationEquipment">Irrigation equipment</label>
          <select
            id="hasIrrigationEquipment"
            value={state.hasIrrigationEquipment}
            onChange={(event) =>
              set('hasIrrigationEquipment', event.target.value as TriState)
            }
          >
            <option value="unknown">Unknown</option>
            <option value="yes">Yes</option>
            <option value="no">No</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="productionSystem">Production system</label>
          <select
            id="productionSystem"
            value={state.productionSystem}
            onChange={(event) =>
              set('productionSystem', event.target.value as '' | 'irrigated' | 'rainfed')
            }
          >
            <option value="">Unknown</option>
            <option value="irrigated">Irrigated</option>
            <option value="rainfed">Rainfed</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="season">Season (optional)</label>
          <input
            id="season"
            value={state.season}
            onChange={(event) => set('season', event.target.value)}
          />
        </div>
          </div>
          <div className="actions">
            <button type="button" className="ghost" onClick={() => setStep(0)}>
              Back
            </button>
            <button type="button" className="primary" onClick={goNext}>
              Next
            </button>
          </div>
        </div>
      )}
      {step === 2 && (
        <div>
          <div className="form-grid">
        <div className="field">
          <label htmlFor="targetEndMonth">Target end month</label>
          <input
            id="targetEndMonth"
            type="month"
            value={state.targetEndMonth}
            onChange={(event) => set('targetEndMonth', event.target.value)}
          />
          <p className="hint">End of the analysis window (YYYY-MM).</p>
          {fieldError('target_end_month')}
        </div>
        <div className="field">
          <label htmlFor="timescaleMonths">Timescale (months)</label>
          <input
            id="timescaleMonths"
            inputMode="numeric"
            value={state.timescaleMonths}
            onChange={(event) => set('timescaleMonths', event.target.value)}
          />
          <p className="hint">Window length, 1–48 months.</p>
          {fieldError('timescale_months')}
        </div>
        <div className="field">
          <label htmlFor="referenceStartYear">
            Reference start year
            <span className="tip" role="img" aria-label={REFERENCE_TIP} title={REFERENCE_TIP}>
              ?
            </span>
          </label>
          <input
            id="referenceStartYear"
            inputMode="numeric"
            value={state.referenceStartYear}
            onChange={(event) => set('referenceStartYear', event.target.value)}
          />
          {fieldError('reference_start_year')}
        </div>
        <div className="field">
          <label htmlFor="referenceEndYear">Reference end year</label>
          <input
            id="referenceEndYear"
            inputMode="numeric"
            value={state.referenceEndYear}
            onChange={(event) => set('referenceEndYear', event.target.value)}
          />
          {fieldError('reference_end_year')}
        </div>
        <div className="field">
          <label htmlFor="minReferenceYears">Minimum reference years</label>
          <input
            id="minReferenceYears"
            inputMode="numeric"
            value={state.minReferenceYears}
            onChange={(event) => set('minReferenceYears', event.target.value)}
          />
          <p className="hint">Years with incomplete data are excluded, never filled in.</p>
          {fieldError('min_reference_years')}
        </div>
          </div>
          <div className="actions">
            <button type="button" className="ghost" onClick={() => setStep(1)}>
              Back
            </button>
            <button type="button" className="primary" onClick={goNext}>
              Next
            </button>
          </div>
        </div>
      )}
      {step === 3 && (
        <div>
          <div className="form-grid">
        <div className="field field-full">
          <label htmlFor="query">Evidence question</label>
          <input
            id="query"
            value={state.query}
            onChange={(event) => set('query', event.target.value)}
          />
          <p className="hint">Guides scientific-evidence retrieval for the report.</p>
          {fieldError('query')}
        </div>
        <div className="field field-full">
          <span id="indicators-label" style={{ fontWeight: 600, fontSize: 14 }}>
            Indicators
          </span>
          <div className="check-list" role="group" aria-labelledby="indicators-label">
            {INDICATORS.map((entry) => (
              <label key={entry.id} className="check-row">
                <input
                  type="checkbox"
                  checked={state.indicators.includes(entry.id)}
                  onChange={() => toggleIndicator(entry.id)}
                />
                {entry.label}
              </label>
            ))}
          </div>
          {fieldError('indicators')}
        </div>
          </div>
          <div className="field field-full">
            <details
              className="card-details"
              open={fallbackOpen}
              onToggle={(event) => setFallbackOpen(event.currentTarget.open)}
            >
              <summary>
                ERA5-Land land fallback
                <span className="tip" role="img" aria-label={FALLBACK_TIP} title={FALLBACK_TIP}>
                  ?
                </span>
              </summary>
        <div className="field field-full">
          <div className="check-row">
            <input
              id="allowFallback"
              type="checkbox"
              checked={state.allowFallback}
              onChange={(event) => set('allowFallback', event.target.checked)}
            />
            <label htmlFor="allowFallback">
              Allow ERA5-Land land fallback
              <p className="hint">
                ERA5-Land masks some coastal grid points. When enabled, a masked
                point falls back to the nearest land grid point within the distance
                below, and the results say so prominently. Disabled means masked
                points simply fail with a typed error.
              </p>
            </label>
          </div>
        </div>
        {state.allowFallback && (
          <div className="field">
            <label htmlFor="fallbackKm">Fallback max distance (km)</label>
            <input
              id="fallbackKm"
              inputMode="decimal"
              value={state.fallbackKm}
              onChange={(event) => set('fallbackKm', event.target.value)}
            />
            {fieldError('land_fallback_max_km')}
          </div>
        )}
            </details>
          </div>
          <div className="field field-full">
            <details
              className="card-details"
              open={advancedOpen}
              onToggle={(event) => setAdvancedOpen(event.currentTarget.open)}
            >
              <summary>Advanced retrieval settings</summary>
        <div className="field">
          <label htmlFor="topK">Evidence passages</label>
          <input
            id="topK"
            inputMode="numeric"
            value={state.topK}
            onChange={(event) => set('topK', event.target.value)}
          />
          {fieldError('top_k')}
        </div>
              <label className="check-row">
                <input
                  type="checkbox"
                  checked={state.excludeReference}
                  onChange={(event) => set('excludeReference', event.target.checked)}
                />
                Exclude reference sections from retrieval
              </label>
              <p className="hint">
                Bibliography sections never answer an adaptation question; excluding
                them keeps evidence passages substantive. On by default.
              </p>
            </details>
          </div>
          <p className="hint">
            Cached results return in seconds. A first run at a new location can take
            several minutes: the satellite archives serve one area at a time, and the
            page polls until the run completes.
          </p>
          <div className="actions">
            <button type="button" className="ghost" onClick={() => setStep(2)}>
              Back
            </button>
            <button type="submit" className="primary" disabled={submitting}>
              {submitting ? 'Creating…' : 'Run analysis'}
            </button>
          </div>
        </div>
      )}
    </form>
  );
}
