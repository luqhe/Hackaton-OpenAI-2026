# R2 Data Security, Privacy, Audit, and Abuse Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build locally verifiable adapters and contracts for R2-13–R2-20 and R2-24–R2-26 without claiming provider-managed staging controls are complete.

**Architecture:** Add an isolated `api.data_security` package beside the existing SQLite store so identity/device branches can integrate it without merge-heavy refactors. Services require family-scoped inputs, object access stays private and proxy-mediated, deletion is tombstone-first, audit is append-only plus HMAC chained, and critical device traffic has independent rate budgets.

**Tech Stack:** Python 3.11+, stdlib protocols/dataclasses/HMAC, SQLite for local contract tests, optional psycopg pool for managed PostgreSQL, injected S3-compatible clients, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-08-19-r2-data-audit-design.md`

## Global Constraints

- Do not modify `.design/`, `HANDOFF.md`, GitHub issues, remote infrastructure, or other agents' worktrees.
- Do not refactor `api/storage.py`, `api/main.py`, or `guardian_core/version.py` before the R2-01–R2-12 branches stabilize.
- Use `guardian_core.identity.FamilyScope` when the R2-01 hash is available; do not create a second tenant concept.
- Every tenant-owned lookup receives family scope; foreign and missing resources return the same result.
- Audit fields never contain frame bytes, OCR, evidence text, credentials, tokens, or free-form payloads.
- Tombstones are monotonic, precede deletion, and are reconciled before restored data becomes accessible.
- `UNLOCK`, `COMMAND_ACK`, and `HEARTBEAT` never share budgets with evidence, login, pairing, or general traffic.
- Managed PostgreSQL, provider TLS/at-rest encryption, KMS, bucket policy, WORM checkpoints, and real backup/restore remain external evidence gates.

---

### Task 1: Managed data-security configuration and PostgreSQL adapter

**Files:**
- Create: `api/data_security/__init__.py`
- Create: `api/data_security/config.py`
- Create: `api/data_security/database.py`
- Modify: `pyproject.toml`
- Test: `tests/test_data_security_config.py`

**Interfaces:**
- Produces: `DataSecuritySettings.from_env(environ)`, `DatabaseConfig.validate()`, `create_database(config, pool_factory=None)`.
- Produces: `SQLiteDatabase.transaction()` for development/test and `PostgresDatabase.transaction()` backed by an injected or psycopg `ConnectionPool`.

- [ ] **Step 1: Write failing configuration/adapter tests**

```python
def test_production_rejects_sqlite_and_unverified_postgres_tls():
    with pytest.raises(ValueError, match="PostgreSQL"):
        DataSecuritySettings.from_env(production_env(GUARDIAN_DATABASE_URL="sqlite:///guardian.db"))
    with pytest.raises(ValueError, match="verify-full"):
        DataSecuritySettings.from_env(production_env(GUARDIAN_DATABASE_URL="postgresql://db/guardian"))

def test_postgres_adapter_uses_bounded_injected_pool():
    pool_factory = RecordingPoolFactory()
    database = create_database(postgres_config(), pool_factory=pool_factory)
    assert pool_factory.kwargs == {"min_size": 1, "max_size": 8, "open": False}
    with database.transaction() as connection:
        assert connection is pool_factory.connection
```

- [ ] **Step 2: Run `pytest tests/test_data_security_config.py -q` and confirm import/behavior failures**
- [ ] **Step 3: Implement strict environment/provider validation and lazy optional psycopg pooling**
- [ ] **Step 4: Run the focused test and `ruff check api/data_security tests/test_data_security_config.py`**
- [ ] **Step 5: Commit `feat(storage): add managed database adapter config`**

### Task 2: Versioned expand-contract migrations and safe rollback

**Files:**
- Create: `api/data_security/migrations.py`
- Create: `api/data_security/schema.py`
- Test: `tests/test_data_security_migrations.py`

**Interfaces:**
- Consumes: database transaction objects exposing `execute`, `fetchone`, `commit`, and `rollback` behavior.
- Produces: `Migration`, `MigrationPhase`, `MigrationRunner.up()`, `MigrationRunner.down()`, `data_security_migration(dialect)`.

- [ ] **Step 1: Write failing migration tests against a tenant-aware SQLite fixture**

```python
def test_migration_round_trip_on_empty_additive_tables(connection):
    runner = MigrationRunner(SQLiteMigrationSession(connection), [data_security_migration("sqlite")])
    runner.up()
    assert runner.applied_ids() == ["r2_data_security_001"]
    runner.down("r2_data_security_001")
    assert runner.applied_ids() == []

