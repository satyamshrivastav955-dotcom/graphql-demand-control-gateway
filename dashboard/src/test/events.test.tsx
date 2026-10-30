import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { EVENT, EVENT_ALLOW, mockApi, READY, renderAt } from './helpers';

const page = (items = [EVENT, EVENT_ALLOW], total = items.length) => ({ items, total, limit: 25, offset: 0 });

test('lists events and opens the detail page on click', async () => {
  mockApi({
    '/api/ready': READY,
    '/api/events': page(),
    '/api/events/evt_1': { ...EVENT, client_timeline: [{ timestamp: EVENT.timestamp, score: 91.5, decision: 'BLOCK' }, { timestamp: EVENT.timestamp, score: 10, decision: 'ALLOW' }] },
  });
  renderAt('/app/events');
  const row = await screen.findByRole('row', { name: /BLOCK/ });
  expect(screen.getByText('1–2 of 2')).toBeInTheDocument();
  userEvent.click(row);
  expect(await screen.findByText('Why this decision')).toBeInTheDocument();
  expect(screen.getByText('Nesting depth 12 exceeds the limit.')).toBeInTheDocument();
  expect(screen.getByText('max_depth exceeded (10)')).toBeInTheDocument();
});

test('sends the decision filter to the API', async () => {
  const fetchMock = mockApi({ '/api/ready': READY, '/api/events': page() });
  renderAt('/app/events');
  await screen.findByRole('row', { name: /BLOCK/ });
  userEvent.selectOptions(screen.getByLabelText('Filter by decision'), 'BLOCK');
  await waitFor(() => expect(fetchMock.mock.calls.some((c) => String(c[0]).includes('decision=BLOCK'))).toBe(true));
});

test('shows an empty state for no events and for no matches', async () => {
  mockApi({ '/api/ready': READY, '/api/events': page([], 0) });
  renderAt('/app/events');
  expect(await screen.findByText('No events recorded yet')).toBeInTheDocument();
});

test('shows an error state when the API fails', async () => {
  mockApi({ '/api/ready': READY, '/api/events': () => ({ status: 500, body: { detail: 'store failure' } }) });
  renderAt('/app/events');
  expect(await screen.findByText('store failure')).toBeInTheDocument();
});

test('event detail shows not-found for an unknown id', async () => {
  mockApi({ '/api/ready': READY, '/api/events/nope': () => ({ status: 404, body: { detail: 'Event not found' } }) });
  renderAt('/app/events/nope');
  expect(await screen.findByText('Event not found')).toBeInTheDocument();
});

test('first run: shows a copyable curl and sends a real test request through the gateway', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.assign(navigator, { clipboard: { writeText } });
  const fetchMock = mockApi({
    '/api/ready': READY,
    '/api/events': page([], 0),
    '/graphql-proxy': { data: { __typename: 'Query' }, extensions: { security: { decision: 'ALLOW', enforced: 'forwarded', event_id: 'e1' } } },
  });
  renderAt('/app/events');
  expect(await screen.findByText('No events recorded yet')).toBeInTheDocument();
  userEvent.click(screen.getByRole('button', { name: /copy curl to clipboard/i }));
  await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
  expect(writeText.mock.calls[0][0]).toMatch(/curl -s .*\/graphql-proxy/);
  userEvent.click(screen.getByRole('button', { name: /send a test request/i }));
  expect(await screen.findByText(/ALLOW: forwarded/)).toBeInTheDocument();
  expect(fetchMock.mock.calls.some((c) => String(c[0]).includes('/graphql-proxy'))).toBe(true);
});

test('event detail offers a copy-as-curl for the recorded operation', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.assign(navigator, { clipboard: { writeText } });
  mockApi({ '/api/ready': READY, '/api/events/evt_1': { ...EVENT, client_timeline: [] } });
  renderAt('/app/events/evt_1');
  userEvent.click(await screen.findByRole('button', { name: 'Copy as curl' }));
  await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
  expect(writeText.mock.calls[0][0]).toContain('query Deep');
  expect(writeText.mock.calls[0][0]).toContain('X-API-Key');
});
