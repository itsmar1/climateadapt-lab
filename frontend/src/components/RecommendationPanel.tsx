import type { RecommendationResponse } from '../api/client';
import {
  evidenceLevelName,
  formatScore,
  scoreBreakdown,
  scoreInputsOf,
} from '../api/reportPresenters';
import Echo from './Echo';
import EvidenceView from './EvidenceView';

/**
 * Deterministic ranking, computed by the platform (no model text here).
 * Scores show the full component breakdown; unknowns are listed explicitly
 * and never enter the arithmetic.
 */
export default function RecommendationPanel({
  ranking,
}: {
  ranking: RecommendationResponse;
}) {
  return (
    <div className="card">
      <div className="status-line">
        <h2 style={{ margin: 0 }}>Recommendations</h2>
        <span className="badge">Computed by the platform</span>
      </div>
      <p className="subtle">Catalog v{ranking.catalog_version} · deterministic ranking.</p>

      <h3>Ranked options</h3>
      {ranking.ranked.length === 0 && (
        <p className="subtle">No eligible options for this scenario.</p>
      )}
      {ranking.ranked.map((option, position) => {
        const inputs = scoreInputsOf(option);
        return (
          <div key={option.intervention_id} className="sub-block">
            <h4>
              {position + 1}. {option.name}{' '}
              <code className="inline">{option.intervention_id}</code>
            </h4>
            <p className="meta">
              Category {option.category} · deterministic score{' '}
              <strong>{formatScore(option.score_total)}</strong>
            </p>
            <table className="score">
              <caption>Score breakdown (value × weight = contribution)</caption>
              <thead>
                <tr>
                  <th scope="col">Component</th>
                  <th scope="col">Value</th>
                  <th scope="col">Weight</th>
                  <th scope="col">Contribution</th>
                </tr>
              </thead>
              <tbody>
                {scoreBreakdown(option).map((row) => (
                  <tr key={row.component}>
                    <th scope="row">{row.component}</th>
                    <td>{formatScore(row.value)}</td>
                    <td>{formatScore(row.weight)}</td>
                    <td>{formatScore(row.contribution)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="meta">
              Evidence strength: {evidenceLevelName(inputs.evidenceLevel)}
              {inputs.evidenceDocIds.length > 0
                ? ` (${inputs.evidenceDocIds.join(', ')})`
                : ' (no documents)'}
              .
            </p>
            {inputs.indicatorStatuses.length > 0 && (
              <p className="meta">
                Indicator availability:{' '}
                {inputs.indicatorStatuses.map((entry) => (
                  <span key={entry.indicator}>
                    <code className="inline">{entry.indicator}</code> {entry.status};{' '}
                  </span>
                ))}
              </p>
            )}
            {option.unknowns.length > 0 && (
              <>
                <p className="meta" style={{ marginBottom: 0 }}>
                  Unknowns (kept out of the score):
                </p>
                <ul className="tight">
                  {option.unknowns.map((unknown) => (
                    <li key={unknown}>Unknown: {unknown}</li>
                  ))}
                </ul>
              </>
            )}
            <Echo label="Benefit" value={option.benefit} />
            <Echo label="Cost" value={option.cost} />
            <Echo label="Risk" value={option.risk} />
            {option.evidence.map((ref, refPosition) => (
              <EvidenceView
                key={`${ref.doc_id}-${ref.pdf_page}`}
                anchor={`ev-rank-${option.intervention_id}-${refPosition + 1}`}
                label={`Source ${refPosition + 1}`}
                docId={ref.doc_id}
                citation={ref.citation}
                pages={`PDF p. ${ref.pdf_page}`}
                locator={ref.reference}
                landingUrl={ref.landing_url}
                license={ref.license}
                licenseStatus={ref.license_status}
                unverifiedFields={ref.unverified_fields}
              />
            ))}
          </div>
        );
      })}

      <h3>Excluded options</h3>
      {ranking.excluded.length === 0 && (
        <p className="subtle">Nothing was excluded.</p>
      )}
      {ranking.excluded.map((excluded) => (
        <div key={excluded.intervention_id} className="sub-block">
          <h4>
            {excluded.name} <code className="inline">{excluded.intervention_id}</code>
          </h4>
          <p className="meta">
            Evidence status: <code className="inline">{excluded.evidence_status}</code>
          </p>
          <ul className="tight">
            {excluded.reasons.map((reason) => (
              <li key={reason.code}>
                <code className="inline">{reason.code}</code> {reason.message}
              </li>
            ))}
          </ul>
        </div>
      ))}

      {ranking.warnings.length > 0 && (
        <>
          <h3>Warnings</h3>
          <ul className="tight">
            {ranking.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </>
      )}

      <h3>Limitations</h3>
      <ul className="tight">
        {ranking.limitations.map((limitation) => (
          <li key={limitation}>{limitation}</li>
        ))}
      </ul>
    </div>
  );
}
