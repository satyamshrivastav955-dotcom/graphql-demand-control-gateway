"""A small, deliberately unprotected GraphQL API used as the demo/test target.

It has no depth, cost or introspection limits, so it shows what Sentinel protects:
cyclic relations (User.friends, Comment.replies) let a client nest queries arbitrarily
deep. Run it only on a private network (docker compose does).
"""
from __future__ import annotations

import random
from typing import Any, Dict

from fastapi import FastAPI, Request
from graphql import build_schema, graphql_sync

SDL = """
type Query {
  me: User
  user(id: ID!): User
  users(first: Int = 10): [User!]!
  post(id: ID!): Post
  posts(first: Int = 10): [Post!]!
  product(id: ID!): Product
  products(first: Int = 10): [Product!]!
}
type Mutation {
  login(email: String!, password: String!): AuthPayload!
  createPost(title: String!, body: String!): Post!
}
type AuthPayload { token: String!  user: User }
type User {
  id: ID!  name: String!  username: String!  email: String!  role: String!  apiToken: String!
  friends(first: Int = 10): [User!]!
  posts(first: Int = 10): [Post!]!
}
type Post { id: ID!  title: String!  body: String!  author: User!  comments(first: Int = 10): [Comment!]! }
type Comment { id: ID!  text: String!  author: User!  replies(first: Int = 10): [Comment!]! }
type Product { id: ID!  name: String!  price: Float!  stock: Int! }
"""

_rng = random.Random(7)
USERS: Dict[str, dict] = {}
POSTS: Dict[str, dict] = {}
PRODUCTS: Dict[str, dict] = {}


def _seed() -> None:
    for i in range(1, 41):
        USERS[str(i)] = {"id": str(i), "name": f"User {i}", "username": f"user{i}", "email": f"user{i}@example.test",
                         "role": "member", "apiToken": f"demo-token-{i}", "_friends": [], "_posts": []}
    for u in USERS.values():
        u["_friends"] = [USERS[str(_rng.randint(1, 40))] for _ in range(6)]
    for i in range(1, 81):
        author = USERS[str(_rng.randint(1, 40))]
        comments = []
        for j in range(4):
            c = {"id": f"{i}-{j}", "text": f"Comment {j} on post {i}", "author": USERS[str(_rng.randint(1, 40))], "_replies": []}
            c["_replies"] = [{"id": f"{i}-{j}-r{k}", "text": "Reply", "author": USERS[str(_rng.randint(1, 40))], "_replies": []}
                             for k in range(2)]
            comments.append(c)
        post = {"id": str(i), "title": f"Post {i}", "body": "Lorem ipsum dolor sit amet.", "author": author, "_comments": comments}
        POSTS[str(i)] = post
        author["_posts"].append(post)
    for i in range(1, 31):
        PRODUCTS[str(i)] = {"id": str(i), "name": f"Product {i}", "price": round(5 + i * 1.7, 2), "stock": 100 - i}


_seed()


def _limit(items, args):
    return items[: max(0, min(int(args.get("first", 10)), 1000))]


def _field(name):
    def resolve(obj, info, **args):
        return _limit(obj[name], args)
    return resolve


ROOT: Dict[str, Any] = {
    "me": lambda info: USERS["1"],
    "user": lambda info, id: USERS.get(id),
    "users": lambda info, first=10: _limit(list(USERS.values()), {"first": first}),
    "post": lambda info, id: POSTS.get(id),
    "posts": lambda info, first=10: _limit(list(POSTS.values()), {"first": first}),
    "product": lambda info, id: PRODUCTS.get(id),
    "products": lambda info, first=10: _limit(list(PRODUCTS.values()), {"first": first}),
    "login": lambda info, email, password: {"token": "demo-session-token", "user": USERS["1"]},
    "createPost": lambda info, title, body: {"id": "new", "title": title, "body": body, "author": USERS["1"], "_comments": []},
}

schema = build_schema(SDL)
for type_name, fields in {"User": {"friends": "_friends", "posts": "_posts"},
                          "Post": {"comments": "_comments"}, "Comment": {"replies": "_replies"}}.items():
    for fname, key in fields.items():
        schema.type_map[type_name].fields[fname].resolve = _field(key)

app = FastAPI(title="Demo GraphQL upstream", docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/graphql")
async def graphql_endpoint(request: Request):
    body = await request.json()
    result = graphql_sync(schema, body.get("query", ""), root_value=ROOT, variable_values=body.get("variables"),
                          operation_name=body.get("operationName"))
    payload: Dict[str, Any] = {"data": result.data}
    if result.errors:
        payload["errors"] = [{"message": e.message} for e in result.errors]
    return payload
