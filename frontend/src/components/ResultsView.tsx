import { useState } from 'react';
import type { ReactNode } from 'react';
import type { ScenarioDetail } from '../api/client';
import { downloadMarkdown, reportToMarkdown } from '../api/export';
import type { FallbackPoint } from '../api/geo';
import { fallbackPoints, formatCoord } from '../api/geo';
import { toCardModel } from '../api/presenters';
import {
  droppedStatements,
  isPartialReport,
  modelStatementCounts,
  replacedStatements,
} from '../api/reportPresenters';
import type { GeoMarker } from './GeoMap';
import GeoMap from './GeoMap';
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

export interface ProblemGroup {
  code: string;
  items: string[];
}

/** Group `detail.problems` by their [code] prefix, codes sorted A–Z. */
export function groupProblems(problems: string[]): ProblemGroup[] {
  const groups = new Map<string, string[]>();
  for (const problem of problems) {
    const { code, text } = splitProblem(problem);
    const key = code ?? 'note';
    const items = groups.get(key) ?? [];
    items.push(code === null ? problem : text);
    groups.set(key, items);
  }
  return [...groups.entries()]
    .map(([code, items]) => ({ code, items }))
    .sort((a, b) => (a.code < b.code ? -1 : a.code > b.code ? 1 : 0));
}

export interface SnapshotLabel {
  label: string;
  capturedAt: string;
}

