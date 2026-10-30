import { useMemo } from 'react';
import type { DemoSample } from '../../data/demo';
import { DEFAULT_LIMITS } from '../../data/demo';
import { layoutFor } from '../../data/stage';
import { useCountUp } from '../../hooks/motion';
import { DECISION_STYLE, TIER_STYLE, fmtInt } from '../../lib';

const TIER_LABEL: Record<string, string> = { SAFE: 'safe', LOW_RISK: 'low risk', MEDIUM_RISK: 'medium risk', HIGH_RISK: 'high risk', CRITICAL: 'critical' };

function Readout({ label, value, limit, over, active }: { label: string; value: number; limit?: number; over?: boolean; active: boolean }) {
  const shown = useCountUp(value, active, 900);
  return (
    <div className="min-w-0">
      <dt className="text-[11.5px] text-ink-400">{label}</dt>
      <dd className={`num mt-0.5 text-[15px] font-semibold tracking-[-0.02em] ${over && active ? 'text-block' : 'text-ink-50'}`}>
        {fmtInt(Math.round(shown))}
        {limit !== undefined && <span className="ml-1 text-[11.5px] font-normal text-ink-400">/ {fmtInt(limit)}</span>}
      </dd>
    </div>
  );
}

/**
 * The hero object: a request packet is parsed into the operation's AST, the gate scores it, and the decision resolves.
 * Every shape is derived from the recorded engine output of `sample`; the animation is driven by `phase` (0-4) and
 * collapses to its final frame when `reduced` is set.
 */
