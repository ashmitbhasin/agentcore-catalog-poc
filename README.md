# agentcore-catalog-poc

Python connector that pulls agents from **AWS Bedrock AgentCore** and lands them in a local **SQLite catalog** — with full metadata, action groups, knowledge bases, and run logs.

Built for the Agently.ai AgentCore → Agent Catalog integration

---

## What it does

- Connects to AWS Bedrock via `boto3`
- Lists all agents in your account/region (`ListAgents`)
- For each agent, fetches full details (`GetAgent`), action groups, and knowledge bases
- Transforms and upserts everything into a local SQLite database
- Logs every run to a `run_logs` table (raw runtime logs area)
- Re-running never duplicates rows — version-aware upsert via `ON CONFLICT`

---

## Schema

### `agents` (metadata area)
| Column | Type | Source |
|---|---|---|
| `agent_id` | TEXT PK | `GetAgent.agentId` |
| `agent_arn` | TEXT | `GetAgent.agentArn` |
| `agent_name` | TEXT | `GetAgent.agentName` |
| `agent_status` | TEXT | `GetAgent.agentStatus` |
| `foundation_model` | TEXT | `GetAgent.foundationModel` |
| `instruction` | TEXT | `GetAgent.instruction` |
| `description` | TEXT | `GetAgent.description` |
| `agent_version` | TEXT | `GetAgent.agentVersion` |
| `iam_role_arn` | TEXT | `GetAgent.agentResourceRoleArn` |
| `idle_session_ttl` | INTEGER | `GetAgent.idleSessionTTLInSeconds` |
| `region` | TEXT | connector config |
| `created_at` | TEXT | `GetAgent.createdAt` |
| `updated_at` | TEXT | `GetAgent.updatedAt` |
| `catalog_updated_at` | TEXT | sync timestamp |

### `action_groups`
| Column | Type | Source |
|---|---|---|
| `action_group_id` | TEXT PK | `GetAgentActionGroup` |
| `agent_id` | TEXT FK | parent agent |
| `action_group_name` | TEXT | |
| `action_group_state` | TEXT | ENABLED / DISABLED |
| `lambda_arn` | TEXT | executor Lambda ARN |
| `api_schema` | TEXT | JSON stringified |

### `knowledge_bases`
| Column | Type | Source |
|---|---|---|
| `knowledge_base_id` | TEXT PK | `ListAgentKnowledgeBases` |
| `agent_id` | TEXT FK | |
| `knowledge_base_state` | TEXT | ENABLED / DISABLED |

### `run_logs` (runtime logs area)
Append-only. One row per `catalog.py` execution — designed to be consumed by the agent registry for observability.

| Column | Type |
|---|---|
| `run_at` | TEXT (ISO 8601) |
| `region` | TEXT |
| `agents_found` | INTEGER |
| `agents_upserted` | INTEGER |
| `agents_failed` | INTEGER |
| `duration_seconds` | REAL |
| `error` | TEXT |

---

## Setup

```bash
# 1. Clone
git clone https://github.com/ashmit/agentcore-catalog-poc.git
cd agentcore-catalog-poc

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure AWS credentials
aws configure
# or set environment variables:
# export AWS_ACCESS_KEY_ID=...
# export AWS_SECRET_ACCESS_KEY=...
# export AWS_DEFAULT_REGION=us-east-1
```

---

## Usage

### Run the connector

```bash
python catalog.py
```

This will:
1. Connect to AWS Bedrock in `us-east-1`
2. List and pull all agents
3. Upsert everything into `catalog.db`
4. Print a summary

**Options:**

```bash
python catalog.py --region us-west-2          # different region
python catalog.py --db my_catalog.db          # custom DB path
python catalog.py --profile my-aws-profile    # named AWS profile
python catalog.py --dry-run                   # print JSON, don't write to DB
```

### Inspect the catalog

```bash
python query_catalog.py                         # list all agents
python query_catalog.py --agent AGENTID         # detail view for one agent
python query_catalog.py --logs                  # show run history
```

### (Optional) Seed a test agent

If you don't have any Bedrock agents yet:

```bash
python seed_test_agent.py --region us-east-1 --role-arn arn:aws:iam::YOUR_ACCOUNT:role/YourBedrockRole
```

Then run `catalog.py` to pull it into the catalog.

---

## Design notes

**Version-aware upsert** — SQLite `ON CONFLICT ... DO UPDATE SET` handles idempotency. The primary key is `agent_id` (AWS-assigned, stable). Re-running always reflects the latest state from AWS without creating duplicates.

**Two raw data areas** (per Andy's guidance):
1. `agents` + `action_groups` + `knowledge_bases` = agent metadata
2. `run_logs` = runtime logs

These are intentionally kept as raw/flat tables for the agent registry to consume, not a finished catalog product.

**Langfuse-influenced logging** — `run_logs` mirrors Langfuse's trace concept: each connector run is a single trace with duration, counts, and error capture. Extend this table with per-agent invocation logs as runtime data becomes available via CloudWatch.

---

## Project context

This POC is Week 2 of the Agently.ai AgentCore integration. The Salesforce Agentforce connector (already in production) is the pattern this mirrors. Future connectors: Microsoft Copilot Studio, Google Vertex AI.

---

## License

MIT
