"""The Envoy ext_proc service, exercised over a real gRPC channel with synthetic Envoy messages."""
import json

import pytest

grpc = pytest.importorskip("grpc")
pytest.importorskip("envoy.service.ext_proc.v3.external_processor_pb2")

from envoy.config.core.v3 import base_pb2  # noqa: E402
from envoy.service.ext_proc.v3 import external_processor_pb2 as pb  # noqa: E402
from envoy.service.ext_proc.v3 import external_processor_pb2_grpc as pb_grpc  # noqa: E402

from backend.core.config import Settings  # noqa: E402
from backend.integrations.envoy_extproc import serve  # noqa: E402
from sentinel_core import build_manifest  # noqa: E402
from sentinel_core.persisted import sha256  # noqa: E402

from .conftest import deep_query  # noqa: E402


def call(stub, body: dict | list | bytes, ip="203.0.113.7"):
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()

    def reqs():
        hdrs = base_pb2.HeaderMap(headers=[base_pb2.HeaderValue(key=":method", raw_value=b"POST"),
                                           base_pb2.HeaderValue(key="x-envoy-external-address", raw_value=ip.encode())])
        yield pb.ProcessingRequest(request_headers=pb.HttpHeaders(headers=hdrs))
        yield pb.ProcessingRequest(request_body=pb.HttpBody(body=raw, end_of_stream=True))

    return list(stub.Process(reqs()))


@pytest.fixture
def stub(tmp_path):
    servers = []

    def factory(overrides=None):
        import socket
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        settings = Settings.model_validate({"throttle": {"rate_limit": 1000, "risky_quota": 1000}, **(overrides or {})})
        server = serve(port=port, metrics_port=None, settings=settings)
        servers.append(server)
        channel = grpc.insecure_channel(f"127.0.0.1:{port}")
        return pb_grpc.ExternalProcessorStub(channel), server

    yield factory
    for s in servers:
        s.stop(0)


def test_benign_operation_continues_to_the_upstream(stub):
    st, _ = stub()
    out = call(st, {"query": "{ users(first: 2) { name } }"})
    assert out[-1].WhichOneof("response") == "request_body"


def test_attack_gets_an_immediate_403_with_owasp_explanations(stub):
    st, _ = stub()
    out = call(st, {"query": deep_query(25)})[-1]
    assert out.WhichOneof("response") == "immediate_response"
    imm = out.immediate_response
    assert imm.status.code == 403
    sec = json.loads(imm.body)["extensions"]["security"]
    assert sec["decision"] == "BLOCK" and "API4" in sec["owasp"]
    assert {h.header.key: h.header.raw_value for h in imm.headers.set_headers}["x-sentinel-decision"] == b"BLOCK"


def test_malformed_and_invalid_bodies_are_rejected(stub):
    st, _ = stub()
    assert call(st, b"not json")[-1].immediate_response.status.code == 400
    assert call(st, {"nope": 1})[-1].immediate_response.status.code == 400
    assert call(st, {"query": "{ me"})[-1].immediate_response.status.code == 400


def test_batches_are_evaluated(stub):
    st, _ = stub()
    ok = call(st, [{"query": "{ users(first: 1) { name } }"}] * 3)[-1]
    assert ok.WhichOneof("response") == "request_body"
    big = call(st, [{"query": "{ users(first: 1) { name } }"}] * 11)[-1]
    assert big.immediate_response.status.code == 403


def test_shadow_mode_continues_but_records(stub):
    st, server = stub({"gateway": {"enforcement": "shadow"}})
    out = call(st, {"query": deep_query(25)})[-1]
    assert out.WhichOneof("response") == "request_body"
    assert 'enforced="shadow"' in server.sentinel_service.metrics.render()


def test_rate_limit_returns_429_with_retry_after(stub):
    st, _ = stub({"throttle": {"rate_limit": 2, "risky_quota": 1000}})
    codes = [call(st, {"query": "{ users(first: 1) { name } }"})[-1] for _ in range(3)]
    assert codes[-1].immediate_response.status.code == 429
    assert any(h.header.key == "retry-after" for h in codes[-1].immediate_response.headers.set_headers)


def test_hash_only_persisted_query_is_resolved_by_body_mutation(stub, tmp_path):
    q = "query Me { me { id } }"
    f = tmp_path / "m.json"
    f.write_text(json.dumps(build_manifest([q])), encoding="utf-8")
    st, _ = stub({"persisted_queries": {"mode": "enforce", "manifest": str(f)}})
    out = call(st, {"extensions": {"persistedQuery": {"version": 1, "sha256Hash": sha256(q)}}})[-1]
    assert out.WhichOneof("response") == "request_body"
    assert json.loads(out.request_body.response.body_mutation.body)["query"] == q
    assert call(st, {"query": "{ users(first: 1) { name } }"})[-1].immediate_response.status.code == 403
