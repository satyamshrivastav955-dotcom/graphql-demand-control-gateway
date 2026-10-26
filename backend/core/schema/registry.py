"""
Enterprise GraphQL SDL Schema Registry and Type Cycle Detector.
Manages schema registration, validation, introspection control,
and detects circular type references (e.g., User -> Post -> User) that enable nested DoS attacks.
"""
from typing import Dict, Set, List, Optional
import os
import logging
from graphql import (
    GraphQLSchema,
    build_schema,
    validate,
    parse,
    get_named_type,
    is_object_type,
)

logger = logging.getLogger(__name__)

DEFAULT_ENTERPRISE_SCHEMA_SDL = """
type Query {
    user(id: ID, name: String): User
    users(limit: Int): [User]
    post(id: ID): Post
    posts(limit: Int): [Post]
    comment(id: ID): Comment
}

type Mutation {
    createUser(name: String!, email: String!): User
    deleteUser(id: ID!): Boolean
    createPost(title: String!, content: String!): Post
}

type User {
    id: ID!
    name: String!
    email: String!
    posts: [Post]
    friends: [User]
}

type Post {
    id: ID!
    title: String!
    content: String
    author: User!
    comments: [Comment]
}

type Comment {
    id: ID!
    text: String!
    author: User!
    post: Post!
}
"""


class SchemaRegistry:
    """
    Central registry for GraphQL SDL schemas.
    Analyzes type graphs to identify recursive circular relationships
    and validates queries against registered schemas.
    """
    def __init__(self, sdl: Optional[str] = None):
        self._schema: Optional[GraphQLSchema] = None
        self._type_graph: Dict[str, Set[str]] = {}
        self._cycles: List[List[str]] = []
        
        if sdl:
            self.load_schema_from_string(sdl)
        else:
            self.load_schema_from_string(DEFAULT_ENTERPRISE_SCHEMA_SDL)

    @property
    def schema(self) -> Optional[GraphQLSchema]:
        return self._schema

    @property
    def type_graph(self) -> Dict[str, Set[str]]:
        return self._type_graph

    @property
    def cycles(self) -> List[List[str]]:
        return self._cycles

    def load_schema_from_string(self, sdl: str) -> GraphQLSchema:
        """Parse SDL string and build GraphQLSchema."""
        try:
            self._schema = build_schema(sdl)
            self._build_type_graph()
            self._detect_cycles()
            logger.info("Schema loaded and analyzed successfully.")
            return self._schema
        except Exception as e:
            logger.error(f"Failed to load schema from SDL: {e}")
            raise

    def load_schema_from_file(self, file_path: str) -> GraphQLSchema:
        """Load and parse SDL schema from a .graphql file."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Schema file not found: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            sdl = f.read()
        return self.load_schema_from_string(sdl)

    def _build_type_graph(self):
        """Build directed adjacency list between Object types in the schema."""
        self._type_graph = {}
        if not self._schema:
            return

        type_map = self._schema.type_map
        for type_name, type_def in type_map.items():
            if type_name.startswith("__") or type_name in ("Query", "Mutation", "Subscription"):
                continue
            if is_object_type(type_def):
                self._type_graph[type_name] = set()
                for field_name, field in type_def.fields.items():
                    named_target = get_named_type(field.type)
                    target_name = named_target.name
                    if is_object_type(named_target) and not target_name.startswith("__"):
                        self._type_graph[type_name].add(target_name)

    def _detect_cycles(self):
        """Find circular paths in the type graph using DFS."""
        self._cycles = []
        visited = set()
        rec_stack = []

        def dfs(node: str):
            visited.add(node)
            rec_stack.append(node)

            for neighbor in sorted(self._type_graph.get(node, set())):
                if neighbor in rec_stack:
                    idx = rec_stack.index(neighbor)
                    cycle_path = rec_stack[idx:] + [neighbor]
                    if cycle_path not in self._cycles:
                        self._cycles.append(cycle_path)
                elif neighbor not in visited:
                    dfs(neighbor)

            rec_stack.pop()

        for node in sorted(self._type_graph.keys()):
            visited.clear()
            dfs(node)

    def has_circular_reference(self) -> bool:
        """Returns True if any type cycle exists in the schema."""
        return len(self._cycles) > 0

    def validate_query(self, query: str) -> List[str]:
        """Validate query syntax and type validity against registered schema."""
        if not self._schema:
            return []
        try:
            doc = parse(query)
            errors = validate(self._schema, doc)
            return [err.message for err in errors]
        except Exception as e:
            return [str(e)]
