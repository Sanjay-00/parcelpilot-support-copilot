function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = String(value);
  return div.innerHTML;
}

function currentUserId() {
  return document.getElementById("user-select").value;
}

document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn, .tab").forEach(el => el.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(btn.dataset.tab).classList.add("active");
    if (btn.dataset.tab === "overview") loadOverview();
    if (btn.dataset.tab === "audit") loadActions();
  });
});

document.querySelectorAll(".chip").forEach(chip => {
  chip.addEventListener("click", () => {
    document.getElementById("query-input").value = chip.dataset.example;
    askQuestion();
  });
});

document.getElementById("ask-button").addEventListener("click", askQuestion);
document.getElementById("query-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") askQuestion();
});

async function askQuestion() {
  const query = document.getElementById("query-input").value.trim();
  if (!query) return;

  const askButton = document.getElementById("ask-button");
  const emptyState = document.getElementById("empty-state");
  const result = document.getElementById("result");
  const timeline = document.getElementById("tool-timeline");
  const answer = document.getElementById("answer");
  const badge = document.getElementById("status-badge");

  askButton.disabled = true;
  askButton.textContent = "Thinking…";
  emptyState.classList.add("hidden");
  result.classList.remove("hidden");
  timeline.innerHTML = `<div class="step"><span class="icon">⏳</span> Understanding your question…</div>`;
  answer.textContent = "";
  badge.textContent = "";
  badge.className = "badge";

  try {
    const res = await fetch("/api/investigate", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({query, user_id: currentUserId()}),
    });
    const data = await res.json();

    if (!res.ok) {
      badge.textContent = "Error";
      badge.classList.add("error");
      answer.textContent = data.detail || "Something went wrong.";
      return;
    }

    const icons = {
      get_order: "📦", get_ticket: "🎫", get_account: "🏢",
      search_policy_documents: "📄",
    };
    timeline.innerHTML = (data.tool_call_log || []).map(t =>
      `<div class="step"><span class="icon">${icons[t.tool] || "🔍"}</span> ${escapeHtml(t.tool)}(${escapeHtml(t.args)})</div>`
    ).join("") || `<div class="step"><span class="icon">💭</span> Answered from reasoning alone — no data lookup needed.</div>`;

    const status = (data.decision_status || "").toLowerCase();
    badge.textContent = data.decision_status || "—";
    badge.classList.add(status === "ready" ? "ready" : "needs_review");
    answer.textContent = data.answer_text || "(no answer text returned)";
  } catch (err) {
    badge.textContent = "Error";
    badge.classList.add("error");
    answer.textContent = "Could not reach the server. Is it running?";
  } finally {
    askButton.disabled = false;
    askButton.textContent = "Ask";
  }
}

async function loadOverview() {
  const slaDiv = document.getElementById("sla-risk-list");
  const clusterDiv = document.getElementById("issue-clusters-list");
  slaDiv.innerHTML = "Loading…";
  clusterDiv.innerHTML = "Loading…";

  const res = await fetch(`/api/overview?user_id=${encodeURIComponent(currentUserId())}`);
  const data = await res.json();

  if (!data.sla_risk || data.sla_risk.length === 0) {
    slaDiv.innerHTML = `<p class="muted-note">No open tickets visible to this user.</p>`;
  } else {
    slaDiv.innerHTML = data.sla_risk.map(r => {
      if (r.needs_review) {
        return `<div class="risk-row"><span class="left">🎫 ${escapeHtml(r.ticket_id)}</span><span class="pill review">Needs review</span></div>`;
      }
      const pillClass = r.at_risk ? "at-risk" : "ok";
      const pillText = r.at_risk ? `${escapeHtml(r.severity)} · At risk` : `${escapeHtml(r.severity)} · On track`;
      return `<div class="risk-row"><span class="left">🎫 ${escapeHtml(r.ticket_id)}</span><span class="pill ${pillClass}">${pillText}</span></div>`;
    }).join("");
  }

  if (!data.clusters || data.clusters.length === 0) {
    clusterDiv.innerHTML = `<p class="muted-note">No recurring issues detected among visible open tickets.</p>`;
  } else {
    clusterDiv.innerHTML = data.clusters.map(c => `
      <div class="cluster-row">
        <span class="left">
          <strong>${escapeHtml(c.ki_id)}</strong>
          <span class="ticket-list">— ${c.ticket_ids.map(escapeHtml).join(", ")}</span>
        </span>
        ${c.is_multi_customer ? `<span class="pill multi">Multi-customer</span>` : `<span class="pill status">${c.account_ids.length} account</span>`}
      </div>
    `).join("");
  }
}

async function loadActions() {
  const div = document.getElementById("actions-list");
  div.innerHTML = "Loading…";

  const res = await fetch(`/api/actions?user_id=${encodeURIComponent(currentUserId())}`);
  const data = await res.json();

  if (!data.actions || data.actions.length === 0) {
    div.innerHTML = `<p class="muted-note">No actions prepared yet for accounts visible to this user.</p>`;
    return;
  }

  div.innerHTML = data.actions.map(a => `
    <div class="action-row" data-action-id="${escapeHtml(a.action_id)}">
      <span class="left">
        <strong>${escapeHtml(a.action_type)}</strong>
        <span class="ticket-list">— ${escapeHtml(a.account_id)}</span>
      </span>
      <span class="left">
        <span class="pill status">${escapeHtml(a.status)}</span>
        ${a.status === "PREPARED" ? `<button class="confirm-btn" data-action-id="${escapeHtml(a.action_id)}">Confirm</button>` : ""}
      </span>
    </div>
  `).join("");

  div.querySelectorAll(".confirm-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      const actionId = btn.dataset.actionId;
      btn.disabled = true;
      btn.textContent = "Confirming…";
      await fetch("/api/actions/confirm", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({action_id: actionId, user_id: currentUserId()}),
      });
      loadActions();
    });
  });
}
