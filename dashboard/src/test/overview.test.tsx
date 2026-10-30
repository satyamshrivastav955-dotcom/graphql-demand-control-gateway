import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { METRICS, mockApi, networkDown, READY, renderAt } from './helpers';

test('shows a loading state, then metrics from the API', async () => {
  mockApi({ '/api/ready': READY, '/api/metrics': METRICS });
  renderAt('/app');
  expect((await screen.findAllByRole('status')).length).toBeGreaterThan(0);
  expect(await screen.findByText('120')).toBeInTheDocument();
  expect(screen.getAllByText('Allowed').length).toBeGreaterThan(0);
  expect(screen.getByText(/block rate 6\.7%/)).toBeInTheDocument();
  // top signal and suspicious event come from the API payload
  expect(screen.getAllByText(/excessive depth/i).length).toBeGreaterThan(0);
  expect(screen.getByRole('row', { name: /BLOCK/ })).toBeInTheDocument();
});

test('requests the selected time range', async () => {
  const fetchMock = mockApi({ '/api/ready': READY, '/api/metrics': METRICS });
  renderAt('/app');
  await screen.findByText('120');
  userEvent.selectOptions(screen.getByLabelText('Time range'), '1440');
  await screen.findByText('120');
  const urls = fetchMock.mock.calls.map((c) => String(c[0]));
  expect(urls.some((u) => u.includes('/api/metrics?minutes=1440'))).toBe(true);
});

test('shows an empty state when there is no traffic', async () => {
  mockApi({ '/api/ready': READY, '/api/metrics': { ...METRICS, total_queries: 0 } });
  renderAt('/app');
  expect(await screen.findByText('No traffic in this window')).toBeInTheDocument();
});

test('shows a gateway-unreachable error with retry', async () => {
  networkDown();
  renderAt('/app');
  expect(await screen.findByText('Gateway unreachable')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  expect(screen.getAllByText('Gateway offline').length).toBeGreaterThan(0);
});
