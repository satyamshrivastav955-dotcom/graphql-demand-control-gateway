import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { getToken } from '../api/auth';
import { CONFIG, makeResponse, mockApi, renderAt } from './helpers';

const TOKEN = 'a-valid-token-0123456789';

/** A config endpoint that only accepts TOKEN. */
function guardedApi(extra: Record<string, unknown> = {}) {
  return mockApi({
    '/api/config': (_url: URL, init?: RequestInit) => {
      const h = (init?.headers ?? {}) as Record<string, string>;
      return h.Authorization === `Bearer ${TOKEN}` ? { body: CONFIG } : { status: 401, body: { detail: 'Invalid or missing bearer token' } };
    },
    '/api/ready': { status: 'ready' },
    ...extra,
  });
}

beforeEach(() => window.sessionStorage.clear());

test('dashboard routes show the token prompt when the API answers 401', async () => {
  guardedApi();
  renderAt('/app/policies');
  expect(await screen.findByRole('form', { name: /dashboard sign in/i })).toBeInTheDocument();
  expect(screen.queryByText(/Policies/i, { selector: 'h1' })).not.toBeInTheDocument();
});

test('a wrong token is rejected and not stored; the right one unlocks and is kept for the tab', async () => {
  const fetchMock = guardedApi();
  renderAt('/app/policies');
  const input = await screen.findByLabelText(/access token/i);
  userEvent.type(input, 'wrong-token-000000000');
  userEvent.click(screen.getByRole('button', { name: /unlock/i }));
  expect(await screen.findByText(/token was not accepted/i)).toBeInTheDocument();
  expect(getToken()).toBeNull();

  userEvent.clear(screen.getByLabelText(/access token/i));
  userEvent.type(screen.getByLabelText(/access token/i), TOKEN);
  userEvent.click(screen.getByRole('button', { name: /unlock/i }));
  await waitFor(() => expect(screen.queryByRole('form', { name: /dashboard sign in/i })).not.toBeInTheDocument());
  expect(getToken()).toBe(TOKEN);
  const sent = fetchMock.mock.calls.map(([, init]) => (init?.headers as Record<string, string> | undefined)?.Authorization);
  expect(sent).toContain(`Bearer ${TOKEN}`);
});

test('a stored token is sent on API calls', async () => {
  window.sessionStorage.setItem('sentinel.apiToken', TOKEN);
  const fetchMock = guardedApi({ '/api/metrics': { status: 200, body: {} } });
  renderAt('/app/policies');
  await waitFor(() => expect(screen.queryByRole('form', { name: /dashboard sign in/i })).not.toBeInTheDocument());
  const authed = fetchMock.mock.calls.filter(([, init]) => (init?.headers as Record<string, string> | undefined)?.Authorization);
  expect(authed.length).toBeGreaterThan(0);
});

test('an unconfigured server disables the dashboard with an explanation', async () => {
  (global as unknown as { fetch: unknown }).fetch = vi.fn(async () => makeResponse(503, { detail: 'Management API token is not configured' }));
  renderAt('/app');
  expect(await screen.findByText(/no management token configured/i)).toBeInTheDocument();
  expect(screen.queryByLabelText(/access token/i)).not.toBeInTheDocument();
});

test('the public landing page does not require a token', async () => {
  const fetchMock = mockApi({ '/api/ready': { status: 'ready' }, '/api/evaluation': { available: false } });
  renderAt('/');
  expect(await screen.findByRole('heading', { level: 1 })).toBeInTheDocument();
  expect(fetchMock.mock.calls.every(([url]) => !String(url).includes('/api/events'))).toBe(true);
});

test('the playground sends the management token as X-API-Key when going through the gateway', async () => {
  window.sessionStorage.setItem('sentinel.apiToken', TOKEN);
  const fetchMock = guardedApi({
    '/graphql-proxy': { data: { ok: true }, extensions: { security: { decision: 'ALLOW', enforced: 'forwarded', event_id: 'e1' } } },
  });
  renderAt('/app/analyze');
  userEvent.click(await screen.findByRole('button', { name: /send through gateway/i }));
  await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/graphql-proxy'))).toBe(true));
  const call = fetchMock.mock.calls.find(([url]) => String(url).includes('/graphql-proxy'))!;
  expect((call[1]?.headers as Record<string, string>)['X-API-Key']).toBe(TOKEN);
});
