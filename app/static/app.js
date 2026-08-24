function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = String(value);
  return div.innerHTML;
}

// Source data (documents.py) labels sections as "§1 ..." -- fine as an
// internal citation key, but not something a non-technical reader should
// see. Same normalization as the backend's _clean_answer_text.
function cleanText(value) {
  return String(value || "").replace(/§/g, "Section ");
}

function currentUserId() {
  return document.getElementById("user-select").value;
}

// Renders answer text (plain prose + occasional "- " bulleted lines, possibly
// indented into sub-points, per the agent's prompt) as real paragraphs and
// (nested) <ul> markup instead of one unbroken blob or a flattened list.
// Escapes first so nothing in the model's output is ever parsed as HTML.
function renderAnswerHtml(rawText) {
  const rawLines = escapeHtml(rawText || "").split("\n");
  let html = "";
  let paragraph = [];
  let listStack = []; // [{indent, items: [{text, nested}, ...]}], outermost first

  const flushParagraph = () => {
    if (paragraph.length) {
      html += `<p>${paragraph.join(" ")}</p>`;
      paragraph = [];
    }
  };
  const closeListLevel = () => {
    const level = listStack.pop();
    const rendered = `<ul>${level.items.map(i => `<li>${i.text}${i.nested}</li>`).join("")}</ul>`;
    if (listStack.length) {
      // Nest inside the parent level's most recent <li>, before it's closed.
      const parent = listStack[listStack.length - 1];
      parent.items[parent.items.length - 1].nested += rendered;
    } else {
      html += rendered;
    }
  };
  const closeAllLists = () => {
    while (listStack.length) closeListLevel();
  };

  for (const rawLine of rawLines) {
    const trimmed = rawLine.trim();
    if (trimmed === "") {
      flushParagraph();
      closeAllLists();
      continue;
    }
    const bullet = trimmed.match(/^-\s+(.*)/);
    if (bullet) {
      flushParagraph();
      const indent = rawLine.match(/^\s*/)[0].length;
      while (listStack.length && indent < listStack[listStack.length - 1].indent) {
        closeListLevel();
      }
      if (!listStack.length || indent > listStack[listStack.length - 1].indent) {
        listStack.push({ indent, items: [] });
      }
      listStack[listStack.length - 1].items.push({ text: bullet[1], nested: "" });
    } else {
      closeAllLists();
      paragraph.push(trimmed);
    }
  }
  flushParagraph();
  closeAllLists();
  return html || "<p></p>";
}

const USER_INITIALS = { priya_mehta: "PM", arjun_rao: "AR", neha_kapoor: "NK", manager: "MG" };

let conversationId = null;
let lastPendingAction = null;
let lastContext = null; // {account_id, account_name, order_id, ticket_id}

document.getElementById("user-select").addEventListener("change", () => {
  document.querySelector(".user-avatar").textContent = USER_INITIALS[currentUserId()] || "?";
  // Conversations are scoped per user_id server-side, so switching the
  // logged-in user starts a fresh one rather than showing a stale context.
  conversationId = null;
  lastPendingAction = null;
  lastContext = null;
  document.getElementById("chat-log").innerHTML = "";
  document.getElementById("empty-state").classList.remove("hidden");
  resetContextPanel();
  loadRecentConversations();
});

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

document.getElementById("ask-button").innerHTML = `${icon("send")}<span>Ask</span>`;
document.getElementById("new-conversation-button").innerHTML = `${icon("plus")}<span>New conversation</span>`;

document.getElementById("ask-button").addEventListener("click", askQuestion);
document.getElementById("query-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") askQuestion();
});

document.getElementById("new-conversation-button").addEventListener("click", () => {
  conversationId = null;
  lastPendingAction = null;
  lastContext = null;
  document.getElementById("chat-log").innerHTML = "";
  document.getElementById("empty-state").classList.remove("hidden");
  resetContextPanel();
  highlightActiveConversation();
});

// ---- Recent conversations (left rail): session-scoped only. Backed by the
// same in-memory, per-(user_id, conversation_id) store the agent writes to,
// so this list -- like the conversations themselves -- is lost on process
// restart. There is no persistent database behind it.

function relativeTime(unixSeconds) {
  const diffMin = Math.round((Date.now() / 1000 - unixSeconds) / 60);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  return `${Math.round(diffHr / 24)}d ago`;
}

function highlightActiveConversation() {
  document.querySelectorAll(".recent-conversation-item").forEach(el => {
    el.classList.toggle("active", el.dataset.conversationId === conversationId);
  });
}

