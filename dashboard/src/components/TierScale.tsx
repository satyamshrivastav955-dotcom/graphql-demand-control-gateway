import { TIER_STYLE } from '../lib';
import type { Tier } from '../api/types';

const ORDER: Tier[] = ['SAFE', 'LOW_RISK', 'MEDIUM_RISK', 'HIGH_RISK', 'CRITICAL'];

/** A 0-100 scale divided into the five risk tiers, with the score marked on it. `bounds` are the tier upper bounds. */
export default function TierScale({ score, bounds = [20, 40, 65, 85], showLabels = true }: { score?: number | null; bounds?: number[]; showLabels?: boolean }) {
  const edges = [0, ...bounds, 100];
  const pos = score == null ? null : Math.max(0, Math.min(100, score));
  return (
    <div role="img" aria-label={score == null ? 'Risk tier scale' : `Risk score ${score.toFixed(1)} on a 0 to 100 tier scale`}>
      <div className="relative">
        <div className="flex h-1.5 gap-[2px] overflow-hidden rounded-full">
          {ORDER.map((t, i) => (
            <div key={t} className="h-full" style={{ width: `${edges[i + 1] - edges[i]}%`, background: TIER_STYLE[t].hex, opacity: 0.85 }} />
          ))}
        </div>
        {pos !== null && (
          <div className="absolute -top-[5px] h-[16px] w-[2px] rounded-full bg-white shadow-[0_0_0_2px_#0d0e10]" style={{ left: `calc(${pos}% - 1px)` }} />
        )}
      </div>
      {showLabels && (
        <div className="num relative mt-1.5 h-4 text-[11px] text-ink-400" aria-hidden>
          {edges.map((e, i) => (
            <span key={i} className="absolute -translate-x-1/2" style={{ left: `${e}%`, ...(i === 0 ? { transform: 'none' } : i === edges.length - 1 ? { transform: 'translateX(-100%)' } : {}) }}>
              {e}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
