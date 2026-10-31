import type { ScenarioDetail } from '../api/client';
import { toCardModel } from '../api/presenters';
import IndicatorCard from './IndicatorCard';
import StatusBadge from './StatusBadge';

function splitProblem(problem: string): { code: string | null; text: string } {
  const match = /^\[([^\]]+)\]\s*(.*)$/.exec(problem);
  if (!match) {
    return { code: null, text: problem };
  }
  return { code: match[1] ?? null, text: match[2] ?? '' };
}

export default function ResultsView({
  detail,
  onNew,
}: {
  detail: ScenarioDetail;
  onNew: () => void;
}) {
  const entries = detail.bundle?.entries ?? [];
  const fallback = detail.report?.fallback === true;

  return (
    <div>
      <div className="card">
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
        </div>
      </div>

      {entries.length > 0 && (
        <div className="cards">
          {entries.map((entry) => (
            <IndicatorCard key={entry.indicator} model={toCardModel(entry)} />
          ))}
        </div>
      )}
    </div>
  );
}
