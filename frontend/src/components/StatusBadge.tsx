const TONE: Record<string, 'ok' | 'warn' | 'bad' | undefined> = {
  complete: 'ok',
  ok: 'ok',
  succeeded: 'ok',
  partial: 'warn',
  undefined: 'warn',
  queued: undefined,
  running: undefined,
  skipped: undefined,
  failed: 'bad',
  timed_out: 'bad',
};

const LABEL: Record<string, string> = {
  complete: 'Complete',
  ok: 'Computed',
  succeeded: 'Succeeded',
  partial: 'Partial',
  undefined: 'Indeterminate',
  queued: 'Queued',
  running: 'Running',
  skipped: 'Skipped',
  failed: 'Failed',
  timed_out: 'Timed out',
};

export default function StatusBadge({ status }: { status: string }) {
  const tone = TONE[status];
  return (
    <span className="badge" data-tone={tone}>
      {LABEL[status] ?? status}
    </span>
  );
}
