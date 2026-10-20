"use strict";
const BOOT = window.SHOUHU || {};
const $ = (id) => document.getElementById(id);
{ const t = new URLSearchParams(location.search).get("theme"); if (t === "light" || t === "dark") document.documentElement.dataset.theme = t; }
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const money = (s) => { const [amt, sym] = String(s ?? "").split(" "); return amt && !isNaN(amt) ? `${Number(amt).toLocaleString("en-US", { maximumFractionDigits: 2 })} ${sym || ""}`.trim() : String(s ?? ""); };   // "1200 tUSDC" -> "1,200 tUSDC"
const short = (h, a = 6, b = 4) => (h && h.length > a + b + 2 ? `${h.slice(0, a)}…${h.slice(-b)}` : h || "");
const proofUrl = (h) => `/proof?tx=${encodeURIComponent(h)}${document.documentElement.dataset.theme ? `&theme=${document.documentElement.dataset.theme}` : ""}`;   // keep a forced theme
let S = null;
let open = null;          // request id whose confirmation panel is open
let working = false;
let seen = null;
let revoking = false;     // the revoke confirmation is open
const ACT = { approval: "approval", contact: "contact", allowlist: "allowlist", pause: "pause", policy: "limits", deposit: "money in" };

async function api(path, body) {
  const opt = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json", "X-Shouhu-Token": BOOT.token }, body: JSON.stringify(body),
  };
  const r = await fetch(path, opt);
  if (r.status === 401) window.ShouhuAuth.expired();
  return r.json().catch(() => ({ error: `HTTP ${r.status}` }));
}

function toast(text, ms = 3600) {
  const t = $("toast");
  t.innerHTML = text;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.hidden = true), ms);
}

const when = (ts) => new Date(ts * 1000).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

function reqCard(r, pending) {
  const confirm = open === r.id ? `
    <div class="confirm">
      <p><b>You are approving exactly this payment, once:</b> ${esc(r.amount_text)} to ${esc(r.name || "an address that is not a contact")}
        <span class="addr">${esc(r.to)}</span>, intent <span class="addr">${esc(short(r.intent_id, 10, 6))}</span>.
        The agent can execute it one time and cannot change the amount or the recipient.</p>
      <p>Type <b>yes</b> to sign with the owner key.</p>
      <div class="actions"><input id="yes" autocomplete="off" placeholder="yes"><button class="btn primary" data-sign="${esc(r.id)}">Sign approval</button>
        <button class="btn" data-cancel="1">Cancel</button></div>
    </div>` : "";
  const tx = (label, h, url) => h && `<a href="${proofUrl(h)}" target="_blank" rel="noopener">${label} proof →</a>${url ? ` <a class="small" href="${url}" target="_blank" rel="noopener">etherscan ↗</a>` : ""}`;
  const links = [tx("approval", r.approve_tx, r.approve_explorer), tx("payment", r.exec_tx, r.exec_explorer)].filter(Boolean).join(" · ");
  return `<div class="req ${pending ? "pending" : ""}">
    <div class="head"><span class="amt">${esc(r.amount_text)}</span><span>→ <b>${esc(r.name || "not a contact")}</b></span>
      <span style="flex:1"></span><span class="st ${esc(r.status)}">${esc(r.status)}</span><b>${esc(r.id)}</b></div>
    <dl>
      <dt>Recipient</dt><dd class="addr">${esc(r.to)}</dd>
      <dt>Why it needs you</dt><dd>${esc((r.reasons || []).join("; "))}</dd>
      ${r.memo ? `<dt>Memo</dt><dd>${esc(r.memo)}</dd>` : ""}
      <dt>Intent id</dt><dd class="addr">${esc(r.intent_id)}</dd>
      <dt>Filed</dt><dd>${when(r.created)}</dd>
      ${links ? `<dt>On-chain</dt><dd>${links}</dd>` : ""}
    </dl>
    ${pending && !BOOT.read_only ? `<div class="actions"><button class="btn primary" data-open="${esc(r.id)}" ${open === r.id ? "hidden" : ""}>Approve once…</button>
      <button class="btn danger" data-deny="${esc(r.id)}">Deny</button></div>` : ""}
    ${confirm}
  </div>`;
}

