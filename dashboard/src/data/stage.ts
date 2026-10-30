import type { DemoSample } from './demo';

export interface StageNode {
  id: number;
  x: number;
  y: number;
  parent: number | null;
}

export interface StageLayout {
  nodes: StageNode[];
  /** Fields the server would execute that are not drawn (the tree is truncated, never faked). */
  hidden: number;
}

/** Drawing area for the AST inside the 640x390 stage. */
const X0 = 62;
const X1 = 392;
const Y0 = 70;
const Y1 = 330;

/** Levels of the given widths, each level evenly spread vertically; a node's parent is the proportionally nearest node above. */
function tree(levels: number[]): StageNode[] {
  const nodes: StageNode[] = [];
  let prevStart = 0;
  let prevCount = 0;
  levels.forEach((count, level) => {
    const x = X0 + (levels.length === 1 ? 0 : (level * (X1 - X0)) / (levels.length - 1));
    const start = nodes.length;
    for (let j = 0; j < count; j++) {
      const y = count === 1 ? (Y0 + Y1) / 2 : Y0 + (j * (Y1 - Y0)) / (count - 1);
      const parent = level === 0 ? null : prevStart + Math.min(prevCount - 1, Math.floor((j * prevCount) / count));
      nodes.push({ id: nodes.length, x, y, parent });
    }
    prevStart = start;
    prevCount = count;
  });
  return nodes;
}

/** A single chain stepping down and right: one node per level of nesting. */
function chain(depth: number): StageNode[] {
  const n = Math.max(2, depth);
  return Array.from({ length: n }, (_, i) => ({
    id: i,
    x: X0 + (i * (X1 - X0)) / (n - 1),
    y: Y0 + 20 + (i * (Y1 - Y0 - 40)) / (n - 1),
    parent: i === 0 ? null : i - 1,
  }));
}

/**
 * The AST drawn for a recorded sample. Shapes follow the sample's real features (depth, alias count, field count);
 * when the operation is larger than what can be drawn, `hidden` carries the remainder so the counter stays honest.
 */
export function layoutFor(sample: DemoSample): StageLayout {
  const f = sample.features;
  const fields = f.field_count ?? 0;
  let nodes: StageNode[];
  switch (sample.id) {
    case 'ordinary':
      nodes = tree([1, 3, 2]);
      break;
    case 'nesting':
      nodes = chain(f.max_depth ?? 10);
      break;
    case 'aliases':
    case 'stuffing': {
      const shown = Math.min(f.alias_count ?? 24, 30);
      nodes = tree([1, shown]);
      break;
    }
    case 'fragments':
      nodes = tree([1, 3, 9, 27]);
      break;
    case 'recon':
      nodes = tree([1, 1, 2, 2, 2]);
      break;
    default:
      nodes = tree([1, Math.min(Math.max(2, fields), 12)]);
  }
  return { nodes, hidden: Math.max(0, fields - nodes.length) };
}

/** Phase start times in ms: 0 packet, 1 parse, 2 score, 3 decide, 4 settled. */
export const PHASE_AT = [0, 450, 1750, 2650, 3350] as const;
/** After settling, auto-advance to the next sample once this long has passed. */
export const HOLD_MS = 6500;
