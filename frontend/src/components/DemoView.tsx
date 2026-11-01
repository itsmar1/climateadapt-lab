import { useEffect, useState } from 'react';
import type { DemoSnapshotFile, DemoSnapshotSummary } from '../api/client';
import { getDemoSnapshot, listDemoSnapshots } from '../api/client';
import { ApiError } from '../api/errors';
import ResultsView from './ResultsView';
import StatusBadge from './StatusBadge';

function formatWhen(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

function messageOf(error: unknown): string {
  return error instanceof ApiError ? error.message : 'Could not load demo snapshots.';
}

/**
 * Demo mode: stored real-data snapshots served verbatim. Every snapshot view
 * is bannered as a cached snapshot with its capture timestamp — never a live
 * result. Works offline and under rate limits; needs CLIMATEADAPT_DEMO_MODE.
 */
export default function DemoView({
  snapshotKey,
  onOpen,
}: {
  snapshotKey: string | null;
  onOpen: (key: string | null) => void;
}) {
  const [summaries, setSummaries] = useState<DemoSnapshotSummary[] | null>(null);
  const [snapshot, setSnapshot] = useState<DemoSnapshotFile | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listDemoSnapshots().then(
      (page) => setSummaries(page.snapshots),
      (failure: unknown) => setError(messageOf(failure)),
    );
  }, []);

  useEffect(() => {
    if (snapshotKey === null) {
      setSnapshot(null);
      return;
    }
    setSnapshot(null);
    setError(null);
    getDemoSnapshot(snapshotKey).then(setSnapshot, (failure: unknown) =>
      setError(messageOf(failure)),
    );
  }, [snapshotKey]);

  if (snapshotKey !== null) {
    if (error) {
      return (
        <div className="card">
          <h2>Demo snapshot</h2>
          <div className="banner error" role="alert">
            <strong>Could not load this snapshot</strong>
            {error}
          </div>
          <div className="actions">
            <button type="button" className="ghost" onClick={() => onOpen(null)}>
              Back to snapshots
            </button>
          </div>
        </div>
      );
    }
    if (snapshot === null) {
      return (
        <div className="card" aria-live="polite">
          <h2>Demo snapshot</h2>
          <p className="subtle">Loading the stored snapshot…</p>
        </div>
      );
    }
    return (
      <ResultsView
        detail={snapshot.detail}
        onNew={() => onOpen(null)}
        snapshot={{ label: snapshot.label, capturedAt: snapshot.captured_at_utc }}
      />
    );
  }

  return (
    <div>
      <div className="card">
        <h2>Demo snapshots</h2>
        <p className="subtle">
          Stored real-data runs, served verbatim. Each view is labelled with its
          capture timestamp; nothing here is a live result. Needs demo mode on
          the server.
        </p>
        {error && (
          <div className="banner error" role="alert">
            <strong>Could not load snapshots</strong>
            {error}
          </div>
        )}
        {summaries !== null && summaries.length === 0 && !error && (
          <p className="subtle">No snapshots stored on this server.</p>
        )}
      </div>
      {(summaries ?? []).map((summary) => (
        <div className="card" key={summary.key}>
          <div className="status-line">
            <StatusBadge status={summary.status} />
            <span className="subtle">captured {formatWhen(summary.captured_at_utc)}</span>
          </div>
          <p style={{ margin: '6px 0' }}>
            <strong>{summary.label}</strong>{' '}
            <code className="inline">{summary.key}</code>
          </p>
          <div className="actions">
            <button
              type="button"
              className="primary"
              onClick={() => onOpen(summary.key)}
            >
              Open
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