function formatSnapshotWhen(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

function formatPoint(lat: number, lon: number): string {
  return `${formatCoord(lat)}°, ${formatCoord(lon)}°`;
}

function reportBadge(report: ScenarioDetail['report']): ReactNode {
  if (!report) {
    return <span className="badge">No report</span>;
  }
  if (isPartialReport(report)) {
    const { model, total } = modelStatementCounts(report);
    return (
      <span className="badge">
        {`AI report: ${model}/${total} statements model-written (validated)`}
      </span>
    );
  }
  if (report.fallback) {
    return (
      <span className="badge" data-tone="warn">
        Platform fallback report
      </span>
    );
  }
  return <span className="badge">AI report accepted</span>;
}

/** One ochre marker per distinct used grid point (indicators often share one). */
function usedMarkers(points: FallbackPoint[]): GeoMarker[] {
  const byPosition = new Map<string, FallbackPoint[]>();
  for (const point of points) {
    const key = `${point.used.lat.toFixed(4)},${point.used.lon.toFixed(4)}`;
    const group = byPosition.get(key) ?? [];
    group.push(point);
    byPosition.set(key, group);
  }
  const markers: GeoMarker[] = [];
  for (const group of byPosition.values()) {
    const first = group[0];
    if (!first) {
      continue;
    }
    const lines = [`Used ${formatPoint(first.used.lat, first.used.lon)}`];
    if (first.distanceKm !== null) {
      lines.push(
        `${first.distanceKm.toFixed(1)} km from the requested point (backend value)`,
      );
    } else {
      lines.push('Distance not reported by the backend');
    }
    markers.push({
      id: `used-${group.map((point) => point.indicator).join('-')}`,
      position: [first.used.lat, first.used.lon],
      popupTitle: `Grid point used (${group.map((point) => point.indicator).join(', ')})`,
      popupLines: lines,
      tone: 'used',
    });
  }
  return markers;
}

const TABS = [
  { id: 'indicators', label: 'Indicators' },
  { id: 'evidence', label: 'Evidence & options' },
  { id: 'report', label: 'Report' },
  { id: 'provenance', label: 'Provenance & methods' },
] as const;

type TabId = (typeof TABS)[number]['id'];

function asCount(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/** Pipeline trace summary: model, stages, token usage, validator verdicts. */
function TraceMethods({ trace }: { trace: NonNullable<ScenarioDetail['trace']> }) {
  const versions = trace.component_versions ?? {};
  const usage = trace.usage ?? {};
  const llmCalls = asCount(usage.llm_calls);
  const prompt = asCount(usage.prompt_tokens);
  const completion = asCount(usage.completion_tokens);
  const stages = trace.stages ?? [];
  const verdicts = trace.validator_verdicts ?? [];
  return (
    <div>
      <h3>Run trace</h3>
      <dl className="facts">
        <div style={{ display: 'contents' }}>
          <dt>Model</dt>
          <dd>
            <code className="inline">{versions.model ?? 'not reported'}</code>
          </dd>
        </div>
        <div style={{ display: 'contents' }}>
          <dt>Outcome</dt>
          <dd>{trace.outcome === '' ? 'not reported' : trace.outcome}</dd>
        </div>
        <div style={{ display: 'contents' }}>
          <dt>Duration</dt>
          <dd>{Math.round(trace.duration_ms_total)} ms</dd>
        </div>
        <div style={{ display: 'contents' }}>
          <dt>Model calls</dt>
          <dd>{llmCalls === null ? 'none reported' : llmCalls}</dd>
        </div>
        {prompt !== null && completion !== null && (
          <div style={{ display: 'contents' }}>
            <dt>Tokens</dt>
            <dd>
              {prompt} prompt · {completion} completion
            </dd>
          </div>
        )}
      </dl>
      {stages.length > 0 && (
        <>
          <h3>Stages</h3>
          <ul className="tight">
            {stages.map((stage) => (
              <li key={stage.name}>
                <code className="inline">{stage.name}</code>: {stage.status} (
                {Math.round(stage.duration_ms)} ms)
                {stage.error_code ? ` [${stage.error_code}]` : ''}
              </li>
            ))}
          </ul>
        </>
      )}
      {verdicts.length > 0 && (
        <>
          <h3>Validator verdicts</h3>
          <ul className="tight">
            {verdicts.map((verdict) => (
              <li key={verdict}>
                <code className="inline">{verdict}</code>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
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
  const groups = groupProblems(detail.problems);
  const partial = detail.report ? isPartialReport(detail.report) : false;
  const replaced = detail.report ? replacedStatements(detail.report) : [];
  const dropped = detail.report ? droppedStatements(detail.report) : [];
  const changedCount = replaced.length + dropped.length;
  const changedLabel =
    changedCount === 1
      ? 'Why 1 statement is platform-written'
      : `Why ${changedCount} statements are platform-written`;
  const points = fallbackPoints(entries);
  const requested = { lat: detail.scenario.latitude, lon: detail.scenario.longitude };
  const markers: GeoMarker[] = [
    {
      id: 'requested',
      position: [requested.lat, requested.lon],
      popupTitle: 'Requested point',
      popupLines: [formatPoint(requested.lat, requested.lon)],
      tone: 'request',
    },
    ...usedMarkers(points),
  ];
  const [tab, setTab] = useState<TabId>('indicators');

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
        <div className="strip-sticky">
        <div className="status-line">
          <h2 style={{ margin: 0 }}>Results</h2>
          <StatusBadge status={detail.status} />
          {reportBadge(detail.report)}
        </div>
        <p className="subtle" data-testid="result-strip-meta">
          {formatPoint(requested.lat, requested.lon)}
          {' · '}scenario <code className="inline">{detail.scenario_id}</code>
          {' · '}target {detail.scenario.target_end_month}
          {', '}
          {detail.scenario.timescale_months}-month window · reference{' '}
          {detail.scenario.reference_start_year}–{detail.scenario.reference_end_year}
        </p>
        </div>
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
        {partial && changedCount > 0 && (
          <details className="problems">
            <summary>
              {changedLabel}
            </summary>
            <ul className="tight">
              {replaced.map(({ location, codes }) => (
                <li key={`replaced-${location}`}>
                  <code className="inline">{location}</code> — replaced ({codes.join(', ')})
                </li>
              ))}
              {dropped.map(({ location, codes }) => (
                <li key={`dropped-${location}`}>
                  <code className="inline">{location}</code> — dropped, no platform
                  counterpart ({codes.join(', ')})
                </li>
              ))}
            </ul>
          </details>
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

      <div className="tabs" role="tablist" aria-label="Result sections">
        {TABS.map((entry) => (
          <button
            key={entry.id}
            type="button"
            role="tab"
            id={`tab-${entry.id}`}
            aria-selected={tab === entry.id}
            aria-controls={`panel-${entry.id}`}
            onClick={() => setTab(entry.id)}
          >
            {entry.label}
          </button>
        ))}
      </div>
      {tab === 'indicators' && (
        <div role="tabpanel" id="panel-indicators" aria-labelledby="tab-indicators">
      <div className="card" id="location">
        <h2>Location</h2>
        <GeoMap
          mapLabel="Result location map"
          center={[requested.lat, requested.lon]}
          zoom={4}
          markers={markers}
          fitMarkers={points.length > 0}
        />
        <p className="meta">
          Teal marker: requested point ({formatPoint(requested.lat, requested.lon)}).
          {points.length > 0
            ? ' Ochre markers: grid points actually used (ERA5-Land land fallback).'
            : ' No land fallback was used in this run.'}
        </p>
        {points.length > 0 && (
          <ul className="tight">
            {points.map((point) => (
              <li key={point.indicator}>
                Grid point used for <code className="inline">{point.indicator}</code>:{' '}
                {formatPoint(point.used.lat, point.used.lon)}
                {point.distanceKm !== null
                  ? ` (${point.distanceKm.toFixed(1)} km from requested)`
                  : ' (distance not reported)'}
              </li>
            ))}
          </ul>
        )}
      </div>
      <div id="indicators">
        <h2 className="section-title">Indicators</h2>
        {entries.length > 0 ? (
          <div className="cards">
            {entries.map((entry) => (
              <IndicatorCard key={entry.indicator} model={toCardModel(entry)} />
            ))}
          </div>
        ) : (
          <div className="card">
            <p className="subtle">No indicators computed for this run.</p>
          </div>
        )}
      </div>
        </div>
      )}
      {tab === 'evidence' && (
        <div role="tabpanel" id="panel-evidence" aria-labelledby="tab-evidence">
      {/* No extra headings here: the panels below render their own, and
          heading names stay unique for tests and screen readers. */}
      <div id="recommendations">
        {detail.ranking ? (
          <RecommendationPanel ranking={detail.ranking} />
        ) : (
          <div className="card">
            <h2>Recommendations</h2>
            <p className="subtle">No ranking stored for this run.</p>
          </div>
        )}
      </div>
        </div>
      )}
      {tab === 'report' && (
        <div role="tabpanel" id="panel-report" aria-labelledby="tab-report">
      <div id="report">
        {detail.report ? (
          <ReportView report={detail.report} />
        ) : (
          <div className="card">
            <h2>Report</h2>
            <p className="subtle">No report stored for this run.</p>
          </div>
        )}
      </div>
        </div>
      )}
      {tab === 'provenance' && (
        <div role="tabpanel" id="panel-provenance" aria-labelledby="tab-provenance">
          <div className="card">
            <h2>Provenance & methods</h2>
        {detail.problems.length > 0 && (
          <details className="problems">
            <summary>
              {fallback ? 'Why this is the platform fallback' : 'Why this run failed'}{' '}
              · {detail.problems.length} problem{detail.problems.length === 1 ? '' : 's'}{' '}
              in {groups.length} group{groups.length === 1 ? '' : 's'}
            </summary>
            {groups.map((group) => (
              <div key={group.code}>
                <h4>
                  <code className="inline">{group.code}</code> × {group.items.length}
                </h4>
                <ul className="tight">
                  {group.items.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            ))}
          </details>
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
            {detail.trace ? (
              <TraceMethods trace={detail.trace} />
            ) : (
              <p className="subtle">No run trace stored for this run.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
