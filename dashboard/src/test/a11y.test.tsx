import { screen, waitFor } from '@testing-library/react';
import axe from 'axe-core';
import { ANALYZE, CONFIG, EVAL_AVAILABLE, EVENT, EVENT_ALLOW, METRICS, mockApi, READY, renderAt } from './helpers';

/** Structure/name/ARIA checks. Colour contrast needs real layout, so it is checked in a browser (see dashboard/README). */
async function violations(container: HTMLElement) {
  const result = await axe.run(container, {
    rules: { 'color-contrast': { enabled: false }, region: { enabled: false } },
    resultTypes: ['violations'],
  });
  return result.violations.map((v) => `${v.impact}: ${v.id} (${v.nodes.length}) ${v.nodes[0]?.html.slice(0, 120)}`);
}

const API = {
  '/api/ready': READY,
  '/api/config': CONFIG,
  '/api/metrics': METRICS,
  '/api/events': { items: [EVENT, EVENT_ALLOW], total: 2, limit: 25, offset: 0 },
  '/api/events/evt_1': { ...EVENT, client_timeline: [{ timestamp: EVENT.timestamp, score: 91.5, decision: 'BLOCK' }] },
  '/api/evaluation': EVAL_AVAILABLE,
  '/api/analyze': ANALYZE,
};

const CASES: [string, string, RegExp][] = [
  ['landing page', '/', /engine output/i],
  ['overview', '/app', /requests/i],
  ['analyze', '/app/analyze', /graphql operation/i],
  ['events', '/app/events', /1.2 of 2/],
  ['event detail', '/app/events/evt_1', /why this decision/i],
  ['policies', '/app/policies', /risk tiers and actions/i],
  ['evaluation', '/app/evaluation', /methods compared/i],
];

test.each(CASES)('%s has no axe violations', async (_name, path, ready) => {
  mockApi(API);
  const { container } = renderAt(path);
  await waitFor(() => expect(screen.getAllByText(ready).length).toBeGreaterThan(0));
  expect(await violations(container)).toEqual([]);
});

test('the access gate has no axe violations', async () => {
  mockApi({ '/api/config': () => ({ status: 401, body: { detail: 'Invalid or missing bearer token' } }) });
  const { container } = renderAt('/app');
  await screen.findByLabelText(/access token/i);
  expect(await violations(container)).toEqual([]);
});
