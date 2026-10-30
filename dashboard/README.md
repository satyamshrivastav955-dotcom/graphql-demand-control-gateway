# GraphQL Sentinel dashboard

React 19 + TypeScript + Tailwind, built with Vite and tested with Vitest. One design system, two surfaces:

* **`/` the public landing page**: dark, high-contrast. A hero stage draws the parsed operation as an SVG tree, scores
  it and stamps the decision. It replays *recorded* engine output (`src/data/demoSamples.json`, produced by
  `python scripts/export_demo_samples.py`); every number on the page comes from that file or from the public
  `GET /api/evaluation`, with honest empty/error states.
* **`/app/*` the dashboard** (Overview, Analyze, Events, Policies, Evaluation), behind a token gate: collapsible rail,
  Ctrl/Cmd+K command palette, dense tables with `j`/`k`/Enter, an event inspector, and an Analyze editor that marks the
  lines that triggered rules. First-run states offer a copyable `curl` and a one-click test request.

Design system: near-black canvas (`#08090a`) with surfaces that step by lightness, 1px hairlines, radius capped at 8px,
white primary buttons and no brand hue. Colour is reserved for data: allow, throttle and block (and the risk tiers).
Numerals are tabular. Typography is self-hosted Geist Sans and Geist Mono (`@fontsource-variable/*`, OFL), so the strict
CSP in `docker/nginx.conf` needs no external origin. Motion honours `prefers-reduced-motion` (the stage shows its final
frame). Dashboard routes and everything below the landing hero are lazy chunks.

## Develop

```bash
npm install
npm run dev        # http://localhost:3000, proxies /api and /graphql-proxy to http://localhost:8000
```

Start the backend first (`python scripts/dev.py` prints a session token for the dashboard login). To point at a different
gateway set `VITE_API_URL` at build time (see `.env.example`), or point the dev proxy elsewhere with `SENTINEL_GATEWAY_URL`; by default requests are same-origin.

## Test and build

```bash
npm run lint       # ESLint (typescript-eslint, react-hooks)
npm run typecheck  # tsc --noEmit
npm test           # Vitest + Testing Library + axe-core (jsdom)
npm run build      # outputs dist/ (no inline scripts, no third-party requests: satisfies docker/nginx.conf CSP)
npm run preview    # serve dist/ on :4173 with the same API proxy
```

The production build is a static SPA. Serve it with a fallback to `index.html` so client-side routes such as `/app/events`
work on reload (`docker/nginx.conf` does).

## Quality gates

Automated (`npm run lint`, `typecheck`, `test`, `npm audit`, all run in CI): ESLint, `tsc`, 62 Vitest tests (including an
axe-core pass over the landing page, every dashboard route and the sign-in gate in jsdom, the command palette, `j`/`k`
row navigation, `lineMarks` and the reduced-motion demo) and a dependency audit.

Measured by hand against the production build (`dist/`) served by the gateway itself (`python scripts/dev.py`), driven in
headless Edge:

* **axe-core with colour contrast, real layout**: 0 violations on the landing page, Overview, Analyze, Events, Policies
  and Evaluation at 1440 and 390 px. Event detail, the sign-in gate and the shadow banner are covered by the jsdom pass
  only (no contrast check).
* **Lighthouse on `/`** (one run each, Edge): desktop 100 performance, 100 accessibility, 100 best practices, 100 SEO.
  Mobile (simulated slow 4G, 4x CPU) 93 / 100 / 100 / 100, with Total Blocking Time (about 320 ms) the limiter.
* **Layouts**: checked at 1440, 1024, 768 and 390 px; `prefers-reduced-motion` renders the final frame.
* **Bundle**: landing entry JS 88.6 kB gzip.

Not covered: real screen-reader testing, Safari/Firefox, the dashboard on a 768 px viewport.