async function loadRecentConversations() {
  const container = document.getElementById("recent-conversations");
  const res = await fetch(`/api/conversations?user_id=${encodeURIComponent(currentUserId())}`);
  const data = await res.json();
  const conversations = data.conversations || [];

  if (conversations.length === 0) {
    container.innerHTML = `<p class="muted-note rail-empty-note">No conversations yet this session.</p>`;
    return;
  }

  container.innerHTML = conversations.map(c => {
    const meta = c.active_ticket_id || c.active_order_id || c.active_account_id || "General";
    return `
      <button class="recent-conversation-item" data-conversation-id="${escapeHtml(c.conversation_id)}">
        <span class="rc-title">${escapeHtml(c.title)}</span>
        <span class="rc-meta">${escapeHtml(meta)} · ${relativeTime(c.updated_at)}</span>
      </button>
    `;
  }).join("");

  container.querySelectorAll(".recent-conversation-item").forEach(btn => {
    btn.addEventListener("click", () => resumeConversation(btn.dataset.conversationId));
  });
  highlightActiveConversation();
}

async function resumeConversation(id) {
  const res = await fetch(`/api/conversations/${encodeURIComponent(id)}?user_id=${encodeURIComponent(currentUserId())}`);
  const data = await res.json();
  if (!data.found) return;

  conversationId = id;
  lastPendingAction = null;
  lastContext = null;
  resetContextPanel();
  highlightActiveConversation();

  const chatLog = document.getElementById("chat-log");
  document.getElementById("empty-state").classList.add("hidden");
  chatLog.innerHTML = data.turns.map(t => {
    if (t.role === "user") {
      return `<div class="chat-turn"><div class="chat-bubble user">${escapeHtml(t.text)}</div></div>`;
    }
    return `
      <div class="chat-turn">
        <div class="chat-bubble assistant">
          <div class="answer-card">
            <div class="answer-text">${renderAnswerHtml(t.text)}</div>
          </div>
        </div>
      </div>
    `;
  }).join("");
  chatLog.scrollTop = chatLog.scrollHeight;
}

function renderTimelineSteps(container, labels, { pulseLast = false } = {}) {
  container.innerHTML = labels.map((label, i) => {
    const isLast = i === labels.length - 1;
    const cls = isLast && pulseLast ? "step step-active" : "step step-done";
    const marker = isLast && pulseLast ? "" : icon("check-circle");
    return `<div class="${cls}">${marker}<span>${escapeHtml(label)}</span></div>`;
  }).join("");
}

function badgeClassFor(status) {
  const s = (status || "").toLowerCase();
  if (s === "ready") return "ready";
  if (s === "awaiting_confirmation") return "awaiting";
  return "needs_review";
}

// ---- Right-side context panel: reflects the *current* investigation state
// (latest turn), not a per-message duplicate -- avoids cluttering the chat
// log with repeated timeline/decision/evidence blocks per turn.

function resetContextPanel() {
  document.getElementById("ctx-empty").classList.remove("hidden");
  ["ctx-summary-section", "ctx-decision-section", "ctx-evidence-section", "ctx-next-steps-section"].forEach(id => {
    document.getElementById(id).classList.add("hidden");
  });
}

function renderContextTimeline(labels, { pulseLast = false } = {}) {
  document.getElementById("ctx-empty").classList.add("hidden");
  const section = document.getElementById("ctx-summary-section");
  section.classList.remove("hidden");
  renderTimelineSteps(document.getElementById("ctx-timeline"), labels, { pulseLast });
}

function formatAmount(prefix, value) {
  if (value === null || value === undefined) return null;
  return `${prefix}₹${value}`;
}

function renderDecisionCard(decision) {
  const section = document.getElementById("ctx-decision-section");
  const el = document.getElementById("ctx-decision");
  if (!decision) {
    section.classList.add("hidden");
    el.innerHTML = "";
    return;
  }
  section.classList.remove("hidden");

  let amount = null;
  let headline = "";
  if (decision.kind === "CancellationDecision") {
    headline = decision.allowed ? "Cancellation allowed" : "Cancellation not allowed";
    amount = formatAmount("Fee ", decision.fee_inr);
  } else if (decision.kind === "CreditDecision") {
    headline = decision.eligible ? "Credit eligible" : "Not eligible for a credit";
    amount = formatAmount("", decision.amount_inr);
  } else if (decision.kind === "SLADecision") {
    headline = `Severity ${decision.severity}${decision.at_risk ? " · at risk" : ""}`;
    amount = `${decision.elapsed_minutes}m / ${decision.target_minutes}m target`;
  } else {
    headline = decision.kind || "Decision";
  }

  const prov = decision.provenance;
  const provRow = prov
    ? `<div class="provenance-row">${icon("scale")}<span>${escapeHtml(prov.source_document)} · ${escapeHtml(cleanText(prov.source_section))}</span></div>`
    : "";
  const managerNote = decision.requires_manager_approval
    ? `<div class="provenance-row">${icon("alert-triangle")}<span>Requires manager approval</span></div>`
    : "";

  el.innerHTML = `
    <div class="decision-headline">
      <strong>${escapeHtml(headline)}</strong>
      ${amount ? `<span class="decision-amount">${escapeHtml(amount)}</span>` : ""}
    </div>
    ${decision.reason ? `<p class="decision-reason">${escapeHtml(decision.reason)}</p>` : ""}
    ${provRow}
    ${managerNote}
  `;
}

