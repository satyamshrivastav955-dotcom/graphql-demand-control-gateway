import { useMemo, useRef } from 'react';
import { highlight, type Token, type TokenKind } from './landing/graphql';

/** Muted, near-monochrome syntax palette: structure in white, values in two quiet hues. No rainbow. */
export const TOKEN_CLASS: Record<TokenKind, string> = {
  keyword: 'font-semibold text-ink-50',
  field: 'text-ink-100',
  alias: 'text-ink-300',
  arg: 'text-ink-300',
  variable: 'text-[#e5c07b]',
  directive: 'text-[#e5c07b]',
  string: 'text-[#8fd6a5]',
  number: 'text-[#e5c07b]',
  meta: 'italic text-ink-50',
  punct: 'text-ink-400',
  comment: 'text-ink-400',
  space: '',
  text: 'text-ink-200',
};

export function Tokens({ tokens }: { tokens: Token[] }) {
  return (
    <>
      {tokens.map((t, i) => (
        <span key={i} className={TOKEN_CLASS[t.kind]}>
          {t.text}
        </span>
      ))}
    </>
  );
}

const SENSITIVE = /(password|passwd|secret|token|ssn|creditcard|cardnumber|apikey|api_key|privatekey|otp|email)/i;

/**
 * Which source lines triggered which rules, for the rules that actually fired (`rules`). This is a presentation
 * aid computed from the text; the authoritative numbers always come from the engine.
 */
export function lineMarks(source: string, rules: string[]): Map<number, string[]> {
  const marks = new Map<number, string[]>();
  const add = (line: number, rule: string) => marks.set(line, [...(marks.get(line) ?? []), rule].filter((r, i, a) => a.indexOf(r) === i));
  const want = new Set(rules);
  const lines = highlight(source);
  let depth = 0;
  let paren = 0;
  let inFragment = false;
  let maxDepth = 0;
  let maxLine = -1;
  lines.forEach((tokens, li) => {
    tokens.forEach((t, ti) => {
      if (t.text === '(') paren += 1;
      else if (t.text === ')') paren = Math.max(0, paren - 1);
      else if (paren > 0) return;
      else if (t.text === '{') depth += 1;
      else if (t.text === '}') {
        depth = Math.max(0, depth - 1);
        if (depth === 0) inFragment = false;
      } else if (t.kind === 'keyword' && t.text === 'fragment' && depth === 0) {
        inFragment = true;
        if (want.has('fragments')) add(li, 'fragments');
      } else if (t.kind === 'field' || t.kind === 'meta' || t.kind === 'alias') {
        if (t.kind === 'alias' && want.has('aliases')) add(li, 'aliases');
        if (t.kind === 'meta' && /^__(schema|type)$/.test(t.text) && want.has('introspection')) add(li, 'introspection');
        if (t.kind !== 'alias' && SENSITIVE.test(t.text) && !t.text.startsWith('__') && want.has('sensitive_fields')) add(li, 'sensitive_fields');
        if (t.kind !== 'alias' && !inFragment && depth > maxDepth && tokens[ti + 1] !== undefined) {
          maxDepth = depth;
          maxLine = li;
        }
      } else if (t.kind === 'directive' && want.has('directives')) add(li, 'directives');
    });
  });
  if (want.has('depth') && maxLine >= 0) add(maxLine, 'depth');
  return marks;
}

function Gutter({ count, marks }: { count: number; marks?: Map<number, string[]> }) {
  return (
    <div aria-hidden className="select-none py-3 pl-1.5 pr-3 text-right font-mono text-[12.5px] leading-[1.65] text-ink-400">
      {Array.from({ length: count }, (_, i) => {
        const m = marks?.get(i);
        return (
          <div key={i} className="relative" title={m ? `Triggered: ${m.join(', ')}` : undefined}>
            {m && <span className="absolute -left-1.5 bottom-[2px] top-[2px] w-[2px] rounded-full bg-throttle" />}
            <span className={m ? 'text-throttle' : ''}>{i + 1}</span>
          </div>
        );
      })}
    </div>
  );
}

