import type { Report } from '../api/client';
import { evidenceIndex, isPlatformReport } from '../api/reportPresenters';
import Echo from './Echo';
import EvidenceView from './EvidenceView';
import StatementView from './StatementView';

export default function ReportView({ report }: { report: Report }) {
  const platform = isPlatformReport(report);
  const index = evidenceIndex(report.evidence ?? []);
  const rankedRecs = report.ranked_recommendations ?? [];
  const excludedOpts = report.excluded_options ?? [];
  const evidence = report.evidence ?? [];
  const assumptions = report.assumptions ?? [];
  return (
    <div className="card">
      <div className="status-line">
        <h2 style={{ margin: 0 }}>Report</h2>
        {platform ? (
          <span className="badge">Computed by the platform</span>
        ) : (
          <span className="badge" data-tone="warn">
            AI-generated narrative
          </span>
        )}
      </div>
      <p className="subtle">
        Generator <code className="inline">{report.generator}</code>
        {' · '}schema v{report.schema_version}
        {platform
          ? ' · fixed templates, no model prose.'
          : ' · validated against retrieved sources; numbers shown are platform values.'}
      </p>
      {report.fallback && report.fallback_note && (
        <div className="banner warn" role="note">
          <strong>Deterministic fallback</strong>
          {report.fallback_note}
        </div>
      )}

      <h3>Summary</h3>
      <StatementView statement={report.summary} evidenceIndex={index} />

      <h3>Environmental findings</h3>
      <ol className="findings">
        {report.environmental_findings.map((finding, position) => (
          <li key={position}>
            <StatementView statement={finding} evidenceIndex={index} />
          </li>
        ))}
      </ol>

      <h3>Ranked recommendations</h3>
      {rankedRecs.length === 0 && <p className="subtle">No ranked recommendations.</p>}
      {rankedRecs.map((rec) => (
        <div key={rec.intervention_id} className="sub-block">
          <h4>
            {rec.name} <code className="inline">{rec.intervention_id}</code>
          </h4>
          <Echo label="Benefit" value={rec.benefit} />
          <Echo label="Cost" value={rec.cost} />
          <Echo label="Risk" value={rec.risk} />
          <StatementView statement={rec.narrative} evidenceIndex={index} />
        </div>
      ))}

      <h3>Excluded options</h3>
      {excludedOpts.length === 0 && <p className="subtle">No excluded options.</p>}
      {excludedOpts.map((excluded) => (
        <div key={excluded.intervention_id} className="sub-block">
          <h4>
            {excluded.name} <code className="inline">{excluded.intervention_id}</code>
          </h4>
          <p className="meta">
            Reason codes:{' '}
            {excluded.reason_codes.map((code) => (
              <code key={code} className="inline">
                {code}
              </code>
            ))}
          </p>
          <StatementView statement={excluded.narrative} evidenceIndex={index} />
        </div>
      ))}

      <h3>Evidence</h3>
      {evidence.length === 0 && <p className="subtle">No cited evidence.</p>}
      {evidence.map((item, position) => (
        <EvidenceView
          key={item.chunk_id}
          anchor={`ev-${position + 1}`}
          label={`E${position + 1}`}
          chunkId={item.chunk_id}
          docId={item.doc_id}
          citation={item.citation}
          pages={item.pages}
          landingUrl={item.landing_url}
          license={item.license}
          licenseStatus={item.license_status}
        />
      ))}

      <h3>Limitations</h3>
      <ul className="tight">
        {report.limitations.map((limitation) => (
          <li key={limitation}>{limitation}</li>
        ))}
      </ul>

      {assumptions.length > 0 && (
        <>
          <h3>Assumptions</h3>
          <ul className="tight">
            {assumptions.map((assumption) => (
              <li key={assumption}>{assumption}</li>
            ))}
          </ul>
        </>
      )}

      <h3>Data coverage</h3>
      <StatementView statement={report.data_coverage} evidenceIndex={index} />

      <h3>Provenance</h3>
      <p className="meta">
        {report.provenance_refs.map((ref) => (
          <code key={ref} className="inline">
            {ref}
          </code>
        ))}
      </p>
    </div>
  );
}