function renderEvidence(citations) {
  const section = document.getElementById("ctx-evidence-section");
  const el = document.getElementById("ctx-evidence");
  if (!citations || citations.length === 0) {
    section.classList.add("hidden");
    el.innerHTML = "";
    return;
  }
  section.classList.remove("hidden");
  el.innerHTML = citations.map(c => `
    <div class="evidence-item">
      <div class="evidence-source">${icon("file-text")}<span>${escapeHtml(c.document_name)} · ${escapeHtml(cleanText(c.section))}</span></div>
      <p class="evidence-text">${escapeHtml(cleanText(c.text))}</p>
    </div>
  `).join("");
}

function renderNextSteps(finalData) {
  const section = document.getElementById("ctx-next-steps-section");
  const el = document.getElementById("ctx-next-steps");
  const chips = [];

  if (finalData.pending_action) {
    chips.push({ id: "confirm", label: "Confirm escalation", iconName: "check-circle", action: () => confirmPendingAction(finalData.pending_action.action_id) });
  } else if (lastContext && (lastContext.ticket_id || lastContext.order_id || lastContext.account_id)) {
    chips.push({ id: "escalate", label: "Escalate this", iconName: "megaphone", action: () => {
      document.getElementById("query-input").value = "Can you escalate this?";
      askQuestion();
    }});
  }

  if (chips.length === 0) {
    section.classList.add("hidden");
    el.innerHTML = "";
    return;
  }
  section.classList.remove("hidden");
  el.innerHTML = chips.map(c => `<button class="next-step-chip" data-chip-id="${c.id}">${icon(c.iconName)}<span>${escapeHtml(c.label)}</span></button>`).join("");
  chips.forEach(c => {
    el.querySelector(`[data-chip-id="${c.id}"]`).addEventListener("click", (e) => {
      e.currentTarget.disabled = true;
      c.action();
    });
  });
}

async function confirmPendingAction(actionId) {
  const confirmRes = await fetch("/api/actions/confirm", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({action_id: actionId, user_id: currentUserId()}),
  });
  const confirmData = await confirmRes.json();
  lastPendingAction = null;
  const el = document.getElementById("ctx-next-steps");
  el.innerHTML = `<span class="pill status">${escapeHtml(confirmData.status)}</span>`;
}

