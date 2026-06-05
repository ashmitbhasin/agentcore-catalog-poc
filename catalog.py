"""
catalog.py — AgentCore → Agent Catalog Connector
Pulls agents from AWS Bedrock and lands them in a local SQLite catalog.
Run: python catalog.py
"""

import boto3
import sqlite3
import json
import logging
import argparse
from datetime import datetime, timezone
from botocore.exceptions import ClientError, NoCredentialsError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# SCHEMA
# ─────────────────────────────────────────────

SCHEMA_AGENTS = """
CREATE TABLE IF NOT EXISTS agents (
    agent_id            TEXT PRIMARY KEY,
    agent_arn           TEXT,
    agent_name          TEXT NOT NULL,
    agent_status        TEXT,
    foundation_model    TEXT,
    instruction         TEXT,
    description         TEXT,
    agent_version       TEXT,
    iam_role_arn        TEXT,
    idle_session_ttl    INTEGER,
    region              TEXT,
    created_at          TEXT,
    updated_at          TEXT,
    catalog_updated_at  TEXT NOT NULL
);
"""

SCHEMA_ACTION_GROUPS = """
CREATE TABLE IF NOT EXISTS action_groups (
    action_group_id     TEXT NOT NULL,
    agent_id            TEXT NOT NULL,
    action_group_name   TEXT,
    action_group_state  TEXT,
    description         TEXT,
    lambda_arn          TEXT,
    api_schema          TEXT,
    updated_at          TEXT,
    PRIMARY KEY (action_group_id, agent_id),
    FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
);
"""

SCHEMA_KNOWLEDGE_BASES = """
CREATE TABLE IF NOT EXISTS knowledge_bases (
    knowledge_base_id   TEXT NOT NULL,
    agent_id            TEXT NOT NULL,
    knowledge_base_state TEXT,
    description         TEXT,
    PRIMARY KEY (knowledge_base_id, agent_id),
    FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
);
"""

SCHEMA_RUN_LOGS = """
CREATE TABLE IF NOT EXISTS run_logs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at              TEXT NOT NULL,
    region              TEXT,
    agents_found        INTEGER,
    agents_upserted     INTEGER,
    agents_failed       INTEGER,
    duration_seconds    REAL,
    error               TEXT
);
"""


# ─────────────────────────────────────────────
# DB SETUP
# ─────────────────────────────────────────────

def init_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    for ddl in [SCHEMA_AGENTS, SCHEMA_ACTION_GROUPS, SCHEMA_KNOWLEDGE_BASES, SCHEMA_RUN_LOGS]:
        conn.execute(ddl)
    conn.commit()
    log.info(f"Database ready: {db_path}")
    return conn


# ─────────────────────────────────────────────
# AWS CONNECTOR
# ─────────────────────────────────────────────

class BedrockAgentConnector:
    def __init__(self, region: str, profile: str | None = None):
        session = boto3.Session(profile_name=profile) if profile else boto3.Session()
        self.client = session.client("bedrock-agent", region_name=region)
        self.region = region

    def list_agents(self) -> list[dict]:
        agents = []
        paginator = self.client.get_paginator("list_agents")
        for page in paginator.paginate():
            agents.extend(page.get("agentSummaries", []))
        log.info(f"Found {len(agents)} agent(s) in {self.region}")
        return agents

    def get_agent(self, agent_id: str) -> dict | None:
        try:
            resp = self.client.get_agent(agentId=agent_id)
            return resp.get("agent", {})
        except ClientError as e:
            log.warning(f"get_agent({agent_id}) failed: {e}")
            return None

    def list_action_groups(self, agent_id: str, agent_version: str = "DRAFT") -> list[dict]:
        try:
            paginator = self.client.get_paginator("list_agent_action_groups")
            groups = []
            for page in paginator.paginate(agentId=agent_id, agentVersion=agent_version):
                groups.extend(page.get("actionGroupSummaries", []))
            return groups
        except ClientError as e:
            log.warning(f"list_action_groups({agent_id}) failed: {e}")
            return []

    def get_action_group(self, agent_id: str, action_group_id: str, agent_version: str = "DRAFT") -> dict | None:
        try:
            resp = self.client.get_agent_action_group(
                agentId=agent_id,
                agentVersion=agent_version,
                actionGroupId=action_group_id,
            )
            return resp.get("agentActionGroup", {})
        except ClientError as e:
            log.warning(f"get_action_group({action_group_id}) failed: {e}")
            return None

    def list_knowledge_bases(self, agent_id: str, agent_version: str = "DRAFT") -> list[dict]:
        try:
            paginator = self.client.get_paginator("list_agent_knowledge_bases")
            kbs = []
            for page in paginator.paginate(agentId=agent_id, agentVersion=agent_version):
                kbs.extend(page.get("agentKnowledgeBaseSummaries", []))
            return kbs
        except ClientError as e:
            log.warning(f"list_knowledge_bases({agent_id}) failed: {e}")
            return []


