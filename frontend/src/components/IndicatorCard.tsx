import type { IndicatorCardModel } from '../api/presenters';
import ReferenceChart from './ReferenceChart';
import StatusBadge from './StatusBadge';

export default function IndicatorCard({ model }: { model: IndicatorCardModel }) {
  return (
    <div className="card" data-testid={`indicator-${model.key}`}>
      <div className="card-head">
        <h3>{model.title}</h3>
        <StatusBadge status={model.status} />
      </div>

      {model.errorMessage && (
        <div className="banner error" role="alert">
          <strong>
            Not computed{model.errorType ? ` (${model.errorType})` : ''}
          </strong>
          {model.errorMessage}
        </div>
      )}

      {model.headlines.length > 0 && (
        <dl className="facts">
          {model.headlines.map((row) => (
            <div key={row.label} style={{ display: 'contents' }}>
              <dt>{row.label}</dt>
              <dd>{row.value}</dd>
            </div>
          ))}
        </dl>
      )}

      {model.warnings.length > 0 && (
        <div className="banner warn">
          <strong>Warnings</strong>
          <ul className="tight">
            {model.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      )}

      {model.chart && (
        <ReferenceChart model={model.chart} referenceLabel={model.reference} />
      )}

      <p className="meta">
        <strong>Reference:</strong> {model.reference ?? 'not reported'}
      </p>
      <p className="meta">
        <strong>Source:</strong> {model.dataSource} · {model.coverage}
      </p>
      <p className="meta">
        <strong>Requested point:</strong> {model.requestedPoint}
        {model.usedPoint ? (
          <>
            {' · '}used <strong>{model.usedPoint}</strong>
          </>
        ) : null}
      </p>

      {model.limitations.length > 0 && (
        <>
          <h3>Limitations</h3>
          <ul className="tight">
            {model.limitations.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      )}

      {(model.citation ?? model.doi ?? model.license) && (
        <>
          <h3>Provenance</h3>
          {model.citation && <p className="meta">{model.citation}</p>}
          {model.doi && (
            <p className="meta">
              DOI:{' '}
              <a
                href={`https://doi.org/${model.doi}`}
                target="_blank"
                rel="noreferrer"
              >
                {model.doi}
              </a>
            </p>
          )}
          {model.license && <p className="meta">Licence: {model.license}</p>}
        </>
      )}
    </div>
  );
}
