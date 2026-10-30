import { useId } from 'react';
import { DECISION_STYLE } from '../lib';
import type { Decision } from '../api/types';
import { useEnforcement } from '../hooks/enforcement';

interface LoadPoint {
  time: string;
  total: number;
  allowed: number;
  throttled: number;
  blocked: number;
}

/** Inline trend line (no axes): 60x24 by default, scales to its container. Values must be real series. */
export function Spark({ values, color = '#a4a7ae', className = 'h-6 w-16' }: { values: number[]; color?: string; className?: string }) {
  const id = useId();
  if (values.length < 2) return null;
  const w = 100;
  const h = 32;
  const max = Math.max(...values, 1);
  const step = w / (values.length - 1);
  const pts = values.map((v, i) => [i * step, h - 3 - (v / max) * (h - 6)] as const);
  const line = pts.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const area = `${line} L${w},${h} L0,${h} Z`;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className={className} aria-hidden>
      <defs>
        <linearGradient id={id} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor={color} stopOpacity="0.22" />
          <stop offset="1" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${id})`} />
      <path d={line} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

/** Stacked per-minute request bars (allowed / throttled / blocked) on a labelled scale. */
export function LoadChart({ points }: { points: LoadPoint[] }) {
  const shadow = useEnforcement() === 'shadow';
  const max = Math.max(1, ...points.map((p) => p.total));
  const every = Math.ceil(points.length / 8);
  const ticks = [1, 0.5, 0];
  return (
    <figure aria-label="Requests over time" className="px-4 pb-3 pt-4">
      <div className="flex">
        <div className="num flex h-44 w-9 shrink-0 flex-col justify-between pr-2 text-right text-[11px] text-ink-400" aria-hidden>
          {ticks.map((t) => (
            <span key={t}>{Math.round(max * t)}</span>
          ))}
        </div>
        <div className="relative min-w-0 flex-1">
          <div className="pointer-events-none absolute inset-0 flex flex-col justify-between" aria-hidden>
            {ticks.map((t) => (
              <div key={t} className="border-t border-line-faint" />
            ))}
          </div>
          <div className="relative flex h-44 items-end justify-end gap-[3px]" role="img" aria-label={`Request volume across ${points.length} intervals, peak ${max}`}>
            {points.map((p) => {
              const h = (p.total / max) * 100;
              const seg = (n: number) => (p.total ? (n / p.total) * 100 : 0);
              const other = Math.max(0, p.total - p.allowed - p.throttled - p.blocked);
              return (
                <div
                  key={p.time}
                  className="group relative flex h-full min-w-0 max-w-[40px] flex-1 flex-col justify-end"
                  title={`${p.time} · ${p.total} total · ${p.allowed} allowed · ${p.throttled} throttled · ${p.blocked} blocked`}
                >
                  <div className="flex w-full flex-col-reverse overflow-hidden rounded-[2px] transition-opacity group-hover:opacity-75" style={{ height: `${h}%` }}>
                    <div className="bg-allow" style={{ height: `${seg(p.allowed)}%` }} />
                    <div className="bg-throttle" style={{ height: `${seg(p.throttled)}%` }} />
                    <div className="bg-block" style={{ height: `${seg(p.blocked)}%` }} />
                    {other > 0 && <div className="bg-fault" style={{ height: `${seg(other)}%` }} />}
                  </div>
                </div>
              );
            })}
          </div>
          <div className="num mt-1.5 flex justify-end gap-[3px] text-[11px] text-ink-400">
            {points.map((p, i) => (
              <span key={p.time} className="min-w-0 max-w-[40px] flex-1 whitespace-nowrap">
                {i % every === 0 ? p.time : ''}
              </span>
            ))}
          </div>
        </div>
      </div>
      <figcaption className="mt-3 flex flex-wrap gap-4 pl-9 text-[12px] text-ink-300">
        <Legend color="bg-allow" label="Allowed" />
        <Legend color="bg-throttle" label={shadow ? 'Would throttle' : 'Throttled'} />
        <Legend color="bg-block" label={shadow ? 'Would block' : 'Blocked'} />
      </figcaption>
    </figure>
  );
}

export function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`h-2 w-2 rounded-[2px] ${color}`} aria-hidden /> {label}
    </span>
  );
}

/** One thin stacked bar with a ranked list: the bar shows proportion, the list carries the exact numbers. */
export function SegmentBar({ segments }: { segments: { key: string; label: string; value: number; color: string; textClass?: string }[] }) {
  const total = segments.reduce((a, s) => a + s.value, 0);
  return (
    <div className="px-4 py-4">
      <div className="flex h-1.5 w-full gap-[2px] overflow-hidden rounded-full" role="img" aria-label={segments.map((s) => `${s.label} ${s.value}`).join(', ')}>
        {total > 0 ? (
          segments.map((s) =>
            s.value > 0 ? <div key={s.key} className="h-full first:rounded-l-full last:rounded-r-full" style={{ width: `${(s.value / total) * 100}%`, background: s.color }} title={`${s.label}: ${s.value}`} /> : null,
          )
        ) : (
          <div className="h-full w-full bg-white/10" />
        )}
      </div>
      <ul className="mt-3.5 divide-y divide-line-faint">
        {segments.map((s) => (
          <li key={s.key} className="flex items-center justify-between py-1.5 text-[13px]">
            <span className="inline-flex items-center gap-2 text-ink-200">
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: s.color }} aria-hidden />
              {s.label}
            </span>
            <span className="num text-ink-50">
              {s.value}
              <span className="ml-2 inline-block w-9 text-right text-[12px] text-ink-400">{total ? `${((s.value / total) * 100).toFixed(0)}%` : '0%'}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Score-over-time line for a client's recent history, with decision-coloured points. */
export function Sparkline({ points }: { points: { score: number; decision: Decision }[] }) {
  if (points.length < 2) return <p className="text-[13px] text-ink-400">Not enough history from this client yet.</p>;
  const w = 320;
  const h = 72;
  const step = w / (points.length - 1);
  const y = (s: number) => h - 6 - (Math.max(0, Math.min(100, s)) / 100) * (h - 12);
  const d = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(1)},${y(p.score).toFixed(1)}`).join(' ');
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full" role="img" aria-label="Risk score of this client's recent requests">
      {[0, 50, 100].map((t) => (
        <line key={t} x1="0" x2={w} y1={y(t)} y2={y(t)} stroke="rgba(255,255,255,0.07)" />
      ))}
      <path d={d} fill="none" stroke="#c9cbd0" strokeWidth="1.4" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
      {points.map((p, i) => (
        <circle key={i} cx={i * step} cy={y(p.score)} r="3" fill={DECISION_STYLE[p.decision]?.hex ?? '#a4a7ae'} stroke="#0d0e10" strokeWidth="1.5">
          <title>{`${p.decision} · score ${p.score}`}</title>
        </circle>
      ))}
    </svg>
  );
}