def test_rollback_refuses_to_drop_existing_tombstone(connection):
    runner = migrated_runner(connection)
    connection.execute(
        "INSERT INTO deletion_tombstones(family_id, target_type, target_id, deleted_at, reason) "
        "VALUES (?, ?, ?, ?, ?)",
        ("family-1", "FAMILY", "family-1", "2026-08-19T12:00:00+00:00", "REQUESTED"),
    )
    with pytest.raises(UnsafeRollbackError, match="tombstone"):
        runner.down("r2_data_security_001")
```

- [ ] **Step 2: Run `pytest tests/test_data_security_migrations.py -q` and verify missing runner failures**
- [ ] **Step 3: Implement transactional history, dependency/drift checks, additive SQLite/PostgreSQL DDL, append-only triggers, and data-preserving down guards**
- [ ] **Step 4: Run focused tests and assert the PostgreSQL migration contains composite family FKs and append-only trigger functions**
- [ ] **Step 5: Commit `feat(migrations): add reversible data security schema`**

### Task 3: Private object storage and authenticated temporary grants

**Files:**
- Create: `api/data_security/evidence.py`
- Test: `tests/test_evidence_security.py`

**Interfaces:**
- Consumes: `guardian_core.identity.FamilyScope` once available; storage/repository collaborators are injected.
- Produces: `FileSystemObjectStore`, `S3ObjectStore`, `EvidenceService.store()`, `EvidenceService.issue_grant()`, `EvidenceService.deliver()`, `EvidenceService.revoke_grants()`.

- [ ] **Step 1: Write failing tests for private upload and family/session-scoped grants**

```python
def test_s3_upload_requires_kms_and_never_sets_public_acl():
    client = RecordingS3Client()
    store = S3ObjectStore(client, bucket="guardian-private", kms_key_id="kms-123")
    store.put("opaque-key", b"minimal", "text/plain")
    assert client.put_kwargs["ServerSideEncryption"] == "aws:kms"
    assert client.put_kwargs["SSEKMSKeyId"] == "kms-123"
    assert "ACL" not in client.put_kwargs

def test_delivery_revalidates_scope_session_epoch_and_expiry():
    token = service.issue_grant(scope, evidence_id, auth_context, ttl=timedelta(minutes=2))
    assert service.deliver(scope, token, auth_context) == b"minimal"
    repository.revoke_session(auth_context.session_id)
    with pytest.raises(EvidenceNotFound):
        service.deliver(scope, token, auth_context)
```

- [ ] **Step 2: Run `pytest tests/test_evidence_security.py -q` and confirm missing implementation failures**
- [ ] **Step 3: Implement opaque object keys, filesystem root confinement, injected S3 calls, scoped metadata, token-digest grants, TTL/revocation/session checks, and uniform not-found errors**
- [ ] **Step 4: Run focused tests plus mutation cases for foreign family, expired grant, advanced epoch, deleted evidence, and path traversal**
- [ ] **Step 5: Commit `feat(evidence): add private scoped evidence grants`**

### Task 4: Retention, family export/delete, and restore reconciliation

**Files:**
- Create: `api/data_security/lifecycle.py`
- Test: `tests/test_data_lifecycle.py`

**Interfaces:**
- Consumes: family scope, evidence service/repositories, monotonic tombstone ledger, session/device revokers.
- Produces: `RetentionCoordinator.expire()`, `FamilyPrivacyService.export()`, `FamilyPrivacyService.delete()`, `RestoreReconciler.reconcile_before_access()`.

- [ ] **Step 1: Write failing lifecycle tests with controlled clock and failure injection**

```python
def test_retention_writes_tombstone_before_blob_delete():
    coordinator.expire(now=fixed_now)
    assert calls[:2] == [("tombstone", "ev-1"), ("delete_blob", "ev-1")]

def test_restore_reconciliation_removes_resurrected_family_before_opening_access():
    result = reconciler.reconcile_before_access(backup_watermark=3)
    assert restored_store.deleted_families == ["family-deleted"]
    assert result.safe_to_open is True
