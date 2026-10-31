import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import RecommendationPanel from './RecommendationPanel';
import {
  evidenceReferenceFixture,
  rankedOptionFixture,
  rankingFixtureFull,
} from '../test/fixtures';

describe('RecommendationPanel', () => {
  it('shows scores with the full breakdown, unknowns, and evidence', () => {
    render(<RecommendationPanel ranking={rankingFixtureFull()} />);
    expect(screen.getByText('Computed by the platform')).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: /Deficit irrigation/ }),
    ).toBeInTheDocument();
    expect(screen.getAllByText('1.000')).toHaveLength(4);
    expect(screen.getAllByText('0.500')).toHaveLength(2);
    expect(screen.getByText('evidence_strength')).toBeInTheDocument();
    expect(screen.getByText(/Evidence strength: multi_source/)).toBeInTheDocument();
    expect(screen.getByText('chirps_spi')).toBeInTheDocument();
    expect(screen.getByText('Unknown: soil type at the farm')).toBeInTheDocument();
    expect(screen.getAllByText('Unknown')).toHaveLength(3);
    expect(
      screen.getByText(/Topic locator: yield response factors for wheat/),
    ).toBeInTheDocument();
    expect(screen.getByText('Supplemental irrigation of rainfed crops')).toBeInTheDocument();
    expect(screen.getAllByText('needs_evidence')).toHaveLength(2);
    expect(screen.getByText(/candidate manuals are not ingested/)).toBeInTheDocument();
    expect(screen.getByText('Synthetic ranking limitation.')).toBeInTheDocument();
  });

  it('renders empty states honestly with limitations always visible', () => {
    render(
      <RecommendationPanel
        ranking={{ ...rankingFixtureFull(), ranked: [], excluded: [] }}
      />,
    );
    expect(screen.getByText('No eligible options for this scenario.')).toBeInTheDocument();
    expect(screen.getByText('Nothing was excluded.')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Limitations' })).toBeInTheDocument();
  });

  it('flags unverified ranking metadata', () => {
    render(
      <RecommendationPanel
        ranking={{
          ...rankingFixtureFull(),
          ranked: [
            rankedOptionFixture({
              evidence: [evidenceReferenceFixture({ unverified_fields: ['year'] })],
            }),
          ],
        }}
      />,
    );
    expect(screen.getByText('Metadata unverified')).toBeInTheDocument();
    expect(screen.getByText(/year/)).toBeInTheDocument();
  });
});
