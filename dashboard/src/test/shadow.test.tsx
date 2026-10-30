import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CONFIG, EVENT, EVENT_ALLOW, METRICS, mockApi, READY, renderAt } from './helpers';

const SHADOW_CONFIG = { ...CONFIG, enforcement: 'shadow' as const };
const shadowEvent = { ...EVENT, enforced: 'shadow' as const, upstream_status: 200 };

test('shadow mode shows a persistent banner in the dashboard shell and on Policies', async () => {
  mockApi({ '/api/ready': READY, '/api/config': SHADOW_CONFIG });
  renderAt('/app/policies');
  expect(await screen.findByText('Enforcement')).toBeInTheDocument();
  const banners = await screen.findAllByText(/decisions are recorded but not enforced/i);
  expect(banners.length).toBe(2); // shell + Policies page
  expect(screen.getByText('Shadow: record only, never block')).toBeInTheDocument();
});

test('enforce mode and older gateways show no shadow wording at all', async () => {
  mockApi({ '/api/ready': READY, '/api/config': { ...CONFIG, enforcement: 'enforce' } });
  const { unmount } = renderAt('/app/policies');
  await screen.findByText('Enforcement');
  expect(screen.queryByText(/not enforced/i)).not.toBeInTheDocument();
  unmount();

  mockApi({ '/api/ready': READY, '/api/config': CONFIG }); // no `enforcement` field
  renderAt('/app/policies');
  await screen.findByText('Risk tiers and actions');
  expect(screen.queryByText(/shadow/i)).not.toBeInTheDocument();
});

test('events recorded in shadow mode read "would block", not "block"', async () => {
  mockApi({
    '/api/ready': READY,
    '/api/config': SHADOW_CONFIG,
    '/api/events': { items: [shadowEvent, EVENT_ALLOW], total: 2, limit: 25, offset: 0 },
  });
  renderAt('/app/events');
  const row = await screen.findByRole('row', { name: /WOULD BLOCK/ });
  expect(row).toHaveTextContent('WOULD BLOCK');
  expect(screen.getByRole('row', { name: /Event ALLOW/ })).toHaveTextContent('ALLOW');
  expect(screen.queryByRole('row', { name: /Event BLOCK/ })).not.toBeInTheDocument();
});

test('event detail explains that the shadow decision was not enforced', async () => {
  mockApi({
    '/api/ready': READY,
    '/api/config': SHADOW_CONFIG,
    '/api/events/evt_1': { ...shadowEvent, client_timeline: [] },
  });
  renderAt('/app/events/evt_1');
  expect(await screen.findByText('Shadow: recorded, not enforced')).toBeInTheDocument();
  expect(screen.getAllByText('WOULD BLOCK').length).toBeGreaterThan(0);
});

test('overview relabels throttled/blocked as would-throttle/would-block in shadow mode', async () => {
  mockApi({ '/api/ready': READY, '/api/config': SHADOW_CONFIG, '/api/metrics': METRICS });
  renderAt('/app');
  expect((await screen.findAllByText('Would block')).length).toBeGreaterThanOrEqual(2); // stat card + chart legend
  expect(screen.getAllByText('Would throttle').length).toBeGreaterThanOrEqual(2);
  expect(screen.queryByText('Blocked')).not.toBeInTheDocument();
  expect(screen.queryByText('Throttled')).not.toBeInTheDocument();
});

test('analyze through the gateway labels a shadow response honestly', async () => {
  mockApi({
    '/api/ready': READY,
    '/api/config': SHADOW_CONFIG,
    '/graphql-proxy': {
      data: { ok: true },
      extensions: { security: { decision: 'BLOCK', enforced: 'shadow', shadow: true, risk_tier: 'CRITICAL', score: 95, rule_score: 90, ml_score: 0.9, explanations: [], limit_violations: [], event_id: 'e9' } },
    },
  });
  renderAt('/app/analyze');
  userEvent.click(await screen.findByRole('button', { name: /send through gateway/i }));
  expect(await screen.findByText('WOULD BLOCK')).toBeInTheDocument();
  expect(screen.getByText(/recorded but not enforced, and the operation was forwarded/i)).toBeInTheDocument();
});
