"""The ground-truth work counter must equal the real executor's field-resolution count."""
import pytest

from benchmarks.corpus.ground_truth import work
from demo.upstream import app as demo

QUERIES = [
    '{ user(id:"3") { id name } }',
    '{ users(first: 4) { id friends(first: 3) { id name } } }',
    '{ users(first: 2) { friends(first: 5) { friends(first: 2) { id } } } }',
    '{ posts(first: 3) { title author { name posts(first: 2) { id } } comments(first: 2) { text replies { id } } } }',
    '{ a: me { id } b: me { id } c: me { name } }',
    '{ me { id id name } }',
    '{ users(first: 2) { ...F } } fragment F on User { id friends(first: 2) { ...G } } fragment G on User { name }',
    '{ users(first: 2) { id @skip(if: true) name @include(if: true) __typename } }',
    'mutation { login(email: "a", password: "b") { token user { id } } }',
    'mutation { createPost(title: "t", body: "b") { id author { name } comments { id } } }',
    '{ products(first: 5) { id name } product(id: "2") { id price } }',
    '{ users(first: 2) { a: friends(first: 3) { id } b: friends(first: 3) { name } } }',
    '{ users(first: 2) { friends(first: 3) { id } friends(first: 3) { name } } }',
]


@pytest.mark.parametrize("query", QUERIES)
def test_matches_real_execution(query):
    before = demo.STATS["work"]
    demo._execute({"query": query})
    assert work(query) == demo.STATS["work"] - before


def test_huge_operation_counted_without_executing():
    q = "{ users(first: 1000) { " + "friends(first: 1000) { " * 9 + "id" + " }" * 9 + " } }"
    assert work(q) > 10 ** 12
