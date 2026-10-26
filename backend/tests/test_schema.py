import pytest
import os
import tempfile
from backend.core.schema.registry import SchemaRegistry

def test_default_schema_loading():
    registry = SchemaRegistry()
    assert registry.schema is not None
    assert "User" in registry.schema.type_map
    assert "Post" in registry.schema.type_map
    assert registry.has_circular_reference() is True

def test_type_cycle_detection():
    registry = SchemaRegistry()
    cycles = registry.cycles
    assert len(cycles) > 0
    # User -> Post -> User is a cycle
    has_user_post_cycle = any("User" in c and "Post" in c for c in cycles)
    assert has_user_post_cycle is True

def test_acyclic_schema_detection():
    acyclic_sdl = """
    type Query {
        user: User
    }
    type User {
        id: ID!
        profile: Profile
    }
    type Profile {
        bio: String
    }
    """
    registry = SchemaRegistry(acyclic_sdl)
    assert registry.has_circular_reference() is False
    assert len(registry.cycles) == 0

def test_schema_query_validation_success():
    registry = SchemaRegistry()
    valid_query = "query { user(id: \"1\") { id name posts { title } } }"
    errors = registry.validate_query(valid_query)
    assert len(errors) == 0

def test_schema_query_validation_failure():
    registry = SchemaRegistry()
    invalid_query = "query { user(id: \"1\") { nonExistentField } }"
    errors = registry.validate_query(invalid_query)
    assert len(errors) > 0
    assert any("nonExistentField" in err for err in errors)

def test_schema_load_from_file():
    sdl_content = """
    type Query {
        ping: String
    }
    """
    with tempfile.NamedTemporaryFile("w", suffix=".graphql", delete=False) as f:
        f.write(sdl_content)
        temp_path = f.name

    try:
        registry = SchemaRegistry()
        registry.load_schema_from_file(temp_path)
        assert "Query" in registry.schema.type_map
        assert registry.validate_query("query { ping }") == []
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
