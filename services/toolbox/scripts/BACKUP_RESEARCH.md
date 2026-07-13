# Backup & Restore Approach Evaluation

## Sources Referenced
- PostgreSQL official docs: Backup/Restore chapter (§25.1, pg_dump)
- AWS RDS Backup & Restore best practices
- Docker container backup patterns (community)
- Backblaze B2 / S3 backup durability documentation
- Industry-standard "3-2-1" backup rule

---

## 1. Summary of Current Approach

The omni-stack toolbox implements a bash-based backup/restore system with 4 scripts:

| Script | Purpose |
|--------|---------|
| `backup.sh` | Syncs `data/` to `s3://.../omni/data/` + PG dumps to `db/` subdir |
| `checkout.sh` | Same as backup but to `s3://.../omni/checkout/YYYYMMDD/` |
| `restore_backup.sh` | Stops services → syncs S3 back → restores PG → restarts |
| `restore_checkout.sh` | Same from a dated checkpoint path |

Uses: rclone → Backblaze B2 (S3-compatible), pg_dump (plain format, gzipped), psql restore.

---

## 2. What's Good ✓

### 2.1. Self-Contained & No External Dependencies
The scripts source everything from `OMNI_DIR/.env` - no Hermes dependency, no hardcoded secrets, no manual steps. This is excellent for disaster recovery where the Hermes container itself might be gone.

### 2.2. Offsite Storage (Backblaze B2 / S3)
Storing backups on an S3-compatible object store in a different region/zone provides **geographic redundancy**. Even if the entire docker host fails, the data survives. This satisfies the "1 offsite" requirement of the 3-2-1 rule.

### 2.3. Date-Stamped Checkpoints
The `checkout.sh` script creates immutable, dated snapshots (YYYYMMDD). This is a **retention-friendly** pattern - you can prune old checkpoints by deleting prefix directories without affecting the main backup stream.

### 2.4. Crash Consistency via Service Stop
Stopping services before restore avoids "dirty database" issues. The backup (pg_dump) runs while services are UP (which is correct - pg_dump provides a consistent snapshot without exclusive locks), but the RESTORE correctly stops everything first.

### 2.5. PG Dump Consistency
`pg_dump` with `--clean --if-exists` creates internally consistent snapshots without blocking writes. Using `--no-owner --no-acl` makes the dump portable across environments.

### 2.6. Credential Isolation
No credentials embedded in scripts - all read from `.env` at runtime. The rclone config is built in-memory via `mktemp` and discarded after use.

---

## 3. What's Concerning / Needs Improvement ⚠

### 3.1. Plain Format (Not Custom) - **Missing Parallelism**
The scripts use `pg_dump` in plain SQL format (piped to gzip), not the `--format=custom` (`.dump`) format. This means:

| Concern | Impact |
|---------|--------|
| No parallel restore | `pg_restore -j N` with custom format = parallel. With plain SQL → single-threaded `psql` import. For databases >1GB, this adds **hours** to restore time |
| No selective restore | Can't restore individual tables from a plain SQL dump without parsing the whole file |
| Larger file size | Custom format with compression level is 10-30% smaller than gzipped SQL |

> **Fix:** Switch to `pg_dump --format=custom --compress=9 -f file.dump` and restore with `pg_restore -j $(nproc)`.

### 3.2. No Point-in-Time Recovery (PITR) Capability
pg_dump provides a **snapshot at dump time only**. Between backups, all changes are lost. Modern PostgreSQL supports WAL-based continuous archiving:

| Approach | RPO (Recovery Point Objective) |
|----------|-------------------------------|
| Daily pg_dump | Up to 24 hours of data loss |
| WAL archiving + hourly WAL shipping | Minutes |
| pgBackRest / barman | Near-zero (depends on WAL frequency) |

> **Verdict:** Acceptable for non-critical data. For production databases, consider adding WAL archiving.

### 3.3. No Backup Integrity Verification
After backup, the scripts do NOT verify the dump is restorable. Common corruption scenarios:

- Silent truncation on large files (network interruption during upload)
- Corrupted gzip stream (bad block on source disk)
- Schema mismatch (dump taken during DDL migration)

> **Fix:** After backup, do `gunzip -t [file].gz` to verify integrity. For high-confidence, restore to a temp database and run `pg_dump -T ...` comparison queries.

### 3.4. No Retention Policy / Lifecycle Management
The regular backup writes to the SAME path (`omni/data/`) every time - the previous backup is **overwritten**, not rotated. The checkpoint script creates dated snapshots, but:

