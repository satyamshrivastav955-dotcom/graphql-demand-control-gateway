import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CONFIG, EVAL_AVAILABLE, METRICS, mockApi, READY, renderAt } from './helpers';

test('policies renders the active configuration', async () => {
  mockApi({ '/api/ready': READY, '/api/config': CONFIG });
  renderAt('/app/policies');
  expect(await screen.findByText('Risk tiers and actions')).toBeInTheDocument();
  expect(screen.getByText('100 req / 60s')).toBeInTheDocument();
  expect(screen.getByText('upstream.internal:4000')).toBeInTheDocument();
  expect(screen.getByText(/Flagged — introspection raises the risk score/)).toBeInTheDocument();
  expect(screen.queryByText('Simulation mode')).not.toBeInTheDocument();
});

test('policies warns loudly in simulation mode', async () => {
  mockApi({ '/api/ready': READY, '/api/config': { ...CONFIG, mode: 'simulation', upstream_configured: false, upstream_host: null } });
  renderAt('/app/policies');
  expect(await screen.findByText('Simulation mode')).toBeInTheDocument();
});

test('evaluation shows an honest empty state when no results exist', async () => {
  mockApi({ '/api/ready': READY, '/api/evaluation': { available: false } });
  renderAt('/app/evaluation');
  expect(await screen.findByText('No evaluation results yet')).toBeInTheDocument();
  expect(screen.queryByRole('table')).not.toBeInTheDocument();
});

test('evaluation renders methods, categories and limitations from the API', async () => {
  mockApi({ '/api/ready': READY, '/api/evaluation': EVAL_AVAILABLE });
  renderAt('/app/evaluation');
  expect(await screen.findByText('Methods compared')).toBeInTheDocument();
  expect(screen.getAllByText('0.924').length).toBeGreaterThan(0);
  expect(screen.getByText('Synthetic attack traffic only.')).toBeInTheDocument();
  const row = screen.getByText('deep nesting').closest('tr')!;
  expect(within(row).getByText('96.0%')).toBeInTheDocument();
});