export default function OperationStage({ sample, phase, reduced }: { sample: DemoSample; phase: number; reduced: boolean }) {
  const layout = useMemo(() => layoutFor(sample), [sample]);
  const decision = sample.decision === 'ERROR' ? 'BLOCK' : sample.decision;
  const color = DECISION_STYLE[decision].hex;
  const bytes = useMemo(() => new Blob([sample.query]).size, [sample]);
  const f = sample.features;
  const step = Math.max(7, Math.min(60, 1100 / layout.nodes.length));
  const dense = layout.nodes.length > 20;
  const r = dense ? 2.7 : 4;
  const parsing = phase >= 1;
  const scoring = phase >= 2;
  const deciding = phase >= 3;
  const settled = phase >= 4;
  const arcLen = Math.PI * 46;
  const gauge = scoring ? sample.score / 100 : 0;
  const tierColor = TIER_STYLE[sample.risk_tier]?.hex ?? color;
  const fields = useCountUp(f.field_count ?? 0, parsing, 1100);
  const overDepth = (f.max_depth ?? 0) > DEFAULT_LIMITS.depth;
  const overAlias = (f.alias_count ?? 0) > DEFAULT_LIMITS.aliases;
  const overCost = (f.complexity_score ?? 0) > DEFAULT_LIMITS.cost;
  const chips = [
    ...sample.limit_violations.map((v) => ({ text: v, hard: true })),
    ...sample.explanations.filter((e) => e.points > 0).slice(0, 3 - Math.min(1, sample.limit_violations.length)).map((e) => ({ text: `${e.rule.replace(/_/g, ' ')} +${Math.round(e.points)}`, hard: false })),
  ].slice(0, 3);

  return (
    <div className="relative overflow-hidden rounded-lg border border-line-strong bg-ink-950">
      <div className="bg-grid pointer-events-none absolute inset-0 opacity-70 [mask-image:radial-gradient(ellipse_at_center,black_40%,transparent_85%)]" aria-hidden />
      <svg viewBox="0 0 640 390" className="relative block w-full" role="img" aria-label={`Operation expander for ${sample.title}: ${fmtInt(f.field_count)} fields, decision ${sample.decision}`}>
        {/* the packet that arrives */}
        <g className={reduced ? '' : 'animate-fade-in'}>
          <rect x="12" y="172" width="40" height="46" rx="5" fill="#0d0e10" stroke="rgba(255,255,255,0.35)" />
          <path d="M20 184h24M20 192h18M20 200h22M20 208h12" stroke="rgba(255,255,255,0.35)" strokeWidth="2" strokeLinecap="round" />
          <text x="32" y="238" textAnchor="middle" className="num fill-ink-300" fontSize="11" fontFamily="inherit">
            {fmtInt(bytes)} B
          </text>
        </g>
        <line x1="52" y1="195" x2={layout.nodes[0].x - 4} y2={layout.nodes[0].y} stroke="rgba(255,255,255,0.18)" />

        {/* AST */}
        <g aria-hidden>
          {layout.nodes.map((n, i) =>
            n.parent === null ? null : (
              <line
                key={`e${n.id}`}
                x1={layout.nodes[n.parent].x}
                y1={layout.nodes[n.parent].y}
                x2={n.x}
                y2={n.y}
                stroke="rgba(255,255,255,0.22)"
                strokeWidth="1"
                className={parsing && !reduced ? 'animate-edge-in' : ''}
                style={{ opacity: parsing ? 1 : 0, animationDelay: reduced ? undefined : `${i * step}ms` }}
              />
            ),
          )}
          {layout.nodes.map((n, i) => (
            <circle
              key={n.id}
              cx={n.x}
              cy={n.y}
              r={r}
              className={`svg-pop ${parsing && !reduced ? 'animate-node-in' : ''}`}
              fill={i === 0 ? '#fff' : '#0d0e10'}
              stroke={i === 0 ? '#fff' : 'rgba(255,255,255,0.7)'}
              strokeWidth="1.3"
              style={{ opacity: parsing ? 1 : 0, animationDelay: reduced ? undefined : `${i * step}ms` }}
            />
          ))}
          {layout.hidden > 0 && (
            <text x="228" y="364" textAnchor="middle" className="num fill-ink-300" fontSize="12" style={{ opacity: parsing ? 1 : 0, transition: 'opacity .4s .9s' }}>
              + {fmtInt(layout.hidden)} more fields not drawn
            </text>
          )}
        </g>

        {/* request on its way to the gate */}
        <line x1="396" y1="230" x2="446" y2="230" stroke="rgba(255,255,255,0.18)" strokeDasharray="3 4" />
        {scoring && !reduced && (
          <circle cx="396" cy="230" r="3.5" fill="#fff" className="animate-travel" style={{ ['--travel' as string]: '50px' }} />
        )}

        {/* the gate */}
        <g>
          <rect x="446" y="44" width="4" height="302" rx="2" fill="#fff" opacity="0.92" />
          {Array.from({ length: 11 }, (_, i) => (
            <line key={i} x1="436" x2="446" y1={64 + i * 26} y2={64 + i * 26} stroke="rgba(255,255,255,0.3)" />
          ))}
          <text x="448" y="30" textAnchor="middle" className="fill-ink-300" fontSize="11" fontWeight="600" letterSpacing="0.04em">
            Sentinel
          </text>
        </g>

        {/* score gauge */}
        <g>
          <path d="M489 150 A46 46 0 0 1 581 150" fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="6" strokeLinecap="round" />
          <path
            d="M489 150 A46 46 0 0 1 581 150"
            fill="none"
            stroke={tierColor}
            strokeWidth="6"
            strokeLinecap="round"
            strokeDasharray={arcLen}
            strokeDashoffset={arcLen * (1 - gauge)}
            style={{ transition: reduced ? undefined : 'stroke-dashoffset 0.9s cubic-bezier(0.22, 1, 0.36, 1)' }}
          />
          <text x="535" y="144" textAnchor="middle" className="num fill-ink-50" fontSize="26" fontWeight="600" letterSpacing="-0.04em">
            {scoring ? sample.score.toFixed(sample.score % 1 === 0 ? 0 : 1) : '–'}
          </text>
          <text x="535" y="166" textAnchor="middle" className="fill-ink-400" fontSize="11">
            {scoring ? `${TIER_LABEL[sample.risk_tier] ?? sample.risk_tier}` : 'risk score'}
          </text>
        </g>

        {/* outcome */}
        <g>
          {deciding && decision !== 'BLOCK' && (
            <line
              x1="450"
              y1="230"
              x2="548"
              y2="230"
              stroke={color}
              strokeWidth="2"
              pathLength={1}
              strokeDasharray={decision === 'THROTTLE' ? '0.06 0.05' : '1'}
              className={reduced ? '' : 'animate-draw'}
              style={decision === 'THROTTLE' ? { strokeDasharray: '5 6' } : undefined}
            />
          )}
          {deciding && decision === 'BLOCK' && (
            <g className={reduced ? '' : 'animate-fade-in'} stroke={color} strokeWidth="2.4" strokeLinecap="round">
              <path d="M439 222l16 16M455 222l-16 16" />
            </g>
          )}
          <rect
            x="548"
            y="198"
            width="78"
            height="64"
            rx="6"
            fill="#0d0e10"
            stroke={deciding && decision !== 'BLOCK' ? color : 'rgba(255,255,255,0.25)'}
            strokeDasharray={deciding && decision === 'BLOCK' ? '4 4' : undefined}
            style={{ transition: reduced ? undefined : 'stroke .4s' }}
          />
          <text x="587" y="226" textAnchor="middle" className="fill-ink-100" fontSize="12" fontWeight="600">
            your API
          </text>
          <text x="587" y="244" textAnchor="middle" className="num" fontSize="11" fill={deciding ? (decision === 'BLOCK' ? '#7f838c' : color) : '#7f838c'}>
            {!deciding ? 'upstream' : decision === 'ALLOW' ? '200 forwarded' : decision === 'THROTTLE' ? '200, then 429' : 'not reached'}
          </text>
        </g>
      </svg>

      {/* reasons and verdict */}
      <div className="relative flex min-h-[56px] flex-wrap items-end justify-between gap-x-4 gap-y-2 border-t border-line px-4 py-3">
        <ul className="flex min-w-0 flex-1 flex-wrap gap-1.5" aria-label="Reasons">
          {settled &&
            chips.map((c, i) => (
              <li
                key={c.text}
                className={`${reduced ? '' : 'animate-grow'} rounded-[4px] border px-1.5 py-0.5 font-mono text-[11.5px] ${c.hard ? 'border-block/40 text-block' : 'border-line-strong text-ink-200'}`}
                style={{ animationDelay: reduced ? undefined : `${i * 90}ms` }}
              >
                {c.text}
              </li>
            ))}
        </ul>
        {settled && (
          <span className={`${reduced ? '' : 'animate-stamp'} text-[20px] font-semibold leading-none tracking-[-0.02em]`} style={{ color }}>
            {sample.decision}
          </span>
        )}
      </div>

      {/* live counters */}
      <dl className="relative grid grid-cols-2 gap-x-4 gap-y-2 border-t border-line bg-ink-900/60 px-4 py-3 sm:grid-cols-4">
        <div className="min-w-0">
          <dt className="text-[11.5px] text-ink-400">Fields executed</dt>
          <dd className={`num mt-0.5 text-[15px] font-semibold tracking-[-0.02em] ${(f.field_count ?? 0) > 1000 && parsing ? 'text-block' : 'text-ink-50'}`}>{fmtInt(Math.round(fields))}</dd>
        </div>
        <Readout label="Depth" value={f.max_depth ?? 0} limit={DEFAULT_LIMITS.depth} over={overDepth} active={parsing} />
        <Readout label="Aliases" value={f.alias_count ?? 0} limit={DEFAULT_LIMITS.aliases} over={overAlias} active={parsing} />
        <Readout label="Cost" value={f.complexity_score ?? 0} limit={DEFAULT_LIMITS.cost} over={overCost} active={parsing} />
      </dl>
    </div>
  );
}
