import type { ChartModel } from '../api/presenters';

interface ReferenceChartProps {
  model: ChartModel;
  referenceLabel: string | null;
}

/**
 * Target value against the reference summary (mean, and mean ± one standard
 * deviation when the backend reports it). The API returns reference summaries,
 * not per-year series, so this chart never implies per-year points.
 */
export default function ReferenceChart({ model, referenceLabel }: ReferenceChartProps) {
  const width = 320;
  const height = 118;
  const pad = 14;
  const lo = model.sd === null ? Math.min(model.target, model.mean) : model.mean - model.sd;
  const hi = model.sd === null ? Math.max(model.target, model.mean) : model.mean + model.sd;
  const span = hi - lo === 0 ? 1 : hi - lo;
  const padSpan = span * 0.18;
  const min = lo - padSpan;
  const max = hi + padSpan;
  const x = (value: number): number =>
    pad + ((value - min) / (max - min)) * (width - 2 * pad);

  const bandY = 44;
  const bandH = 18;
  const targetX = x(model.target);
  const meanX = x(model.mean);
  const loX = model.sd === null ? meanX : x(model.mean - model.sd);
  const hiX = model.sd === null ? meanX : x(model.mean + model.sd);

  const label = `Target ${model.targetLabel} ${model.target} ${model.unit}; reference mean ${model.mean} ${model.unit} over ${model.nYears} years`;
  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label}>
        <title>{label}</title>
        <rect
          x={Math.min(loX, hiX)}
          y={bandY}
          width={Math.max(2, Math.abs(hiX - loX))}
          height={bandH}
          fill="#e4e9ef"
          rx={3}
        />
        <line x1={meanX} y1={bandY - 6} x2={meanX} y2={bandY + bandH + 6} stroke="#1a56db" strokeWidth={2.5} />
        <circle cx={targetX} cy={bandY + bandH / 2} r={6} fill="#1b2430" />
        <text x={targetX} y={bandY - 12} textAnchor="middle" fontSize={11} fill="#1b2430">
          {model.targetLabel}: {model.target} {model.unit}
        </text>
        <text x={pad} y={height - 26} fontSize={10.5} fill="#55606e">
          ref mean {model.mean} {model.unit}
        </text>
        <text x={width - pad} y={height - 26} textAnchor="end" fontSize={10.5} fill="#55606e">
          {model.nYears} years
          {model.percentilePct === null ? '' : ` · ${model.percentilePct.toFixed(1)}th pct`}
        </text>
        <text x={pad} y={height - 10} fontSize={10.5} fill="#55606e">
          {model.sd === null ? 'No reference spread reported' : 'Band: reference mean ± 1 std dev'}
        </text>
      </svg>
      <p className="subtle" style={{ margin: '2px 0 0' }}>
        {referenceLabel ?? 'Reference period not reported'} · per-year values are not
        returned by the API, so only the summary is drawn.
      </p>
    </div>
  );
}
