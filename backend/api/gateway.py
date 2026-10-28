import json
import os
import time
import logging
import uuid
from datetime import datetime
import httpx
from ..core.features.feature_pipeline import FeaturePipeline
from ..core.features.behavioral import set_behavioral_store
from ..core.features.behavioral_store import BehavioralStore
from ..core.security_engine.scorer import SecurityScorer
from ..core.security_engine.policy import SecurityPolicy
from ..core.security_engine.explainability import ExplainabilityEngine
from ..core.throttling.token_bucket import TokenBucketLimiter
from ..core.quarantine.manager import QuarantineManager
from ..alerts.webhook_dispatcher import WebhookDispatcher
from ..storage.ring_buffer import LogRingBuffer, ring_buffer as default_ring_buffer

logger = logging.getLogger(__name__)

class GraphQLGateway:
    def __init__(self, config: dict, model_paths: dict, http_client: httpx.AsyncClient = None, ring_buffer: LogRingBuffer = None):
        self.config = config
        self.ring_buffer = ring_buffer if ring_buffer is not None else default_ring_buffer
        self.feature_pipeline = FeaturePipeline()
        self.scorer = SecurityScorer(model_paths, config)  # Pass config
        self.policy = SecurityPolicy(config.get('security', {}).get('policy', {}))
        self.explainer = ExplainabilityEngine()
        self.log_path = config.get('logging', {}).get('save_path', 'backend/storage/logs/decisions.jsonl')

        # Upstream proxy configuration
        upstream_cfg = config.get('upstream', {})
        self.upstream_url = upstream_cfg.get('url') or os.environ.get('UPSTREAM_GRAPHQL_URL')
        self.upstream_timeout = float(upstream_cfg.get('timeout_seconds', 10.0))
        limits = httpx.Limits(
            max_connections=int(upstream_cfg.get('max_connections', 100)),
            max_keepalive_connections=int(upstream_cfg.get('max_keepalive_connections', 20))
        )
        self.http_client = http_client or httpx.AsyncClient(limits=limits, timeout=self.upstream_timeout)
        self._owns_client = http_client is None

        # Batch security policy
        batch_cfg = config.get('security', {}).get('batch', {})
        self.allow_batching = bool(batch_cfg.get('allow_batching', True))
        self.max_batch_size = int(batch_cfg.get('max_operations', 10))

        # Token Bucket Throttling Policy
        throttling_cfg = config.get('security', {}).get('throttling', {})
        self.rate_limiter = TokenBucketLimiter(
            rate_limit=int(throttling_cfg.get('rate_limit', 100)),
            window_seconds=int(throttling_cfg.get('window', 60))
        )

        # Automated Quarantine & Dynamic Blacklist Manager
        self.quarantine_manager = QuarantineManager()

        # Webhook Alert Dispatcher
        alerts_cfg = config.get('alerts', {})
        webhook_url = alerts_cfg.get('webhook_url') or os.environ.get('ALERT_WEBHOOK_URL')
        self.webhook_dispatcher = WebhookDispatcher(
            webhook_url=webhook_url,
            enabled=bool(alerts_cfg.get('enabled', False) or webhook_url),
            min_severity=alerts_cfg.get('min_severity', 'CRITICAL'),
            cooldown_seconds=float(alerts_cfg.get('cooldown_seconds', 60.0)),
            http_client=self.http_client
        )

        # Ensure the log directory exists before the first write
        if self.log_path:
            os.makedirs(os.path.dirname(self.log_path) or ".", exist_ok=True)
        
        # Initialize behavioral store
        self.behavioral_store = BehavioralStore(window_seconds=60, max_history=100)
        set_behavioral_store(self.behavioral_store)
        
        # Log counter for unique IDs
        self.log_counter = 0

    async def close(self):
        """Close managed HTTP connection pool."""
        if self._owns_client and self.http_client:
            await self.http_client.aclose()

    async def process_batch_request(self, batch_data: list, client_info: dict):
        """Process and enforce security policy on a batch GraphQL array request."""
        start_time = time.time()
        client_id = client_info.get('client_id', 'unknown')
        ip = client_info.get('ip', 'unknown')
        actor_key = ip if ip != 'unknown' else client_id

        # 0. Check active quarantine status
        is_quarantined, q_record = self.quarantine_manager.is_quarantined(client_id, ip)
        if is_quarantined:
            self.log_counter += 1
            err_entry = {
                "id": str(uuid.uuid4()),
                "index": self.log_counter,
                "timestamp": datetime.now().isoformat(),
                "client_id": client_id,
                "ip": ip,
                "query": "[BATCH_QUARANTINED_BLOCKED]",
                "features": {"quarantined": 1, "batch_size": len(batch_data)},
                "scores": {"ensemble_score": 100.0, "risk_tier": "CRITICAL"},
                "decision": "BLOCK",
                "explanations": [{"feature": "client_quarantine", "score": 1.0, "description": f"Actor is quarantined: {q_record.reason}"}],
                "latency_ms": (time.time() - start_time) * 1000
            }
            self._log_decision(err_entry)
            return {
                "data": None,
                "errors": [{"message": f"Client is quarantined due to repeated violations: {q_record.reason}"}],
                "extensions": {
                    "security": {
                        "decision": "BLOCK",
                        "risk_tier": "CRITICAL",
                        "score": 100.0,
                        "quarantined": True,
                        "latency_ms": (time.time() - start_time) * 1000
                    }
                }
            }

        # 1. Batching Policy Disablement Check
        if not self.allow_batching:
            self.log_counter += 1
            err_entry = {
                "id": str(uuid.uuid4()),
                "index": self.log_counter,
                "timestamp": datetime.now().isoformat(),
                "client_id": client_id,
                "ip": ip,
                "query": "[BATCH_DISABLED]",
                "features": {"batch_size": len(batch_data)},
                "scores": {"ensemble_score": 90.0, "risk_tier": "HIGH_RISK"},
                "decision": "BLOCK",
                "explanations": [{"feature": "batch_query", "score": 1.0, "description": "Batch GraphQL requests are disallowed by policy"}],
                "latency_ms": (time.time() - start_time) * 1000
            }
            self._log_decision(err_entry)
            return {
                "data": None,
                "errors": [{"message": "Batch GraphQL requests are disabled by security policy"}],
                "extensions": {
                    "security": {
                        "decision": "BLOCK",
                        "risk_tier": "HIGH_RISK",
                        "score": 90.0,
                        "latency_ms": (time.time() - start_time) * 1000
                    }
                }
            }

        # 2. Maximum Operations Limit
        if len(batch_data) > self.max_batch_size:
            self.log_counter += 1
            err_entry = {
                "id": str(uuid.uuid4()),
                "index": self.log_counter,
                "timestamp": datetime.now().isoformat(),
                "client_id": client_id,
                "ip": ip,
                "query": f"[BATCH_OVERLOAD_ATTACK: {len(batch_data)} ops]",
                "features": {"batch_size": len(batch_data), "max_allowed": self.max_batch_size},
                "scores": {"ensemble_score": 95.0, "risk_tier": "CRITICAL"},
                "decision": "BLOCK",
                "explanations": [{"feature": "batch_overload", "score": 1.0, "description": f"Batch size ({len(batch_data)}) exceeds configured threshold ({self.max_batch_size})"}],
                "latency_ms": (time.time() - start_time) * 1000
            }
            self._log_decision(err_entry)
            return {
                "data": None,
                "errors": [{"message": f"Batch size ({len(batch_data)}) exceeds maximum allowed limit ({self.max_batch_size})"}],
                "extensions": {
                    "security": {
                        "decision": "BLOCK",
                        "risk_tier": "CRITICAL",
                        "score": 95.0,
                        "latency_ms": (time.time() - start_time) * 1000
                    }
                }
            }

        # 3. Rate Limit for batch
        is_allowed, rate_meta = self.rate_limiter.check(actor_key, cost=float(len(batch_data)))
        if not is_allowed:
            self.log_counter += 1
            err_entry = {
                "id": str(uuid.uuid4()),
                "index": self.log_counter,
                "timestamp": datetime.now().isoformat(),
                "client_id": client_id,
                "ip": ip,
                "query": f"[BATCH_RATE_LIMITED: {len(batch_data)} ops]",
                "features": {"rate_limited": 1, "retry_after": rate_meta["retry_after"]},
                "scores": {"ensemble_score": 80.0, "risk_tier": "HIGH_RISK"},
                "decision": "THROTTLE",
                "explanations": [{"feature": "rate_limit_exceeded", "score": 0.9, "description": f"Batch exhausted rate limit tokens. Retry after {rate_meta['retry_after']}s"}],
                "latency_ms": (time.time() - start_time) * 1000
            }
            self._log_decision(err_entry)
            return {
                "data": None,
                "errors": [{"message": f"Rate limit exceeded. Try again in {rate_meta['retry_after']} seconds."}],
                "extensions": {
                    "security": {
                        "decision": "THROTTLE",
                        "risk_tier": "HIGH_RISK",
                        "score": 80.0,
                        "retry_after_seconds": rate_meta["retry_after"],
                        "latency_ms": (time.time() - start_time) * 1000
                    }
                }
            }

        # 4. Process each query in batch
        batch_results = []
        for req in batch_data:
            res = await self.process_request(req, client_info, skip_rate_check=True)
            batch_results.append(res)
        return batch_results

    async def process_request(self, request_data: dict, client_info: dict, skip_rate_check: bool = False):
        start_time = time.time()
        query = request_data.get('query')

        if not isinstance(query, str) or not query.strip():
            return {"errors": [{"message": "No valid query provided"}]}

        client_id = client_info.get('client_id', 'unknown')
        ip = client_info.get('ip', 'unknown')
        actor_key = ip if ip != 'unknown' else client_id

        # 0a. Check active quarantine status
        is_quarantined, q_record = self.quarantine_manager.is_quarantined(client_id, ip)
        if is_quarantined:
            self.log_counter += 1
            log_entry = {
                "id": str(uuid.uuid4()),
                "index": self.log_counter,
                "timestamp": datetime.now().isoformat(),
                "client_id": client_id,
                "ip": ip,
                "query": "[QUARANTINED_ACTOR_BLOCKED]",
                "features": {"quarantined": 1, "remaining_seconds": q_record.remaining_seconds},
                "scores": {"ensemble_score": 100.0, "risk_tier": "CRITICAL"},
                "decision": "BLOCK",
                "explanations": [{
                    "feature": "client_quarantine",
                    "score": 1.0,
                    "description": f"Actor is quarantined: {q_record.reason}. Remaining: {q_record.remaining_seconds}s"
                }],
                "latency_ms": (time.time() - start_time) * 1000
            }
            self._log_decision(log_entry)
            return {
                "data": None,
                "errors": [{"message": f"Client is quarantined due to repeated violations: {q_record.reason}"}],
                "extensions": {
                    "security": {
                        "decision": "BLOCK",
                        "risk_tier": "CRITICAL",
                        "score": 100.0,
                        "quarantined": True,
                        "remaining_seconds": q_record.remaining_seconds,
                        "latency_ms": (time.time() - start_time) * 1000
                    }
                }
            }

        # 0b. Token Bucket Rate Limiting Check
        if not skip_rate_check:
            is_rate_allowed, rate_meta = self.rate_limiter.check(actor_key)
            if not is_rate_allowed:
                self.log_counter += 1
                log_entry = {
                    "id": str(uuid.uuid4()),
                    "index": self.log_counter,
                    "timestamp": datetime.now().isoformat(),
                    "client_id": client_id,
                    "ip": ip,
                    "query": query[:120],
                    "features": {"rate_limited": 1, "retry_after": rate_meta["retry_after"]},
                    "scores": {"ensemble_score": 80.0, "risk_tier": "HIGH_RISK"},
                    "decision": "THROTTLE",
                    "explanations": [{
                        "feature": "rate_limit_exceeded",
                        "score": 0.9,
                        "description": f"Rate limit quota exceeded. Remaining: 0, retry in {rate_meta['retry_after']}s"
                    }],
                    "latency_ms": (time.time() - start_time) * 1000
                }
                self._log_decision(log_entry)
                return {
                    "data": None,
                    "errors": [{"message": f"Rate limit exceeded. Try again in {rate_meta['retry_after']} seconds."}],
                    "extensions": {
                        "security": {
                            "decision": "THROTTLE",
                            "risk_tier": "HIGH_RISK",
                            "score": 80.0,
                            "retry_after_seconds": rate_meta["retry_after"],
                            "latency_ms": (time.time() - start_time) * 1000
                        }
                    }
                }

        try:
            # 1. Feature Extraction
            features = self.feature_pipeline.extract_features(query, client_id, {})
            
            if not features:
                return {"errors": [{"message": "Invalid GraphQL Query"}]}
    
            # 2. Scoring
            scores = self.scorer.score(features)
            
            # 3. Policy Decision
            decision = self.policy.decide(scores)
            
            # 4. Explanation
            explanations = self.explainer.explain(features, scores)
            
            # 5. Record in behavioral store
            is_error = decision == "BLOCK"
            self.behavioral_store.record_query(client_id, query, ip, is_error)
            
            # 6. Logging with unique ID
            self.log_counter += 1
            log_entry = {
                "id": str(uuid.uuid4()),  # Unique ID for each log
                "index": self.log_counter,  # Sequential index
                "timestamp": datetime.now().isoformat(),
                "client_id": client_id,
                "ip": ip,
                "query": query,
                "features": features,
                "scores": scores,
                "decision": decision,
                "explanations": explanations,
                "latency_ms": (time.time() - start_time) * 1000
            }
            self._log_decision(log_entry)
            
            # 7. Action
            if decision == "BLOCK":
                # Automated Quarantine: Record violation if CRITICAL attack
                if scores.get('risk_tier') == "CRITICAL":
                    atk_label = explanations[0]["feature"] if explanations else "CriticalAttack"
                    self.quarantine_manager.record_violation(client_id, ip, attack_type=atk_label)

                # Dispatch real-time webhook alert in background
                if scores.get('risk_tier') in ("CRITICAL", "HIGH_RISK"):
                    self.webhook_dispatcher.dispatch_alert_background({
                        "ip": ip,
                        "client_id": client_id,
                        "risk_tier": scores.get('risk_tier', 'CRITICAL'),
                        "score": scores.get('ensemble_score', 0),
                        "decision": decision,
                        "attack_type": explanations[0]["feature"] if explanations else "CriticalAttack",
                        "query": query
                    })

                return {
                    "data": None,
                    "errors": [{"message": "Query blocked by Security Policy"}],
                    "extensions": {
                        "security": {
                            "decision": "BLOCK",
                            "risk_tier": scores.get('risk_tier', 'CRITICAL'),
                            "score": scores.get('ensemble_score'),
                            "model_scores": {
                                "autoencoder": scores.get('autoencoder', 0),
                                "random_forest": scores.get('random_forest', 0),
                                "lstm": scores.get('lstm', 0),
                                "gnn": scores.get('gnn', 0)
                            },
                            "latency_ms": (time.time() - start_time) * 1000
                        }
                    }
                }
            
            # 8. Upstream Proxy or Simulation Response
            if self.upstream_url:
                upstream_payload = {
                    "query": query,
                    "variables": request_data.get("variables"),
                    "operationName": request_data.get("operationName")
                }
                headers = {"Content-Type": "application/json"}
                client_headers = client_info.get("headers") or {}
                for h_name in ("authorization", "x-request-id", "x-api-key", "apollographql-client-name", "apollographql-client-version"):
                    if h_name in client_headers:
                        headers[h_name] = client_headers[h_name]

                try:
                    resp = await self.http_client.post(self.upstream_url, json=upstream_payload, headers=headers)
                    if resp.headers.get("content-type", "").startswith("application/json"):
                        upstream_data = resp.json()
                    else:
                        upstream_data = {"data": resp.text}
                except Exception as up_err:
                    logger.error(f"Upstream GraphQL service error: {up_err}")
                    return {
                        "errors": [{"message": "Upstream GraphQL service unavailable"}],
                        "extensions": {
                            "security": {
                                "decision": decision,
                                "risk_tier": scores.get('risk_tier', 'UNKNOWN'),
                                "score": scores.get('ensemble_score'),
                                "latency_ms": (time.time() - start_time) * 1000
                            }
                        }
                    }

                if not isinstance(upstream_data, dict):
                    upstream_data = {"data": upstream_data}
                if "extensions" not in upstream_data or not isinstance(upstream_data["extensions"], dict):
                    upstream_data["extensions"] = {}
                upstream_data["extensions"]["security"] = {
                    "decision": decision,
                    "risk_tier": scores.get('risk_tier', 'UNKNOWN'),
                    "score": scores.get('ensemble_score'),
                    "model_scores": {
                        "autoencoder": scores.get('autoencoder', 0),
                        "random_forest": scores.get('random_forest', 0),
                        "lstm": scores.get('lstm', 0),
                        "gnn": scores.get('gnn', 0)
                    },
                    "explanations": explanations,
                    "latency_ms": (time.time() - start_time) * 1000
                }
                return upstream_data

            # Fallback simulation mode (standalone/demo when no upstream is configured)
            return {
                "data": {"message": "Query allowed and processed"},
                "extensions": {
                    "security": {
                        "decision": decision,
                        "risk_tier": scores.get('risk_tier', 'UNKNOWN'),
                        "score": scores.get('ensemble_score'),
                        "model_scores": {
                            "autoencoder": scores.get('autoencoder', 0),
                            "random_forest": scores.get('random_forest', 0),
                            "lstm": scores.get('lstm', 0),
                            "gnn": scores.get('gnn', 0)
                        },
                        "explanations": explanations,
                        "latency_ms": (time.time() - start_time) * 1000
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"Error processing request: {e}", exc_info=True)
            # Never expose internal exception details to clients.
            return {
                "errors": [{"message": "Internal security system error"}],
                "extensions": {
                    "security": {
                        "decision": "ERROR",
                        "latency_ms": (time.time() - start_time) * 1000
                    }
                }
            }

    def _log_decision(self, entry):
        # 1. In-memory ring buffer for sub-millisecond retrieval and SSE broadcast
        if self.ring_buffer is not None:
            self.ring_buffer.append(entry)

        # 2. Append to JSONL file on disk for persistent audit trail
        try:
            with open(self.log_path, 'a', encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to log decision: {e}")
