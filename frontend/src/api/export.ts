/**
 * Markdown export of a scenario report. Pure function of the stored detail:
 * every section the report page shows, with citations and limitations.
 * Model-written text is labelled as such; platform values stay attributed.
 */

import type {
  RankedOption,
  RankingExcludedOption,
  Report,
  ScenarioDetail,
  Statement,
} from './client';
import {
  droppedStatements,
  echoDisplay,
  evidenceIndex,
  formatPlatformNumber,
  formatScore,
  isPartialReport,
  isPlatformReport,
  modelStatementCounts,
  replacedStatements,
  scoreBreakdown,
  scoreInputsOf,
  statementOrigin,
} from './reportPresenters';

function statementRefs(
  statement: Statement,
  index: Map<string, number>,
  lines: string[],
): void {
  const evidenceIds = statement.evidence_ids ?? [];
  if (evidenceIds.length > 0) {
    const refs = evidenceIds.map((chunkId) => {
      const n = index.get(chunkId);
      return n === undefined ? `unresolved:${chunkId}` : `E${n}`;
    });
    lines.push(`Evidence: ${refs.join(', ')}.`);
  }
  const toolOutputIds = statement.tool_output_ids ?? [];
  if (toolOutputIds.length > 0) {
    lines.push(`Deterministic outputs: ${toolOutputIds.join(', ')}.`);
  }
  for (const number of statement.numbers ?? []) {
    const unit = number.unit ? ` ${number.unit}` : '';
    lines.push(
      `- Platform value: ${formatPlatformNumber(number.value)}${unit} ` +
        `(from ${number.tool_output_id}.${number.field}).`,
    );
  }
}

function statementBlock(
  heading: string | null,
  statement: Statement,
  index: Map<string, number>,
  lines: string[],
): void {
  if (heading) {
    lines.push(`### ${heading}`, '');
  }
  lines.push(statement.text, '');
  statementRefs(statement, index, lines);
  lines.push('');
}

function rankedSection(detail: ScenarioDetail, report: Report, lines: string[]): void {
  lines.push('## Ranked recommendations', '');
  const rankedRecs = report.ranked_recommendations ?? [];
  if (rankedRecs.length === 0) {
    lines.push('No ranked recommendations.', '');
    return;
  }
  const byId = new Map<string, RankedOption>();
  for (const option of detail.ranking?.ranked ?? []) {
    byId.set(option.intervention_id, option);
  }
  for (const [position, rec] of rankedRecs.entries()) {
    lines.push(`### ${rec.name} (\`${rec.intervention_id}\`)`, '');
    const ranked = byId.get(rec.intervention_id);
    if (ranked) {
      lines.push(
        `Deterministic score: ${formatScore(ranked.score_total)} ` +
          `(category ${ranked.category}).`,
        '',
        '| Component | Value | Weight | Contribution |',
        '| --- | --- | --- | --- |',
      );
      for (const row of scoreBreakdown(ranked)) {
        lines.push(
          `| ${row.component} | ${formatScore(row.value)} | ${formatScore(row.weight)} ` +
            `| ${formatScore(row.contribution)} |`,
        );
      }
      lines.push('');
      const inputs = scoreInputsOf(ranked);
      lines.push(
        `Evidence strength: level ${String(inputs.evidenceLevel)} ` +
          `(${inputs.evidenceDocIds.join(', ') || 'no documents'}).`,
        '',
      );
      if (ranked.unknowns.length > 0) {
        lines.push('Unknowns (kept out of the score):', '');
        for (const unknown of ranked.unknowns) {
          lines.push(`- Unknown: ${unknown}`);
        }
        lines.push('');
      }
    } else {
      lines.push('No deterministic ranking entry (not in the stored ranking).', '');
    }
    for (const [label, echo] of [
      ['Benefit', rec.benefit],
      ['Cost', rec.cost],
      ['Risk', rec.risk],
    ] as const) {
      const shown = echoDisplay(echo);
      lines.push(`- ${label}: ${shown.text}`);
    }
    lines.push('', rec.narrative.text, '');
    statementRefs(rec.narrative, evidenceIndex(report.evidence ?? []), lines);
    pushOrigin(report, `ranked_recommendations[${position}]`, lines);
    lines.push('');
  }
}

function excludedSection(detail: ScenarioDetail, report: Report, lines: string[]): void {
  lines.push('## Excluded options', '');
  const excludedOpts = report.excluded_options ?? [];
  if (excludedOpts.length === 0) {
    lines.push('No excluded options.', '');
    return;
  }
  const byId = new Map<string, RankingExcludedOption>();
  for (const option of detail.ranking?.excluded ?? []) {
    byId.set(option.intervention_id, option);
  }
  for (const [position, excluded] of excludedOpts.entries()) {
    lines.push(`### ${excluded.name} (\`${excluded.intervention_id}\`)`, '');
    lines.push(`Reason codes: ${excluded.reason_codes.join(', ')}.`, '');
    const ranking = byId.get(excluded.intervention_id);
    if (ranking) {
      lines.push(`Evidence status: ${ranking.evidence_status}.`, '');
      for (const reason of ranking.reasons) {
        lines.push(`- ${reason.code}: ${reason.message}`);
      }
      lines.push('');
    }
    lines.push(excluded.narrative.text, '');
    statementRefs(excluded.narrative, evidenceIndex(report.evidence ?? []), lines);
    pushOrigin(report, `excluded_options[${position}]`, lines);
    lines.push('');
  }
}