describe('landing page and navigation', () => {
  test('renders the hero, the recorded console and the offline evaluation state', async () => {
    mockApi({ '/api/ready': READY, '/api/evaluation': { available: false } });
    renderAt('/');
    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent(/secure the operation, not just the request/i);
    expect(screen.getByText(/Recorded \d{4}-\d{2}-\d{2} from engine v\d+\.\d+\.\d+/)).toBeInTheDocument();
    expect((await screen.findAllByText('No benchmark has been generated yet')).length).toBe(2);
  });

  test('evaluation sections are filled from the live API, not hard-coded', async () => {
    mockApi({ '/api/ready': READY, '/api/evaluation': EVAL_AVAILABLE });
    renderAt('/');
    expect(await screen.findByText('F1 0.92')).toBeInTheDocument();
    expect(screen.getByText(/Held-out test split, seed 1234/)).toBeInTheDocument();
    expect(screen.getByText('This benchmark run has no leave-one-category-out results')).toBeInTheDocument();
  });

  test('draws the leave-one-category-out chart when the API provides it', async () => {
    const withGen = {
      ...EVAL_AVAILABLE,
      generalization: {
        description: 'x',
        folds: [
          { held_out_category: 'field_duplication', n: 10, ml_recall: 0, rules_recall: 0.74, combined_recall: 0.54, ml_fpr: 0, combined_fpr: 0.2 },
          { held_out_category: 'alias_batching', n: 10, ml_recall: 1, rules_recall: 0.85, combined_recall: 1, ml_fpr: 0, combined_fpr: 0.2 },
        ],
      },
    };
    mockApi({ '/api/ready': READY, '/api/evaluation': withGen });
    renderAt('/');
    expect(await screen.findByText('model 0% · rules 74% · both 54%')).toBeInTheDocument();
    expect(screen.getByText('model 100% · rules 85% · both 100%')).toBeInTheDocument();
  });

  test('says so when the benchmark cannot be loaded, and the rest of the page still renders', async () => {
    (global as unknown as { fetch: unknown }).fetch = vi.fn(async () => {
      throw new TypeError('down');
    });
    renderAt('/');
    expect(await screen.findByRole('heading', { level: 1 })).toBeInTheDocument();
    expect((await screen.findAllByText('Benchmark unavailable')).length).toBe(2);
  });

  test('decision console plays the pipeline for the selected recorded sample', async () => {
    mockApi({ '/api/ready': READY, '/api/evaluation': { available: false } });
    renderAt('/');
    await screen.findByRole('heading', { level: 1 });
    userEvent.click(screen.getByRole('tab', { name: 'Alias batching' }));
    expect(screen.getByRole('tab', { name: 'Alias batching' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByLabelText('Alias batching operation')).toHaveTextContent('u0: user');
    // the staged playback ends with the recorded decision and the hard-limit reason
    const panel = screen.getByRole('tabpanel', { name: 'Alias batching' });
    expect(await within(panel).findByText('BLOCK')).toBeInTheDocument();
    expect(within(panel).getAllByText(/alias_count>50/).length).toBeGreaterThan(0);
  });

  test('console reveals the pipeline in stages and ends with the recorded decision', async () => {
    mockApi({ '/api/ready': READY, '/api/evaluation': { available: false } });
    renderAt('/');
    await screen.findByRole('heading', { level: 1 });
    vi.useFakeTimers();
    try {
      act(() => {
        userEvent.click(screen.getByRole('tab', { name: 'Credential stuffing' }));
      });
      // before any stage has fired, the verdict is held back
      expect(document.querySelector('#console-panel .animate-stamp')).toBeNull();
      expect(screen.getByRole('tabpanel', { name: 'Credential stuffing' }).textContent).not.toMatch(/Result for/);
      act(() => {
        vi.advanceTimersByTime(1000);
      });
      expect(document.querySelector('#console-panel .animate-stamp')).toBeNull(); // still parsing/extracting
      act(() => {
        vi.advanceTimersByTime(3000);
      });
      const stamp = document.querySelector('#console-panel .animate-stamp');
      expect(stamp).not.toBeNull();
      expect(stamp?.textContent).toBe('BLOCK');
      expect(document.querySelector('#demo-console p.sr-only')?.textContent).toMatch(/Result for Credential stuffing: BLOCK, risk score 100/);
    } finally {
      vi.useRealTimers();
    }
  });

  test('console tabs are keyboard operable', async () => {
    mockApi({ '/api/ready': READY, '/api/evaluation': { available: false } });
    renderAt('/');
    await screen.findByRole('heading', { level: 1 });
    const tab = screen.getByRole('tab', { name: 'Nesting abuse' });
    tab.focus();
    userEvent.keyboard('{arrowright}');
    expect(screen.getByRole('tab', { name: 'Alias batching' })).toHaveAttribute('aria-selected', 'true');
  });

  test('quick start tabs switch and the copy button copies the shown commands', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    mockApi({ '/api/ready': READY, '/api/evaluation': { available: false } });
    renderAt('/');
    await screen.findByRole('heading', { level: 1 });
    userEvent.click(screen.getByRole('tab', { name: 'Send a request' }));
    userEvent.click(screen.getByRole('button', { name: /copy commands to clipboard/i }));
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    expect(writeText.mock.calls[0][0]).toContain('/graphql-proxy');
    expect(await screen.findByText('Copied')).toBeInTheDocument();
  });

  test('primary calls to action point at the demo and the quick start', async () => {
    mockApi({ '/api/ready': READY, '/api/evaluation': { available: false } });
    renderAt('/');
    await screen.findByRole('heading', { level: 1 });
    const ctas = screen.getAllByRole('link', { name: /see it decide|run it yourself/i });
    const hrefs = ctas.map((a) => a.getAttribute('href'));
    expect(hrefs).toEqual(expect.arrayContaining(['#demo', '#start']));
    expect(screen.getAllByText(/MIT/).length).toBeGreaterThan(0);
  });

  test('can navigate from the landing page into the dashboard and between pages', async () => {
    mockApi({ '/api/ready': READY, '/api/evaluation': { available: false }, '/api/metrics': METRICS, '/api/events': { items: [], total: 0, limit: 25, offset: 0 }, '/api/config': CONFIG });
    renderAt('/');
    userEvent.click((await screen.findAllByRole('link', { name: 'Open dashboard' }))[0]);
    expect(await screen.findByRole('heading', { name: 'Overview' })).toBeInTheDocument();
    userEvent.click(within(screen.getByRole('navigation', { name: 'Primary' })).getByRole('link', { name: /events/i }));
    expect(await screen.findByRole('heading', { name: 'Security events' })).toBeInTheDocument();
    userEvent.click(within(screen.getByRole('navigation', { name: 'Primary' })).getByRole('link', { name: /policies/i }));
    expect(await screen.findByRole('heading', { name: 'Policies' })).toBeInTheDocument();
  });

  test('unknown routes show a 404', async () => {
    mockApi({ '/api/ready': READY });
    renderAt('/nope');
    expect(await screen.findByText('404')).toBeInTheDocument();
  });
});

test('a deep link to a below-the-fold section scrolls once that lazily loaded section mounts', async () => {
  mockApi({ '/api/ready': READY, '/api/evaluation': { available: false } });
  const scrollIntoView = vi.fn();
  Element.prototype.scrollIntoView = scrollIntoView;
  window.history.replaceState(null, '', '/#how');
  renderAt('/');
  await screen.findByRole('heading', { name: /four steps, no black box/i });
  await waitFor(() => expect(scrollIntoView).toHaveBeenCalled());
  window.history.replaceState(null, '', '/');
});
