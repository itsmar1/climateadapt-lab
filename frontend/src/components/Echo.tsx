import { echoDisplay } from '../api/reportPresenters';

/** Benefit/cost/risk echo: literal "unknown" renders as an Unknown badge. */
export default function Echo({ label, value }: { label: string; value: string }) {
  const shown = echoDisplay(value);
  return (
    <p className="meta">
      {label}:{' '}
      {shown.unknown ? <span className="badge">Unknown</span> : <span>{shown.text}</span>}
    </p>
  );
}
