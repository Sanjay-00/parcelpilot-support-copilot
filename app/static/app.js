function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = String(value);
  return div.innerHTML;
}

function currentUserId() {
  return document.getElementById("user-select").value;
}

document.querySelectorAll("nav button").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("nav button, .tab").forEach(el => el.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(btn.dataset.tab).classList.add("active");
    if (btn.dataset.tab === "overview") loadOverview();
    if (btn.dataset.tab === "audit") loadActions();
  });
});

document.getElementById("ask-button").addEventListener("click", async () => {
  const query = document.getElementById("query-input").value;
  const res = await fetch("/api/investigate", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({query, user_id: currentUserId()}),
  });
  const data = await res.json();
  document.getElementById("tool-timeline").innerHTML =
    data.tool_call_log.map(t => `<div>&#128269; ${escapeHtml(t.tool)}(${escapeHtml(t.args)})</div>`).join("");
  document.getElementById("answer").innerText =
    `[${data.decision_status}] ${data.answer_text}`;
});

async function loadOverview() {
  const res = await fetch(`/api/overview?user_id=${encodeURIComponent(currentUserId())}`);
  const data = await res.json();

  const slaDiv = document.getElementById("sla-risk-list");
  if (!data.sla_risk || data.sla_risk.length === 0) {
    slaDiv.innerHTML = "<p>No open tickets visible to this user.</p>";
  } else {
    slaDiv.innerHTML = data.sla_risk.map(r => {
      if (r.needs_review) {
        return `<div class="risk-row">🟡 ${escapeHtml(r.ticket_id)} — severity unclear, needs human review</div>`;
      }
      const flag = r.at_risk ? "🔴" : "🟢";
      return `<div class="risk-row">${flag} ${escapeHtml(r.ticket_id)} — ${escapeHtml(r.severity)}${r.at_risk ? " (AT RISK)" : ""}</div>`;
    }).join("");
  }

  const clusterDiv = document.getElementById("issue-clusters-list");
  if (!data.clusters || data.clusters.length === 0) {
    clusterDiv.innerHTML = "<p>No recurring issues detected among visible open tickets.</p>";
  } else {
    clusterDiv.innerHTML = data.clusters.map(c => `
      <div class="cluster-row">
        <strong>${escapeHtml(c.ki_id)}</strong>${c.is_multi_customer ? " ⚠️ multi-customer" : ""}<br>
        Tickets: ${c.ticket_ids.map(escapeHtml).join(", ")}<br>
        Accounts: ${c.account_ids.map(escapeHtml).join(", ")}
      </div>
    `).join("");
  }
}

async function loadActions() {
  const res = await fetch(`/api/actions?user_id=${encodeURIComponent(currentUserId())}`);
  const data = await res.json();
  const div = document.getElementById("actions-list");

  if (!data.actions || data.actions.length === 0) {
    div.innerHTML = "<p>No actions prepared yet for accounts visible to this user.</p>";
    return;
  }

  div.innerHTML = data.actions.map(a => `
    <div class="action-row" data-action-id="${escapeHtml(a.action_id)}">
      <strong>${escapeHtml(a.action_type)}</strong> — ${escapeHtml(a.account_id)} — status: ${escapeHtml(a.status)}
      ${a.status === "PREPARED" ? `<button class="confirm-btn" data-action-id="${escapeHtml(a.action_id)}">Confirm</button>` : ""}
    </div>
  `).join("");

  div.querySelectorAll(".confirm-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      const actionId = btn.dataset.actionId;
      await fetch("/api/actions/confirm", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({action_id: actionId, user_id: currentUserId()}),
      });
      loadActions();
    });
  });
}
