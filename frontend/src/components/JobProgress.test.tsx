import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import JobProgress from './JobProgress';
import { mockFetch, scenarioDetailFixture } from '../test/fixtures';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('JobProgress', () => {
  it('polls until the run is terminal, then hands over the detail', async () => {
    const running = scenarioDetailFixture({ status: 'running' });
    const done = scenarioDetailFixture({ status: 'complete' });
    const fetchMock = mockFetch([{ body: running }, { body: running }, { body: done }]);
    vi.stubGlobal('fetch', fetchMock);
    const onDone = vi.fn();

    render(
      <JobProgress
        scenarioId="sc-1"
        pollIntervalMs={5}
        timeoutMs={5000}
        onDone={onDone}
        onStop={() => undefined}
      />,
    );

    expect(screen.getByText('Analysis running')).toBeInTheDocument();
    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
    expect(onDone.mock.calls[0]?.[0]).toMatchObject({ status: 'complete' });
    expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(3);
  });

  it('shows a timeout state with a keep-waiting path', async () => {
    let status: 'running' | 'complete' = 'running';
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() =>
        Promise.resolve(
          new Response(JSON.stringify(scenarioDetailFixture({ status })), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }),
        ),
      ),
    );
    const onDone = vi.fn();

    render(
      <JobProgress
        scenarioId="sc-1"
        pollIntervalMs={5}
        timeoutMs={30}
        onDone={onDone}
        onStop={() => undefined}
      />,
    );

    await waitFor(() => expect(screen.getByText(/Still running after/)).toBeInTheDocument());
    status = 'complete';
    fireEvent.click(screen.getByRole('button', { name: 'Keep waiting' }));
    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
  });

  it('shows fetch failures with a retry path', async () => {
    const done = scenarioDetailFixture({ status: 'complete' });
    vi.stubGlobal('fetch', mockFetch([new TypeError('down'), { body: done }]));
    const onDone = vi.fn();

    render(
      <JobProgress
        scenarioId="sc-1"
        pollIntervalMs={5}
        timeoutMs={5000}
        onDone={onDone}
        onStop={() => undefined}
      />,
    );

    await waitFor(() => expect(screen.getByText('Polling failed')).toBeInTheDocument());
    expect(screen.getByText(/could not be reached/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
  });
});
