import type { ScenarioDetail } from '../api/client';
import { downloadMarkdown, reportToMarkdown } from '../api/export';
import { toCardModel } from '../api/presenters';
import IndicatorCard from './IndicatorCard';
import RecommendationPanel from './RecommendationPanel';
import ReportView from './ReportView';
import StatusBadge from './StatusBadge';

function splitProblem(problem: string): { code: string | null; text: string } {
  const match = /^\[([^\]]+)\]\s*(.*)$/.exec(problem);
  if (!match) {
    return { code: null, text: problem };
  }
  return { code: match[1] ?? null, text: match[2] ?? '' };
}

export interface SnapshotLabel {
  label: string;
  capturedAt: string;
}

function formatSnapshotWhen(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

export default function ResultsView({
  detail,
  onNew,
  snapshot,
}: {
  detail: ScenarioDetail;
  onNew: () => void;
  snapshot?: SnapshotLabel;
}) {
  const entries = detail.bundle?.entries ?? [];
  const fallback = detail.report?.fallback === true;

  return (
    <div>
      <div className="card">
        {snapshot && (
          <div className="banner warn" role="note">
            <strong>Cached real-data snapshot</strong>
            {snapshot.label} — captured {formatSnapshotWhen(snapshot.capturedAt)}.
            Stored results, not a live run.
          </div>
        )}
        <div className="status-line">
          <h2 style={{ margin: 0 }}>Results</h2>
          <StatusBadge status={detail.status} />
        </div>
        <p className="subtle">
          Scenario <code className="inline">{detail.scenario_id}</code>
          {' · '}target {detail.scenario.target_end_month}
          {', '}
          {detail.scenario.timescale_months}-month window · reference{' '}
          {detail.scenario.reference_start_year}–{detail.scenario.reference_end_year}
        </p>
        {fallback && (
          <div className="banner warn" role="alert">
            <strong>Deterministic fallback report</strong>
            The model draft was rejected or unavailable, so this report contains
            only deterministic values with no AI narrative.
          </div>
        )}
        {detail.status === 'failed' && (
          <div className="banner error" role="alert">
            <strong>This run failed</strong>
            No report could be grounded. The problems below explain why; missing
            values are shown as missing, never filled in.
          </div>
        )}
        {detail.problems.length > 0 && (
          <>
            <h3>Problems</h3>
            <ul className="tight">
              {detail.problems.map((problem) => {
                const { code, text } = splitProblem(problem);
                return (
                  <li key={problem}>
                    {code ? <code className="inline">{code}</code> : null} {text}
                  </li>
                );
              })}
            </ul>
          </>
        )}
        {detail.warnings.length > 0 && (
          <>
            <h3>Warnings</h3>
            <ul className="tight">
              {detail.warnings.map((warning) => {
                const { code, text } = splitProblem(warning);
                return (
                  <li key={warning}>
                    {code ? <code className="inline">{code}</code> : null} {text}
                  </li>
                );
              })}
            </ul>
          </>
        )}
        <div className="actions">
          <button type="button" className="ghost" onClick={onNew}>
            New scenario
          </button>
          {detail.report && (
            <button
              type="button"
              className="ghost"
              onClick={() =>
                downloadMarkdown(
                  `scenario-${detail.scenario_id}-report.md`,
                  reportToMarkdown(detail),
                )
              }
            >
              Export report (Markdown)
            </button>
          )}
        </div>
      </div>

      {entries.length > 0 && (
        <div className="cards">
          {entries.map((entry) => (
            <IndicatorCard key={entry.indicator} model={toCardModel(entry)} />
          ))}
        </div>
      )}

      {detail.ranking ? (
        <RecommendationPanel ranking={detail.ranking} />
      ) : (
        <div className="card">
          <h2>Recommendations</h2>
          <p className="subtle">No ranking stored for this run.</p>
        </div>
      )}

      {detail.report ? (
        <ReportView report={detail.report} />
      ) : (
        <div className="card">
          <h2>Report</h2>
          <p className="subtle">No report stored for this run.</p>
        </div>
      )}
    </div>
  );
}
