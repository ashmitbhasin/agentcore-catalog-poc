"""
report.py — Generates catalog_report.html from catalog.db.
Run: python report.py
"""

import sqlite3
import html
from pathlib import Path
from datetime import datetime

DB_PATH = "catalog.db"
OUTPUT_PATH = "catalog_report.html"

STATUS_COLORS = {
    "PREPARED": "#16a34a",
    "NOT_PREPARED": "#ca8a04",
    "FAILED": "#dc2626",
}
DEFAULT_STATUS_COLOR = "#64748b"


def esc(value) -> str:
    if value is None:
        return ""
    return html.escape(str(value))


def truncate(text, length=200) -> str:
    if not text:
        return ""
    text = str(text)
    if len(text) <= length:
        return text
    return text[:length] + "..."


def fetch_agents(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("""
        SELECT a.*,
               COUNT(DISTINCT ag.action_group_id) AS action_group_count,
               COUNT(DISTINCT kb.knowledge_base_id) AS knowledge_base_count
        FROM agents a
        LEFT JOIN action_groups ag ON ag.agent_id = a.agent_id
        LEFT JOIN knowledge_bases kb ON kb.agent_id = a.agent_id
        GROUP BY a.agent_id
        ORDER BY a.region, a.agent_name
    """).fetchall()


def fetch_action_groups(conn: sqlite3.Connection, agent_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM action_groups WHERE agent_id = ? ORDER BY action_group_name",
        (agent_id,),
    ).fetchall()


def fetch_knowledge_bases(conn: sqlite3.Connection, agent_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM knowledge_bases WHERE agent_id = ? ORDER BY knowledge_base_id",
        (agent_id,),
    ).fetchall()


def fetch_run_logs(conn: sqlite3.Connection, limit: int = 5) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM run_logs ORDER BY run_at DESC LIMIT ?",
        (limit,),
    ).fetchall()


def status_badge(status: str) -> str:
    color = STATUS_COLORS.get(status, DEFAULT_STATUS_COLOR)
    return f'<span class="badge" style="background:{color}">{esc(status or "UNKNOWN")}</span>'


def render_action_groups_table(action_groups: list[sqlite3.Row]) -> str:
    if not action_groups:
        return '<p class="empty">No action groups.</p>'
    rows = "\n".join(
        f"""<tr>
            <td>{esc(ag['action_group_name'])}</td>
            <td>{esc(ag['action_group_state'])}</td>
            <td>{esc(ag['action_group_id'])}</td>
            <td>{esc(truncate(ag['description'], 80))}</td>
        </tr>"""
        for ag in action_groups
    )
    return f"""
    <table>
        <thead><tr><th>Name</th><th>State</th><th>ID</th><th>Description</th></tr></thead>
        <tbody>{rows}</tbody>
    </table>
    """


def render_knowledge_bases_table(knowledge_bases: list[sqlite3.Row]) -> str:
    if not knowledge_bases:
        return '<p class="empty">No knowledge bases.</p>'
    rows = "\n".join(
        f"""<tr>
            <td>{esc(kb['knowledge_base_id'])}</td>
            <td>{esc(kb['knowledge_base_state'])}</td>
            <td>{esc(truncate(kb['description'], 80))}</td>
        </tr>"""
        for kb in knowledge_bases
    )
    return f"""
    <table>
        <thead><tr><th>ID</th><th>State</th><th>Description</th></tr></thead>
        <tbody>{rows}</tbody>
    </table>
    """


