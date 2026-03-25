#!/usr/bin/env python3
"""
Maps Hunter Dashboard v2 — AJAX status updates, no full page reloads.
"""

import re
import sqlite3
import urllib.parse

from flask import Flask, jsonify, render_template, request

from messaging.ai_message import generate_whatsapp_message

DB_PATH = "leads_v2.db"

app = Flask(__name__, template_folder="templates")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def clean_phone(phone: str) -> str:
    if not phone or phone == "N/A":
        return ""
    return re.sub(r"[^\d+]", "", phone)


def row_to_lead(row: sqlite3.Row) -> dict:
    phone_clean = clean_phone(row["phone"])
    wa_message = (
        "Dobrý den, viděl jsem vaši provozovnu na Google Maps "
        "a chtěl bych se zeptat na možnost spolupráce. "
        "Máte zájem o krátký rozhovor?"
    )
    keys = row.keys()
    return {
        "id": row["id"],
        "name": row["name"],
        "address": row["address"],
        "phone": row["phone"],
        "rating": row["rating"],
        "reviews_count": row["reviews_count"],
        "maps_url": row["maps_url"],
        "social_link":  row["social_link"]  if "social_link"  in keys else None,
        "category":     row["category"]     if "category"     in keys else None,
        "description":  row["description"]  if "description"  in keys else None,
        "email": row["email"],
        "status": row["status"],
        "wa_url": (
            f"https://wa.me/{phone_clean}?text={urllib.parse.quote(wa_message)}"
            if phone_clean else None
        ),
    }


CATEGORY_LABELS = {
    "barbershop":  "Barbershop",
    "tattoo":      "Tattoo",
    "dentist":     "Dentist",
    "nail_salon":  "Nail Salon",
    "auto_repair": "Auto Repair",
    "yoga":        "Yoga",
}


@app.route("/")
def index():
    status_filter   = request.args.get("status",   "new")
    category_filter = request.args.get("category", "all")
    conn = get_db()

    # Build query dynamically based on both filters
    clauses, params = [], []
    if status_filter != "all":
        clauses.append("status = ?")
        params.append(status_filter)
    if category_filter != "all":
        clauses.append("category = ?")
        params.append(category_filter)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM restaurants {where} ORDER BY rating DESC NULLS LAST",
        params,
    ).fetchall()

    # Status counts (unaffected by category filter, so totals stay meaningful)
    status_counts = {
        r["status"]: r["cnt"]
        for r in conn.execute(
            "SELECT status, COUNT(*) as cnt FROM restaurants GROUP BY status"
        ).fetchall()
    }
    status_counts["all"] = sum(status_counts.values())

    # Category counts (respect status filter so numbers match what's visible)
    cat_where = "WHERE status = ?" if status_filter != "all" else ""
    cat_params = [status_filter] if status_filter != "all" else []
    category_counts = {
        r["category"]: r["cnt"]
        for r in conn.execute(
            f"SELECT category, COUNT(*) as cnt FROM restaurants {cat_where} "
            f"GROUP BY category",
            cat_params,
        ).fetchall()
        if r["category"]
    }
    conn.close()

    leads = [row_to_lead(r) for r in rows]
    return render_template(
        "index_v2.html",
        leads=leads,
        status_filter=status_filter,
        category_filter=category_filter,
        status_counts=status_counts,
        category_counts=category_counts,
        category_labels=CATEGORY_LABELS,
    )


@app.route("/api/status/<int:lead_id>", methods=["POST"])
def api_update_status(lead_id: int):
    """AJAX endpoint — accepts JSON or form data, returns JSON."""
    data = request.get_json(silent=True) or request.form
    new_status = data.get("status", "")

    if new_status not in ("new", "contacted", "rejected"):
        return jsonify({"ok": False, "error": "invalid status"}), 400

    conn = get_db()
    conn.execute(
        "UPDATE restaurants SET status = ? WHERE id = ?", (new_status, lead_id)
    )
    conn.commit()
    conn.close()

    return jsonify({"ok": True, "id": lead_id, "status": new_status})


@app.route("/api/send-whatsapp/<int:lead_id>", methods=["POST"])
def api_send_whatsapp(lead_id: int):
    """Automate WhatsApp Web to send a message to the lead's phone number."""
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"ok": False, "error": "message is required"}), 400

    conn = get_db()
    row = conn.execute(
        "SELECT phone FROM restaurants WHERE id = ?", (lead_id,)
    ).fetchone()
    conn.close()

    if not row:
        return jsonify({"ok": False, "error": "lead not found"}), 404
    phone = row["phone"]
    if not phone or phone == "N/A":
        return jsonify({"ok": False, "error": "no phone number for this lead"}), 400

    try:
        from messaging.whatsapp import send_message
        send_message(phone, message)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/ai-message/<int:lead_id>", methods=["POST"])
def api_ai_message(lead_id: int):
    """Generate a personalized WhatsApp message for a lead via Claude."""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM restaurants WHERE id = ?", (lead_id,)
    ).fetchone()
    conn.close()

    if not row:
        return jsonify({"ok": False, "error": "lead not found"}), 404

    lead = row_to_lead(row)
    try:
        message = generate_whatsapp_message(lead)
        return jsonify({"ok": True, "message": message})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 503
    except Exception as e:
        return jsonify({"ok": False, "error": f"AI generation failed: {e}"}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5051)
