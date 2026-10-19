"use strict";
const BOOT = window.SHOUHU || {};
const $ = (id) => document.getElementById(id);
{ const t = new URLSearchParams(location.search).get("theme"); if (t === "light" || t === "dark") document.documentElement.dataset.theme = t; }
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const short = (h, a = 6, b = 4) => (h && h.length > a + b + 2 ? `${h.slice(0, a)}…${h.slice(-b)}` : h || "");
let S = null;
let open = null;          // request id whose confirmation panel is open
let working = false;
let seen = null;

async function api(path, body) {
  const opt = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json", "X-Shouhu-Token": BOOT.token }, body: JSON.stringify(body),
  };
  const r = await fetch(path, opt);
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
  const tx = (label, h, url) => h && (url ? `<a href="${url}" target="_blank" rel="noopener">${label} ↗</a>` : `${label} <span class="addr">${esc(short(h, 10, 6))}</span>`);
  const links = [tx("approval tx", r.approve_tx, r.approve_explorer), tx("payment tx", r.exec_tx, r.exec_explorer)].filter(Boolean).join(" · ");
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
  const [amt, sym] = S.balance.split(" ");
  $("balance").textContent = `${Number(amt).toLocaleString("en-US", { maximumFractionDigits: 2 })} ${sym}`;
  $("perCap").textContent = S.per_transfer_cap;
  $("rollCap").textContent = S.rolling_cap;
  $("spent").textContent = S.spent_24h;
  $("headroom").textContent = S.headroom;
  if (S.wallet_explorer) $("walletLink").href = S.wallet_explorer; else $("walletLink").hidden = true;
  $("paused").textContent = S.paused ? "paused" : "active";
  $("paused").className = `status ${S.paused ? "bad" : "ok"}`;
  $("pauseBtn").textContent = S.paused ? "Resume the agent" : "Pause the agent";
  $("pauseBtn").disabled = BOOT.read_only || working;
  $("allow").innerHTML = S.contacts.map((c) => `<div class="item"><div class="grow"><div><b>${esc(c.name)}</b></div><div class="addr small">${esc(short(c.address))}</div></div>
    ${c.allowlisted ? `<span class="ok-mark">✓ allowed</span>` : `<span class="no-mark">not allowed</span>`}</div>`).join("");
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
    else toast(`Approved ${esc(r.id)} on-chain. ${r.explorer ? `<a style="color:inherit;text-decoration:underline" href="${r.explorer}" target="_blank" rel="noopener">tx ↗</a>` : esc(short(r.tx, 10, 6))} Shouhu can now complete it.`, 7000);
    document.activeElement?.blur();
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
if (BOOT.read_only) $("readonly").hidden = false;
load();
setInterval(() => { if (!working) load(); }, 5000);