# ─────────────────────────────────────────────
# TRANSFORM
# ─────────────────────────────────────────────

def _ts(dt) -> str | None:
    """Normalize datetime to ISO string."""
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.astimezone(timezone.utc).isoformat()
    return str(dt)


def transform_agent(detail: dict, region: str) -> dict:
    return {
        "agent_id":         detail.get("agentId"),
        "agent_arn":        detail.get("agentArn"),
        "agent_name":       detail.get("agentName"),
        "agent_status":     detail.get("agentStatus"),
        "foundation_model": detail.get("foundationModel"),
        "instruction":      detail.get("instruction"),
        "description":      detail.get("description"),
        "agent_version":    detail.get("agentVersion"),
        "iam_role_arn":     detail.get("agentResourceRoleArn"),
        "idle_session_ttl": detail.get("idleSessionTTLInSeconds"),
        "region":           region,
        "created_at":       _ts(detail.get("createdAt")),
        "updated_at":       _ts(detail.get("updatedAt")),
        "catalog_updated_at": datetime.now(timezone.utc).isoformat(),
    }


def transform_action_group(ag: dict, agent_id: str) -> dict:
    api_schema = ag.get("apiSchema") or ag.get("functionSchema")
    return {
        "action_group_id":    ag.get("actionGroupId"),
        "agent_id":           agent_id,
        "action_group_name":  ag.get("actionGroupName"),
        "action_group_state": ag.get("actionGroupState"),
        "description":        ag.get("description"),
        "lambda_arn":         (ag.get("actionGroupExecutor") or {}).get("lambda"),
        "api_schema":         json.dumps(api_schema) if api_schema else None,
        "updated_at":         _ts(ag.get("updatedAt")),
    }


def transform_knowledge_base(kb: dict, agent_id: str) -> dict:
    return {
        "knowledge_base_id":    kb.get("knowledgeBaseId"),
        "agent_id":             agent_id,
        "knowledge_base_state": kb.get("knowledgeBaseState"),
        "description":          kb.get("description"),
    }


# ─────────────────────────────────────────────
# UPSERT
# ─────────────────────────────────────────────

def upsert_agent(conn: sqlite3.Connection, agent: dict):
    conn.execute("""
        INSERT INTO agents (
            agent_id, agent_arn, agent_name, agent_status, foundation_model,
            instruction, description, agent_version, iam_role_arn,
            idle_session_ttl, region, created_at, updated_at, catalog_updated_at
        ) VALUES (
            :agent_id, :agent_arn, :agent_name, :agent_status, :foundation_model,
            :instruction, :description, :agent_version, :iam_role_arn,
            :idle_session_ttl, :region, :created_at, :updated_at, :catalog_updated_at
        )
        ON CONFLICT(agent_id) DO UPDATE SET
            agent_arn           = excluded.agent_arn,
            agent_name          = excluded.agent_name,
            agent_status        = excluded.agent_status,
            foundation_model    = excluded.foundation_model,
            instruction         = excluded.instruction,
            description         = excluded.description,
            agent_version       = excluded.agent_version,
            iam_role_arn        = excluded.iam_role_arn,
            idle_session_ttl    = excluded.idle_session_ttl,
            region              = excluded.region,
            updated_at          = excluded.updated_at,
            catalog_updated_at  = excluded.catalog_updated_at
    """, agent)


def upsert_action_group(conn: sqlite3.Connection, ag: dict):
    conn.execute("""
        INSERT INTO action_groups (
            action_group_id, agent_id, action_group_name, action_group_state,
            description, lambda_arn, api_schema, updated_at
        ) VALUES (
            :action_group_id, :agent_id, :action_group_name, :action_group_state,
            :description, :lambda_arn, :api_schema, :updated_at
        )
        ON CONFLICT(action_group_id, agent_id) DO UPDATE SET
            action_group_name   = excluded.action_group_name,
            action_group_state  = excluded.action_group_state,
            description         = excluded.description,
            lambda_arn          = excluded.lambda_arn,
            api_schema          = excluded.api_schema,
            updated_at          = excluded.updated_at
    """, ag)


