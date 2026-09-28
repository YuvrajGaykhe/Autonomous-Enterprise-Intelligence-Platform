import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ApiError, ContractError, NetworkError, type ApiCall } from '@/api/client';
import { EmptyState, ErrorState, LoadingState, QueryView } from '@/states/states';

const call: ApiCall = {
  method: 'GET',
  path: '/x',
  status: 404,
  durationMs: 3,
  requestId: 'req-42',
};

function Harness({ fetcher, empty }: { fetcher: () => Promise<string[]>; empty?: string }) {
  const query = useQuery({ queryKey: ['harness'], queryFn: fetcher, retry: false });
  return (
    <QueryView
      query={query}
      label="things"
      isEmpty={(data) => data.length === 0}
      {...(empty === undefined ? {} : { emptyMessage: empty })}
    >
      {(data) => (
        <ul>
          {data.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
    </QueryView>
  );
}

function renderHarness(fetcher: () => Promise<string[]>, empty?: string) {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <Harness fetcher={fetcher} {...(empty === undefined ? {} : { empty })} />
    </QueryClientProvider>,
  );
}

describe('the four states (§8.7)', () => {
  it('loading: skeletons announced to screen readers', () => {
    renderHarness(() => new Promise(() => undefined));

    expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByText('Loading things…')).toBeInTheDocument();
  });

  it('empty: the fixed copy for the surface', async () => {
    renderHarness(() => Promise.resolve([]), 'No records yet: run an ingestion first.');

    expect(await screen.findByText('No records yet: run an ingestion first.')).toBeInTheDocument();
  });

  it('success: the data, rendered by the surface', async () => {
    renderHarness(() => Promise.resolve(['alpha', 'beta']));

    expect(await screen.findByText('alpha')).toBeInTheDocument();
    expect(screen.getByText('beta')).toBeInTheDocument();
  });

  it('success with no data and no empty copy: the surface still renders', async () => {
    renderHarness(() => Promise.resolve([]));

    expect(await screen.findByRole('list')).toBeEmptyDOMElement();
  });

  it('error: the message, the code and the request id, with Retry for a GET', async () => {
    const fetcher = vi
      .fn<() => Promise<string[]>>()
      .mockRejectedValueOnce(
        new ApiError(
          404,
          {
            code: 'BRIEF_NOT_FOUND',
            message: 'risk brief does not exist',
            details: null,
            request_id: 'req-42',
          },
          'req-42',
          call,
        ),
      )
      .mockResolvedValueOnce(['after retry']);
    renderHarness(fetcher);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('risk brief does not exist');
    expect(alert).toHaveTextContent('BRIEF_NOT_FOUND');
    expect(alert).toHaveTextContent('req-42');

    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('after retry')).toBeInTheDocument();
  });
});

describe('ErrorState', () => {
  it('lists contract issues and says when no request id arrived', () => {
    render(
      <ErrorState
        error={
          new ContractError('bad shape', ['band: Invalid option'], { ...call, requestId: null })
        }
      />,
    );

    expect(screen.getByRole('alert')).toHaveTextContent('CONTRACT_ERROR');
    expect(screen.getByText('band: Invalid option')).toBeInTheDocument();
    expect(screen.getByText('none received')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('names a timeout', () => {
    render(<ErrorState error={new NetworkError('The request timed out.', true, call)} />);

    expect(screen.getByRole('alert')).toHaveTextContent('TIMEOUT');
  });
});

describe('LoadingState and EmptyState', () => {
  it('draw the requested number of skeleton lines', () => {
    const { container } = render(<LoadingState label="rows" lines={5} />);
    expect(container.querySelectorAll('.animate-pulse')).toHaveLength(5);
  });

  it('show the message they are given', () => {
    render(<EmptyState message="No customer is at WATCH or above on this date." />);
    expect(screen.getByText('No customer is at WATCH or above on this date.')).toBeInTheDocument();
  });
});
