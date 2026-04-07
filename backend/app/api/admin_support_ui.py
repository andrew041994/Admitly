from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["admin-support-ui"])


@router.get("/admin/support", response_class=HTMLResponse)
def admin_support_workspace() -> str:
    return """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Admin Order Support</title>
  <style>
    :root { color-scheme: light dark; }
    body { margin: 0; font-family: Inter, system-ui, -apple-system, sans-serif; background: #0b1020; color: #f3f4f6; }
    .shell { max-width: 1200px; margin: 0 auto; padding: 20px; }
    h1 { margin: 0 0 6px; }
    .muted { color: #9ca3af; }
    .grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: 12px; }
    .card { background: #131a2d; border: 1px solid #29314a; border-radius: 10px; padding: 14px; }
    .span-12 { grid-column: span 12; }
    .span-6 { grid-column: span 6; }
    .span-4 { grid-column: span 4; }
    .span-8 { grid-column: span 8; }
    label { display: block; font-size: 12px; color: #c7cedf; margin: 8px 0 4px; }
    input, select, textarea, button { width: 100%; box-sizing: border-box; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: #f8fafc; padding: 10px; }
    textarea { min-height: 90px; resize: vertical; }
    button { cursor: pointer; background: #1d4ed8; border-color: #1e40af; font-weight: 600; }
    button.secondary { background: #0f172a; }
    button[disabled] { opacity: .55; cursor: not-allowed; }
    .row { display: flex; gap: 8px; align-items: end; }
    .row > * { flex: 1; }
    .badge { display: inline-block; padding: 3px 8px; border-radius: 999px; border: 1px solid #3b4f79; font-size: 12px; margin: 2px 6px 2px 0; }
    .kvs { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 14px; }
    .k { font-size: 12px; color: #9ca3af; }
    .v { margin-bottom: 8px; }
    .item { border: 1px solid #334155; border-radius: 8px; padding: 10px; margin-top: 8px; }
    .system { border-color: #7c3aed; }
    .timeline-item { border-left: 3px solid #334155; margin: 10px 0; padding: 6px 10px; }
    .error { color: #fca5a5; }
    .ok { color: #86efac; }
    .hidden { display: none; }
    @media (max-width: 900px) { .span-6,.span-4,.span-8 { grid-column: span 12; } }
  </style>
</head>
<body>
  <div class=\"shell\">
    <h1>Order Support</h1>
    <div class=\"muted\">Admin support workspace for order snapshots, case updates, notes, timeline, and actions.</div>
    <div id=\"notice\" class=\"muted\" style=\"margin-top:8px\"></div>

    <div class=\"card\" style=\"margin-top:12px\">
      <form id=\"lookup-form\" class=\"row\">
        <div>
          <label for=\"admin-user-id\">Admin User ID (header x-user-id)</label>
          <input id=\"admin-user-id\" type=\"number\" min=\"1\" placeholder=\"e.g. 1\" required />
        </div>
        <div>
          <label for=\"order-id\">Order ID</label>
          <input id=\"order-id\" type=\"text\" placeholder=\"Enter order ID\" required />
        </div>
        <div>
          <button id=\"load-btn\" type=\"submit\">Load order</button>
        </div>
        <div>
          <button id=\"clear-btn\" class=\"secondary\" type=\"button\">Clear</button>
        </div>
      </form>
    </div>

    <div id=\"workspace\" class=\"grid hidden\" style=\"margin-top:12px\">
      <section class=\"card span-6\"><h3>Order summary</h3><div id=\"order-summary\"></div></section>
      <section class=\"card span-6\"><h3>Payment / refund / dispute / promo / transfer</h3><div id=\"ops-summary\"></div></section>

      <section class=\"card span-4\">
        <h3>Support case</h3>
        <div id=\"case-empty\" class=\"muted\">No support case yet.</div>
        <form id=\"case-form\" class=\"hidden\">
          <label>Status</label><select id=\"case-status\"><option value=\"\">No change</option><option>open</option><option>investigating</option><option>resolved</option><option>closed</option></select>
          <label>Priority</label><select id=\"case-priority\"><option value=\"\">No change</option><option>low</option><option>normal</option><option>high</option><option>urgent</option></select>
          <label>Assigned admin user ID</label><input id=\"case-assignee\" type=\"number\" min=\"1\" />
          <label>Category</label><input id=\"case-category\" type=\"text\" placeholder=\"refund_issue\" />
          <button id=\"case-save\" type=\"submit\">Update case</button>
        </form>
      </section>

      <section class=\"card span-8\">
        <h3>Internal notes</h3>
        <form id=\"note-form\">
          <label>Add internal note</label>
          <textarea id=\"note-body\" placeholder=\"Type note\"></textarea>
          <button id=\"note-save\" type=\"submit\">Add note</button>
        </form>
        <div id=\"notes-list\"></div>
      </section>

      <section class=\"card span-8\"><h3>Timeline / audit trail</h3><div id=\"timeline\"></div></section>
      <section class=\"card span-4\">
        <h3>Admin actions</h3>
        <div id=\"actions\" class=\"row\" style=\"flex-direction:column; align-items:stretch\"></div>
      </section>
    </div>
  </div>

  <script>
    const state = { adminUserId: null, orderId: null, snapshot: null, loading: false };

    const SENSITIVE_ACTIONS = new Set(["flag_for_fraud_review", "remove_promo_application"]);
    const ACTIONS = [
      ["resend_confirmation", false],
      ["resend_transfer_invite", false],
      ["reopen_refund_review", false],
      ["flag_for_fraud_review", true],
      ["remove_promo_application", true],
      ["re-run_reconciliation", false],
    ];

    const notice = document.getElementById("notice");
    const workspace = document.getElementById("workspace");

    function say(msg, cls = "muted") {
      notice.className = cls;
      notice.textContent = msg;
    }

    function fmtDate(value) {
      return value ? new Date(value).toLocaleString() : "—";
    }

    function fmtMoney(amount, currency) {
      if (amount === null || amount === undefined) return "—";
      return new Intl.NumberFormat(undefined, { style: "currency", currency: currency || "USD" }).format(amount);
    }

    async function api(path, options = {}) {
      const headers = { "Content-Type": "application/json", "x-user-id": String(state.adminUserId || "") };
      const res = await fetch(path, { ...options, headers: { ...headers, ...(options.headers || {}) } });
      if (!res.ok) {
        let detail = `Request failed (${res.status})`;
        try { const body = await res.json(); detail = body.detail || detail; } catch {}
        throw new Error(detail);
      }
      return res.status === 204 ? null : res.json();
    }

    function kvs(entries) {
      return `<div class=\"kvs\">${entries.map(([k, v]) => `<div><div class=\"k\">${k}</div><div class=\"v\">${v ?? "—"}</div></div>`).join("")}</div>`;
    }

    function renderSummary(s) {
      document.getElementById("order-summary").innerHTML = kvs([
        ["Order ID", s.order_id], ["Event", s.event_title || `#${s.event_id}`], ["Event ID", s.event_id], ["Buyer", `User #${s.buyer_user_id}`],
        ["Status", s.order_status], ["Quantity", s.quantity], ["Currency", s.currency], ["Created", fmtDate(s.timeline?.[0]?.timestamp)]
      ]);
      document.getElementById("ops-summary").innerHTML = kvs([
        ["Subtotal", fmtMoney(s.subtotal_amount, s.currency)], ["Discount", fmtMoney(s.discount_amount, s.currency)], ["Total", fmtMoney(s.total_amount, s.currency)],
        ["Payment ref", s.payment_reference || "—"], ["Payment verify", s.payment_verification_status], ["Paid at", fmtDate(s.paid_at)],
        ["Refund status", s.refund_status], ["Refunded at", fmtDate(s.refunded_at)], ["Disputes", s.dispute_count], ["Transfers", s.transfer_invite_count],
        ["Promo", s.promo_code_text || "—"], ["Reconciliation", `${s.reconciliation_status} / ${s.payout_status}`]
      ]);
    }

    function renderCase(s) {
      const form = document.getElementById("case-form");
      const empty = document.getElementById("case-empty");
      if (!s.support_case) {
        form.classList.add("hidden");
        empty.classList.remove("hidden");
        return;
      }
      empty.classList.add("hidden");
      form.classList.remove("hidden");
      document.getElementById("case-status").value = s.support_case.status;
      document.getElementById("case-priority").value = s.support_case.priority;
      document.getElementById("case-assignee").value = s.support_case.assigned_to_user_id || "";
      document.getElementById("case-category").value = s.support_case.category || "";
    }

    function renderNotes(s) {
      const list = document.getElementById("notes-list");
      list.innerHTML = (s.support_notes || []).map((n) => {
        const cls = n.is_system_note ? "item system" : "item";
        const kind = n.is_system_note ? "System" : "Admin";
        return `<div class=\"${cls}\"><div><strong>${kind} note</strong> · ${fmtDate(n.created_at)} · user:${n.author_user_id}</div><div>${n.body}</div></div>`;
      }).join("") || "<div class='muted'>No notes.</div>";
    }

    function renderTimeline(s) {
      const t = document.getElementById("timeline");
      t.innerHTML = (s.timeline || []).map((item) => {
        const meta = item.metadata ? `<div class='muted'>${JSON.stringify(item.metadata)}</div>` : "";
        return `<div class='timeline-item'><div><strong>${item.title}</strong> <span class='badge'>${item.type}</span></div><div>${item.description}</div><div class='muted'>${fmtDate(item.timestamp)} · ${item.actor || "system"}</div>${meta}</div>`;
      }).join("") || "<div class='muted'>No timeline entries.</div>";
    }

    function renderActions() {
      const box = document.getElementById("actions");
      box.innerHTML = ACTIONS.map(([name, sensitive]) => `<button data-action=\"${name}\" class=\"secondary\">${name}${sensitive ? " (reason)" : ""}</button>`).join("");
      box.querySelectorAll("button").forEach((btn) => btn.addEventListener("click", () => runAction(btn.dataset.action, btn)));
    }

    async function loadSnapshot(orderId) {
      state.orderId = orderId;
      say(`Loading order ${orderId}...`);
      try {
        state.snapshot = await api(`/admin/support/orders/${orderId}`);
        workspace.classList.remove("hidden");
        renderSummary(state.snapshot);
        renderCase(state.snapshot);
        renderNotes(state.snapshot);
        renderTimeline(state.snapshot);
        renderActions();
        say(`Loaded order ${orderId}.`, "ok");
      } catch (err) {
        say(err.message, "error");
      }
    }

    document.getElementById("lookup-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const userId = Number(document.getElementById("admin-user-id").value);
      const orderRaw = document.getElementById("order-id").value.trim();
      if (!orderRaw) return say("Order ID is required.", "error");
      if (!userId) return say("Admin user ID is required.", "error");
      state.adminUserId = userId;
      await loadSnapshot(Number(orderRaw));
    });

    document.getElementById("clear-btn").addEventListener("click", () => {
      state.orderId = null;
      state.snapshot = null;
      workspace.classList.add("hidden");
      say("Cleared current order.");
    });

    document.getElementById("note-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!state.orderId) return;
      const bodyEl = document.getElementById("note-body");
      const body = bodyEl.value.trim();
      if (!body) return say("Note body is required.", "error");
      const btn = document.getElementById("note-save");
      btn.disabled = true;
      try {
        await api(`/admin/support/orders/${state.orderId}/notes`, { method: "POST", body: JSON.stringify({ body }) });
        bodyEl.value = "";
        await loadSnapshot(state.orderId);
        say("Note added.", "ok");
      } catch (err) {
        say(err.message, "error");
      } finally {
        btn.disabled = false;
      }
    });

    document.getElementById("case-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!state.orderId) return;
      const payload = {
        status: document.getElementById("case-status").value || null,
        priority: document.getElementById("case-priority").value || null,
        assigned_to_user_id: document.getElementById("case-assignee").value ? Number(document.getElementById("case-assignee").value) : null,
        category: document.getElementById("case-category").value.trim() || null,
      };
      const btn = document.getElementById("case-save");
      btn.disabled = true;
      try {
        await api(`/admin/support/orders/${state.orderId}/case`, { method: "PATCH", body: JSON.stringify(payload) });
        await loadSnapshot(state.orderId);
        say("Case updated.", "ok");
      } catch (err) {
        say(err.message, "error");
      } finally {
        btn.disabled = false;
      }
    });

    async function runAction(action, button) {
      if (!state.orderId) return;
      let reason = null;
      if (SENSITIVE_ACTIONS.has(action)) {
        reason = (window.prompt(`Reason required for ${action}:`) || "").trim();
        if (!reason) return say("Reason is required for this action.", "error");
        if (!window.confirm(`Confirm action: ${action}?`)) return;
      } else if (window.confirm(`Run action ${action}?`)) {
        reason = "";
      } else {
        return;
      }

      button.disabled = true;
      try {
        const result = await api(`/admin/support/orders/${state.orderId}/actions`, {
          method: "POST",
          body: JSON.stringify({ action_type: action, reason: reason || null }),
        });
        await loadSnapshot(state.orderId);
        say(result.message || `Action ${action} completed.`, result.success ? "ok" : "error");
      } catch (err) {
        say(err.message, "error");
      } finally {
        button.disabled = false;
      }
    }
  </script>
</body>
</html>
"""
