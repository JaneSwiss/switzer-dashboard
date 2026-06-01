"""
HTML report generator — two-tab layout: DM Leads and Email Leads.
- Static mode (default): generates a file and opens it in the browser.
- Server mode: called by report_server.py — status changes saved live via localhost:8765.
"""

import subprocess
from datetime import date
from pathlib import Path

DRAFTS_DIR  = Path(__file__).resolve().parents[2] / "outputs" / "leads" / "outreach-drafts"
REPORTS_DIR = Path(__file__).resolve().parents[2] / "outputs" / "leads"
SERVER_URL  = "http://127.0.0.1:8765"

STATUS_OPTIONS = ["found", "qualified", "messaged", "replied", "paid"]


def _load_draft(lead_id: str):
    if not DRAFTS_DIR.exists():
        return None, ""
    for path in DRAFTS_DIR.glob(f"{lead_id}-*.txt"):
        text = path.read_text(encoding="utf-8")
        parts = path.stem.split("-")
        outreach_type = parts[-1] if parts else ""
        body = text.split("─" * 10, 1)[-1].strip() if "─" * 10 in text else text.strip()
        return outreach_type, body
    return None, ""


def _load_email_draft(lead_id: str):
    """Load email-specific draft, returning (subject, body) or ('', '')."""
    if not DRAFTS_DIR.exists():
        return "", ""
    for path in DRAFTS_DIR.glob(f"{lead_id}-*-email.txt"):
        text = path.read_text(encoding="utf-8")
        subject = ""
        for line in text.splitlines():
            if line.startswith("Subject:"):
                subject = line.split("Subject:", 1)[1].strip()
                break
        separator = "─" * 60
        body = text.split(separator, 1)[1].strip() if separator in text else ""
        return subject, body
    return "", ""


def _priority_class(score) -> str:
    try:
        s = int(score or 0)
    except (ValueError, TypeError):
        s = 0
    if s >= 10: return "high"
    if s >= 6:  return "mid"
    return "low"


def _contact_display(lead: dict) -> str:
    parts = []
    if lead.get("contact_email"):
        parts.append(f'<a href="mailto:{lead["contact_email"]}">{lead["contact_email"]}</a>')
    if lead.get("instagram_handle"):
        handle = lead["instagram_handle"].lstrip("@")
        parts.append(f'<a href="https://instagram.com/{handle}" target="_blank">{lead["instagram_handle"]}</a>')
    if lead.get("contact_page_url"):
        parts.append(f'<a href="{lead["contact_page_url"]}" target="_blank">Contact form</a>')
    if lead.get("etsy_url") and not parts:
        parts.append(f'<a href="{lead["etsy_url"]}" target="_blank">Etsy message</a>')
    return "<br>".join(parts) if parts else "<span class='empty'>—</span>"


def _links_display(lead: dict) -> str:
    parts = []
    if lead.get("etsy_url"):
        parts.append(f'<a href="{lead["etsy_url"]}" target="_blank">Etsy</a>')
    if lead.get("website"):
        parts.append(f'<a href="{lead["website"]}" target="_blank">Website</a>')
    return " · ".join(parts) if parts else "<span class='empty'>—</span>"


