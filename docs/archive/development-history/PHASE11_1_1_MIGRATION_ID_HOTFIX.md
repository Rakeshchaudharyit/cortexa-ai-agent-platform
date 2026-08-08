# Phase 11.1.1 — Alembic Revision ID Hotfix

The original Phase 11.1 revision identifier exceeded the existing `alembic_version.version_num` column width of 32 characters. PostgreSQL therefore rolled back the transactional migration when Alembic attempted to record the new head.

The revision identifier is now `0015_knowledge_mgmt`, which preserves the same migration contents and `down_revision` while fitting the existing Alembic version column. A regression assertion prevents future revision identifiers in this migration from exceeding 32 characters.
