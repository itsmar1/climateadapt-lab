interface EvidenceViewProps {
  /** DOM anchor id for statement-chip scrolling. */
  anchor: string;
  /** Short label: E-number for report evidence, doc reference for ranking. */
  label: string;
  chunkId?: string;
  docId: string;
  /**
   * Full formatted citation (carries title, authors, year, publisher). Shown
   * verbatim — never parsed — because the payload has no separate fields.
   */
  citation: string;
  /** Page locator (carries PDF page and printed page when available). */
  pages: string;
  /** Ranking-only topic locator (not a quote, never a claim). */
  locator?: string;
  landingUrl: string;
  license: string;
  licenseStatus: string;
  unverifiedFields?: string[];
}

/**
 * One cited source. Title/authors/year travel inside the formatted citation
 * string (the API exposes no separate fields and this UI invents none);
 * everything else renders from structured fields.
 */
export default function EvidenceView({
  anchor,
  label,
  chunkId,
  docId,
  citation,
  pages,
  locator,
  landingUrl,
  license,
  licenseStatus,
  unverifiedFields = [],
}: EvidenceViewProps) {
  const metadataUnverified =
    licenseStatus === 'unverified' || unverifiedFields.length > 0;
  return (
    <div className="evidence" id={anchor}>
      <h4>{label}</h4>
      <p className="citation">{citation}</p>
      <p className="meta">
        {chunkId ? (
          <>
            Chunk <code className="inline">{chunkId}</code>
            {' · '}
          </>
        ) : null}
        Document <code className="inline">{docId}</code>
        {' · '}
        {pages}
      </p>
      {locator && <p className="meta">Topic locator: {locator}</p>}
      <p className="meta">
        Landing page:{' '}
        <a href={landingUrl} target="_blank" rel="noreferrer">
          {landingUrl}
        </a>
      </p>
      <p className="meta">
        Licence: {license} <span className="badge">licence {licenseStatus}</span>
      </p>
      {metadataUnverified && (
        <div className="banner warn" role="note">
          <strong>Metadata unverified</strong>
          {unverifiedFields.length > 0
            ? `These manifest fields could not be verified: ${unverifiedFields.join(', ')}.`
            : 'The licence status is unverified.'}
        </div>
      )}
    </div>
  );
}
