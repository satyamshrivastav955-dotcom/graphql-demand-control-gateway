import { KeyboardEvent, useEffect, useMemo, useRef, useState } from 'react';
import { Pause, Play, RotateCcw } from 'lucide-react';
import { DEMO, ENFORCEMENT } from '../../data/demo';
import type { DemoSample } from '../../data/demo';
import { HOLD_MS, PHASE_AT } from '../../data/stage';
import { useReducedMotion } from '../../hooks/motion';
import { fmtFixed, fmtInt } from '../../lib';
import { QueryView } from '../code';
import RuleWaterfall from '../RuleWaterfall';
import TierScale from '../TierScale';
import { DecisionBadge } from '../ui/badges';
import { expandChains } from './graphql';
import OperationStage from './OperationStage';

const START = Math.max(0, DEMO.samples.findIndex((s) => s.id === 'fragments'));

/**
 * Drives the staged playback: phase 0..4 advances on a timer after a sample is selected, then (unless the visitor has
 * taken control or is hovering/focusing the demo) the next sample plays. With reduced motion it sits on the final frame.
 */
export function useDemoPlayer() {
  const reduced = useReducedMotion();
  const count = DEMO.samples.length;
  const [idx, setIdx] = useState(START);
  const [phase, setPhase] = useState(reduced ? 4 : 0);
  const [nonce, setNonce] = useState(0);
  const [auto, setAuto] = useState(!reduced);
  const [hold, setHold] = useState(false);

  useEffect(() => {
    if (reduced) {
      setPhase(4);
      return;
    }
    setPhase(0);
    const timers = PHASE_AT.slice(1).map((ms, i) => window.setTimeout(() => setPhase(i + 1), ms));
    return () => timers.forEach(window.clearTimeout);
  }, [idx, nonce, reduced]);

  useEffect(() => {
    if (reduced || !auto || hold || phase < 4) return;
    const t = window.setTimeout(() => setIdx((i) => (i + 1) % count), HOLD_MS);
    return () => window.clearTimeout(t);
  }, [phase, auto, hold, reduced, count]);

  return {
    reduced,
    idx,
    phase,
    auto,
    sample: DEMO.samples[idx],
    select: (i: number) => {
      setAuto(false);
      setIdx(i);
      setNonce((n) => n + 1);
    },
    replay: () => setNonce((n) => n + 1),
    toggleAuto: () => setAuto((a) => !a),
    setHold,
  };
}
export type DemoPlayer = ReturnType<typeof useDemoPlayer>;

/** Tabs + stage. The only interactive chrome of the hero object. */
export function DemoConsole({ player }: { player: DemoPlayer }) {
  const { idx, phase, sample, reduced } = player;
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  useEffect(() => {
    tabs.current[idx]?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' });
  }, [idx]);
  const onKey = (e: KeyboardEvent) => {
    const at = Math.max(0, tabs.current.findIndex((t) => t === document.activeElement));
    const n = e.key === 'ArrowRight' ? at + 1 : e.key === 'ArrowLeft' ? at - 1 : e.key === 'Home' ? 0 : e.key === 'End' ? DEMO.samples.length - 1 : null;
    if (n === null) return;
    e.preventDefault();
    const j = (n + DEMO.samples.length) % DEMO.samples.length;
    player.select(j);
    tabs.current[j]?.focus();
  };
  return (
    <div id="demo-console" className="scroll-mt-24" onMouseEnter={() => player.setHold(true)} onMouseLeave={() => player.setHold(false)} onFocus={() => player.setHold(true)} onBlur={() => player.setHold(false)}>
      <div className="mb-2.5 flex items-center justify-between gap-3">
        <div
          role="tablist"
          aria-label="Recorded samples"
          onKeyDown={onKey}
          className="-mx-1 flex min-w-0 gap-0.5 overflow-x-auto px-1 [mask-image:linear-gradient(to_right,black_calc(100%-28px),transparent)] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        >
          {DEMO.samples.map((s, i) => (
            <button
              key={s.id}
              ref={(el) => {
                tabs.current[i] = el;
              }}
              role="tab"
              id={`tab-${s.id}`}
              aria-selected={i === idx}
              aria-controls="console-panel"
              tabIndex={i === idx ? 0 : -1}
              onClick={() => player.select(i)}
              className={`h-8 shrink-0 rounded-md px-2.5 text-[12.5px] font-medium transition-colors ${i === idx ? 'bg-white/[0.1] text-ink-50' : 'text-ink-300 hover:bg-white/[0.05] hover:text-ink-50'}`}
            >
              {s.title}
            </button>
          ))}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button type="button" onClick={player.replay} className="btn-ghost h-8 px-2 text-[12.5px]" aria-label="Replay">
            <RotateCcw className="h-3.5 w-3.5" aria-hidden /> <span className="hidden sm:inline">Replay</span>
          </button>
          {!reduced && (
            <button type="button" onClick={player.toggleAuto} className="btn-ghost h-8 w-8 px-0" aria-pressed={player.auto} aria-label={player.auto ? 'Pause auto-play' : 'Resume auto-play'}>
              {player.auto ? <Pause className="h-3.5 w-3.5" aria-hidden /> : <Play className="h-3.5 w-3.5" aria-hidden />}
            </button>
          )}
        </div>
      </div>
      <div id="console-panel" role="tabpanel" aria-labelledby={`tab-${sample.id}`} aria-label={sample.title}>
        <OperationStage sample={sample} phase={phase} reduced={reduced} />
        {phase >= 4 && (
          <p className="sr-only" aria-live="polite">
            Result for {sample.title}: {sample.decision}, risk score {sample.score}
            {sample.limit_violations.length ? `, ${sample.limit_violations.join(', ')}` : ''}.
          </p>
        )}
      </div>
    </div>
  );
}