def _build_row(lead: dict, server_mode: bool, tab: str) -> str:
    lead_id  = lead.get("lead_id", "")
    business = lead.get("shop_or_business_name") or lead.get("owner_name") or "Unknown"
    owner    = lead.get("owner_name") or ""
    niche    = lead.get("product_type") or "—"
    source   = lead.get("source") or "—"
    status   = lead.get("status") or "found"
    score    = lead.get("priority_score") or "—"
    pint     = lead.get("pinterest_present") or "—"
    pclass   = _priority_class(score)

    if tab == "email":
        subject, draft = _load_email_draft(lead_id)
        outreach_type  = "email"
        sent_date      = lead.get("outreach_date") or ""
    else:
        outreach_type, draft = _load_draft(lead_id)
        subject   = ""
        sent_date = ""

    options_html = "".join(
        f'<option value="{s}" {"selected" if s == status else ""}>{s.capitalize()}</option>'
        for s in STATUS_OPTIONS
    )
    if server_mode:
        status_cell = f"""<select class="status-select status-{status}" id="sel-{lead_id}"
          onchange="updateStatus('{lead_id}', this)">
          {options_html}
        </select>"""
    else:
        status_cell = f'<span class="status status-{status}">{status.capitalize()}</span>'

    draft_panel = ""
    msg_btn = "<span class='no-draft'>—</span>"

    if draft:
        escaped = (
            draft
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>")
        )
        type_label = {
            "dm": "Instagram DM",
            "email": "Email",
            "contact-form": "Contact form message",
        }.get((outreach_type or "").lower(), "Message")

        subject_line = f'<div class="draft-subject">Subject: {subject}</div>' if subject else ""

        draft_panel = f"""
        <tr class="draft-panel" id="panel-{lead_id}" style="display:none;">
          <td colspan="9">
            <div class="draft-box">
              <div class="draft-meta">{type_label} &middot; {business}</div>
              {subject_line}
              <div class="draft-text" id="draft-{lead_id}">{escaped}</div>
              <button class="copy-btn" onclick="copyDraft(event, '{lead_id}')">Copy message</button>
            </div>
          </td>
        </tr>"""

        msg_btn = f"""<button class="msg-btn" onclick="toggleDraft(event, '{lead_id}')" title="View message">
          <span>&#9993;</span> <span class="msg-label">View</span>
        </button>"""

    if tab == "email":
        _subj_html   = subject if subject else "<span class='empty'>—</span>"
        subject_cell = f'<td class="subject-cell"><span class="subject-text">{_subj_html}</span></td>'
        sent_cell    = f'<td><span class="status status-messaged">Sent {sent_date}</span></td>' if sent_date else '<td><span class="empty">—</span></td>'
        view_cell    = f"<td class='msg-cell'>{msg_btn}</td>"
    else:
        subject_cell = sent_cell = view_cell = ""

    colspan = "10" if tab == "email" else "9"
    if draft_panel:
        draft_panel = draft_panel.replace('colspan="9"', f'colspan="{colspan}"')

    row = f"""
    <tr class="lead-row priority-{pclass}" id="row-{lead_id}"
        data-source="{source}" data-status="{status}"
        data-niche="{niche.lower()}" data-pinterest="{pint}"
        data-hasmsg="{'1' if draft else '0'}">
      <td><span class="badge source-{source}">{source}</span></td>
      <td>
        <strong>{business}</strong>
        {"<br><small>" + owner + "</small>" if owner else ""}
      </td>
      <td>{niche}</td>
      <td>{_contact_display(lead)}</td>
      {subject_cell}
      <td><span class="score score-{pclass}">{score}</span></td>
      <td class="status-cell">{status_cell}</td>
      {sent_cell if tab == "email" else ""}
      {"<td class='msg-cell'>" + msg_btn + "</td>" if tab == "dm" else view_cell}
    </tr>
    {draft_panel}"""

    return row


def _has_msg_filter(tab: str) -> str:
    if tab == "email":
        return ""
    return (
        '<div style="display:flex;align-items:center;gap:6px;">'
        f'<input type="checkbox" id="fHasMsg-{tab}" onchange="filterTable(\'{tab}\')">'
        f'<label for="fHasMsg-{tab}" style="cursor:pointer">Has message</label>'
        '</div>'
    )


def _build_table(leads: list, server_mode: bool, tab: str, tab_id: str) -> str:
    rows = "".join(_build_row(l, server_mode, tab) for l in leads)

    sent     = sum(1 for l in leads if l.get("outreach_date"))
    messaged = sum(1 for l in leads if l.get("status") == "messaged")

    if tab == "email":
        col_last     = "<th>Sent</th>"
        stats_extra  = f'<div class="stat"><div class="num">{sent}</div><div class="lbl">Sent</div></div>'
        drafted_stat = sum(1 for l in leads if _load_email_draft(l.get("lead_id", ""))[1])
    else:
        col_last     = "<th>Message</th>"
        stats_extra  = ""
        drafted_stat = sum(1 for l in leads if _load_draft(l.get("lead_id", ""))[1])


    return f"""
<div id="{tab_id}" class="tab-content">
  <div class="tab-stats">
    <div class="stat"><div class="num">{len(leads)}</div><div class="lbl">Total</div></div>
    <div class="stat"><div class="num">{drafted_stat}</div><div class="lbl">Drafts ready</div></div>
    <div class="stat"><div class="num">{messaged}</div><div class="lbl">Messaged</div></div>
    {stats_extra}
  </div>
  <div class="filters">
    <div>
      <label>Search</label>
      <input type="text" id="search-{tab}" placeholder="name, niche..." oninput="filterTable('{tab}')">
    </div>
    <div>
      <label>Status</label>
      <select id="fStatus-{tab}" onchange="filterTable('{tab}')">
        <option value="">All</option>
        <option value="found">Found</option>
        <option value="qualified">Qualified</option>
        <option value="messaged">Messaged</option>
        <option value="replied">Replied</option>
        <option value="paid">Paid</option>
      </select>
    </div>
    <div>
      <label>Source</label>
      <select id="fSource-{tab}" onchange="filterTable('{tab}')">
        <option value="">All</option>
        <option value="etsy">Etsy</option>
        <option value="instagram">Instagram</option>
        <option value="google">Google</option>
      </select>
    </div>
    <div style="display:flex;align-items:center;gap:6px;">
      <input type="checkbox" id="fNoPint-{tab}" onchange="filterTable('{tab}')">
      <label for="fNoPint-{tab}" style="cursor:pointer">No Pinterest only</label>
    </div>
    {_has_msg_filter(tab)}
  </div>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Source</th>
          <th>Business</th>
          <th>Niche</th>
          <th>Contact</th>
          {"<th>Subject line</th>" if tab == "email" else "<th>Links</th><th>Pinterest</th>"}
          <th>Score</th>
          <th>Status</th>
          {col_last}
          {"<th>Preview</th>" if tab == "email" else ""}
        </tr>
      </thead>
      <tbody>
        {rows}
      </tbody>
    </table>
  </div>
</div>"""


