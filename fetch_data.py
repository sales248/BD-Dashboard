"""
OA BD Dashboard — HubSpot Data Fetcher
Generates data.json for the GitHub Pages dashboard.

Requirements:
  pip install requests python-dateutil

Environment variables:
  HUBSPOT_TOKEN   HubSpot Private App access token
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from dateutil.relativedelta import relativedelta
import requests

HUBSPOT_TOKEN = os.environ.get("HUBSPOT_TOKEN", "")
BASE_URL = "https://api.hubapi.com"
HEADERS = {"Authorization": f"Bearer {HUBSPOT_TOKEN}", "Content-Type": "application/json"}

BD_PIPELINE_ID = "68218158"
PORTAL_ID = "44390857"

# Stage IDs
STAGES = {
    "deal_created":     "132946329",
    "dc_outreach":      "244709522",
    "dc_completed":     "222405237",
    "dc_no_show":       "132946331",
    "ac_outreach":      "244520495",
    "ac_no_show":       "133003872",
    "ac_completed":     "132946333",
    "cd_main":          "1029860491",
    "cd_scheduled":     "1053002936",
    "cd_no_show":       "1053002935",
    "cd_completed":     "1053002937",
    "hiring_recruiting":"133348729",
    "closed_won":       "132946334",
    "closed_lost":      "132946335",
    "deal_unqualified": "991351894",
}

MANILA_TZ = timezone(timedelta(hours=8))


def search_deals(filters, properties, limit=200, after=None):
    """Single HubSpot CRM search call."""
    url = f"{BASE_URL}/crm/v3/objects/deals/search"
    body = {
        "filterGroups": [{"filters": f} for f in filters] if isinstance(filters[0], list) else [{"filters": filters}],
        "properties": properties,
        "limit": min(limit, 200),
    }
    if after:
        body["after"] = after
    r = requests.post(url, headers=HEADERS, json=body)
    r.raise_for_status()
    return r.json()


def search_all_deals(filters, properties):
    """Paginate through all results."""
    results = []
    after = None
    while True:
        page = search_deals(filters, properties, limit=200, after=after)
        results.extend(page.get("results", []))
        paging = page.get("paging", {}).get("next", {})
        after = paging.get("after")
        if not after:
            break
    return results, page.get("total", len(results))


def count_stage(stage_id):
    """Return count of deals in this stage."""
    body = {
        "filterGroups": [{"filters": [
            {"propertyName": "pipeline",   "operator": "EQ", "value": BD_PIPELINE_ID},
            {"propertyName": "dealstage",  "operator": "EQ", "value": stage_id},
        ]}],
        "properties": ["hs_object_id"],
        "limit": 1,
    }
    r = requests.post(f"{BASE_URL}/crm/v3/objects/deals/search", headers=HEADERS, json=body)
    r.raise_for_status()
    return r.json().get("total", 0)


def get_total_pipeline():
    body = {
        "filterGroups": [{"filters": [
            {"propertyName": "pipeline", "operator": "EQ", "value": BD_PIPELINE_ID}
        ]}],
        "properties": ["hs_object_id"],
        "limit": 1,
    }
    r = requests.post(f"{BASE_URL}/crm/v3/objects/deals/search", headers=HEADERS, json=body)
    r.raise_for_status()
    return r.json().get("total", 0)


def get_deals_created_between(start_iso, end_iso):
    body = {
        "filterGroups": [{"filters": [
            {"propertyName": "pipeline",   "operator": "EQ",  "value": BD_PIPELINE_ID},
            {"propertyName": "createdate", "operator": "GTE", "value": start_iso},
            {"propertyName": "createdate", "operator": "LTE", "value": end_iso},
        ]}],
        "properties": ["dealname", "dealstage", "createdate"],
        "limit": 1,
    }
    r = requests.post(f"{BASE_URL}/crm/v3/objects/deals/search", headers=HEADERS, json=body)
    r.raise_for_status()
    return r.json().get("total", 0)


def get_paid_between(start_iso, end_iso):
    body = {
        "filterGroups": [{"filters": [
            {"propertyName": "pipeline",               "operator": "EQ",  "value": BD_PIPELINE_ID},
            {"propertyName": "paid_recruitment_date",  "operator": "GTE", "value": start_iso},
            {"propertyName": "paid_recruitment_date",  "operator": "LTE", "value": end_iso},
        ]}],
        "properties": ["dealname"],
        "limit": 1,
    }
    r = requests.post(f"{BASE_URL}/crm/v3/objects/deals/search", headers=HEADERS, json=body)
    r.raise_for_status()
    return r.json().get("total", 0)


def get_top_deals():
    """Fetch the 100 most recently modified active deals for scoring."""
    body = {
        "filterGroups": [{"filters": [
            {"propertyName": "pipeline",  "operator": "EQ",      "value": BD_PIPELINE_ID},
            {"propertyName": "dealstage", "operator": "NOT_IN",
             "values": [STAGES["closed_lost"], STAGES["deal_unqualified"]]},
        ]}],
        "properties": [
            "dealname", "dealstage", "paid_recruitment_date",
            "hs_lastmodifieddate", "notes_last_contacted",
            "hs_is_closed_won", "hs_is_closed_lost", "amount"
        ],
        "sorts": [{"propertyName": "hs_lastmodifieddate", "direction": "DESCENDING"}],
        "limit": 100,
    }
    r = requests.post(f"{BASE_URL}/crm/v3/objects/deals/search", headers=HEADERS, json=body)
    r.raise_for_status()
    data = r.json()

    stage_labels = {v: k.replace("_", " ").title() for k, v in STAGES.items()}
    stage_labels.update({
        STAGES["dc_completed"]:      "DC Completed",
        STAGES["dc_no_show"]:        "DC No Show",
        STAGES["ac_completed"]:      "AC Completed",
        STAGES["ac_no_show"]:        "AC No Show",
        STAGES["hiring_recruiting"]: "Hiring & Recruiting",
        STAGES["closed_won"]:        "Closed Won",
        STAGES["deal_created"]:      "Deal Created",
        STAGES["deal_unqualified"]:  "Deal Unqualified",
    })

    deals = []
    for d in data.get("results", []):
        p = d.get("properties", {})
        last_act = p.get("notes_last_contacted") or p.get("hs_lastmodifieddate")
        deals.append({
            "id": d["id"],
            "name": p.get("dealname", "Unnamed Deal"),
            "stage_id": p.get("dealstage", ""),
            "stage_label": stage_labels.get(p.get("dealstage", ""), p.get("dealstage", "")),
            "paid_recruitment_date": p.get("paid_recruitment_date"),
            "last_activity": last_act,
            "has_notes": bool(p.get("notes_last_contacted")),
            "hs_is_closed_lost": p.get("hs_is_closed_lost", "false") == "true",
            "amount": int(float(p.get("amount") or 0)),
        })
    return deals


def week_bounds(offset_weeks=0):
    """Return (monday_iso, tuesday_23:59_iso) for a given week offset from current week."""
    now = datetime.now(MANILA_TZ)
    # Find most recent Monday
    days_since_monday = now.weekday()  # 0=Mon
    monday = (now - timedelta(days=days_since_monday + offset_weeks * 7)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    tuesday = monday + timedelta(days=1, hours=23, minutes=59, seconds=59)
    return monday.isoformat(), tuesday.isoformat()


def month_bounds(offset_months=0):
    """Return (first_day_iso, last_day_iso) for a month offset."""
    now = datetime.now(MANILA_TZ)
    first = (now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
             - relativedelta(months=abs(offset_months)) if offset_months < 0
             else now.replace(day=1, hour=0, minute=0, second=0, microsecond=0))
    if offset_months < 0:
        first = first.replace(day=1)
    last = (first + relativedelta(months=1) - timedelta(seconds=1))
    return first.isoformat(), last.isoformat()


def main():
    if not HUBSPOT_TOKEN:
        print("ERROR: HUBSPOT_TOKEN environment variable not set.", file=sys.stderr)
        sys.exit(1)

    now = datetime.now(MANILA_TZ)
    print(f"[{now.isoformat()}] Fetching HubSpot data for BD Dashboard…")

    # ── Counts by stage
    print("  Counting pipeline stages…")
    stage_counts = {}
    for key, sid in STAGES.items():
        c = count_stage(sid)
        print(f"    {key}: {c}")
        stage_counts[key] = c

    total = get_total_pipeline()
    print(f"  Total pipeline: {total}")

    dc_attended  = stage_counts["dc_completed"]
    dc_no_show   = stage_counts["dc_no_show"]
    ac_attended  = stage_counts["ac_completed"]
    ac_no_show   = stage_counts["ac_no_show"]
    dc_total     = dc_attended + dc_no_show
    ac_total     = ac_attended + ac_no_show
    dc_rate      = round((dc_attended / dc_total * 100) if dc_total else 0, 1)
    ac_rate      = round((ac_attended / ac_total * 100) if ac_total else 0, 1)

    # Count paid total
    paid_body = {
        "filterGroups": [{"filters": [
            {"propertyName": "pipeline",              "operator": "EQ",           "value": BD_PIPELINE_ID},
            {"propertyName": "paid_recruitment_date", "operator": "HAS_PROPERTY"},
        ]}],
        "properties": ["dealname"],
        "limit": 1,
    }
    r = requests.post(f"{BASE_URL}/crm/v3/objects/deals/search", headers=HEADERS, json=paid_body)
    r.raise_for_status()
    paid_total = r.json().get("total", 0)
    print(f"  Paid total: {paid_total}")

    # ── Weekly
    w0_start, w0_end = week_bounds(0)
    w1_start, w1_end = week_bounds(-1)
    wk_deals  = get_deals_created_between(w0_start, w0_end)
    wk_paid   = get_paid_between(w0_start, w0_end)
    pw_deals  = get_deals_created_between(w1_start, w1_end)
    pw_paid   = get_paid_between(w1_start, w1_end)
    wk_label  = f"{datetime.fromisoformat(w0_start).strftime('%b %-d')} – {datetime.fromisoformat(w0_end).strftime('%-d')}"
    pw_label  = f"{datetime.fromisoformat(w1_start).strftime('%b %-d')} – {datetime.fromisoformat(w1_end).strftime('%-d')}"
    print(f"  Weekly deals: {wk_deals} (prev: {pw_deals})")

    # ── Monthly
    m0_start, m0_end = month_bounds(0)
    m1_start, m1_end = month_bounds(-1)
    mo_deals   = get_deals_created_between(m0_start, m0_end)
    mo_paid    = get_paid_between(m0_start, m0_end)
    pm_deals   = get_deals_created_between(m1_start, m1_end)
    pm_paid    = get_paid_between(m1_start, m1_end)
    mo_label   = datetime.fromisoformat(m0_start).strftime("%B %Y")
    pm_label   = datetime.fromisoformat(m1_start).strftime("%B %Y")
    print(f"  Monthly deals: {mo_deals} / prev: {pm_deals}")

    # ── Other active (exclude known stage groups)
    known_total = sum([
        stage_counts["deal_created"],
        stage_counts["dc_completed"], stage_counts["dc_no_show"],
        stage_counts["ac_completed"], stage_counts["ac_no_show"],
        stage_counts["hiring_recruiting"],
        stage_counts["closed_won"], stage_counts["closed_lost"],
    ])
    other_active = total - known_total

    # ── Top deals
    print("  Fetching top deals for scoring…")
    top_deals = get_top_deals()
    print(f"  Top deals fetched: {len(top_deals)}")

    # ── Build output
    output = {
        "generated_at": now.isoformat(),
        "pipeline": {"id": BD_PIPELINE_ID, "name": "OA Biz Dev Qualified Leads", "total": total},
        "stage_counts": {
            "deal_created":      stage_counts["deal_created"],
            "dc_completed":      stage_counts["dc_completed"],
            "dc_no_show":        stage_counts["dc_no_show"],
            "ac_completed":      stage_counts["ac_completed"],
            "ac_no_show":        stage_counts["ac_no_show"],
            "hiring_recruiting": stage_counts["hiring_recruiting"],
            "closed_won":        stage_counts["closed_won"],
            "closed_lost":       stage_counts["closed_lost"],
            "other_active":      max(0, other_active),
        },
        "attendance": {
            "dc_attended": dc_attended, "dc_no_show": dc_no_show,
            "dc_scheduled_total": dc_total, "dc_rate_pct": dc_rate,
            "ac_attended": ac_attended, "ac_no_show": ac_no_show,
            "ac_scheduled_total": ac_total, "ac_rate_pct": ac_rate,
        },
        "monthly": {
            "label": mo_label, "deals_created": mo_deals, "paid_deals": mo_paid,
            "prev_month_label": pm_label, "prev_deals_created": pm_deals, "prev_paid_deals": pm_paid,
        },
        "weekly": {
            "label": wk_label, "deals_created": wk_deals, "paid_deals": wk_paid,
            "prev_week_label": pw_label, "prev_deals_created": pw_deals, "prev_paid_deals": pw_paid,
        },
        "paid_total": paid_total,
        "conversion": {
            "total_to_dc_attended_pct": round((dc_attended / total * 100) if total else 0, 1),
            "dc_to_ac_pct": round((ac_attended / dc_attended * 100) if dc_attended else 0, 1),
            "overall_to_paid_pct": round((paid_total / total * 100) if total else 0, 1),
        },
        "top_deals": top_deals,
    }

    out_path = os.path.join(os.path.dirname(__file__), "data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"  ✓ data.json written → {out_path}")
    print(f"  Generated at: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")


if __name__ == "__main__":
    main()
