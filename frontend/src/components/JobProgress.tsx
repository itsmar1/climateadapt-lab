import { useEffect, useRef, useState } from 'react';
import type { ScenarioDetail } from '../api/client';
import { getScenario } from '../api/client';
import { ApiError } from '../api/errors';
import StatusBadge from './StatusBadge';

interface JobProgressProps {
  scenarioId: string;
  pollIntervalMs?: number;
  timeoutMs?: number;
  onDone: (detail: ScenarioDetail) => void;
  onStop: () => void;
}

type Phase = 'polling' | 'fetch-error' | 'timed-out';

const TERMINAL = new Set(['complete', 'partial', 'failed']);

export default function JobProgress({
  scenarioId,
  pollIntervalMs = 2000,
  timeoutMs = 600000,
  onDone,
  onStop,
}: JobProgressProps) {
  const [phase, setPhase] = useState<Phase>('polling');
  const [status, setStatus] = useState<string>('queued');
  const [jobId, setJobId] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [failure, setFailure] = useState<string | null>(null);
  const [generation, setGeneration] = useState(0);
  const stateRef = useRef({ cancelled: false, done: false });
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  useEffect(() => {
    stateRef.current = { cancelled: false, done: false };
    const startedAt = Date.now();
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function poll(): Promise<void> {
      if (stateRef.current.cancelled || stateRef.current.done) {
        return;
      }
      if (Date.now() - startedAt >= timeoutMs) {
        setPhase('timed-out');
        return;
      }
      try {
        const detail = await getScenario(scenarioId);
        if (stateRef.current.cancelled) {
          return;
        }
        setStatus(detail.status);
        setJobId(detail.job_id);
        setElapsed(Math.round((Date.now() - startedAt) / 1000));
        if (TERMINAL.has(detail.status)) {
          stateRef.current.done = true;
          onDoneRef.current(detail);
          return;
        }
      } catch (error: unknown) {
        if (stateRef.current.cancelled) {
          return;
        }
        setFailure(error instanceof ApiError ? error.message : 'Polling failed.');
        setPhase('fetch-error');
        return;
      }
      timer = setTimeout(() => void poll(), pollIntervalMs);
    }

    void poll();
    return () => {
      stateRef.current.cancelled = true;
      if (timer !== undefined) {
        clearTimeout(timer);
      }
    };
    // Re-runs only when the scenario changes or the user retries/extends.
  }, [scenarioId, generation, pollIntervalMs, timeoutMs]);

  function retry(): void {
    setFailure(null);
    setPhase('polling');
    setGeneration((value) => value + 1);
  }

  return (
    <div className="card" aria-live="polite">
      <h2>Analysis running</h2>
      <p className="subtle">
        Scenario <code className="inline">{scenarioId}</code>
        {jobId ? (
          <>
            {' · '}job <code className="inline">{jobId}</code>
          </>
        ) : null}
      </p>
      <div className="status-line">
        {phase === 'polling' && <span className="spinner" aria-hidden="true" />}
        <StatusBadge status={status} />
        <span className="subtle">elapsed {elapsed}s · cold runs can take minutes</span>
      </div>
      {phase === 'fetch-error' && (
        <div className="banner error" role="alert">
          <strong>Polling failed</strong>
          {failure}
        </div>
      )}
      {phase === 'timed-out' && (
        <div className="banner warn" role="alert">
          <strong>Still running after {Math.round(timeoutMs / 1000)}s</strong>
          The run may still finish on the server. You can keep waiting or go back;
          the scenario stays stored either way.
        </div>
      )}
      <div className="actions">
        {phase === 'fetch-error' && (
          <button type="button" className="primary" onClick={retry}>
            Retry
          </button>
        )}
        {phase === 'timed-out' && (
          <button type="button" className="primary" onClick={retry}>
            Keep waiting
          </button>
        )}
        <button type="button" className="ghost" onClick={onStop}>
          Back to form
        </button>
      </div>
    </div>
  );
}