function render() {
  if (!S) return;
  $("chainName").textContent = S.chain === "anvil" ? "Local chain (Anvil)" : S.chain === "sepolia" ? "Ethereum Sepolia" : S.chain;
  $("balance").textContent = money(S.balance);
  $("perCap").textContent = money(S.per_transfer_cap);
  $("rollCap").textContent = money(S.rolling_cap);
  $("spent").textContent = money(S.spent_24h);
  $("headroom").textContent = money(S.headroom);
  if (S.wallet_explorer) $("walletLink").href = S.wallet_explorer; else $("walletLink").hidden = true;
  $("paused").textContent = S.paused ? "paused" : "active";
  $("paused").className = `status ${S.paused ? "bad" : "ok"}`;
  $("pauseBtn").textContent = S.paused ? "Resume the agent" : "Pause the agent";
  for (const id of ["pauseBtn", "limitsBtn", "fundBtn"]) $(id).disabled = BOOT.read_only || working;
  $("allow").innerHTML = S.contacts.map((c) => `<div class="item"><div class="grow"><div><b>${esc(c.name)}</b> ${c.alias ? `<span class="small">${esc(c.alias)}</span>` : ""}</div><div class="addr small" title="${esc(c.address)}">${esc(short(c.address))}</div></div>
    ${c.allowlisted ? `<span class="ok-mark">✓ allowed</span>` : `<span class="no-mark">not allowed</span>`}
    ${BOOT.read_only ? "" : `<button class="btn xs" data-allow="${esc(c.address)}" data-to="${c.allowlisted ? "0" : "1"}">${c.allowlisted ? "Remove" : "Allow"}</button>`}</div>`).join("");
  const a = S.account, st = S.student;
  const stmtOpen = $("family").querySelector("details")?.open;
  const typing = $("family").contains(document.activeElement) && document.activeElement.tagName === "INPUT";
  const invite = a && a.invite;
  const theme = document.documentElement.dataset.theme;       // a forced theme carries over to the student's page
  const link = invite ? `${BOOT.student_url}?invite=${encodeURIComponent(invite)}${theme ? `&theme=${theme}` : ""}` : "";
  const studentRow = st ? `
    <div class="item"><div class="avatar">${esc((st.chinese_name || st.name)[0])}</div><div class="grow">
      <div><b>${esc(st.name)}</b> ${st.chinese_name ? `<span class="small">${esc(st.chinese_name)}</span>` : ""} <span class="small">student</span></div>
      <div class="small">registered ${when(st.created)} with your one-time code · holds no key</div>
      ${revoking ? `<div class="confirm small-confirm"><p>Type <b>${esc(st.name)}</b> to remove this account. Their sign-in stops at once; you get a new invite code.</p>
        <div class="actions"><input id="revokeName" autocomplete="off" placeholder="${esc(st.name)}"><button class="btn danger" data-revoke="1" type="button">Remove access</button>
        <button class="btn" data-revoke-cancel="1" type="button">Cancel</button></div></div>`
        : `<div><button class="linkish danger-text" data-revoke-open="1" type="button">Revoke access</button></div>`}</div></div>`
    : `<div class="invite-box">
        <div class="invite-title">Invite your student · 邀请学生</div>
        <div class="invite-code mono">${esc(invite || "—")}</div>
        <div class="small">One-time code. Your student enters it on the sign-up page, or opens the link.</div>
        <div class="actions"><button class="btn xs" data-copy-invite="${esc(link)}" type="button" ${invite ? "" : "disabled"}>Copy invite link</button>
          ${invite ? `<a class="btn xs" href="${esc(link)}" target="_blank" rel="noopener">Open student sign-up ↗</a>` : ""}
          <button class="btn xs" data-new-invite="1" type="button" ${BOOT.read_only ? "disabled" : ""}>New code</button></div>
      </div>`;
  if (!typing) $("family").innerHTML = `
    <div class="item"><div class="avatar" style="background:var(--ink);color:var(--card)">家</div><div class="grow"><div><b>${esc(a ? a.name : "—")}</b> <span class="small">parent · owner</span></div>
      <div class="small">${a ? `owner key verified by signature <span class="addr" title="${esc(a.signature)}">${esc(short(a.signature, 10, 6))}</span>` : ""}</div>
      ${a && a.policy_tx ? `<div class="small"><a href="${proofUrl(a.policy_tx)}" target="_blank" rel="noopener">limits set at registration: proof →</a></div>` : ""}
      ${a ? `<details class="stmt" ${stmtOpen ? "open" : ""}><summary>signed statement</summary><pre>${esc(a.statement)}</pre></details>` : ""}</div></div>
    ${studentRow}`;
  const act = S.activity || [];
  $("activity").innerHTML = act.length ? act.map((x) => `<div class="item"><span class="kind-badge k-${esc(x.kind)}">${esc(ACT[x.kind] || x.kind)}</span><div class="grow"><div>${esc(x.text)}</div>
      <div class="small">${when(x.ts)} · <span class="addr">${esc(short(x.tx, 10, 6))}</span></div></div>
      <a class="proof-link" href="${proofUrl(x.tx)}" target="_blank" rel="noopener">proof →</a></div>`).join("")
    : `<div class="empty">No owner transactions yet. Registering a contact, approving a request, changing the limits, adding money or pausing shows up here.</div>`;
  const pend = S.requests.filter((r) => r.status === "pending");
  const done = S.requests.filter((r) => r.status !== "pending");
  // keep the confirmation panel stable while the owner types
  if (!(open && document.activeElement && document.activeElement.id === "yes")) {
    $("pending").innerHTML = pend.length ? pend.map((r) => reqCard(r, true)).join("")
      : `<div class="empty">No pending requests. When Shouhu files one, it appears here within a few seconds.</div>`;
  }
  $("settled").innerHTML = done.length ? done.map((r) => reqCard(r, false)).join("") : `<div class="empty">Nothing settled yet.</div>`;
  $("footnote").innerHTML = `Owner <span class="addr">${short(S.owner)}</span> · gas ${S.owner_gas_eth} ETH${S.owner_key_loaded && !S.owner_matches ? " · <b style='color:var(--cinnabar)'>the loaded key is not this wallet's owner</b>" : ""}<br>
    Agent <span class="addr">${short(S.agent)}</span> · gas ${S.agent_gas_eth} ETH`;
  const ids = pend.map((r) => r.id).join(",");
  if (seen !== null && ids && ids !== seen) {
    const fresh = pend.find((r) => !seen.split(",").includes(r.id));
    if (fresh) { toast(`New request ${esc(fresh.id)}: ${esc(fresh.amount_text)} to ${esc(fresh.name || short(fresh.to))}`); document.title = "● Shouhu Owner Console"; }
  }
  seen = ids;
}