```

- [ ] **Step 2: Run `pytest tests/test_data_lifecycle.py -q` and confirm missing service failures**
- [ ] **Step 3: Implement data-class TTLs, tombstone-first idempotent deletion, minimized JSON export, family revocation/deletion orchestration, and fail-closed restore reconciliation**
- [ ] **Step 4: Run focused tests for retries, partial failures, monotonic sequences, export cross-family denial, and stale backup resurrection**
- [ ] **Step 5: Commit `feat(privacy): enforce tombstone-first data lifecycle`**

### Task 5: Append-only, key-rotatable tamper-evident audit trail

**Files:**
- Create: `api/data_security/audit.py`
- Test: `tests/test_audit_trail.py`

**Interfaces:**
- Consumes: current `key_id`, secret key provider, clock, and atomic append repository.
- Produces: closed enums/types `AuditActorType`, `AuditAction`, `AuditResult`, `AuditRecord`; `AuditTrail.append()` and `AuditTrail.verify()`.

- [ ] **Step 1: Write failing audit behavior tests**

```python
def test_audit_records_only_bounded_metadata_and_verifies_after_key_rotation():
    first = trail.append(valid_input(action=AuditAction.EVIDENCE_READ))
    keyring.rotate("audit-v2", b"second-secret")
    second = trail.append(valid_input(action=AuditAction.POLICY_UPDATED))
    assert second.previous_hash == first.event_hash
    assert trail.verify().valid is True

def test_tampering_or_forbidden_content_is_rejected():
    repository.records[0] = replace(repository.records[0], target_id="changed")
    assert trail.verify().valid is False
    assert "details" not in AuditInput.__dataclass_fields__
    assert "payload" not in AuditInput.__dataclass_fields__
```

- [ ] **Step 2: Run `pytest tests/test_audit_trail.py -q` and confirm missing implementation failures**
- [ ] **Step 3: Implement canonical HMAC-SHA-256 chaining, atomic sequencing, key IDs/rotation, closed metadata schema, checkpoint verification, and production key validation**
- [ ] **Step 4: Run focused tests for edit/removal/reorder/wrong key/truncation checkpoint and verify no secret/content field exists**
- [ ] **Step 5: Commit `feat(audit): add append-only tamper evidence`**

### Task 6: Non-starving principal-aware rate limits

**Files:**
- Create: `api/data_security/rate_limit.py`
- Test: `tests/test_rate_limit.py`

**Interfaces:**
- Consumes: authenticated principal/device identifiers or anonymous source address plus a secret hashing key.
- Produces: `RouteClass`, `RateLimitPolicy`, `RateLimitDecision`, `InMemoryRateLimitBackend`, `RateLimiter.check()` and PostgreSQL atomic-consume SQL.

- [ ] **Step 1: Write failing bucket isolation and retry tests**

```python
def test_evidence_abuse_cannot_starve_unlock_ack_or_heartbeat():
    exhaust(RouteClass.EVIDENCE_READ, principal="p1")
    assert limiter.check("p1", RouteClass.UNLOCK).allowed
    assert limiter.check("p1", RouteClass.COMMAND_ACK).allowed
    assert limiter.check("p1", RouteClass.HEARTBEAT).allowed

def test_keys_are_hashed_and_retry_after_is_bounded():
    decision = exhaust(RouteClass.LOGIN, principal="parent@example.test")
    assert decision.retry_after_seconds == 60
    assert "parent@example.test" not in repr(backend.windows)
```

- [ ] **Step 2: Run `pytest tests/test_rate_limit.py -q` and confirm missing limiter failures**
- [ ] **Step 3: Implement independent fixed-window buckets, HMAC-hashed identities, deterministic retry, safe defaults, and atomic PostgreSQL upsert statement**
- [ ] **Step 4: Run focused tests for IP/principal separation, window reset, critical-class independence, and concurrency**
- [ ] **Step 5: Commit `feat(api): add non-starving abuse limits`**

### Task 7: External evidence checklist, integration contract, and final verification

**Files:**
- Create: `docs/operations/r2-data-security-staging-checklist.md`
- Create: `docs/engineering/r2-data-security-integration.md`
- Modify: `config/environments/development.env.example`
- Modify: `config/environments/staging.env.example`
- Modify: `config/environments/production.env.example`
- Test: `tests/test_data_security_docs.py`

**Interfaces:**
- Documents the exact `FamilyScope`, device-principal, route-class, migration-order, and store-factory integration points.
- Separates code-complete local evidence from provider/staging blockers for every roadmap ID.

- [ ] **Step 1: Write a failing executable configuration test that parses development/staging/production examples through `DataSecuritySettings.from_env()` and proves placeholders cannot be mistaken for deployable secrets**
- [ ] **Step 2: Run `pytest tests/test_data_security_docs.py -q` and confirm missing configuration/checklist failures**
- [ ] **Step 3: Add safe local examples, placeholder-only staging/production variables, staged migration/rollback/KMS/bucket/backup/restore/audit/rate-load steps, and integration contracts**
- [ ] **Step 4: Run all new tests, then `bash scripts/check.sh`, then inspect `git diff origin/main...HEAD --check` and ensure `.design/`/`HANDOFF.md` are absent**
- [ ] **Step 5: Commit `docs(operations): add R2 data security evidence gates`**
