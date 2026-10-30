import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { lineMarks } from '../components/code';
import { EVENT, EVENT_ALLOW, METRICS, mockApi, READY, renderAt } from './helpers';

const page = { items: [EVENT, EVENT_ALLOW], total: 2, limit: 25, offset: 0 };

test('Ctrl+K opens the command palette, filters it and Escape closes it', async () => {
  mockApi({ '/api/ready': READY, '/api/metrics': METRICS, '/api/events': page });
  renderAt('/app');
  await screen.findByText('Requests', {}, { timeout: 8000 });
  userEvent.keyboard('{ctrl}k{/ctrl}');
  const box = await screen.findByRole('combobox', { name: /type a command/i });
  expect(screen.getByRole('listbox', { name: 'Commands' })).toBeInTheDocument();
  userEvent.type(box, 'polic');
  const list = screen.getByRole('listbox', { name: 'Commands' });
  await waitFor(() => expect(within(list).getAllByRole('option')[0]).toHaveTextContent(/polic/i));
  expect(within(list).queryByText('Overview')).not.toBeInTheDocument();
  userEvent.keyboard('{esc}');
  await waitFor(() => expect(screen.queryByRole('combobox', { name: /type a command/i })).not.toBeInTheDocument());
}, 20000);

test('palette Enter navigates to the highlighted page', async () => {
  mockApi({ '/api/ready': READY, '/api/metrics': METRICS, '/api/config': {}, '/api/events': page });
  renderAt('/app');
  await screen.findByText('Requests');
  userEvent.keyboard('{ctrl}k{/ctrl}');
  userEvent.type(await screen.findByRole('combobox', { name: /type a command/i }), 'events');
  userEvent.keyboard('{enter}');
  expect(await screen.findByText('Security events')).toBeInTheDocument();
});

test('j and k move the selected row and Enter opens it', async () => {
  mockApi({ '/api/ready': READY, '/api/events': page, '/api/events/evt_1': { ...EVENT, client_timeline: [] } });
  renderAt('/app/events');
  const rows = await screen.findAllByRole('row', { name: /^Event/ });
  expect(rows[0]).toHaveAttribute('aria-selected', 'true');
  userEvent.keyboard('j');
  await waitFor(() => expect(screen.getAllByRole('row', { name: /^Event/ })[1]).toHaveAttribute('aria-selected', 'true'));
  userEvent.keyboard('k');
  await waitFor(() => expect(screen.getAllByRole('row', { name: /^Event/ })[0]).toHaveAttribute('aria-selected', 'true'));
  userEvent.keyboard('{enter}');
  expect(await screen.findByText('Why this decision')).toBeInTheDocument();
});

describe('lineMarks', () => {
  test('marks alias lines only when the engine reported aliases', () => {
    const q = '{\n  a: user(id: 1) { name }\n  b: user(id: 2) { name }\n}';
    expect([...lineMarks(q, ['aliases']).keys()]).toEqual([1, 2]);
    expect(lineMarks(q, []).size).toBe(0);
  });
  test('marks the fragment definition and introspection fields', () => {
    const q = 'query { __schema { types { name } } }\nfragment F on User { id }';
    const m = lineMarks(q, ['introspection', 'fragments']);
    expect(m.get(0)).toContain('introspection');
    expect(m.get(1)).toContain('fragments');
  });
  test('ignores arguments inside parentheses', () => {
    expect(lineMarks('{ user(id: "__schema") { name } }', ['introspection']).size).toBe(0);
  });
});

describe('landing demo with reduced motion', () => {
  const original = window.matchMedia;
  beforeEach(() => {
    window.matchMedia = ((q: string) => ({ matches: q.includes('reduce'), media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, onchange: null, dispatchEvent: () => false })) as typeof window.matchMedia;
  });
  afterEach(() => {
    window.matchMedia = original;
  });

  test('shows the settled verdict immediately, without waiting for timers', async () => {
    mockApi({ '/api/ready': READY, '/api/evaluation': { available: false } });
    renderAt('/');
    await screen.findByRole('heading', { level: 1 });
    await act(async () => {});
    expect(document.querySelector('#console-panel .animate-stamp, #console-panel')?.textContent).toMatch(/BLOCK/);
    expect(document.querySelector('#demo-console p.sr-only')?.textContent).toMatch(/Result for Fragment bomb: BLOCK/);
  });

  test('tabs expose the full recorded set and the selected one is announced', async () => {
    mockApi({ '/api/ready': READY, '/api/evaluation': { available: false } });
    renderAt('/');
    await screen.findByRole('heading', { level: 1 });
    expect(screen.getAllByRole('tab', { selected: true })[0]).toHaveAccessibleName('Fragment bomb');
    expect(screen.getByRole('tablist', { name: 'Recorded samples' }).querySelectorAll('[role=tab]').length).toBe(6);
  });
});