function shorten(code: string, keep = 13): { text: string; hidden: number } {
  const lines = code.split('\n');
  if (lines.length <= keep + 2) return { text: code, hidden: 0 };
  return { text: [...lines.slice(0, keep), `# … ${lines.length - keep - 1} more lines`, lines[lines.length - 1]].join('\n'), hidden: lines.length - keep - 1 };
}

/** The real query and the engine's real output for the selected sample. */
export function EngineReadout({ player }: { player: DemoPlayer }) {
  const s: DemoSample = player.sample;
  const decision = s.decision === 'ERROR' ? 'BLOCK' : s.decision;
  const view = useMemo(() => shorten(expandChains(s.query)), [s]);
  const settled = player.phase >= 4;
  return (
    <div className="grid gap-px overflow-hidden rounded-lg border border-line-strong bg-line lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <section className="min-w-0 bg-ink-900 p-4" aria-label={`${s.title} operation`}>
        <div className="mb-2.5 flex items-baseline justify-between gap-3">
          <h2 className="text-[13px] font-medium text-ink-50">{s.title}</h2>
          <span className="num shrink-0 text-[12px] text-ink-400">{fmtInt(new Blob([s.query]).size)} bytes</span>
        </div>
        <p className="mb-3 text-[13px] leading-relaxed text-ink-300">{s.blurb}</p>
        <QueryView code={view.text} maxHeight="max-h-[340px]" label={`${s.title} query text`} />
        <pre className="sr-only" aria-label={`${s.title} full query`}>
          {s.query}
        </pre>
      </section>
      <section className="min-w-0 bg-ink-900 p-4" aria-label="Engine output">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="text-[13px] font-medium text-ink-50">Engine output</h2>
          <span className={settled ? 'opacity-100' : 'opacity-30'} style={{ transition: 'opacity .3s' }}>
            <DecisionBadge decision={decision} size="md" />
          </span>
        </div>
        <div className={settled ? '' : 'opacity-40'} style={{ transition: 'opacity .4s' }}>
          <div className="flex items-baseline justify-between">
            <span className="text-[13px] text-ink-300">Blended risk score</span>
            <span className="num text-[26px] font-semibold leading-none tracking-[-0.04em] text-ink-50">{fmtFixed(s.score, s.score % 1 === 0 ? 0 : 1)}</span>
          </div>
          <div className="mt-2.5">
            <TierScale score={s.score} />
          </div>
          <p className="mt-3 text-[13px] leading-relaxed text-ink-300">
            <span className="num mr-2 font-mono text-[12px] text-ink-100">{ENFORCEMENT[decision].status}</span>
            {ENFORCEMENT[decision].text}
          </p>
        </div>
        <div className={`-mx-4 mt-3 border-t border-line ${settled ? '' : 'opacity-40'}`} style={{ transition: 'opacity .4s' }}>
          <RuleWaterfall compact explanations={s.explanations.filter((e) => e.points > 0 || e.rule === 'hard_limit')} ruleScore={s.rule_score} mlScore={s.ml_score} score={s.score} />
        </div>
      </section>
      <p className="bg-ink-900 px-4 pb-3.5 pt-0 text-[12px] leading-relaxed text-ink-400 lg:col-span-2">
        Recorded {DEMO.recorded_at} from engine v{DEMO.engine_version}, model {DEMO.model ?? 'none'}. Default limits and thresholds. Each sample was run through the shipped engine and its output stored, so the scores are what it
        really produces, not mock-ups.
      </p>
    </div>
  );
}