async function askQuestion() {
  const query = document.getElementById("query-input").value.trim();
  if (!query) return;

  const askButton = document.getElementById("ask-button");
  const emptyState = document.getElementById("empty-state");
  const chatLog = document.getElementById("chat-log");

  emptyState.classList.add("hidden");
  document.getElementById("query-input").value = "";

  const turn = document.createElement("div");
  turn.className = "chat-turn";
  turn.innerHTML = `
    <div class="chat-bubble user">${escapeHtml(query)}</div>
    <div class="chat-bubble assistant">
      <div class="thinking-indicator">
        <div class="step step-active">${icon("search")}<span class="thinking-label">Understanding your question&hellip;</span></div>
      </div>
      <div class="answer-card hidden">
        <div class="answer-header"><span class="badge"></span></div>
        <div class="answer-text"></div>
      </div>
    </div>
  `;
  chatLog.appendChild(turn);
  chatLog.scrollTop = chatLog.scrollHeight;

  const thinkingIndicator = turn.querySelector(".thinking-indicator");
  const thinkingLabel = turn.querySelector(".thinking-label");
  const answerCard = turn.querySelector(".answer-card");
  const answerEl = turn.querySelector(".answer-text");
  const badge = turn.querySelector(".badge");

  // Swaps the inline "thinking" trail for the real answer/error content --
  // called from every exit path below (success, stream error, network
  // failure) so the bubble never gets stuck showing a stale in-progress step.
  const stopThinking = () => thinkingIndicator.classList.add("hidden");

  askButton.disabled = true;
  askButton.innerHTML = `${icon("search")}<span>Thinking…</span>`;
  const stepLabels = [];
  renderContextTimeline(["Understanding your question…"], { pulseLast: true });

  try {
    const res = await fetch("/api/investigate/stream", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({query, user_id: currentUserId(), conversation_id: conversationId}),
    });

    if (!res.ok || !res.body) {
      stopThinking();
      answerCard.classList.remove("hidden");
      badge.textContent = "Error"; badge.className = "badge error";
      answerEl.textContent = "Something went wrong contacting the server.";
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let finalData = null;

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let boundary;
      while ((boundary = buffer.indexOf("\n\n")) >= 0) {
        const rawEvent = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);

        let eventType = "message";
        let dataStr = "";
        for (const line of rawEvent.split("\n")) {
          if (line.startsWith("event: ")) eventType = line.slice(7);
          else if (line.startsWith("data: ")) dataStr += line.slice(6);
        }
        if (!dataStr) continue;
        const data = JSON.parse(dataStr);

        if (eventType === "step") {
          stepLabels.push(data.label);
          thinkingLabel.textContent = data.label;
          renderContextTimeline(stepLabels, { pulseLast: true });
        } else if (eventType === "done") {
          finalData = data;
        }
      }
      chatLog.scrollTop = chatLog.scrollHeight;
    }

    if (!finalData) {
      stopThinking();
      answerCard.classList.remove("hidden");
      badge.textContent = "Error"; badge.className = "badge error";
      answerEl.textContent = "The response stream ended unexpectedly.";
      renderContextTimeline(stepLabels, { pulseLast: false });
      return;
    }

    stopThinking();

    if (finalData.conversation_id) conversationId = finalData.conversation_id;

    document.getElementById("ctx-empty").classList.add("hidden");
    document.getElementById("ctx-summary-section").classList.remove("hidden");
    const timelineEl = document.getElementById("ctx-timeline");
    if (!finalData.tool_call_log || finalData.tool_call_log.length === 0) {
      timelineEl.innerHTML = `<div class="step step-done">${icon("message-circle")}<span>Answered from reasoning alone. No data lookup needed.</span></div>`;
    } else {
      timelineEl.innerHTML = finalData.tool_call_log.map(t => {
        const iconName = TOOL_ICON[t.tool] || "search";
        return `<div class="step step-done">${icon(iconName)}<span>${escapeHtml(t.tool)}(${escapeHtml(t.args)})</span></div>`;
      }).join("");
    }

    renderDecisionCard(finalData.policy_decision);
    renderEvidence(finalData.citations);
    lastPendingAction = finalData.pending_action || null;
    lastContext = finalData.context || null;
    renderNextSteps(finalData);

    answerCard.classList.remove("hidden");
    badge.textContent = finalData.decision_status || "N/A";
    badge.className = `badge ${badgeClassFor(finalData.decision_status)}`;
    answerEl.innerHTML = finalData.answer_text ? renderAnswerHtml(finalData.answer_text) : "<p>(no answer text returned)</p>";
  } catch (err) {
    stopThinking();
    answerCard.classList.remove("hidden");
    badge.textContent = "Error"; badge.className = "badge error";
    answerEl.textContent = "Could not reach the server. Is it running?";
  } finally {
    askButton.disabled = false;
    askButton.innerHTML = `${icon("send")}<span>Ask</span>`;
    chatLog.scrollTop = chatLog.scrollHeight;
    loadRecentConversations();
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
        return `<div class="risk-row"><span class="left">${icon("ticket")} ${escapeHtml(r.ticket_id)}</span><span class="pill review">Needs review</span></div>`;
      }
      const pillClass = r.at_risk ? "at-risk" : "ok";
      const pillText = r.at_risk ? `${escapeHtml(r.severity)} · At risk` : `${escapeHtml(r.severity)} · On track`;
      return `<div class="risk-row"><span class="left">${icon("ticket")} ${escapeHtml(r.ticket_id)}</span><span class="pill ${pillClass}">${pillText}</span></div>`;
    }).join("");
  }

  if (!data.clusters || data.clusters.length === 0) {
    clusterDiv.innerHTML = `<p class="muted-note">No recurring issues detected among visible open tickets.</p>`;
  } else {
    clusterDiv.innerHTML = data.clusters.map(c => `
      <div class="cluster-row">
        <span class="left">
          <strong>${escapeHtml(c.ki_id)}</strong>
          <span class="ticket-list">${c.ticket_ids.map(escapeHtml).join(", ")}</span>
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
        <span class="ticket-list">${escapeHtml(a.account_id)}</span>
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

document.querySelector(".user-avatar").textContent = USER_INITIALS[currentUserId()] || "?";
loadRecentConversations();
