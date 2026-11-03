import { useEffect, useState } from 'react';
import {
  Activity,
  BookOpen,
  Database,
  FileCheck2,
  ListOrdered,
} from 'lucide-react';
import type { DemoSnapshotSummary, ScenarioSummary } from '../api/client';
import {
  getDemoSnapshot,
  listDemoSnapshots,
  listScenarios,
} from '../api/client';
import { ApiError } from '../api/errors';
import {
  CHIRPS_COVERAGE,
  CHIRPS_SOURCE,
  ERA5_COVERAGE,
  ERA5_SOURCE,
} from '../api/presenters';
import type { GeoMarker } from './GeoMap';
import GeoMap from './GeoMap';

const FLOW = [
  {
    icon: Database,
    label: 'Archives',
    caption: 'CHIRPS + ERA5-Land stores',
  },
  {
    icon: Activity,
    label: 'Indicators',
    caption: 'Deterministic SPI + anomalies',
  },
  {
    icon: BookOpen,
    label: 'Cited evidence',
    caption: 'Passages with page citations',
  },
  {
    icon: ListOrdered,
    label: 'Ranked options',
    caption: 'Constraints + scored ranking',
  },
  {
    icon: FileCheck2,
    label: 'Validated report',
    caption: 'Model draft, platform-checked',
  },
];