- No automatic cleanup of old checkpoints
- No retention tiers (daily → weekly → monthly)
- Storage grows unbounded

> **Fix:** Add a `prune` step that deletes checkpoints older than N days. Consider S3 lifecycle policies for automatic tiering to cold storage.

### 3.5. Backup Protocol No Longer Includes Checkpoint Step
The backup script syncs to `omni/data/` and PG dumps to `omni/data/db/`. Checkpoints are a **separate script** (`checkout.sh`). A complete backup run should call both:

```bash
backup && checkout $(date +%Y%m%d)
```

Currently, no cron job or automation ties them together.

### 3.6. Mattermost Restore Has a Race Condition
Mattermost's database restore drops and recreates the `mattermost` database, but the Mattermost **application** is stopped before restore and restarted after. However:

- If Mattermost uses connection pooling or has sidecars, they may hold stale connections
- The current `docker ps -a -q` fix correctly finds stopped containers, but was broken before

### 3.7. No Monitoring / Alerting
Nothing notifies on backup failure, skipped dumps, or size anomalies. A backup that silently produces a 20-byte dump (as happened during development) would go undetected until restore time.

> **Fix:** Add output size validation (fail if dump < 1KB). For production, integrate with the existing Loki/Grafana observability stack.

### 3.8. `set -euo pipefail` Aggressiveness
The scripts use `set -euo pipefail`, which is good for catching errors early. However:

- `pg_dump ... 2>/dev/null` masks all pg_dump errors - the script would think an empty dump is fine
- The `set -e` combined with `$RC` rclone commands can cause unexpected exits from non-critical failures (missing S3 prefix, slow network)

---

## 4. Scoring Against Industry Standards

| Criteria | Industry Best Practice | Our Approach | Score |
|----------|----------------------|--------------|-------|
| 3-2-1 Rule (3 copies, 2 media, 1 offsite) | ✅ | S3 (offsite) + local data + checkpoints | ✅ 3/3 |
| Point-in-Time Recovery | WAL archiving | ❌ Snapshot only | ❌ Missing |
| Backup Format | Custom format w/ compression | Plain SQL + gzip | ⚠ Needs upgrade |
| Parallel Restore | pg_restore -j | psql (single-threaded) | ❌ Missing |
| Integrity Verification | Restore test | None | ❌ Missing |
| Retention Management | Tiered (daily/weekly/monthly) | Overwrite + unbounded checkpoints | ⚠ Partial |
| Monitoring/Alerting | Prometheus/Grafana | None | ❌ Missing |
| Encryption at Rest | S3-SSE or client-side | S3-SSE (B2 default) | ✅ |
| Encryption in Transit | TLS | rclone HTTPS (default) | ✅ |
| Credential Safety | Env vars, mktemp config | ✅ .env + mktemp | ✅ |
| Self-Contained DR | One command to restore | ✅ restore_backup/sh | ✅ |
| RTO (Recovery Time) | < 1h for critical | ~2-5 min (small DB) | ✅ |
| Automation | Cron | Manual (no cron set up) | ⚠ Manual only |

---

## 5. Recommendations (Priority Order)

### P0 - Must Fix
1. **Add integrity verification** - `gunzip -t` after backup, size threshold checks
2. **Add retention pruning** - delete checkpoints > 30/90/365 days old
3. **Fix pg_dump error masking** - remove `2>/dev/null` from pg_dump, redirect to log instead

### P1 - Important
4. **Switch to custom format** - `--format=custom --compress=9` for parallel restore
5. **Add backup+checkout combo cron** - `backup && checkout $(date +%Y%m%d)`
6. **Add size validation** - fail if dump < 100 bytes (empty DB indicator)

### P2 - Nice to Have
7. **Monitoring integration** - export backup duration/size as metrics to Loki
8. **WAL archiving** - for sub-minute RPO on production data
9. **Restore dry-run** - option to verify integrity without touching live databases

---

## 6. Verdict

**Overall: GOOD for a self-hosted, non-critical stack.** The approach is sound in its fundamentals: offsite storage, self-contained scripts, consistent snapshots, and proper credential handling. It passed an end-to-end restore test (30 kanban tasks → 29 → restore → 30 verified).

**Not production-grade for high-availability or compliance-sensitive databases** - primarily due to:
- No PITR (worst case: up to 24h data loss)
- No parallel restore (will struggle with databases >10GB)
- No automated integrity checks
- No retention management

For the current omni-stack use case (agent development, kanban, research notes), this is **appropriate and sufficient**. The scripts are simple, auditable, and repairable - which matters more than feature completeness for a 4-script bash toolbox.
