"use strict";
const $ = id => document.getElementById(id);
const state = { token: "", view: "overview", overview: null, selected: null, review: null, loading: false };
const labels = {blocked:"Needs attention", ready_for_review:"Ready for review", roadmap:"Roadmap", preparation_only:"Input preparation only", verification_pending:"Verification pending"};
function element(tag, className, text) { const e = document.createElement(tag); if (className) e.className = className; if (text !== undefined) e.textContent = text; return e; }
function badge(status) { return element("span", `badge ${status}`, labels[status] || status); }
function repository(url) { try { return new URL(url).pathname.replace(/^\//, "").replace(/\.git$/, ""); } catch { return url; } }
function date(text) { const d = new Date(text); return Number.isNaN(d.valueOf()) ? "Date unavailable" : d.toLocaleString([], {month:"short", day:"numeric", hour:"2-digit", minute:"2-digit"}); }
function empty(title, body) { const box = element("div", "empty"); box.append(element("span", "empty-symbol", "⌁"), element("h3", "", title), element("p", "", body)); return box; }
function notice(message) { $("notice").textContent = message || ""; $("notice").hidden = !message; }
async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (state.token) headers.set("Authorization", `Bearer ${state.token}`);
  if (options.body) headers.set("Content-Type", "application/json");
  const response = await fetch(path, {...options, headers, cache:"no-store"});
  const payload = await response.json().catch(() => ({detail:"Unexpected server response"}));
  if (!response.ok) { const error = new Error(typeof payload.detail === "string" ? payload.detail : "The request could not be completed."); error.status = response.status; throw error; }
  return payload;
}
function showView(name) {
  state.view = name;
  document.querySelectorAll(".view").forEach(e => e.hidden = e.id !== `view-${name}`);
  document.querySelectorAll("[data-view]").forEach(e => e.classList.toggle("active", e.dataset.view === name));
  $("breadcrumb").textContent = {overview:"Overview", runs:"Runs & evidence", adapters:"Ecosystem adapters", configuration:"Configuration"}[name];
  if (name === "runs") renderRunPicker();
}
function showAccess() { $("access-dialog").showModal(); }
function runRow(run) {
  const row = element("div", "row"), main = element("div", "row-main"), actions = element("div", "row-actions");
  main.append(element("strong", "", repository(run.repo_url)), element("small", "", `${run.kind === "unpinned" ? "Argon migration" : run.kind.toUpperCase() + " comparison"} · Target ${run.target} · ${date(run.started_at)}`));
  const button = element("button", "quiet", "Review →"); button.addEventListener("click", () => selectRun(run.run_id));
  actions.append(badge(run.status), button); row.append(main, actions); return row;
}
function fact(label, text) { const box = element("div", "fact"); box.append(element("span", "", label), element("strong", "", text)); return box; }
function renderConfiguration() {
  const config = state.overview.configuration;
  $("credential-list").replaceChildren(...Object.entries(config.credentials).map(([key, present]) => {
    const row = element("div", "credential"); row.append(element("code", "", key), element("span", `badge ${present ? "ready_for_review" : "blocked"}`, present ? "Set" : "Not set")); return row;
  }));
  $("configuration-facts").replaceChildren(fact("TARGET VERSION", config.target_version), fact("BASELINE VERSION", config.baseline_version), fact("MAXIMUM REPAIR ITERATIONS", config.max_iterations), fact("FORK OWNER", config.fork_owner_configured ? "Configured" : "Not configured"), fact("WRITE ACCESS", config.write_access === "read_only" ? "Read-only server" : "Dashboard token required"));
}
function renderOverview() {
  const data = state.overview;
  $("version").textContent = `v${data.version}`;
  for (const [id, key] of [["count-runs","runs"],["count-ready","ready_for_review"],["count-blocked","blocked"],["count-verified","verified_artifacts"]]) $(id).textContent = data.counts[key];
  $("recent-runs").replaceChildren(...(data.runs.length ? data.runs.slice(0,5).map(runRow) : [empty("No migration runs recorded", "Start from the terminal. Saved application runs appear here; local fixture proofs do not count as migrations.")]));
  $("connection").textContent = data.configuration.write_access === "read_only" ? "Read-only workspace" : state.token ? "Browser token saved" : "Write token required";
  renderRunPicker(); renderConfiguration();
}
function renderRunPicker() {
  if (!state.overview) return;
  const query = $("run-search").value.toLowerCase();
  const runs = state.overview.runs.filter(r => `${r.repo_url} ${r.run_id}`.toLowerCase().includes(query));
  $("run-list").replaceChildren(...(runs.length ? runs.map(run => { const button = element("button", `run-choice ${state.selected === run.run_id ? "selected" : ""}`); button.append(element("strong", "", repository(run.repo_url)), element("small", "", run.run_id), element("small", "", labels[run.status])); button.addEventListener("click", () => selectRun(run.run_id)); return button; }) : [empty("No matching runs", "Recorded runs will appear here.")]));
}
async function selectRun(id) {
  state.selected = id; state.review = null; $("approve").disabled = true; $("download-diff").disabled = true;
  $("approval-output").hidden = true; $("run-detail").hidden = true; $("run-empty").hidden = false;
  showView("runs");
  try { await loadRun(id); notice(""); } catch(e) { notice(e.message); }
}
async function loadRun(id) {
  $("approve").disabled = true;
  const encoded = encodeURIComponent(id);
  const [run, review] = await Promise.all([api(`/api/runs/${encoded}`), api(`/api/runs/${encoded}/review`)]);
  if (state.selected !== id) return;
  state.review = review;
  $("run-empty").hidden = true; $("run-detail").hidden = false;
  $("detail-repo").textContent = repository(run.repo_url); $("detail-id").textContent = run.run_id;
  $("detail-state").className = `badge ${review.ready_for_review ? "ready_for_review" : "blocked"}`;
  $("detail-state").textContent = review.ready_for_review ? "Ready for review" : "Needs attention";
  const final = (run.iterations || []).at(-1)?.report;
  const trusted = final?.artifacts_verified === true && final?.evidence_source === "sandbox_artifacts";
  $("evidence-facts").replaceChildren(fact("TARGET", run.target_django), fact("SOURCE COMMIT", run.source_commit || "Not recorded"), fact("EVIDENCE", trusted ? "Verified sandbox artifacts" : final?.evidence_source === "local_fixture" ? "Local fixture only" : "Unverified / incomplete"), fact("APPLICATION TESTS", trusted ? `${final.suite.passed} / ${Object.values(final.suite).reduce((a,b) => a+b,0)} passed` : "Awaiting trusted results"), fact("PATCH SHA-256", review.patch_sha256 || "Not available"), fact("PUBLICATION", review.publication_available ? "Available after approval" : "Not available"));
  $("blocker-list").replaceChildren(...(review.blockers.length ? review.blockers.map(b => element("li", "", b)) : [element("li", "", "Evidence gates passed for this reviewed patch.")]));
  $("iteration-list").replaceChildren(...((run.iterations || []).length ? run.iterations.map(i => element("div", "iteration", `Attempt ${i.n} · ${i.report.evidence_source.replaceAll("_"," ")} · ${i.report.artifacts_verified && i.report.evidence_source === "sandbox_artifacts" ? "artifacts verified" : "not independently verified"}`)) : [element("p", "muted", "No verification attempts recorded.")]));
  $("patch").textContent = review.diff || "No reviewable patch available.";
  $("download-diff").disabled = !review.diff;
  $("approval-note").textContent = !review.publication_available ? "PR publication is unavailable. Review and verification do not publish changes." : !state.token ? "Set this browser's dashboard token before approving." : "Approval is bound to the full SHA-256 shown above. The server rechecks the evidence and patch when you approve.";
  $("approve").disabled = !review.ready_for_review || !review.publication_available || !state.token || Boolean(run.pr_url);
}
async function loadAdapters() {
  const adapters = await api("/api/adapters");
  $("adapter-list").replaceChildren(...adapters.map(a => { const card = element("article", "panel adapter-card"); card.append(element("span", "adapter-icon", a.language === "Python" ? "⌘" : "＋"), element("h2", "", a.framework), badge(a.status), element("p", "", a.description), element("small", "muted", `${a.language} · ${a.name}`)); return card; }));
}
async function refresh() {
  if (state.loading) return;
  state.loading = true;
  try { state.overview = await api("/api/overview"); renderOverview(); notice(""); if (state.view === "runs" && state.selected) await loadRun(state.selected); }
  catch(e) { state.review = null; $("approve").disabled = true; $("connection").textContent = "Connection unavailable"; notice(e.message); }
  finally { state.loading = false; }
}
document.querySelectorAll("[data-view]").forEach(button => button.addEventListener("click", () => { showView(button.dataset.view); if (button.dataset.view === "adapters") loadAdapters().catch(e => notice(e.message)); }));
document.querySelectorAll("[data-close]").forEach(button => button.addEventListener("click", () => $(button.dataset.close).close()));
$("access-button").addEventListener("click", showAccess); $("configuration-access").addEventListener("click", showAccess);
$("new-run-button").addEventListener("click", () => { const target = state.overview?.configuration.target_version || "5.2.18"; $("cli-command").textContent = `uv run jatayu run https://github.com/OWNER/REPO --adapter django --target ${target} --live`; $("new-dialog").showModal(); });
$("all-runs-button").addEventListener("click", () => showView("runs")); $("refresh-button").addEventListener("click", refresh); $("run-search").addEventListener("input", renderRunPicker);
$("access-form").addEventListener("submit", event => { event.preventDefault(); state.token = $("access-token").value; $("access-token").value = ""; $("access-dialog").close(); refresh(); });
$("forget-token").addEventListener("click", () => { state.token = ""; $("access-token").value = ""; $("access-dialog").close(); $("approve").disabled = true; refresh(); });
$("download-diff").addEventListener("click", () => { if (!state.review?.diff) return; const url = URL.createObjectURL(new Blob([state.review.diff], {type:"text/plain"})); const link = element("a"); link.href = url; link.download = `jatayu-${state.selected}.patch`; link.click(); setTimeout(() => URL.revokeObjectURL(url),1000); });
$("approve").addEventListener("click", async () => {
  if (!state.review?.ready_for_review || !state.review?.publication_available || !state.token) return;
  const id = state.selected, digest = state.review.patch_sha256;
  if (!confirm(`Approve and publish exactly patch ${digest}?`)) return;
  $("approve").disabled = true; $("approval-output").hidden = false;
  try { const result = await api(`/api/runs/${encodeURIComponent(id)}/approve`, {method:"POST", body:JSON.stringify({patch_sha256:digest})}); $("approval-output").textContent = JSON.stringify(result,null,2); }
  catch(e) { $("approval-output").textContent = e.message; }
});
refresh(); setInterval(refresh,10000);
