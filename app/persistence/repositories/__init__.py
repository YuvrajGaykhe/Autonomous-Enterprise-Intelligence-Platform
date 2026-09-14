"""
E1 persistence repositories for Layer 1.

Thin, explicit data-access functions over the B1 ORM tables. Every function
takes a caller-owned SQLAlchemy Session and never commits, rolls back, or
logs: transaction boundaries belong to the E1 unit of work, and payloads
must never reach logs.

Modules:
    runs       ingestion_runs lifecycle (create, count increments, finish)
    raw        source_records raw capture with deterministic content hashes
    canonical  canonical entity state lookup and source-identity upserts
    errors     ingestion_errors rows (quarantine, warnings, failures)
    cursors    ingestion_cursors checkpoint state
"""
