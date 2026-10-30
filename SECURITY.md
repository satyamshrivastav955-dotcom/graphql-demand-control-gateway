# Security policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately through GitHub's
["Report a vulnerability"](https://github.com/satyamshrivastav955-dotcom/GraphQL-Sentinel/security/advisories/new)
form on this repository rather than opening a public issue. Include the affected version or commit, a minimal
reproduction (a request body is usually enough) and the impact you observed.

You can expect an acknowledgement within a few days. This is a student project maintained on a best-effort basis,
so there is no bug bounty or guaranteed fix timeline.

## Scope

In scope: bypasses of the hard limits or rate limiting, requests that reach the upstream when they should be
blocked, information disclosure through errors/logs/the API, denial of service of the gateway itself, and unsafe
handling of the model artifact.

Out of scope: weaknesses in upstream APIs behind the gateway, the demo upstream (`demo/upstream`, intentionally
unprotected), and anything that requires the management token (a single shared token by design; see the
[threat model](docs/threat-model.md)).

## Deployment hardening checklist

* Keep the upstream reachable only through the gateway.
* Set a strong `SENTINEL_API_TOKEN`; it protects the management API. Serve everything over TLS.
* Leave `app.debug` false; leave `gateway.mode` as `proxy`.
* Enable `gateway.trust_proxy_headers` only behind a proxy that overwrites `X-Forwarded-For`.
* Treat the SQLite event database as sensitive (query text is stored; variables and credential literals are not).