def render_run_logs_table(run_logs: list[sqlite3.Row]) -> str:
    if not run_logs:
        return '<p class="empty">No run logs.</p>'
    rows = "\n".join(
        f"""<tr>
            <td>{esc(r['run_at'])}</td>
            <td>{esc(r['region'])}</td>
            <td>{esc(r['agents_found'])}</td>
            <td>{esc(r['agents_upserted'])}</td>
            <td>{esc(r['agents_failed'])}</td>
            <td>{f"{r['duration_seconds']:.2f}s" if r['duration_seconds'] is not None else ""}</td>
            <td>{esc(r['error']) if r['error'] else '<span class="ok">ok</span>'}</td>
        </tr>"""
        for r in run_logs
    )
    return f"""
    <table>
        <thead><tr><th>Run At</th><th>Region</th><th>Found</th><th>Upserted</th><th>Failed</th><th>Duration</th><th>Status</th></tr></thead>
        <tbody>{rows}</tbody>
    </table>
    """


def render_agent_card(agent: sqlite3.Row, action_groups: list[sqlite3.Row], knowledge_bases: list[sqlite3.Row]) -> str:
    return f"""
    <div class="card">
        <div class="card-header">
            <h2>{esc(agent['agent_name'])}</h2>
            {status_badge(agent['agent_status'])}
        </div>
        <div class="meta-grid">
            <div><span class="label">ID</span>{esc(agent['agent_id'])}</div>
            <div><span class="label">Model</span>{esc(agent['foundation_model'])}</div>
            <div><span class="label">Region</span>{esc(agent['region'])}</div>
            <div><span class="label">Version</span>{esc(agent['agent_version'])}</div>
            <div><span class="label">Created</span>{esc(agent['created_at'])}</div>
            <div><span class="label">IAM Role</span>{esc(agent['iam_role_arn'])}</div>
        </div>
        <div class="instruction">
            <span class="label">Instruction</span>
            <p>{esc(truncate(agent['instruction'], 200)) or '<span class="empty">No instruction set.</span>'}</p>
        </div>
        <div class="subsection">
            <h3>Action Groups ({agent['action_group_count']})</h3>
            {render_action_groups_table(action_groups)}
        </div>
        <div class="subsection">
            <h3>Knowledge Bases ({agent['knowledge_base_count']})</h3>
            {render_knowledge_bases_table(knowledge_bases)}
        </div>
    </div>
    """


def render_region_section(region: str, agents_html: list[str]) -> str:
    return f"""
    <section class="region-section">
        <h2 class="region-title">Region: {esc(region or "unknown")}</h2>
        <div class="card-grid">
            {''.join(agents_html)}
        </div>
    </section>
    """