function formatWhen(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

function demoMarker(summary: DemoSnapshotSummary, lat: number, lon: number): GeoMarker {
  return {
    id: `demo-${summary.key}`,
    position: [lat, lon],
    popupTitle: 'Captured real run',
    popupLines: [
      summary.label,
      `${summary.status} · captured ${formatWhen(summary.captured_at_utc)}`,
    ],
    tone: 'demo',
  };
}

function historyMarker(item: ScenarioSummary): GeoMarker {
  return {
    id: `history-${item.scenario_id}`,
    position: [item.latitude, item.longitude],
    popupTitle: 'Your analysis',
    popupLines: [
      `${item.latitude.toFixed(2)}°, ${item.longitude.toFixed(2)}° · target ${item.target_end_month}`,
      `${item.status} · updated ${formatWhen(item.updated_at)}`,
    ],
    tone: 'history',
  };
}

/**
 * Default landing: what the platform does, where its data covers, and where
 * real runs exist. Every marker comes from a live API response (demo files
 * carry their scenario coordinates; history summaries carry theirs); when an
 * API is unavailable the map still renders with a clear unavailable note and
 * no placeholder numbers.
 */
export default function Overview() {
  const [demoMarkers, setDemoMarkers] = useState<GeoMarker[] | null>(null);
  const [historyMarkers, setHistoryMarkers] = useState<GeoMarker[] | null>(null);
  const [demoError, setDemoError] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [skippedSnapshots, setSkippedSnapshots] = useState<string[]>([]);
  const loading = demoMarkers === null || historyMarkers === null;

  useEffect(() => {
    let cancelled = false;

    async function loadDemo(): Promise<void> {
      try {
        const page = await listDemoSnapshots();
        const markers: GeoMarker[] = [];
        const skipped: string[] = [];
        for (const summary of page.snapshots) {
          try {
            const file = await getDemoSnapshot(summary.key);
            const lat = file.detail.scenario.latitude;
            const lon = file.detail.scenario.longitude;
            if (typeof lat !== 'number' || typeof lon !== 'number') {
              skipped.push(summary.key);
              continue;
            }
            markers.push(demoMarker(summary, lat, lon));
          } catch {
            skipped.push(summary.key);
          }
        }
        if (!cancelled) {
          setDemoMarkers(markers);
          setSkippedSnapshots(skipped);
        }
      } catch (error: unknown) {
        if (!cancelled) {
          setDemoError(
            error instanceof ApiError ? error.message : 'Could not load demo snapshots.',
          );
          setDemoMarkers([]);
        }
      }
    }

    async function loadHistory(): Promise<void> {
      try {
        const page = await listScenarios(20, 0);
        if (!cancelled) {
          setHistoryMarkers(page.items.map(historyMarker));
        }
      } catch (error: unknown) {
        if (!cancelled) {
          setHistoryError(
            error instanceof ApiError ? error.message : 'Could not load history.',
          );
          setHistoryMarkers([]);
        }
      }
    }

    void loadDemo();
    void loadHistory();
    return () => {
      cancelled = true;
    };
  }, []);

  const markers = [...(demoMarkers ?? []), ...(historyMarkers ?? [])];

  return (
    <div>
      <div className="hero">
        <h1>From satellite archives to a citable adaptation report</h1>
        <p>
          ClimateAdapt Lab computes environmental indicators deterministically
          from CHIRPS and ERA5-Land, retrieves cited scientific evidence, ranks
          adaptation options with transparent rules, and has Meta&apos;s Muse
          Spark model draft a report that deterministic code validates
          statement by statement. Numbers are computed, claims are cited, and
          uncertainty stays visible.
        </p>
        <div className="hero-actions">
          <a className="primary" href="#/new">
            Start an analysis
          </a>
          <a className="ghost" href="#/demo">
            Open the demo
          </a>
        </div>
      </div>

      <div className="card">
        <h2>Coverage &amp; runs</h2>
        <p className="subtle">
          Shaded bands lie outside 60°S–60°N: there, CHIRPS does not apply and
          ERA5-Land indicators still run. Markers show real runs only.
        </p>
        {loading && (
          <div className="loading-row" aria-live="polite">
            <span className="spinner" aria-hidden="true" />
            Loading run locations…
          </div>
        )}
        <GeoMap
          mapLabel="Dataset coverage and run locations"
          center={[20, 0]}
          zoom={2}
          markers={markers}
          showChirpsBand
          className="geo-map geo-map-large"
        />
        <ul className="map-legend" aria-label="Map legend">
          <li>
            <span className="swatch swatch-demo" aria-hidden="true" />
            Captured real run (demo snapshot)
          </li>
          <li>
            <span className="swatch swatch-history" aria-hidden="true" />
            Your analysis (history)
          </li>
          <li>
            <span className="swatch swatch-band" aria-hidden="true" />
            Outside the CHIRPS band
          </li>
        </ul>
        {!loading && (
          <p className="meta" data-testid="overview-counts">
            {(demoMarkers ?? []).length} demo snapshot
            {(demoMarkers ?? []).length === 1 ? '' : 's'} ·{' '}
            {(historyMarkers ?? []).length} recent{' '}
            {(historyMarkers ?? []).length === 1 ? 'analysis' : 'analyses'} on
            this map.
          </p>
        )}
        {demoError && (
          <div className="banner error" role="alert">
            <strong>Demo snapshots unavailable</strong>
            {demoError}
          </div>
        )}
        {historyError && (
          <div className="banner error" role="alert">
            <strong>Your analyses unavailable</strong>
            {historyError}
          </div>
        )}
        {skippedSnapshots.length > 0 && (
          <div className="banner warn" role="note">
            <strong>Some snapshots have no map position</strong>
            {skippedSnapshots.join(', ')} could not be placed; open them from
            the Demo page instead.
          </div>
        )}
        <ul className="coverage-list">
          <li>
            <strong>CHIRPS v3 Final</strong> — {CHIRPS_COVERAGE}.{' '}
            <span className="subtle">Source: {CHIRPS_SOURCE}.</span>
          </li>
          <li>
            <strong>ERA5-Land monthly means</strong> — {ERA5_COVERAGE}.{' '}
            <span className="subtle">Source: {ERA5_SOURCE}.</span>
          </li>
        </ul>
      </div>

      <div className="card">
        <h2>How it works</h2>
        <p className="subtle">
          One fixed pipeline per run. Each stage is exhibited by the captured
          demo runs.
        </p>
        <ol className="flow-strip" aria-label="Pipeline stages">
          {FLOW.map((step) => (
            <li key={step.label}>
              <a href="#/demo" aria-label={`${step.label}: ${step.caption}`}>
                <step.icon size={16} aria-hidden="true" />
                <span>
                  {step.label}
                  <br />
                  <span className="subtle">{step.caption}</span>
                </span>
              </a>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}
