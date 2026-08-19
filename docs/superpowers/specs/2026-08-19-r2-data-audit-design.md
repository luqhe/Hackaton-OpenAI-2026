# R2 Data Security, Privacy, Audit, and Abuse Controls

**Status:** approved in chat on 2026-08-19

**Roadmap coverage:** R2-13–R2-20 and R2-24–R2-26

## Purpose

Add production-oriented contracts and locally verifiable behavior for managed PostgreSQL, private evidence storage, retention and family deletion, tamper-evident audit records, and abuse controls. The work remains a modular FastAPI monolith and does not claim that provider-managed encryption, KMS, bucket policy, or backup recovery has been proven without staging evidence.

## Integration boundary

The R2-01–R2-06 identity branch owns `guardian_core.identity.FamilyScope`, the tenant-aware SQLite v2 schema, and `GuardianStore` family-scoped queries. This branch must consume that type when available and must not invent a second tenant identity. Until the dependency lands, new services accept a narrow structural scope contract with the same `family_id` attribute and record the exact integration point.

The R2-07–R2-12 device branch owns device principals, pairing, signed agent requests, and command lifecycle. Rate limiting uses route classes that keep `UNLOCK`, `COMMAND_ACK`, and `HEARTBEAT` in independent critical buckets. Evidence, pairing, and general API traffic cannot consume those budgets.

Existing `api/storage.py`, `api/main.py`, and `guardian_core/version.py` are not refactored in the additive commits. The final integration may wire factories and middleware after the two dependency branches settle.

## Architecture

### Database and migrations

`api/data_security/database.py` owns a validated database configuration and connection factory. SQLite URLs are accepted only for `development` and `test`; `staging` and `production` require PostgreSQL, TLS verification, a bounded connection pool, and secrets supplied outside source control. The PostgreSQL adapter is real code but is tested locally with an injected connector; a managed staging instance remains a release-gate dependency.

`api/data_security/migrations.py` owns an ordered migration manifest and transactional runner. Every migration declares an identifier, dependencies, `up`, `down`, risk classification, and expand/contract phase. The data-security migration creates only additive tables owned by this branch: evidence objects and access grants, deletion tombstones, audit events/checkpoints, and rate-limit windows. It assumes tenant parent tables from SQLite v2 and uses composite family foreign keys where relationships are tenant-owned. Rollback removes only newly added structures and never removes tombstones or restores expired/deleted data; destructive cleanup is a later contract phase.

Local tests execute `up` and the safe `down` path against SQLite fixtures and validate PostgreSQL statements. A rollback may remove empty additive tables, but it refuses to drop a tombstone ledger containing any row; an existing tombstone is never deleted by rollback. Empty database, representative migration, and schema drift checks are local. Managed PostgreSQL migration, rollback, and restored-backup exercises are staging evidence, not local completion.

### Private evidence lifecycle

`api/data_security/evidence.py` defines an injected `ObjectStore`. `FileSystemObjectStore` is restricted to development/test and enforces a private root. `S3ObjectStore` accepts an injected S3-compatible client, never creates a public ACL, requires bucket encryption with a configured KMS key in staging/production, uses opaque object keys, and exposes delete/head/get/put without public URLs.

Evidence metadata always contains `family_id`, `incident_id`, object key, content type, digest, created time, expiry, and deletion state. Services receive a family scope and query metadata by `(family_id, evidence_id)`; unknown and foreign evidence use the same not-found result. Short-lived access grants contain an opaque random token, family scope, authenticated principal/session binding or revocation epoch, expiry, and revocation timestamp. Raw tokens are returned once while only their digest is stored. Delivery requires current authentication and rechecks the family, principal/session binding or epoch, expiry, grant revocation, evidence deletion, and object availability before streaming. Logout, session revocation, membership revocation, or an advanced family revocation epoch invalidates the grant even before its TTL. It never logs frame, OCR, blob content, or token.

### Encryption controls

