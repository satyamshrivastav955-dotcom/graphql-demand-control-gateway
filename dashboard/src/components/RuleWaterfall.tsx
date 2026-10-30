import type { Explanation } from '../api/types';
import { fmtFixed, humanize } from '../lib';
import { SeverityDot } from './ui/badges';

/**
 * The rule points that sum to the rule score, as a ledger: one row per rule with a bar sized by its points, then the
 * sum and the model's probability. Every number is the engine's own (nothing is recomputed here).
 */
export default function RuleWaterfall({
  explanations,
  ruleScore,
  mlScore,
  score,
  compact = false,
}: {
  compact?: boolean;
  explanations: Explanation[];
  ruleScore?: number | null;
  mlScore?: number | null;
  score?: number | null;
}) {
  const rows = explanations.filter((x) => x.rule !== 'ml_model');
  const ml = explanations.find((x) => x.rule === 'ml_model');
  const scale = Math.max(100, ...rows.map((r) => r.points));
  return (
    <div className="px-4 py-2">
      <ul className="divide-y divide-line-faint">
        {rows.map((x, i) => (
          <li key={`${x.rule}-${i}`} className={compact ? 'py-2' : 'py-2.5'}>
            <div className="grid grid-cols-[1fr_auto] items-baseline gap-3">
              <div className="flex min-w-0 items-center gap-2">
                <SeverityDot severity={x.severity} />
                <span className="truncate text-[13px] font-medium capitalize text-ink-50">{humanize(x.rule)}</span>
              </div>
              <span className="num text-[13px] text-ink-100">{x.points > 0 ? `+${fmtFixed(x.points, 0)}` : '—'}</span>
            </div>
            <div className="mt-1.5 h-[3px] overflow-hidden rounded-full bg-white/[0.07]" aria-hidden>
              <div className="h-full rounded-full bg-ink-200" style={{ width: `${Math.min(100, (x.points / scale) * 100)}%` }} />
            </div>
            {compact ? (
              <p className="mt-1 truncate font-mono text-[11.5px] text-ink-400" title={x.description}>
                {x.feature} = {String(x.value)}
              </p>
            ) : (
              <>
                <p className="mt-1.5 text-[12.5px] leading-snug text-ink-300">{x.description}</p>
                <p className="mt-0.5 font-mono text-[11.5px] text-ink-400">
                  {x.feature} = {String(x.value)}
                </p>
              </>
            )}
          </li>
        ))}
      </ul>
      {(ruleScore != null || ml || score != null) && (
        <dl className="mt-1 space-y-1.5 border-t border-line pt-3 text-[13px]">
          {ruleScore != null && (
            <div className="flex justify-between">
              <dt className="text-ink-300">Rule score <span className="text-ink-400">(sum of points, capped at 100)</span></dt>
              <dd className="num font-medium text-ink-50">{fmtFixed(ruleScore, 1)}</dd>
            </div>
          )}
          {(ml || mlScore != null) && (
            <div className="flex justify-between">
              <dt className="text-ink-300">Model probability{ml ? <span className="text-ink-400"> (adds {fmtFixed(ml.points, 0)} to the blend)</span> : null}</dt>
              <dd className="num font-medium text-ink-50">{mlScore == null ? 'n/a' : fmtFixed(mlScore, 3)}</dd>
            </div>
          )}
          {score != null && (
            <div className="flex justify-between border-t border-line-faint pt-1.5">
              <dt className="text-ink-200">Blended risk score</dt>
              <dd className="num font-semibold text-ink-50">{fmtFixed(score, 1)}</dd>
            </div>
          )}
        </dl>
      )}
    </div>
  );
}
