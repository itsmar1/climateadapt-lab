import type { Statement } from '../api/client';
import { evidenceChips, formatPlatformNumber } from '../api/reportPresenters';

interface StatementViewProps {
  statement: Statement;
  /** Chunk-id → E-number map from the report's evidence list. */
  evidenceIndex: Map<string, number>;
}

/**
 * One traceable claim: prose plus evidence chips (buttons, not hash links —
 * hash links would fight the app's hash router), deterministic-output refs,
 * and platform-copied numbers. Numerals in prose are never authoritative on
 * their own; the chips carry the traced values.
 */
export default function StatementView({ statement, evidenceIndex }: StatementViewProps) {
  function scrollToEvidence(n: number): void {
    document.getElementById(`ev-${n}`)?.scrollIntoView?.();
  }

  const chips = evidenceChips(statement, evidenceIndex);
  const toolOutputIds = statement.tool_output_ids ?? [];
  const numbers = statement.numbers ?? [];
  return (
    <div className="statement">
      <p style={{ margin: '0 0 6px' }}>{statement.text}</p>
      {chips.length > 0 && (
        <p className="meta">
          Evidence:{' '}
          {chips.map((chip) =>
            chip.resolved && chip.n !== null ? (
              <button
                key={chip.chunkId}
                type="button"
                className="chip"
                title={chip.chunkId}
                onClick={() => chip.n !== null && scrollToEvidence(chip.n)}
              >
                E{chip.n}
              </button>
            ) : (
              <span key={chip.chunkId} className="chip chip-bad" title={chip.chunkId}>
                unresolved evidence
              </span>
            ),
          )}
        </p>
      )}
      {toolOutputIds.length > 0 && (
        <p className="meta">
          Deterministic outputs:{' '}
          {toolOutputIds.map((id) => (
            <code key={id} className="inline">
              {id}
            </code>
          ))}
        </p>
      )}
      {numbers.length > 0 && (
        <div className="meta">
          <p style={{ margin: '0 0 4px' }}>Platform values (copied, not written):</p>
          <ul className="tight">
            {numbers.map((number, position) => (
              <li key={`${number.tool_output_id}.${number.field}.${position}`}>
                <strong>
                  {formatPlatformNumber(number.value)}
                  {number.unit ? ` ${number.unit}` : ''}
                </strong>{' '}
                from{' '}
                <code className="inline">
                  {number.tool_output_id}.{number.field}
                </code>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
