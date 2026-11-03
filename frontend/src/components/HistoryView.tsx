import { useCallback, useEffect, useState } from 'react';
import type { ScenarioSummary } from '../api/client';
import { deleteScenario, getScenario, listScenarios } from '../api/client';
import { ApiError } from '../api/errors';
import StatusBadge from './StatusBadge';

const PAGE_SIZE = 20;

function formatWhen(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

function HistoryRow({
  item,
  onOpen,
  onDeleted,
}: {
  item: ScenarioSummary;
  onOpen: (id: string) => void;
  onDeleted: (id: string) => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [problems, setProblems] = useState<string[] | null>(null);
  const [rowError, setRowError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const showProblemsToggle = item.status === 'failed' || item.status === 'partial';

  async function remove(): Promise<void> {
    setBusy(true);
    setRowError(null);
    try {
      await deleteScenario(item.scenario_id);
      onDeleted(item.scenario_id);
    } catch (error: unknown) {
      setRowError(error instanceof ApiError ? error.message : 'Delete failed.');
      setBusy(false);
      setConfirming(false);
    }
  }

  async function toggleProblems(): Promise<void> {
    if (expanded) {
      setExpanded(false);
      return;
    }
    if (problems === null) {
      setBusy(true);
      setRowError(null);
      try {
        const detail = await getScenario(item.scenario_id);
        setProblems(detail.problems);
      } catch (error: unknown) {
        setRowError(error instanceof ApiError ? error.message : 'Could not load details.');
        setBusy(false);
        return;
      }
      setBusy(false);
    }
    setExpanded(true);
  }

  return (
    <div className="card">
      <div className="status-line">
        <StatusBadge status={item.status} />
        <span className="subtle">
          {item.latitude.toFixed(2)}°, {item.longitude.toFixed(2)}° · target{' '}
          {item.target_end_month} · updated {formatWhen(item.updated_at)}
        </span>
      </div>
      <p style={{ margin: '6px 0' }}>
        <code className="inline">{item.scenario_id}</code> — {item.query}
      </p>
      {rowError && (
        <div className="banner error" role="alert">
          {rowError}
        </div>
      )}
      {expanded && problems !== null && (
        <div>
          {problems.length === 0 ? (
            <p className="subtle">No recorded problems.</p>
          ) : (
            <ul className="tight">
              {problems.map((problem) => (
                <li key={problem}>{problem}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      <div className="actions">
        <button type="button" className="primary" onClick={() => onOpen(item.scenario_id)}>
          Open
        </button>
        {showProblemsToggle && (
          <button type="button" className="ghost" disabled={busy} onClick={toggleProblems}>
            {expanded ? 'Hide problems' : 'Show problems'}
          </button>
        )}
        {confirming ? (
          <>
            <button type="button" className="danger" disabled={busy} onClick={remove}>
              Confirm delete
            </button>
            <button
              type="button"
              className="ghost"
              disabled={busy}
              onClick={() => setConfirming(false)}
            >
              Cancel
            </button>
          </>
        ) : (
          <button
            type="button"
            className="ghost"
            disabled={busy}
            onClick={() => setConfirming(true)}
          >
            Delete
          </button>
        )}
      </div>
    </div>
  );
}

export default function HistoryView({ onOpen }: { onOpen: (id: string) => void }) {
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [items, setItems] = useState<ScenarioSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (nextOffset: number): Promise<void> => {
    setError(null);
    try {
      const page = await listScenarios(PAGE_SIZE, nextOffset);
      setTotal(page.total);
      setItems(page.items);
      setOffset(nextOffset);
    } catch (error_: unknown) {
      setError(error_ instanceof ApiError ? error_.message : 'Could not load history.');
    }
  }, []);

  useEffect(() => {
    void load(0);
  }, [load]);

  function handleDeleted(id: string): void {
    setItems((current) => (current === null ? current : current.filter((item) => item.scenario_id !== id)));
    setTotal((current) => Math.max(0, current - 1));
  }

  return (
    <div>
      <div className="card">
        <h2>Scenario history</h2>
        <p className="subtle">
          {total === 0 ? 'No stored scenarios.' : `${total} stored scenario${total === 1 ? '' : 's'}, newest first.`}
        </p>
        {error && (
          <div className="banner error" role="alert">
            <strong>Could not load history</strong>
            {error}
          </div>
        )}
        {error && (
          <div className="actions">
            <button type="button" className="primary" onClick={() => void load(offset)}>
              Retry
            </button>
          </div>
        )}
      </div>

      {(items ?? []).map((item) => (
        <HistoryRow key={item.scenario_id} item={item} onOpen={onOpen} onDeleted={handleDeleted} />
      ))}

      {items !== null && total > PAGE_SIZE && (
        <div className="actions">
          <button
            type="button"
            className="ghost"
            disabled={offset === 0}
            onClick={() => void load(Math.max(0, offset - PAGE_SIZE))}
          >
            Previous
          </button>
          <span className="subtle">
            {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
          </span>
          <button
            type="button"
            className="ghost"
            disabled={offset + PAGE_SIZE >= total}
            onClick={() => void load(offset + PAGE_SIZE)}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
