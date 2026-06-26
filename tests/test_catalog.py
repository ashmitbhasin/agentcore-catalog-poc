"""
test_catalog.py — Tests catalog.py's connector logic against a mocked
Bedrock Agent API (moto) and a temp SQLite DB.
"""

import sqlite3

import boto3
import pytest
from moto import mock_aws

from catalog import BedrockAgentConnector, init_db, run_catalog

REGION = "us-east-1"
ROLE_ARN = "arn:aws:iam::123456789012:role/TestRole"
AGENT_NAME = "test-agent"
INSTRUCTION = "You are a test agent used purely for unit testing purposes."
MODEL = "anthropic.claude-3-haiku-20240307-v1:0"


@pytest.fixture
def temp_db(tmp_path):
    return str(tmp_path / "catalog.db")


@pytest.fixture
def mocked_bedrock(monkeypatch):
    # moto's bedrock-agent backend doesn't implement list_agent_action_groups
    # or list_agent_knowledge_bases yet; stub them out so the connector can
    # still complete its run against the mocked agent.
    monkeypatch.setattr(BedrockAgentConnector, "list_action_groups", lambda self, agent_id, agent_version="DRAFT": [])
    monkeypatch.setattr(BedrockAgentConnector, "list_knowledge_bases", lambda self, agent_id, agent_version="DRAFT": [])
    with mock_aws():
        client = boto3.client("bedrock-agent", region_name=REGION)
        client.create_agent(
            agentName=AGENT_NAME,
            agentResourceRoleArn=ROLE_ARN,
            foundationModel=MODEL,
            instruction=INSTRUCTION,
            description="A fake agent for testing the connector.",
            idleSessionTTLInSeconds=600,
        )
        yield client


def test_connector_lands_correct_row(mocked_bedrock, temp_db):
    run_catalog(region=REGION, db_path=temp_db)

    conn = init_db(temp_db)
    rows = conn.execute("SELECT * FROM agents").fetchall()
    conn.close()

    assert len(rows) == 1
    row = rows[0]
    assert row["agent_name"] == AGENT_NAME
    assert row["foundation_model"] == MODEL
    assert row["region"] == REGION
    assert row["agent_id"]


def test_connector_upsert_does_not_duplicate(mocked_bedrock, temp_db):
    run_catalog(region=REGION, db_path=temp_db)
    run_catalog(region=REGION, db_path=temp_db)

    conn = init_db(temp_db)
    rows = conn.execute("SELECT * FROM agents").fetchall()
    run_log_count = conn.execute("SELECT COUNT(*) AS c FROM run_logs").fetchone()["c"]
    conn.close()

    assert len(rows) == 1
    assert run_log_count == 2