/** Read-only, syntax-highlighted operation with line numbers and rule marks. */
export function QueryView({
  code,
  marks,
  maxHeight = 'max-h-[420px]',
  label = 'Operation',
}: {
  code: string;
  marks?: Map<number, string[]>;
  maxHeight?: string;
  label?: string;
}) {
  const lines = useMemo(() => highlight(code), [code]);
  return (
    <div className={`flex overflow-auto rounded-md border border-line bg-ink-950 ${maxHeight}`} role="region" aria-label={label} tabIndex={0}>
      <Gutter count={lines.length} marks={marks} />
      <pre className="min-w-0 flex-1 py-3 pr-4 font-mono text-[12.5px] leading-[1.65]">
        <code>
          {lines.map((tokens, i) => (
            <div key={i} className={`min-h-[1.65em] ${marks?.has(i) ? '-ml-1 bg-throttle/[0.07] pl-1' : ''}`}>
              <Tokens tokens={tokens} />
            </div>
          ))}
        </code>
      </pre>
    </div>
  );
}

/** A textarea with live syntax highlighting: the visible text is a <pre> underneath; the textarea overlays it transparently. */
export function CodeEditor({
  value,
  onChange,
  onRun,
  marks,
  label,
  minRows = 14,
}: {
  value: string;
  onChange: (v: string) => void;
  onRun?: () => void;
  marks?: Map<number, string[]>;
  label: string;
  minRows?: number;
}) {
  const lines = useMemo(() => highlight(value), [value]);
  const pre = useRef<HTMLDivElement>(null);
  const count = Math.max(lines.length, minRows);
  const gutter = useRef<HTMLDivElement>(null);
  const onScroll = (e: React.UIEvent<HTMLTextAreaElement>) => {
    const t = e.currentTarget;
    if (pre.current) {
      pre.current.scrollTop = t.scrollTop;
      pre.current.scrollLeft = t.scrollLeft;
    }
    if (gutter.current) gutter.current.scrollTop = t.scrollTop;
  };
  const height = `${Math.min(Math.max(count, minRows), 30) * 1.65 * 12.5 + 24}px`;
  return (
    <div className="flex overflow-hidden rounded-md border border-line bg-ink-950 focus-within:border-white/40" style={{ height }}>
      <div ref={gutter} className="overflow-hidden">
        <Gutter count={count} marks={marks} />
      </div>
      <div className="relative min-w-0 flex-1">
        <div ref={pre} aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
          <pre className="py-3 pr-4 font-mono text-[12.5px] leading-[1.65]">
            <code>
              {lines.map((tokens, i) => (
                <div key={i} className={`min-h-[1.65em] ${marks?.has(i) ? '-ml-1 bg-throttle/[0.07] pl-1' : ''}`}>
                  <Tokens tokens={tokens} />
                </div>
              ))}
            </code>
          </pre>
        </div>
        <textarea
          aria-label={label}
          spellCheck={false}
          autoCapitalize="off"
          autoCorrect="off"
          wrap="off"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onScroll={onScroll}
          onKeyDown={(e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
              e.preventDefault();
              onRun?.();
            }
            if (e.key === 'Tab') {
              e.preventDefault();
              const t = e.currentTarget;
              const s = t.selectionStart;
              onChange(`${value.slice(0, s)}  ${value.slice(t.selectionEnd)}`);
              requestAnimationFrame(() => t.setSelectionRange(s + 2, s + 2));
            }
          }}
          className="absolute inset-0 h-full w-full resize-none whitespace-pre bg-transparent py-3 pr-4 font-mono text-[12.5px] leading-[1.65] text-transparent caret-white selection:bg-white/20 focus:outline-none"
          style={{ color: 'transparent' }}
        />
      </div>
    </div>
  );
}