def build_html(agents, action_groups_by_agent, kbs_by_agent, run_logs) -> str:
    total_agents = len(agents)
    regions = sorted({a["region"] or "unknown" for a in agents})
    total_action_groups = sum(a["action_group_count"] for a in agents)
    total_knowledge_bases = sum(a["knowledge_base_count"] for a in agents)
    prepared_count = sum(1 for a in agents if a["agent_status"] == "PREPARED")

    regions_grouped: dict[str, list] = {}
    for agent in agents:
        regions_grouped.setdefault(agent["region"] or "unknown", []).append(agent)

    region_sections = []
    for region in sorted(regions_grouped):
        cards = [
            render_agent_card(
                agent,
                action_groups_by_agent.get(agent["agent_id"], []),
                kbs_by_agent.get(agent["agent_id"], []),
            )
            for agent in regions_grouped[region]
        ]
        region_sections.append(render_region_section(region, cards))

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>AgentCore Catalog Report</title>
<style>
    * {{ box-sizing: border-box; }}
    body {{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        background: #0f172a;
        color: #e2e8f0;
        margin: 0;
        padding: 0 0 60px;
    }}
    header {{
        background: linear-gradient(135deg, #1e293b, #0f172a);
        padding: 32px 40px;
        border-bottom: 1px solid #334155;
    }}
    header h1 {{ margin: 0 0 4px; font-size: 28px; }}
    header p {{ margin: 0; color: #94a3b8; font-size: 13px; }}
    .stats-bar {{
        display: flex;
        gap: 16px;
        padding: 24px 40px;
        flex-wrap: wrap;
    }}
    .stat {{
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 16px 24px;
        min-width: 140px;
    }}
    .stat .value {{ font-size: 26px; font-weight: 700; color: #38bdf8; }}
    .stat .key {{ font-size: 12px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; }}
    main {{ padding: 0 40px; }}
    .region-section {{ margin-bottom: 40px; }}
    .region-title {{
        font-size: 18px;
        color: #94a3b8;
        border-bottom: 1px solid #334155;
        padding-bottom: 8px;
        margin-bottom: 20px;
    }}
    .card-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(420px, 1fr));
        gap: 20px;
    }}
    .card {{
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 20px;
    }}
    .card-header {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 14px;
    }}
    .card-header h2 {{ margin: 0; font-size: 17px; }}
    .badge {{
        color: #fff;
        font-size: 11px;
        font-weight: 700;
        padding: 4px 10px;
        border-radius: 999px;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        white-space: nowrap;
    }}
    .meta-grid {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 8px 16px;
        font-size: 13px;
        margin-bottom: 14px;
        word-break: break-all;
    }}
    .label {{
        display: block;
        font-size: 11px;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        margin-bottom: 2px;
    }}
    .instruction {{ margin-bottom: 14px; font-size: 13px; }}
    .instruction p {{ margin: 4px 0 0; color: #cbd5e1; }}
    .subsection {{ margin-top: 14px; }}
    .subsection h3 {{ font-size: 13px; color: #94a3b8; margin: 0 0 8px; text-transform: uppercase; letter-spacing: 0.04em; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    th, td {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid #334155; }}
    th {{ color: #64748b; font-weight: 600; text-transform: uppercase; font-size: 11px; }}
    .empty {{ color: #475569; font-style: italic; font-size: 12px; }}
    .ok {{ color: #16a34a; }}
    footer.run-logs {{
        margin-top: 40px;
        padding: 0 40px;
    }}
    footer.run-logs h2 {{
        font-size: 18px;
        color: #94a3b8;
        border-bottom: 1px solid #334155;
        padding-bottom: 8px;
        margin-bottom: 20px;
    }}
</style>
</head>
<body>
<header>
    <h1>AgentCore Catalog Report</h1>
    <p>Generated {esc(generated_at)}</p>
</header>
<div class="stats-bar">
    <div class="stat"><div class="value">{total_agents}</div><div class="key">Agents</div></div>
    <div class="stat"><div class="value">{len(regions)}</div><div class="key">Regions</div></div>
    <div class="stat"><div class="value">{total_action_groups}</div><div class="key">Action Groups</div></div>
    <div class="stat"><div class="value">{total_knowledge_bases}</div><div class="key">Knowledge Bases</div></div>
    <div class="stat"><div class="value">{prepared_count}</div><div class="key">Prepared</div></div>
</div>
<main>
    {''.join(region_sections) if region_sections else '<p class="empty">No agents found in catalog.</p>'}
</main>
<footer class="run-logs">
    <h2>Recent Run Logs</h2>
    {render_run_logs_table(run_logs)}
</footer>
</body>
</html>
"""


def generate_report(db_path: str = DB_PATH, output_path: str = OUTPUT_PATH) -> None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    agents = fetch_agents(conn)
    action_groups_by_agent = {a["agent_id"]: fetch_action_groups(conn, a["agent_id"]) for a in agents}
    kbs_by_agent = {a["agent_id"]: fetch_knowledge_bases(conn, a["agent_id"]) for a in agents}
    run_logs = fetch_run_logs(conn)

    conn.close()

    output = build_html(agents, action_groups_by_agent, kbs_by_agent, run_logs)
    Path(output_path).write_text(output, encoding="utf-8")

    print(f"✓ Report generated: {output_path} ({len(agents)} agents across "
          f"{len({a['region'] for a in agents})} region(s))")


if __name__ == "__main__":
    generate_report()