async function load() {
  const s = await api("/api/state").catch(() => null);
  if (!s || s.error) { $("dot").className = "dot off"; $("chainName").textContent = "chain unreachable, retrying"; return; }
  $("dot").className = "dot";
  S = s;
  render();
}

document.addEventListener("click", async (e) => {
  const t = e.target.closest("button");
  if (!t || working) return;
  if (t.dataset.open) { open = t.dataset.open; render(); $("yes")?.focus(); return; }
  if (t.dataset.cancel) { open = null; render(); return; }
  if (t.dataset.deny) {
    working = true;
    const r = await api("/api/deny", { id: t.dataset.deny });
    working = false;
    toast(r.error ? esc(r.error) : `${esc(t.dataset.deny)} denied. Nothing was sent.`);
    return load();
  }
  if (t.dataset.sign) {
    const r0 = S.requests.find((x) => x.id === t.dataset.sign);
    if (($("yes").value || "").trim().toLowerCase() !== "yes") { toast("Type yes to approve."); return; }
    working = true;
    t.disabled = true;
    t.textContent = "Signing and waiting for the block…";
    const r = await api("/api/approve", { id: r0.id, confirm: "yes", intent_id: r0.intent_id, amount: r0.amount, to: r0.to });
    working = false;
    open = null;
    if (r.error) toast(esc(r.error), 6000);
    else toast(`Approved ${esc(r.id)} on-chain; Shouhu can now complete it. <a style="color:inherit;text-decoration:underline" href="${proofUrl(r.tx)}" target="_blank" rel="noopener">proof →</a>`, 7000);
    document.activeElement?.blur();
    return load();
  }
  if (t.dataset.allow) {
    working = true;
    t.disabled = true;
    t.textContent = "Waiting…";
    const r = await api("/api/allowlist", { address: t.dataset.allow, allowed: t.dataset.to === "1" });
    working = false;
    toast(r.error ? esc(r.error) : `Allowlist updated on-chain. <a style="color:inherit;text-decoration:underline" href="${proofUrl(r.tx)}" target="_blank" rel="noopener">proof →</a>`, 6000);
    return load();
  }
  if (t.id === "limitsBtn") {
    const f = $("limitsForm");
    f.hidden = !f.hidden;
    $("fundForm").hidden = true;
    if (!f.hidden) { f.per_transfer_cap.value = S.per_transfer_cap.split(" ")[0]; f.rolling_cap.value = S.rolling_cap.split(" ")[0]; f.per_transfer_cap.focus(); }
    return;
  }
  if (t.id === "fundBtn") { $("fundForm").hidden = !$("fundForm").hidden; $("limitsForm").hidden = true; return; }
  if (t.dataset.close) { $(t.dataset.close).hidden = true; return; }
  if (t.dataset.copyInvite !== undefined && t.dataset.copyInvite) {
    try { await navigator.clipboard.writeText(t.dataset.copyInvite); toast("Invite link copied. Send it to your student."); }
    catch (_) { toast(`Invite link: ${esc(t.dataset.copyInvite)}`, 9000); }
    return;
  }
  if (t.dataset.newInvite) {
    const r = await api("/api/invite", {});
    toast(r.error ? esc(r.error) : `New invite code ${esc(r.invite)}. The old one no longer works.`);
    return load();
  }
  if (t.dataset.revokeOpen) { revoking = true; render(); $("revokeName")?.focus(); return; }
  if (t.dataset.revokeCancel) { revoking = false; render(); return; }
  if (t.dataset.revoke) {
    working = true;
    const r = await api("/api/student/revoke", { confirm: $("revokeName").value });
    working = false;
    if (r.error) { toast(esc(r.error)); return; }
    revoking = false;
    document.activeElement?.blur();
    toast(`Access removed. New invite code ${esc(r.invite)}.`, 6000);
    return load();
  }
  if (t.id === "pauseBtn") {
    working = true;
    t.textContent = "Waiting for the block…";
    const r = await api("/api/pause", { paused: !S.paused });
    working = false;
    toast(r.error ? esc(r.error) : (S.paused ? "Agent resumed." : "Agent paused. The contract now refuses every agent payment."));
    return load();
  }
});
document.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target.id === "yes") document.querySelector("[data-sign]")?.click(); });
window.addEventListener("focus", () => (document.title = "Shouhu Owner Console"));
$("contactForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (working) return;
  const f = e.target, data = Object.fromEntries(new FormData(f).entries());
  data.allowlist = f.allowlist.checked;
  working = true;
  const btn = $("contactBtn");
  btn.disabled = true;
  btn.textContent = data.allowlist ? "Saving and waiting for the block…" : "Saving…";
  const r = await api("/api/contacts", data);
  working = false;
  btn.disabled = BOOT.read_only;
  btn.textContent = "Register contact";
  if (r.error && !r.contact) { toast(esc(r.error), 6000); return; }
  f.reset();
  toast(r.tx ? `${esc(r.contact.name)} registered and allowlisted on-chain. <a style="color:inherit;text-decoration:underline" href="${proofUrl(r.tx)}" target="_blank" rel="noopener">proof →</a>`
             : r.error ? esc(r.error) : `${esc(r.contact.name)} registered (not allowlisted).`, 8000);
  load();
});
async function sendForm(form, path, btn, waitText, okText) {
  if (working) return;
  const data = Object.fromEntries(new FormData(form).entries());
  working = true;
  const label = btn.textContent;
  btn.disabled = true;
  btn.textContent = waitText;
  const r = await api(path, data);
  working = false;
  btn.disabled = false;
  btn.textContent = label;
  if (r.error) { toast(esc(r.error), 6000); return; }
  form.hidden = true;
  toast(`${okText} <a style="color:inherit;text-decoration:underline" href="${proofUrl(r.tx)}" target="_blank" rel="noopener">proof →</a>`, 8000);
  load();
}
$("limitsForm").addEventListener("submit", (e) => { e.preventDefault(); sendForm(e.target, "/api/policy", $("limitsSave"), "Signing and waiting for the block…", "New limits are on-chain."); });
$("fundForm").addEventListener("submit", (e) => { e.preventDefault(); sendForm(e.target, "/api/topup", $("fundSave"), "Minting and waiting for the block…", "Test money added to the wallet."); });
document.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target.id === "revokeName") document.querySelector("[data-revoke]")?.click(); });
if (BOOT.read_only) { $("readonly").hidden = false; $("contactBtn").disabled = true; }
window.addEventListener("shouhu-registered", (e) => toast(`Registered. The owner key signed your statement and it matches the contract's owner. Next: invite your student with the code in the Family panel.`, 7000));
window.ShouhuAuth.ready(() => {
  load();
  setInterval(() => { if (!working && window.ShouhuAuth.account) load(); }, 5000);
});
