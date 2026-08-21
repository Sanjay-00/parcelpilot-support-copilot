document.querySelectorAll("nav button").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("nav button, .tab").forEach(el => el.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(btn.dataset.tab).classList.add("active");
  });
});

document.getElementById("ask-button").addEventListener("click", async () => {
  const query = document.getElementById("query-input").value;
  const userId = document.getElementById("user-select").value;
  const res = await fetch("/api/investigate", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({query, user_id: userId}),
  });
  const data = await res.json();
  document.getElementById("tool-timeline").innerHTML =
    data.tool_call_log.map(t => `<div>&#128269; ${t.tool}(${t.args})</div>`).join("");
  document.getElementById("answer").innerText =
    `[${data.decision_status}] ${data.answer_text}`;
});
