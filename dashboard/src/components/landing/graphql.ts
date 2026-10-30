/** Tiny GraphQL helpers for the landing page: syntax tokens, long-chain expansion and a structural outline. No parser dependency. */

export type TokenKind = 'keyword' | 'field' | 'alias' | 'arg' | 'variable' | 'directive' | 'string' | 'number' | 'meta' | 'punct' | 'comment' | 'space' | 'text';
export interface Token {
  kind: TokenKind;
  text: string;
}

const KEYWORDS = new Set(['query', 'mutation', 'subscription', 'fragment', 'on']);
const RE =
  /(#[^\n]*)|("(?:[^"\\\n]|\\.)*")|(\$[A-Za-z_]\w*)|(@[A-Za-z_]\w*)|(\d+(?:\.\d+)?)|([A-Za-z_]\w*)|(\.\.\.|[{}()[\]:,!=|&])|(\n)|([ \t\r]+)|([\s\S])/g;

/** Splits GraphQL source into lines of coloured tokens. */
export function highlight(source: string): Token[][] {
  const lines: Token[][] = [[]];
  const flat: { m: RegExpExecArray }[] = [];
  RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = RE.exec(source))) flat.push({ m });

  let paren = 0;
  const nextSignificant = (i: number) => {
    for (let j = i + 1; j < flat.length; j++) {
      const t = flat[j].m;
      if (!t[8] && !t[9]) return t[0];
    }
    return '';
  };
  flat.forEach(({ m: t }, i) => {
    const line = lines[lines.length - 1];
    const text = t[0];
    if (t[8]) {
      lines.push([]);
    } else if (t[9]) {
      line.push({ kind: 'space', text });
    } else if (t[1]) {
      line.push({ kind: 'comment', text });
    } else if (t[2]) {
      line.push({ kind: 'string', text });
    } else if (t[3]) {
      line.push({ kind: 'variable', text });
    } else if (t[4]) {
      line.push({ kind: 'directive', text });
    } else if (t[5]) {
      line.push({ kind: 'number', text });
    } else if (t[6]) {
      let kind: TokenKind = 'field';
      if (KEYWORDS.has(text)) kind = 'keyword';
      else if (text.startsWith('__')) kind = 'meta';
      else if (nextSignificant(i) === ':') kind = paren > 0 ? 'arg' : 'alias';
      line.push({ kind, text });
    } else if (t[7]) {
      if (text === '(') paren += 1;
      if (text === ')') paren = Math.max(0, paren - 1);
      line.push({ kind: 'punct', text });
    } else {
      line.push({ kind: 'text', text });
    }
  });
  return lines;
}

/** Expands lines that open three or more selection sets so a deep chain reads as a staircase. */
export function expandChains(source: string): string {
  return source
    .split('\n')
    .map((line) => {
      if ((line.match(/\{/g) ?? []).length < 3) return line;
      const indent = line.match(/^\s*/)?.[0] ?? '';
      let depth = 0;
      let out = '';
      let inString = false;
      for (let i = 0; i < line.length; i++) {
        const c = line[i];
        if (c === '"' && line[i - 1] !== '\\') inString = !inString;
        if (!inString && c === '{') {
          depth += 1;
          out = out.replace(/\s+$/, '') + ' {\n' + indent + '  '.repeat(depth);
        } else if (!inString && c === '}') {
          depth -= 1;
          out = out.replace(/\s+$/, '') + '\n' + indent + '  '.repeat(Math.max(0, depth)) + '}';
        } else {
          out += c;
        }
      }
      return out.replace(/\n\s*\n/g, '\n').replace(/^\s+(?=\S)/, indent);
    })
    .join('\n');
}

export interface OutlineField {
  depth: number;
  name: string;
  alias?: string;
}
export interface Outline {
  fields: OutlineField[];
  fragments: string[];
  spreads: number;
  maxDepth: number;
}

/** Field names by nesting depth in the operation (fragment definitions are listed separately, not expanded). */
export function outline(source: string): Outline {
  const lines = highlight(source);
  const sig = lines.flat().filter((t) => t.kind !== 'space' && t.kind !== 'comment');
  const fields: OutlineField[] = [];
  const fragments: string[] = [];
  let spreads = 0;
  let depth = 0;
  let paren = 0;
  let inFragmentDef = false;
  let pendingAlias: string | undefined;
  for (let i = 0; i < sig.length; i++) {
    const t = sig[i];
    if (t.text === '(') paren += 1;
    else if (t.text === ')') paren = Math.max(0, paren - 1);
    else if (paren > 0) continue;
    else if (t.text === '{') depth += 1;
    else if (t.text === '}') {
      depth = Math.max(0, depth - 1);
      if (depth === 0) inFragmentDef = false;
    } else if (t.kind === 'keyword' && t.text === 'fragment' && depth === 0) {
      inFragmentDef = true;
      const name = sig[i + 1];
      if (name) fragments.push(name.text);
    } else if (t.text === '...' && sig[i + 1]?.kind !== 'keyword') {
      spreads += 1;
    } else if (depth > 0 && !inFragmentDef && (t.kind === 'field' || t.kind === 'meta' || t.kind === 'alias')) {
      if (t.kind === 'alias') {
        pendingAlias = t.text;
      } else if (sig[i - 1]?.text !== '...') {
        fields.push({ depth, name: t.text, alias: pendingAlias });
        pendingAlias = undefined;
      }
    }
  }
  return { fields, fragments, spreads, maxDepth: fields.reduce((m, f) => Math.max(m, f.depth), 0) };
}
