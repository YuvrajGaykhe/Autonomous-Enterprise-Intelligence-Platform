"""
E1 ingestion orchestration package for Layer 1.

Architecture position:
    connector page -> D1 normalize + D2 quality gate -> E1 batch unit of work
                                                      -> canonical PostgreSQL store

Modules:
    reconciliation  Pure batch planner: canonical FK resolution and
                    insert/update/unchanged classification by source identity.
    batch           One fetched page = one database transaction: raw capture,
                    upserts, structured errors, run counts, checkpoint.
    errors          Stable E1 finding codes.
"""
