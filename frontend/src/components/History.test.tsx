import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import HistoryView from './HistoryView';
import {
  mockFetch,
  scenarioDetailFixture,
  scenarioListFixture,
  scenarioSummaryFixture,
} from '../test/fixtures';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('HistoryView', () => {
  it('lists scenarios with badges and opens on click', async () => {
    const page = scenarioListFixture(
      [
        scenarioSummaryFixture({ scenario_id: 'sc-1', status: 'complete' }),
        scenarioSummaryFixture({ scenario_id: 'sc-2', status: 'failed' }),
      ],
      2,
    );
    vi.stubGlobal('fetch', mockFetch([{ body: page }]));
    const onOpen = vi.fn();
    render(<HistoryView onOpen={onOpen} />);

    await waitFor(() => expect(screen.getByText('sc-1')).toBeInTheDocument());
    expect(screen.getByText('sc-2')).toBeInTheDocument();
    expect(screen.getByText('2 stored scenarios, newest first.')).toBeInTheDocument();
    expect(screen.getByText('Complete')).toBeInTheDocument();
    expect(screen.getByText('Failed')).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: 'Open' })[0] as HTMLElement);
    expect(onOpen).toHaveBeenCalledWith('sc-1');
  });

  it('expands failure details on demand, fetching once', async () => {
    const page = scenarioListFixture(
      [scenarioSummaryFixture({ scenario_id: 'sc-2', status: 'failed' })],
      1,
    );
    const detail = scenarioDetailFixture({
      scenario_id: 'sc-2',
      status: 'failed',
      problems: ['[outside_coverage] Point outside coverage.'],
    });
    const fetchMock = mockFetch([{ body: page }, { body: detail }]);
    vi.stubGlobal('fetch', fetchMock);
    render(<HistoryView onOpen={() => undefined} />);

    await waitFor(() => expect(screen.getByText('sc-2')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Show problems' }));
    await waitFor(() =>
      expect(screen.getByText(/Point outside coverage/)).toBeInTheDocument(),
    );
    expect(fetchMock).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole('button', { name: 'Hide problems' }));
    expect(screen.queryByText(/Point outside coverage/)).not.toBeInTheDocument();
  });

  it('deletes with inline confirmation and removes the row', async () => {
    const page = scenarioListFixture([scenarioSummaryFixture({ scenario_id: 'sc-1' })], 1);
    vi.stubGlobal('fetch', mockFetch([{ body: page }, { status: 204 }]));
    render(<HistoryView onOpen={() => undefined} />);

    await waitFor(() => expect(screen.getByText('sc-1')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirm delete' }));
    await waitFor(() => expect(screen.queryByText('sc-1')).not.toBeInTheDocument());
    expect(screen.getByText('No stored scenarios.')).toBeInTheDocument();
  });

  it('cancels deletion without calling the backend', async () => {
    const page = scenarioListFixture([scenarioSummaryFixture({ scenario_id: 'sc-1' })], 1);
    const fetchMock = mockFetch([{ body: page }]);
    vi.stubGlobal('fetch', fetchMock);
    render(<HistoryView onOpen={() => undefined} />);

    await waitFor(() => expect(screen.getByText('sc-1')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.getByText('sc-1')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('paginates forward and back', async () => {
    const page1 = scenarioListFixture(
      [scenarioSummaryFixture({ scenario_id: 'sc-1' })],
      21,
      0,
    );
    const page2 = scenarioListFixture(
      [scenarioSummaryFixture({ scenario_id: 'sc-21' })],
      21,
      20,
    );
    vi.stubGlobal('fetch', mockFetch([{ body: page1 }, { body: page2 }, { body: page1 }]));
    render(<HistoryView onOpen={() => undefined} />);

    await waitFor(() => expect(screen.getByText('sc-1')).toBeInTheDocument());
    expect(screen.getByText('1–20 of 21')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    await waitFor(() => expect(screen.getByText('sc-21')).toBeInTheDocument());
    expect(screen.getByText('21–21 of 21')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Previous' }));
    await waitFor(() => expect(screen.getByText('sc-1')).toBeInTheDocument());
  });

  it('shows load errors with a retry path', async () => {
    const page = scenarioListFixture([scenarioSummaryFixture({ scenario_id: 'sc-1' })], 1);
    vi.stubGlobal(
      'fetch',
      mockFetch([
        {
          body: { detail: [{ loc: [], msg: 'boom', type: 'internal' }] },
          status: 500,
        },
        { body: page },
      ]),
    );
    render(<HistoryView onOpen={() => undefined} />);

    await waitFor(() =>
      expect(screen.getByText('Could not load history')).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(screen.getByText('sc-1')).toBeInTheDocument());
  });

  it('shows the empty state', async () => {
    vi.stubGlobal('fetch', mockFetch([{ body: scenarioListFixture([], 0) }]));
    render(<HistoryView onOpen={() => undefined} />);

    await waitFor(() =>
      expect(screen.getByText('No stored scenarios.')).toBeInTheDocument(),
    );
  });
});
