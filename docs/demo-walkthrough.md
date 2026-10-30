# Demo walkthrough (about 3 minutes)

Start the stack (`docker compose up --build`, or `python scripts/dev.py` + `cd dashboard && npm run dev`).
Dashboard: <http://localhost:8080> (Docker) or <http://localhost:3000> (dev).

1. **Landing page** (`/`): the Decision Console replays recorded output of the shipped engine for six sample
   operations (pick one, or press Replay): parse, features, rule points, model probability, blended score, decision and
   what the gateway does. The "evidence" and "why the model never decides alone" charts are drawn live from the public
   `/api/evaluation`.
2. **Analyze** (`/app/analyze`): load *Ordinary query* → **Analyze (dry run)**: SAFE, ALLOW, features listed.
   Deep link: `/app/analyze?example=deep&run=dry`.
3. Load *Alias batching* → dry run: BLOCK, CRITICAL (about 93/100). No hard limit is hit at 24 aliases; the alias,
   breadth and model contributions push the score over the CRITICAL threshold. "Why this decision" shows points per rule.
4. Load *Deep nesting* → **Send through gateway** six times quickly: the first calls are forwarded (THROTTLE tier,
   real upstream data), then `429` with `Retry-After` once the per-client quota (5/min) is spent.
5. **Events** (`/app/events`): filter by decision, open an event: query, score breakdown, extracted features, upstream
   status, the client's recent history. Toggle **Go live** and send more requests from a terminal:

   ```bash
   python scripts/e2e_check.py
   ```
6. **Overview**: counts, decisions, risk tiers and top signals computed from stored events only.
7. **Policies**: the effective limits, tiers and actions from `/api/config` (read-only on purpose).
8. **Evaluation**: methods compared, confusion matrices, per-category detection, limitations.

Talking points: BLOCK never reaches the upstream (event shows no upstream status); without an upstream the gateway
returns 503; the classifier alone looks perfect but does not generalise to unseen attack types, which is why the
shipped score is a blend.
