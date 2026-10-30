import { fireEvent, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ANALYZE, mockApi, networkDown, READY, renderAt } from './helpers';

const editor = () => screen.getByLabelText('GraphQL operation');

/** Renders the page and waits for the access gate to let it through. */
async function renderAnalyze() {
  renderAt('/app/analyze');
  await screen.findByLabelText('GraphQL operation');
}

test('validates an empty operation before calling the API', async () => {
  const fetchMock = mockApi({ '/api/ready': READY });
  await renderAnalyze();
  fireEvent.change(editor(), { target: { value: '   ' } });
  userEvent.click(screen.getByRole('button', { name: /analyze \(dry run\)/i }));
  expect(await screen.findByText('Enter a GraphQL operation first.')).toBeInTheDocument();
  expect(fetchMock.mock.calls.some((c) => String(c[0]).includes('/api/analyze'))).toBe(false);
});

test('rejects variables that are not a JSON object', async () => {
  mockApi({ '/api/ready': READY });
  await renderAnalyze();
  fireEvent.change(screen.getByLabelText(/variables/i), { target: { value: '[1,2]' } });
  userEvent.click(screen.getByRole('button', { name: /analyze \(dry run\)/i }));
  expect(await screen.findByText('Variables must be a valid JSON object.')).toBeInTheDocument();
});

test('dry run posts the operation and renders the verdict, score and explanations', async () => {
  const fetchMock = mockApi({ '/api/ready': READY, '/api/analyze': ANALYZE });
  await renderAnalyze();
  fireEvent.change(editor(), { target: { value: 'query { a { b } }' } });
  fireEvent.change(screen.getByLabelText(/variables/i), { target: { value: '{"id": 1}' } });
  userEvent.click(screen.getByRole('button', { name: /analyze \(dry run\)/i }));

  const result = await screen.findByTestId('result');
  expect(result).toHaveTextContent('THROTTLE');
  expect(result).toHaveTextContent('72.4');
  expect(result).toHaveTextContent('Depth 9 is above the norm.');
  expect(result).toHaveTextContent('would be forwarded');

  const call = fetchMock.mock.calls.find((c) => String(c[0]).includes('/api/analyze'))!;
  expect(JSON.parse(String((call[1] as RequestInit).body))).toEqual({ query: 'query { a { b } }', variables: { id: 1 } });
});

test('shows the syntax error returned for an invalid operation', async () => {
  mockApi({ '/api/ready': READY, '/api/analyze': () => ({ status: 400, body: { detail: 'Syntax Error: Expected Name' } }) });
  await renderAnalyze();
  userEvent.click(screen.getByRole('button', { name: /analyze \(dry run\)/i }));
  expect(await screen.findByText('Not a valid GraphQL operation')).toBeInTheDocument();
  expect(screen.getByText('Syntax Error: Expected Name')).toBeInTheDocument();
});

test('sending through the gateway shows the enforced block and links to the event', async () => {
  mockApi({
    '/api/ready': READY,
    '/graphql-proxy': () => ({
      status: 403,
      headers: { 'X-Sentinel-Decision': 'BLOCK' },
      body: {
        data: null,
        errors: [{ message: 'Blocked by security policy' }],
        extensions: { security: { event_id: 'evt_9', decision: 'BLOCK', enforced: 'blocked', risk_tier: 'CRITICAL', score: 95, rule_score: 90, ml_score: null, explanations: [], limit_violations: ['max_depth exceeded (10)'], latency_ms: 0.7 } },
      },
    }),
  });
  await renderAnalyze();
  userEvent.click(screen.getByRole('button', { name: /send through gateway/i }));
  const result = await screen.findByTestId('result');
  expect(result).toHaveTextContent('BLOCK');
  expect(result).toHaveTextContent('HTTP 403');
  expect(result).toHaveTextContent('never reached the upstream');
  expect(result).toHaveTextContent('n/a'); // no ML score
  expect(screen.getByRole('link', { name: /open recorded event/i })).toHaveAttribute('href', '/app/events/evt_9');
});

test('flags simulated responses explicitly', async () => {
  mockApi({
    '/api/ready': READY,
    '/graphql-proxy': {
      data: { simulated: true },
      extensions: { security: { event_id: 'e1', decision: 'ALLOW', enforced: 'simulated', simulated: true, risk_tier: 'SAFE', score: 1, rule_score: 1, ml_score: 0.01, explanations: [], limit_violations: [] } },
    },
  });
  await renderAnalyze();
  userEvent.click(screen.getByRole('button', { name: /send through gateway/i }));
  expect(await screen.findByText(/Simulation mode: the response body below is not from a real upstream/)).toBeInTheDocument();
});

test('shows an unreachable-gateway error', async () => {
  networkDown();
  await renderAnalyze();
  userEvent.click(screen.getByRole('button', { name: /analyze \(dry run\)/i }));
  expect(await screen.findByText('Gateway unreachable')).toBeInTheDocument();
});
