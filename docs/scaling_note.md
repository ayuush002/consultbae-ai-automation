# Scaling Note

The submitted system is deliberately small and easy to evaluate. This note describes how I would evolve it for high-volume production use.

## Target architecture

```text
CSV/API uploads -> Object storage -> Queue -> Stateless validation workers
                                      |
                                      v
                             Identity-resolution service
                                      |
                         +------------+------------+
                         |                         |
                    PostgreSQL               Review queue
                         |
                  API + automation events

Audio uploads -> Signed object-storage upload -> Metadata worker -> PostgreSQL
```

## Data ingestion

- Store every original file immutably in object storage with a checksum, batch ID, source, and arrival timestamp.
- Run ingestion asynchronously through a queue so large files do not hold open HTTP requests.
- Version source schemas and normalization rules. Quarantine unknown schemas instead of guessing.
- Process files in chunks or use database bulk loading rather than holding all rows in memory.
- Make every batch idempotent using file hashes and source-row keys, allowing safe retries.
- Track accepted, repaired, rejected, and duplicate rates as operational metrics and alert on sudden changes.

## Identity resolution

- Keep deterministic exact matches for normalized email and phone.
- Add confidence-scored fuzzy matching only behind explainable thresholds.
- Send uncertain matches and conflicting identities to a human-review queue.
- Record match rules, confidence, rule version, and merge history so decisions can be reversed.
- Use source trust, field recency, and completeness when selecting canonical values.

## Database and API

- Replace SQLite with managed PostgreSQL, using transactions, constraints, connection pooling, backups, and replicas.
- Add unique normalized-identifier tables rather than relying only on nullable columns in a candidate row.
- Put the Flask/Gunicorn application behind a managed load balancer and run multiple stateless instances.
- Add authentication, authorization, rate limits, request-size limits, pagination, structured logs, tracing, and API versioning.
- Publish duplicate-check outcomes as durable events so email, Slack, CRM, and audit consumers do not depend on one synchronous workflow.

## n8n automation

- Keep credentials in n8n's credential store and environment secrets, never in exported workflow JSON.
- Separate ingestion, duplicate evaluation, alerting, and failure handling into reusable workflows.
- Add retries with exponential backoff, timeout handling, an error workflow, and a dead-letter destination.
- Include batch and correlation IDs in every request and alert.
- Pin and review workflow versions before promotion from staging to production.

## Audio pipeline

- Upload audio directly to private object storage using short-lived signed URLs.
- Store only object keys and metadata in PostgreSQL; never depend on an application container's filesystem.
- Analyse audio asynchronously with a maintained library/FFmpeg worker and scan uploads for malware.
- Validate actual file signatures, codecs, duration, and decompressed size rather than trusting the filename or MIME type.
- Serve playback through authorized, expiring URLs or a CDN where appropriate.

## Security and privacy

- Encrypt candidate and audio data in transit and at rest.
- Apply least-privilege service roles and audit all access to personal information.
- Mask phone and email values in logs and monitoring.
- Define consent, retention, deletion, and subject-access workflows for recordings and candidate profiles.
- Add secrets rotation, dependency scanning, backups, restore drills, and incident-response procedures.

## Suggested rollout

1. Move persistence to PostgreSQL and object storage.
2. Add idempotent batches, authentication, and operational monitoring.
3. Introduce queues and stateless workers for large CSV and audio workloads.
4. Add review tooling and confidence scoring for uncertain identity matches.
5. Load-test realistic traffic, test recovery procedures, and roll out gradually with measurable service-level objectives.