def generate(leads: list, open_browser: bool = True, server_mode: bool = False):
    today = date.today().isoformat()

    # Split into email leads and DM leads
    email_leads = [l for l in leads if l.get("contact_email")]
    dm_leads    = [l for l in leads if not l.get("contact_email")]

    total     = len(leads)
    email_cnt = len(email_leads)
    dm_cnt    = len(dm_leads)

    email_table = _build_table(email_leads, server_mode, "email", "tab-email")
    dm_table    = _build_table(dm_leads,    server_mode, "dm",    "tab-dm")

    server_note = ""
    if not server_mode:
        server_note = """<div class="server-note">
          Status changes are view-only here. Run <code>python3 skills/lead-gen-agent/main.py --serve</code> to track progress live.
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Lead Tracker</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          background: #f8f5f2; color: #383838; font-size: 14px; }}

  .header {{ background: #383838; color: #f8f5f2; padding: 24px 40px; }}
  .header h1 {{ font-size: 19px; font-weight: 600; letter-spacing: 0.02em; }}
  .header p  {{ color: #bbb0aa; font-size: 13px; margin-top: 3px; }}

  .server-note {{ background: #fde8d4; color: #8a3a00; font-size: 12px;
                  padding: 10px 40px; border-bottom: 1px solid #f5c6a0; }}
  .server-note code {{ background: rgba(0,0,0,0.08); padding: 1px 5px; border-radius: 3px;
                       font-family: monospace; }}

  /* Tabs */
  .tab-nav {{ background: #fff; border-bottom: 2px solid #e8e3de;
              padding: 0 40px; display: flex; gap: 0; }}
  .tab-btn {{ background: none; border: none; border-bottom: 3px solid transparent;
              padding: 14px 22px; font-size: 14px; font-weight: 500; color: #a5988e;
              cursor: pointer; margin-bottom: -2px; transition: all 0.15s; }}
  .tab-btn:hover {{ color: #383838; }}
  .tab-btn.active {{ color: #8d6e63; border-bottom-color: #8d6e63; }}
  .tab-btn .count {{ background: #f0ebe7; color: #8d6e63; border-radius: 10px;
                     padding: 1px 7px; font-size: 11px; margin-left: 6px; font-weight: 600; }}
  .tab-btn.active .count {{ background: #8d6e63; color: #fff; }}

  .tab-content {{ display: none; }}
  .tab-content.active {{ display: block; }}

  /* Per-tab stats */
  .tab-stats {{ background: #fff; border-bottom: 1px solid #e8e3de;
               padding: 14px 40px; display: flex; gap: 28px; align-items: center; flex-wrap: wrap; }}
  .stat .num {{ font-size: 26px; font-weight: 700; color: #8d6e63; }}
  .stat .lbl {{ font-size: 11px; color: #a5988e; text-transform: uppercase; letter-spacing: 0.06em; }}

  .filters {{ background: #fff; padding: 12px 40px; border-bottom: 1px solid #e8e3de;
              display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }}
  .filters label {{ font-size: 11px; color: #a5988e; text-transform: uppercase;
                    letter-spacing: 0.05em; margin-right: 3px; }}
  .filters input, .filters select {{
    border: 1px solid #e8e3de; border-radius: 4px; padding: 5px 10px;
    font-size: 13px; color: #383838; background: #f8f5f2; outline: none; }}
  .filters input:focus, .filters select:focus {{ border-color: #8d6e63; }}

  .table-wrap {{ padding: 20px 40px; overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff;
           border-radius: 8px; overflow: hidden;
           box-shadow: 0 1px 4px rgba(0,0,0,0.06); }}
  th {{ background: #383838; color: #f8f5f2; font-size: 11px; font-weight: 600;
        letter-spacing: 0.06em; text-transform: uppercase; padding: 11px 14px;
        text-align: left; white-space: nowrap; }}
  td {{ padding: 10px 14px; border-bottom: 1px solid #f0ebe7; vertical-align: middle;
        line-height: 1.5; }}
  td small {{ color: #a5988e; font-size: 12px; }}
  tr.lead-row:hover td {{ background: #fdfcfb; }}
  tr.lead-row.priority-high {{ border-left: 3px solid #8d6e63; }}
  tr.lead-row.priority-mid  {{ border-left: 3px solid #bbb0aa; }}
  tr.lead-row.priority-low  {{ border-left: 3px solid #e8e3de; }}
  tr.lead-row.sent td {{ opacity: 0.45; }}

  .status-select {{
    border: 1px solid #e8e3de; border-radius: 4px; padding: 4px 8px;
    font-size: 11px; background: #f8f5f2; color: #383838; cursor: pointer; outline: none;
  }}
  .status-select.status-messaged {{ background: #e8f7dc; color: #3a7a30; border-color: #c4e6b0; }}
  .status-select.status-replied  {{ background: #fde8d4; color: #c05c00; border-color: #f5c6a0; }}
  .status-select.status-paid     {{ background: #383838; color: #f8f5f2; }}
  .status-select.status-qualified {{ background: #dcedf7; color: #1a5e8a; border-color: #b0d4ec; }}
  .status-select.status-found    {{ background: #f0ebe7; color: #8d6e63; }}
  .status-select.saving {{ opacity: 0.6; pointer-events: none; }}
  .status-select.saved  {{ outline: 2px solid #6a9e72; outline-offset: 1px; }}

  .badge {{ font-size: 11px; padding: 2px 8px; border-radius: 3px; font-weight: 500; }}
  .source-etsy      {{ background: #fde8d4; color: #c05c00; }}
  .source-instagram {{ background: #f3e0f7; color: #7b2d8b; }}
  .source-google,
  .source-bing      {{ background: #dcedf7; color: #1a5e8a; }}

  .score {{ font-weight: 700; font-size: 13px; }}
  .score-high {{ color: #8d6e63; }}
  .score-mid  {{ color: #bbb0aa; }}
  .score-low  {{ color: #c8c0bb; }}

  .pint-no  {{ color: #6a9e72; font-weight: 600; font-size: 12px; }}
  .pint-yes {{ color: #bbb0aa; font-size: 12px; }}

  .status {{ font-size: 11px; padding: 3px 8px; border-radius: 3px; }}
  .status-found     {{ background: #f0ebe7; color: #8d6e63; }}
  .status-qualified {{ background: #dcedf7; color: #1a5e8a; }}
  .status-messaged  {{ background: #e8f7dc; color: #3a7a30; }}
  .status-replied   {{ background: #fde8d4; color: #c05c00; }}
  .status-paid      {{ background: #383838; color: #f8f5f2; }}

  .msg-cell {{ text-align: center; }}
  .msg-btn {{
    background: #f8f5f2; border: 1px solid #e8e3de; border-radius: 5px;
    padding: 5px 11px; font-size: 12px; color: #8d6e63; cursor: pointer;
    display: inline-flex; align-items: center; gap: 5px; transition: all 0.15s;
  }}
  .msg-btn:hover {{ background: #8d6e63; color: #fff; border-color: #8d6e63; }}
  .msg-btn.open   {{ background: #8d6e63; color: #fff; border-color: #8d6e63; }}
  .no-draft {{ color: #c8c0bb; font-size: 12px; }}

  tr.draft-panel td {{ background: #fdf9f7; padding: 0 40px 18px 40px;
                       border-bottom: 1px solid #e8e3de; }}
  .draft-box {{ border-left: 3px solid #8d6e63; padding: 14px 18px;
                background: #fff; border-radius: 0 6px 6px 0; }}
  .draft-meta {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.07em;
                 color: #a5988e; margin-bottom: 6px; }}
  .draft-subject {{ font-size: 12px; font-weight: 600; color: #383838; margin-bottom: 10px; }}
  .subject-cell {{ max-width: 300px; }}
  .subject-text {{ font-size: 13px; color: #383838; line-height: 1.4; }}
  .draft-text {{ font-size: 13px; line-height: 1.8; color: #383838; white-space: pre-wrap; }}
  .copy-btn {{ margin-top: 14px; background: #383838; color: #f8f5f2; border: none;
               border-radius: 4px; padding: 7px 18px; font-size: 12px; cursor: pointer; }}
  .copy-btn:hover  {{ background: #8d6e63; }}
  .copy-btn.copied {{ background: #6a9e72; }}

  a {{ color: #8d6e63; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .empty {{ color: #c8c0bb; }}
  .hidden {{ display: none !important; }}
</style>
</head>
<body>

<div class="header">
  <h1>Lead Tracker</h1>
  <p>Pinterest Services &middot; Switzertemplates &middot; {today} &middot; {total} total leads</p>
</div>

{server_note}

<div class="tab-nav">
  <button class="tab-btn active" data-tab="email" onclick="showTab('email')">
    Email Leads <span class="count">{email_cnt}</span>
  </button>
  <button class="tab-btn" data-tab="dm" onclick="showTab('dm')">
    DM &amp; Manual Outreach <span class="count">{dm_cnt}</span>
  </button>
</div>

{email_table}
{dm_table}

<script>
function showTab(tab) {{
  document.querySelectorAll('.tab-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.tab === tab));
  document.querySelectorAll('.tab-content').forEach(c =>
    c.classList.toggle('active', c.id === 'tab-' + tab));
  window._activeTab = tab;
}}

// Activate first tab on load
showTab('email');

function toggleDraft(event, id) {{
  event.stopPropagation();
  const panel = document.getElementById('panel-' + id);
  const btn   = event.currentTarget;
  if (!panel) return;
  const open = panel.style.display !== 'none';
  panel.style.display = open ? 'none' : 'table-row';
  btn.classList.toggle('open', !open);
  btn.querySelector('.msg-label').textContent = open ? 'View' : 'Hide';
}}

function copyDraft(event, id) {{
  event.stopPropagation();
  const el = document.getElementById('draft-' + id);
  if (!el) return;
  const text = el.innerHTML
    .replace(/<br\s*\\/?>/gi, '\\n')
    .replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&middot;/g, '·');
  navigator.clipboard.writeText(text).then(() => {{
    const btn = event.currentTarget;
    const orig = btn.textContent;
    btn.textContent = 'Copied!';
    btn.classList.add('copied');
    setTimeout(() => {{ btn.textContent = orig; btn.classList.remove('copied'); }}, 2000);
  }});
}}

function updateStatus(leadId, sel) {{
  const newStatus = sel.value;
  sel.className = 'status-select status-' + newStatus + ' saving';
  fetch('{SERVER_URL}/update', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ lead_id: leadId, status: newStatus }})
  }})
  .then(r => r.json())
  .then(() => {{
    sel.className = 'status-select status-' + newStatus + ' saved';
    const row = document.getElementById('row-' + leadId);
    if (row) row.dataset.status = newStatus;
    if (newStatus === 'messaged' || newStatus === 'paid') row && row.classList.add('sent');
    else row && row.classList.remove('sent');
    setTimeout(() => {{ sel.className = 'status-select status-' + newStatus; }}, 1200);
  }})
  .catch(() => {{ sel.className = 'status-select status-' + newStatus; }});
}}

function filterTable(tab) {{
  const search  = (document.getElementById('search-' + tab) || {{}}).value || '';
  const src     = (document.getElementById('fSource-' + tab) || {{}}).value || '';
  const stat    = (document.getElementById('fStatus-' + tab) || {{}}).value || '';
  const noPint  = (document.getElementById('fNoPint-' + tab) || {{}}).checked || false;
  const hasMsg  = (document.getElementById('fHasMsg-' + tab) || {{}}).checked || false;

  document.querySelectorAll('#tab-' + tab + ' tr.lead-row').forEach(row => {{
    const panel = row.nextElementSibling;
    const hasPanel = panel && panel.classList.contains('draft-panel');
    const match =
      (!search || row.textContent.toLowerCase().includes(search.toLowerCase())) &&
      (!src    || row.dataset.source === src) &&
      (!stat   || row.dataset.status === stat) &&
      (!noPint || row.dataset.pinterest === 'N') &&
      (!hasMsg || row.dataset.hasmsg === '1');
    row.classList.toggle('hidden', !match);
    if (hasPanel) panel.classList.toggle('hidden', !match);
  }});
}}
</script>
</body>
</html>"""

    if server_mode:
        return html

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"lead-report-{date.today().isoformat()}.html"
    out.write_text(html, encoding="utf-8")
    if open_browser:
        subprocess.Popen(["open", str(out)])
    return out
