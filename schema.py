"""
schema.py — Schema definitions and documentation reference.
This file documents the data model. The actual CREATE TABLE statements
live in catalog.py and are executed on init_db().
"""

# ─────────────────────────────────────────────────────────────────────────────
# agents
# ─────────────────────────────────────────────────────────────────────────────
# PRIMARY KEY: agent_id (AWS-assigned, globally unique per account+region)
# Upsert key:  agent_id  — re-running updates in place, never duplicates
#
# agent_id            TEXT    — e.g. "ABCD1234EF"
# agent_arn           TEXT    — full ARN
# agent_name          TEXT    — human-readable name set at creation
# agent_status        TEXT    — CREATING | PREPARING | PREPARED | NOT_PREPARED | FAILED | VERSIONING | UPDATING | DELETING
# foundation_model    TEXT    — e.g. "anthropic.claude-3-haiku-20240307-v1:0"
# instruction         TEXT    — system prompt / instruction (raw text)
# description         TEXT    — optional description field
# agent_version       TEXT    — e.g. "DRAFT" or "1", "2"
# iam_role_arn        TEXT    — execution role ARN
# idle_session_ttl    INTEGER — seconds before an idle session is terminated
# region              TEXT    — AWS region, e.g. "us-east-1"
# created_at          TEXT    — ISO 8601 UTC
# updated_at          TEXT    — ISO 8601 UTC (from AWS)
# catalog_updated_at  TEXT    — ISO 8601 UTC (when this row was last synced)

# ─────────────────────────────────────────────────────────────────────────────
# action_groups
# ─────────────────────────────────────────────────────────────────────────────
# PRIMARY KEY: (action_group_id, agent_id)
# An agent can have many action groups; each action group belongs to one agent.
#
# action_group_id     TEXT    — AWS-assigned
# agent_id            TEXT    — FK → agents.agent_id
# action_group_name   TEXT
# action_group_state  TEXT    — ENABLED | DISABLED
# description         TEXT
# lambda_arn          TEXT    — Lambda executor ARN (null if return-control)
# api_schema          TEXT    — JSON stringified OpenAPI or function schema
# updated_at          TEXT    — ISO 8601 UTC

# ─────────────────────────────────────────────────────────────────────────────
# knowledge_bases
# ─────────────────────────────────────────────────────────────────────────────
# PRIMARY KEY: (knowledge_base_id, agent_id)
#
# knowledge_base_id    TEXT
# agent_id             TEXT    — FK → agents.agent_id
# knowledge_base_state TEXT    — ENABLED | DISABLED
# description          TEXT

# ─────────────────────────────────────────────────────────────────────────────
# run_logs  (Andy's "runtime logs" area)
# ─────────────────────────────────────────────────────────────────────────────
# Append-only. One row per catalog.py execution.
# Consumed by the agent registry for observability.
#
# id                  INTEGER — autoincrement PK
# run_at              TEXT    — ISO 8601 UTC
# region              TEXT
# agents_found        INTEGER — total agents returned by ListAgents
# agents_upserted     INTEGER — successfully written to catalog
# agents_failed       INTEGER — errors during get/transform/upsert
# duration_seconds    REAL    — wall-clock time for the full run
# error               TEXT    — top-level error message if run aborted early