`api/data_security/controls.py` validates transport and at-rest configuration. Staging/production require verified PostgreSQL TLS, HTTPS object endpoints, a KMS key identifier, server-side encryption mode, a non-default audit HMAC key ID, and a secret loaded from the environment/secret provider. The report separates locally validated configuration from external provider evidence. KMS key policy, rotation, bucket public-access block, TLS certificate, encrypted backup, and restore attestations remain checklist items.

### Retention, export, deletion, and restore

`api/data_security/lifecycle.py` defines retention policies by data class and a clock-injected coordinator. Expiration creates a monotonic tombstone before deleting the blob and metadata. Retries are idempotent; a failed blob deletion leaves the record inaccessible and retryable rather than reopening it.

Family export is authorized by family scope, contains structured tenant-owned records and minimized evidence metadata, and is delivered through the same short-lived grant pattern. Family deletion first records a family tombstone, revokes sessions/device credentials through injected collaborators, revokes evidence grants, makes data inaccessible, and then removes blobs and structured rows. Required audit records retain only approved metadata.

Restore reconciliation consumes an authoritative tombstone ledger before access is reopened. It reapplies every deletion whose sequence is newer than the backup watermark and verifies that no matching row or object is accessible. Tombstone sequence numbers only increase. Production requires the ledger/checkpoints to live outside a backup set that could resurrect deleted family data.

### Audit integrity

`api/data_security/audit.py` defines a closed audit event schema: event ID, sequence, time, actor type and opaque actor ID, family ID, action, target type and opaque target ID, result, correlation ID, `key_id`, previous hash, and event hash. There is no free-form payload field. Validation rejects known secret/content field names and values outside bounded enums.

Each event hash is HMAC-SHA-256 over canonical metadata plus the previous hash. The writer obtains keys by `key_id`, supports rotation by starting new events with the current key while retaining verification keys, and refuses staging/production configuration without secure key material. Database permissions/triggers deny update and delete. A verifier detects changes, non-terminal removal, reordering, and broken rotation; an immutable checkpoint is required to detect truncation at the end. External checkpoints or WORM retention remain a staging/operations requirement because a database administrator could otherwise replace a complete chain.

### Rate limiting

`api/data_security/rate_limit.py` defines stable route classes and a backend contract. The in-memory backend is development/test only; a transactional database backend stores hashed principal/device/IP keys and fixed-window counters for multi-process deployments. Keys never embed PII.

The policy gives separate critical budgets to `UNLOCK`, `COMMAND_ACK`, and `HEARTBEAT`. `LOGIN`, `PAIRING`, `EVIDENCE_READ`, `EVIDENCE_WRITE`, and `GENERAL` have independent budgets. Rejected calls return a deterministic retry interval and aggregate-safe audit fields. The integration layer derives limiter identity from the authenticated principal or a keyed hash of the source IP for anonymous endpoints.

## Security and privacy invariants

- A global opaque ID never authorizes tenant-owned access; every repository lookup receives family scope.
- Composite `(family_id, id)` references prevent cross-family evidence/incident links.
- Object keys contain no names, account IDs, child IDs, OCR, or filenames supplied by clients.
- Evidence is private, minimized, expiring, revocable, and every successful or denied access is auditable without content.
- Deletion tombstones are written before destructive work and survive restore reconciliation.
- Audit records contain metadata only and are append-only plus tamper-evident.
- Rate limiting cannot let evidence, login, pairing, or general traffic starve unlock, acknowledgement, or heartbeat.
- The classifier remains separate from policy and never controls a device directly.

## Verification and honest completion

Local tests cover configuration rejection, injected PostgreSQL pooling behavior, migration `up/down` and drift, private object operations, scoped/revocable grants, retention retries, export minimization, deletion/tombstones, restore reconciliation, audit chain verification/rotation/tampering, forbidden audit content, and independent rate buckets.

The following evidence stays open until staging exists: managed PostgreSQL connectivity and least privilege; real migration/rollback on a representative copy; provider TLS and encryption-at-rest attestation; KMS policy/rotation; private bucket/public-access block; presigned/proxy delivery through deployed authorization; encrypted backup RPO/RTO; restore reconciliation against a real backup; WORM/external audit checkpoint; and distributed rate-limit behavior under load.
