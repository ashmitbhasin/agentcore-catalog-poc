"""
query_catalog.py — Quick inspection of your local catalog.db.
Usage:
    python query_catalog.py                  # show all agents
    python query_catalog.py --agent AGENTID  # show one agent + its action groups
    python query_catalog.py --logs           # show run history
"""

import sqlite3
import argparse
import json

DB = "catalog.db"


def show_agents(db: str):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT a.*,
               COUNT(DISTINCT ag.action_group_id) AS action_groups,
               COUNT(DISTINCT kb.knowledge_base_id) AS knowledge_bases
        FROM agents a
        LEFT JOIN action_groups ag ON ag.agent_id = a.agent_id
        LEFT JOIN knowledge_bases kb ON kb.agent_id = a.agent_id
        GROUP BY a.agent_id
        ORDER BY a.updated_at DESC
    """).fetchall()

    print(f"\n{'─'*60}")
    print(f"  AGENTS ({len(rows)} total)")
    print(f"{'─'*60}")
    for r in rows:
        print(f"\n  Name:          {r['agent_name']}")
        print(f"  ID:            {r['agent_id']}")
        print(f"  Status:        {r['agent_status']}")
        print(f"  Model:         {r['foundation_model']}")
        print(f"  Region:        {r['region']}")
        print(f"  Version:       {r['agent_version']}")
        print(f"  Action Groups: {r['action_groups']}")
        print(f"  Know. Bases:   {r['knowledge_bases']}")
        print(f"  Last Updated:  {r['updated_at']}")
        print(f"  Catalog Sync:  {r['catalog_updated_at']}")
    conn.close()


def show_agent(db: str, agent_id: str):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row

    agent = conn.execute("SELECT * FROM agents WHERE agent_id = ?", (agent_id,)).fetchone()
    if not agent:
        print(f"Agent '{agent_id}' not found in catalog.")
        return

    print(f"\n{'─'*60}")
    print(f"  {agent['agent_name']} ({agent['agent_id']})")
    print(f"{'─'*60}")
    for key in agent.keys():
        val = agent[key]
        if key == "instruction" and val and len(val) > 100:
            val = val[:100] + "..."
        print(f"  {key:<22} {val}")

    ags = conn.execute("SELECT * FROM action_groups WHERE agent_id = ?", (agent_id,)).fetchall()
    if ags:
        print(f"\n  Action Groups ({len(ags)}):")
        for ag in ags:
            print(f"    • {ag['action_group_name']} [{ag['action_group_state']}]  id={ag['action_group_id']}")

    kbs = conn.execute("SELECT * FROM knowledge_bases WHERE agent_id = ?", (agent_id,)).fetchall()
    if kbs:
        print(f"\n  Knowledge Bases ({len(kbs)}):")
        for kb in kbs:
            print(f"    • {kb['knowledge_base_id']} [{kb['knowledge_base_state']}]")

    conn.close()


def show_logs(db: str):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM run_logs ORDER BY run_at DESC LIMIT 20").fetchall()
    print(f"\n{'─'*60}")
    print(f"  RUN LOGS (last {len(rows)})")
    print(f"{'─'*60}")
    for r in rows:
        status = "✗ " + r['error'] if r['error'] else "✓"
        print(f"  {r['run_at']}  region={r['region']}  found={r['agents_found']}  "
              f"upserted={r['agents_upserted']}  failed={r['agents_failed']}  "
              f"duration={r['duration_seconds']:.1f}s  {status}")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", default=None, help="Show details for a specific agent ID")
    parser.add_argument("--logs",  action="store_true", help="Show run log history")
    parser.add_argument("--db",    default=DB)
    args = parser.parse_args()

    if args.logs:
        show_logs(args.db)
    elif args.agent:
        show_agent(args.db, args.agent)
    else:
        show_agents(args.db)