function originLine(origin: 'model' | 'platform' | null): string | null {
  if (origin === null) {
    return null;
  }
  return origin === 'model' ? '*Origin: AI-written.*' : '*Origin: platform-written.*';
}

/** Append one statement's origin marker (mixed reports only, else nothing). */
function pushOrigin(report: Report, location: string, lines: string[]): void {
  if (!isPartialReport(report)) {
    return;
  }
  const line = originLine(statementOrigin(report, location));
  if (line) {
    lines.push(line, '');
  }
}

/** Render the full report (plus linked ranking context) as Markdown. */
export function reportToMarkdown(detail: ScenarioDetail): string {
  const report = detail.report;
  const lines: string[] = [
    `# ClimateAdapt Lab report — scenario \`${detail.scenario_id}\``,
    '',
    `Status: ${detail.status}. Target ${detail.scenario.target_end_month}, ` +
      `${detail.scenario.timescale_months}-month window, reference ` +
      `${detail.scenario.reference_start_year}–${detail.scenario.reference_end_year}.`,
    '',
  ];
  if (!report) {
    lines.push('No report was produced for this run.', '');
    return lines.join('\n');
  }
  const platform = isPlatformReport(report);
  const partial = isPartialReport(report);
  const { model, total } = modelStatementCounts(report);
  lines.push(
    partial
      ? `Mixed report: ${model} of ${total} statements model-written ` +
        `(generator \`${report.generator}\`), validated; platform statements marked.`
      : platform
      ? `Computed by the platform (generator \`${report.generator}\`).`
      : `AI-generated narrative (generator \`${report.generator}\`), validated ` +
        'against retrieved sources; numbers below are platform values.',
    '',
  );
  if (report.fallback && report.fallback_note) {
    lines.push(`Deterministic fallback: ${report.fallback_note}`, '');
  }
  if (partial) {
    const replaced = replacedStatements(report);
    const dropped = droppedStatements(report);
    if (replaced.length + dropped.length > 0) {
      lines.push('## Statement origins', '');
      for (const { location, codes } of replaced) {
        lines.push(`- ${location}: replaced (${codes.join(', ')}).`);
      }
      for (const { location, codes } of dropped) {
        lines.push(`- ${location}: dropped, no platform counterpart (${codes.join(', ')}).`);
      }
      lines.push('');
    }
  }
  const index = evidenceIndex(report.evidence ?? []);

  lines.push('## Summary', '', report.summary.text, '');
  statementRefs(report.summary, index, lines);
  pushOrigin(report, 'summary', lines);
  lines.push('');

  lines.push('## Environmental findings', '');
  report.environmental_findings.forEach((finding, position) => {
    statementBlock(`Finding ${position + 1}`, finding, index, lines);
    pushOrigin(report, `environmental_findings[${position}]`, lines);
  });

  rankedSection(detail, report, lines);
  excludedSection(detail, report, lines);

  lines.push('## Evidence', '');
  const evidence = report.evidence ?? [];
  if (evidence.length === 0) {
    lines.push('No cited evidence.', '');
  }
  evidence.forEach((item, position) => {
    lines.push(
      `### E${position + 1} — \`${item.chunk_id}\``,
      '',
      item.citation,
      '',
      `Document: \`${item.doc_id}\`. ${item.pages}.`,
      '',
      `Landing page: ${item.landing_url}`,
      '',
      `Licence: ${item.license} (status: ${item.license_status}).`,
      '',
    );
  });

  lines.push('## Limitations', '');
  for (const [position, limitation] of report.limitations.entries()) {
    const limitationMarker = originLine(
      isPartialReport(report) ? statementOrigin(report, `limitations[${position}]`) : null,
    );
    lines.push(`- ${limitation}${limitationMarker ? ` ${limitationMarker}` : ''}`);
  }
  lines.push('');

  const assumptions = report.assumptions ?? [];
  if (assumptions.length > 0) {
    lines.push('## Assumptions', '');
    for (const [position, assumption] of assumptions.entries()) {
      const assumptionMarker = originLine(
        isPartialReport(report) ? statementOrigin(report, `assumptions[${position}]`) : null,
      );
      lines.push(`- ${assumption}${assumptionMarker ? ` ${assumptionMarker}` : ''}`);
    }
    lines.push('');
  }

  lines.push('## Data coverage', '');
  lines.push(report.data_coverage.text, '');
  statementRefs(report.data_coverage, index, lines);
  pushOrigin(report, 'data_coverage', lines);
  lines.push('');

  lines.push('## Provenance', '');
  lines.push(`References: ${report.provenance_refs.join(', ')}.`, '');
  return lines.join('\n');
}

/** Trigger a browser download of exported text (thin DOM glue, untested). */
export function downloadMarkdown(filename: string, text: string): void {
  const blob = new Blob([text], { type: 'text/markdown' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