def upsert_knowledge_base(conn: sqlite3.Connection, kb: dict):
    conn.execute("""
        INSERT INTO knowledge_bases (
            knowledge_base_id, agent_id, knowledge_base_state, description
        ) VALUES (
            :knowledge_base_id, :agent_id, :knowledge_base_state, :description
        )
        ON CONFLICT(knowledge_base_id, agent_id) DO UPDATE SET
            knowledge_base_state = excluded.knowledge_base_state,
            description          = excluded.description
    """, kb)


def log_run(conn: sqlite3.Connection, region: str, found: int, upserted: int,
            failed: int, duration: float, error: str | None = None):
    conn.execute("""
        INSERT INTO run_logs (run_at, region, agents_found, agents_upserted,
                              agents_failed, duration_seconds, error)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (datetime.now(timezone.utc).isoformat(), region, found, upserted, failed, duration, error))
    conn.commit()


# ─────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────

def run_catalog(region: str, db_path: str, profile: str | None = None, dry_run: bool = False):
    start = datetime.now(timezone.utc)
    conn = init_db(db_path)
    connector = BedrockAgentConnector(region=region, profile=profile)

    try:
        summaries = connector.list_agents()
    except NoCredentialsError:
        log.error("No AWS credentials found. Run `aws configure` or set AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY.")
        return
    except ClientError as e:
        log.error(f"AWS error listing agents: {e}")
        log_run(conn, region, 0, 0, 0, 0.0, str(e))
        return

    found = len(summaries)
    upserted = 0
    failed = 0

    for summary in summaries:
        agent_id = summary["agentId"]
        log.info(f"Processing agent: {agent_id} ({summary.get('agentName')})")

        detail = connector.get_agent(agent_id)
        if not detail:
            failed += 1
            continue

        agent_row = transform_agent(detail, region)

        # Action groups
        ag_summaries = connector.list_action_groups(agent_id)
        ag_rows = []
        for ags in ag_summaries:
            full_ag = connector.get_action_group(agent_id, ags["actionGroupId"])
            if full_ag:
                ag_rows.append(transform_action_group(full_ag, agent_id))

        # Knowledge bases
        kb_summaries = connector.list_knowledge_bases(agent_id)
        kb_rows = [transform_knowledge_base(kb, agent_id) for kb in kb_summaries]

        if dry_run:
            print(json.dumps(agent_row, indent=2))
        else:
            try:
                upsert_agent(conn, agent_row)
                for ag in ag_rows:
                    upsert_action_group(conn, ag)
                for kb in kb_rows:
                    upsert_knowledge_base(conn, kb)
                conn.commit()
                upserted += 1
                log.info(f"  ✓ Upserted | action_groups={len(ag_rows)} | knowledge_bases={len(kb_rows)}")
            except Exception as e:
                failed += 1
                conn.rollback()
                log.error(f"  ✗ DB error for {agent_id}: {e}")

    duration = (datetime.now(timezone.utc) - start).total_seconds()
    log_run(conn, region, found, upserted, failed, duration)

    log.info(f"Done in {duration:.1f}s — found={found}, upserted={upserted}, failed={failed}")
    print_summary(conn)
    conn.close()


def print_summary(conn: sqlite3.Connection):
    print("\n─── Catalog Summary ───────────────────────────")
    rows = conn.execute("""
        SELECT a.agent_id, a.agent_name, a.agent_status, a.foundation_model,
               a.region, a.agent_version,
               COUNT(DISTINCT ag.action_group_id) as action_groups,
               COUNT(DISTINCT kb.knowledge_base_id) as knowledge_bases
        FROM agents a
        LEFT JOIN action_groups ag ON ag.agent_id = a.agent_id
        LEFT JOIN knowledge_bases kb ON kb.agent_id = a.agent_id
        GROUP BY a.agent_id
    """).fetchall()
    for r in rows:
        print(f"  {r['agent_name']} ({r['agent_id']})")
        print(f"    status={r['agent_status']} | model={r['foundation_model']} | region={r['region']}")
        print(f"    action_groups={r['action_groups']} | knowledge_bases={r['knowledge_bases']}")
    print(f"  Total agents: {len(rows)}")
    print("───────────────────────────────────────────────\n")


# ─────────────────────────────────────────────
# ENTRYPOINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AgentCore → Catalog connector")
    parser.add_argument("--region",  default="us-east-1",    help="AWS region (default: us-east-1)")
    parser.add_argument("--db",      default="catalog.db",   help="SQLite DB file (default: catalog.db)")
    parser.add_argument("--profile", default=None,           help="AWS profile name (optional)")
    parser.add_argument("--dry-run", action="store_true",    help="Print agents as JSON, don't write to DB")
    args = parser.parse_args()

    run_catalog(
        region=args.region,
        db_path=args.db,
        profile=args.profile,
        dry_run=args.dry_run,
    )
