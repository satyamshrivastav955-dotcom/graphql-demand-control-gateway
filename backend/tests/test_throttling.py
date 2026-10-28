import pytest
import time
from backend.core.throttling.token_bucket import TokenBucket, TokenBucketLimiter
from backend.api.gateway import GraphQLGateway

def test_token_bucket_consume_and_refill():
    # Capacity 5, refill rate 10 tokens/sec
    bucket = TokenBucket(capacity=5, refill_rate=10)
    assert bucket.remaining == 5.0
    allowed, retry = bucket.consume(3)
    assert allowed is True
    assert retry == 0.0
    assert bucket.remaining == 2.0

def test_token_bucket_exhaustion_and_retry_after():
    bucket = TokenBucket(capacity=2, refill_rate=1)
    allowed1, _ = bucket.consume(2)
    assert allowed1 is True
    # Next consume should fail
    allowed2, retry_after = bucket.consume(1)
    assert allowed2 is False
    assert retry_after > 0

def test_token_bucket_limiter_multi_client():
    limiter = TokenBucketLimiter(rate_limit=5, window_seconds=10, burst_multiplier=1.0)
    # Client A consumes 5 tokens
    for _ in range(5):
        allowed, _ = limiter.check("client_A")
        assert allowed is True

    # 6th attempt for client_A fails
    allowed_fail, meta_a = limiter.check("client_A")
    assert allowed_fail is False
    assert meta_a["remaining"] == 0.0

    # Client B still has full quota
    allowed_b, meta_b = limiter.check("client_B")
    assert allowed_b is True
    assert meta_b["remaining"] > 0

@pytest.mark.anyio
async def test_gateway_throttles_when_rate_exceeded():
    config = {
        "security": {
            "throttling": {
                "rate_limit": 2,
                "window": 60
            },
            "policy": {"default_action": "ALLOW"}
        },
        "logging": {"save_path": "backend/storage/logs/test_decisions.jsonl"}
    }
    gateway = GraphQLGateway(config, {})
    client_info = {"ip": "192.168.1.100", "client_id": "rate_tester"}
    req = {"query": "query { user { id } }"}

    # First 2 requests pass (or up to capacity: 2 * 1.2 = 2.4, so 2 requests)
    res1 = await gateway.process_request(req, client_info)
    assert res1.get("extensions", {}).get("security", {}).get("decision") == "ALLOW"
    res2 = await gateway.process_request(req, client_info)
    assert res2.get("extensions", {}).get("security", {}).get("decision") == "ALLOW"

    # 3rd request gets throttled
    res3 = await gateway.process_request(req, client_info)
    assert res3.get("extensions", {}).get("security", {}).get("decision") == "THROTTLE"
    assert "Rate limit exceeded" in res3["errors"][0]["message"]
