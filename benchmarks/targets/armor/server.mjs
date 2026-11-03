// Benchmark target: the demo upstream's schema served by GraphQL Yoga, optionally protected by graphql-armor.
//   ARMOR_PROFILE=off      same server, no protection (latency baseline for armor)
//   ARMOR_PROFILE=default  graphql-armor 3.2.0 with its documented defaults (depth 6, aliases 15, tokens 1000,
//                          directives 50, cost 5000, field suggestions masked)
//   ARMOR_PROFILE=matched  armor with limits widened to the values Sentinel ships with
//                          (depth 15, aliases 50, tokens 5000, cost 20000), so the comparison is not just "defaults"
// DEMO_WORK_BUDGET aborts an operation after that many field resolutions (same fuse as demo/upstream/app.py).
import { createServer } from "node:http";
import { buildSchema, defaultFieldResolver } from "graphql";
import { createYoga } from "graphql-yoga";
import { EnvelopArmor } from "@escape.tech/graphql-armor";

const PORT = Number(process.env.PORT || 4001);
const PROFILE = process.env.ARMOR_PROFILE || "default";
const BUDGET = Number(process.env.DEMO_WORK_BUDGET || 0);
const [N_USERS, N_FRIENDS, N_POSTS, N_COMMENTS, N_REPLIES] = [200, 25, 600, 6, 3];

const SDL = `
type Query { me: User user(id: ID!): User users(first: Int = 10): [User!]! post(id: ID!): Post
  posts(first: Int = 10): [Post!]! product(id: ID!): Product products(first: Int = 10): [Product!]! }
type Mutation { login(email: String!, password: String!): AuthPayload! createPost(title: String!, body: String!): Post! }
type AuthPayload { token: String! user: User }
type User { id: ID! name: String! username: String! email: String! role: String! apiToken: String!
  friends(first: Int = 10): [User!]! posts(first: Int = 10): [Post!]! }
type Post { id: ID! title: String! body: String! author: User! comments(first: Int = 10): [Comment!]! }
type Comment { id: ID! text: String! author: User! replies(first: Int = 10): [Comment!]! }
type Product { id: ID! name: String! price: Float! stock: Int! }`;

// Deterministic data with the same sizes as demo/upstream/app.py.
let seed = 7;
const rnd = (n) => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return 1 + (seed % n); };
const USERS = {}, POSTS = {}, PRODUCTS = {};
for (let i = 1; i <= N_USERS; i++) USERS[i] = { id: `${i}`, name: `User ${i}`, username: `user${i}`, email: `user${i}@example.test`,
  role: "member", apiToken: `demo-token-${i}`, _friends: [], _posts: [] };
for (const u of Object.values(USERS)) u._friends = Array.from({ length: N_FRIENDS }, () => USERS[rnd(N_USERS)]);
for (let i = 1; i <= N_POSTS; i++) {
  const author = USERS[rnd(N_USERS)];
  const comments = Array.from({ length: N_COMMENTS }, (_, j) => ({ id: `${i}-${j}`, text: `Comment ${j}`, author: USERS[rnd(N_USERS)],
    _replies: Array.from({ length: N_REPLIES }, (_, k) => ({ id: `${i}-${j}-r${k}`, text: "Reply", author: USERS[rnd(N_USERS)], _replies: [] })) }));
  POSTS[i] = { id: `${i}`, title: `Post ${i}`, body: "Lorem ipsum", author, _comments: comments };
  author._posts.push(POSTS[i]);
}
for (let i = 1; i <= 30; i++) PRODUCTS[i] = { id: `${i}`, name: `Product ${i}`, price: 5 + i * 1.7, stock: 100 - i };

const lim = (a, args) => a.slice(0, Math.max(0, Math.min(args.first ?? 10, 1000)));
const first = (obj) => Object.values(obj);
const ROOT = {
  me: () => USERS[1], user: (_, { id }) => USERS[id], users: (_, a) => lim(first(USERS), a), post: (_, { id }) => POSTS[id],
  posts: (_, a) => lim(first(POSTS), a), product: (_, { id }) => PRODUCTS[id], products: (_, a) => lim(first(PRODUCTS), a),
  login: () => ({ token: "demo-session-token", user: USERS[1] }),
  createPost: (_, { title, body }) => ({ id: "new", title, body, author: USERS[1], _comments: [] }),
};
const FIELD = { "User.friends": (o, a) => lim(o._friends, a), "User.posts": (o, a) => lim(o._posts, a),
  "Post.comments": (o, a) => lim(o._comments, a), "Comment.replies": (o, a) => lim(o._replies, a) };

const STATS = { operations: 0, work: 0, aborted: 0, requests: 0 };
const schema = buildSchema(SDL);
// Count every field resolution (like the Python middleware) and enforce the optional fuse.
for (const [tname, type] of Object.entries(schema.getTypeMap())) {
  if (!type.getFields || tname.startsWith("__")) continue;
  for (const [fname, field] of Object.entries(type.getFields())) {
    const base = tname === "Query" || tname === "Mutation" ? ROOT[fname] : FIELD[`${tname}.${fname}`];
    const inner = base ? (src, args, ctx, info) => (tname === "Query" || tname === "Mutation" ? base(src, args) : base(src, args))
      : defaultFieldResolver;
    field.resolve = (src, args, ctx, info) => {
      const w = ctx.__work;
      w.n++; STATS.work++;
      if (BUDGET && w.n > BUDGET) {
        if (!w.aborted) { w.aborted = true; STATS.aborted++; }
        throw new Error("work budget exceeded");
      }
      return inner(src, args, ctx, info);
    };
  }
}

const profiles = {
  off: null,
  default: {},
  matched: { maxDepth: { n: 15 }, maxAliases: { n: 50 }, maxTokens: { n: 5000 }, costLimit: { maxCost: 20000 }, maxDirectives: { n: 50 } },
};
if (!(PROFILE in profiles)) throw new Error(`unknown ARMOR_PROFILE ${PROFILE}`);
const plugins = [{ onExecute() { STATS.operations++; } }];
if (profiles[PROFILE]) plugins.push(...new EnvelopArmor(profiles[PROFILE]).protect().plugins);

const yoga = createYoga({
  schema, plugins, batching: { limit: 1000 }, graphiql: false, landingPage: false, maskedErrors: false, logging: false,
  context: () => ({ __work: { n: 0, aborted: false } }),
});
createServer((req, res) => {
  if (req.url === "/health") { res.end('{"status":"ok"}'); return; }
  if (req.url === "/__stats") { res.setHeader("content-type", "application/json"); res.end(JSON.stringify(STATS)); return; }
  STATS.requests++;
  yoga(req, res);
}).listen(PORT, "0.0.0.0", () => console.log(`armor target profile=${PROFILE} on :${PORT}`));
