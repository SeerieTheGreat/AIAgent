"use strict";
const BOOT = window.SHOUHU || {};
const $ = (id) => document.getElementById(id);
{ const t = new URLSearchParams(location.search).get("theme"); if (t === "light" || t === "dark") document.documentElement.dataset.theme = t; }
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const short = (h, a = 6, b = 4) => (h && h.length > a + b + 2 ? `${h.slice(0, a)}…${h.slice(-b)}` : h || "");
const proofUrl = (h) => `/proof?tx=${encodeURIComponent(h)}${document.documentElement.dataset.theme ? `&theme=${document.documentElement.dataset.theme}` : ""}`;   // keep a forced theme
const GROUPS = [["all", "All"], ["payments", "Payments"], ["approvals", "Parent approvals"], ["rules", "Contacts & limits"], ["deposits", "Money added"]];
const BADGE = { payment: "payment", approval: "approval", allowlist: "contact", policy: "limits", pause: "pause", agent: "agent key", deposit: "money in" };
const SIGNER = { agent: "agent key (Shouhu)", owner: "owner key (parent)", other: "anyone" };
let DATA = null;
let FILTER = "all";

if (BOOT.side === "owner") { $("seal").style.background = "var(--ink)"; $("seal").textContent = "家长"; $("brandTitle").textContent = "Owner console · 家长"; }
$("chainName").textContent = BOOT.chain === "anvil" ? "Local chain (Anvil)" : BOOT.chain === "sepolia" ? "Ethereum Sepolia" : BOOT.chain;

function toast(text, ms = 3200) {
  const t = $("toast");
  t.textContent = text;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.hidden = true), ms);
}

const when = (ts) => (ts ? new Date(ts * 1000).toLocaleString([], { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "");
function ago(ts) {
  if (!ts) return "";
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 90) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400 * 2) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} days ago`;
}
const num = (amount) => (amount ? Number(amount.split(" ")[0]).toLocaleString("en-US", { maximumFractionDigits: 2 }) : "");

function render() {
  if (!DATA) return;
  const st = DATA.stats || {};
  $("stats").innerHTML = DATA.stats ? `
    <div class="stat"><span>Paid out</span><b>${esc(num(st.paid))} <small>tUSDC</small></b><em>${st.payments} payment${st.payments === 1 ? "" : "s"}</em></div>
    <div class="stat"><span>Tier 1 · Tier 2</span><b>${st.tier1} <small>·</small> ${st.tier2}</b><em>inside the limits · with approval</em></div>
    <div class="stat"><span>Parent approvals</span><b>${st.approvals}</b><em>one-time, signed with the owner key</em></div>
    <div class="stat"><span>Money added</span><b>${esc(num(st.deposited))} <small>tUSDC</small></b><em>${st.deposits} deposit${st.deposits === 1 ? "" : "s"}</em></div>` : "";
  const counts = { all: DATA.entries.length };
  for (const e of DATA.entries) counts[e.group] = (counts[e.group] || 0) + 1;
  $("filters").innerHTML = GROUPS.map(([g, label]) => `<button type="button" class="chip ${FILTER === g ? "on" : ""}" data-g="${g}">${label} <span>${counts[g] || 0}</span></button>`).join("");
  const rows = DATA.entries.filter((e) => FILTER === "all" || e.group === FILTER);
  if (!rows.length) {
    $("table").innerHTML = `<div class="empty">${DATA.error ? esc("The ledger is unavailable right now: " + DATA.error.slice(0, 200)) : "Nothing here yet."}</div>`;
    return;
  }
  $("table").innerHTML = `<div class="tx-row tx-th"><div>When</div><div>Event</div><div class="r">Amount</div><div>Who</div><div>Signed by</div><div>Proof</div></div>` +
    rows.map((e) => {
      const sign = e.kind === "payment" ? "−" : e.kind === "deposit" ? "+" : "";
      const amtCls = e.kind === "payment" ? "out" : e.kind === "deposit" ? "in" : "muted";
      return `<div class="tx-row">
        <div class="c-when" title="${esc(when(e.time))}">${esc(ago(e.time))}<small>${esc(when(e.time))}</small></div>
        <div class="c-what"><span class="kind-badge k-${esc(e.kind)}">${esc(BADGE[e.kind] || e.kind)}</span><b>${esc(e.title)}</b><small>${esc(e.detail || "")}${e.tier ? ` <span class="tag t${e.tier}">Tier ${e.tier}</span>` : ""}</small></div>
        <div class="c-amt r ${amtCls}">${e.amount ? `${sign}${esc(num(e.amount))} <small>tUSDC</small>` : "—"}</div>
        <div class="c-who">${e.minted ? `tUSDC mint<small>new test money, no sender</small>` : e.party ? `${esc(e.party_name || "")}<small class="mono" title="${esc(e.party)}">${esc(short(e.party))}</small>` : "—"}</div>
        <div class="c-by"><span class="by by-${esc(e.signer)}">${esc(SIGNER[e.signer] || e.signer)}</span></div>
        <div class="c-link"><a class="proof-link" href="${proofUrl(e.tx_hash)}">proof →</a>${e.explorer ? ` <a href="${e.explorer}" target="_blank" rel="noopener" title="Open on Etherscan">↗</a>` : ""}<small>block ${e.block.toLocaleString("en-US")}</small></div>
      </div>`;
    }).join("");
}

async function load(fresh) {
  if (fresh) await fetch("/api/refresh", { method: "POST", headers: { "Content-Type": "application/json", "X-Shouhu-Token": BOOT.token }, body: "{}" }).catch(() => null);
  const r = await fetch(`/api/ledger${fresh ? "?fresh=1" : ""}`);
  if (r.status === 401) return window.ShouhuAuth.expired();
  const d = await r.json().catch(() => null);
  if (!d) { $("dot").className = "dot off"; return; }
  $("dot").className = d.error ? "dot off" : "dot";
  DATA = d;
  $("foot").textContent = d.error ? "" : `${d.entries.length} events on ${d.chain}. Read ${new Date().toLocaleTimeString()}; amounts in tUSDC, a test token with no value.`;
  render();
}

function download(name, text, type) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type }));
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
const stamp = () => new Date().toISOString().slice(0, 10);
$("csv").addEventListener("click", () => {
  if (!DATA) return;
  const cols = ["time_utc", "kind", "title", "amount_tusdc", "party_name", "party_address", "tier", "signed_by", "block", "tx_hash", "explorer"];
  const q = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const lines = [cols.join(",")].concat(DATA.entries.map((e) => [e.time ? new Date(e.time * 1000).toISOString() : "", e.kind, e.title,
    e.amount ? e.amount.split(" ")[0] : "", e.party_name, e.party, e.tier, SIGNER[e.signer] || e.signer, e.block, e.tx_hash, e.explorer].map(q).join(",")));
  download(`shouhu-transactions-${DATA.chain}-${stamp()}.csv`, lines.join("\n") + "\n", "text/csv");
});
$("json").addEventListener("click", () => { if (DATA) download(`shouhu-transactions-${DATA.chain}-${stamp()}.json`, JSON.stringify(DATA, null, 2), "application/json"); });
$("refresh").addEventListener("click", () => { $("table").innerHTML = `<div class="empty">Reading the wallet's events from the chain…</div>`; load(true); });
$("filters").addEventListener("click", (e) => { const b = e.target.closest("[data-g]"); if (b) { FILTER = b.dataset.g; render(); } });
window.ShouhuAuth.ready(() => load(false));
