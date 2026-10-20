"use strict";
const BOOT = window.SHOUHU || {};
const $ = (id) => document.getElementById(id);
{ const t = new URLSearchParams(location.search).get("theme"); if (t === "light" || t === "dark") document.documentElement.dataset.theme = t; }
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const short = (h, a = 10, b = 8) => (h && h.length > a + b + 2 ? `${h.slice(0, a)}…${h.slice(-b)}` : h || "");
const proofUrl = (h) => `/proof?tx=${encodeURIComponent(h)}${document.documentElement.dataset.theme ? `&theme=${document.documentElement.dataset.theme}` : ""}`;   // keep a forced theme
let last = null;

if (BOOT.side === "owner") $("seal").style.background = "var(--ink)";
$("chainName").textContent = BOOT.chain === "anvil" ? "Local chain (Anvil)" : BOOT.chain === "sepolia" ? "Ethereum Sepolia" : BOOT.chain;

function toast(text, ms = 3200) {
  const t = $("toast");
  t.textContent = text;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.hidden = true), ms);
}

const when = (ts) => new Date(ts * 1000).toLocaleString([], { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit", timeZoneName: "short" });
const addr = (a, label) => `<span class="addr" title="${esc(a)}">${esc(a)}</span>${label ? ` <span class="small">${esc(label)}</span>` : ""}`;
const copyable = (v) => `<span class="addr copy" data-copy="${esc(v)}" title="Click to copy">${esc(v)}</span>`;

function render(p) {
  last = p;
  if (!p.found) {
    $("out").innerHTML = `<div class="verdict bad"><div class="mark">✗</div><div><h2>Not found</h2><p>${esc(p.error || "")}</p></div></div>`;
    return;
  }
  const kindTag = { payment: "Payment", approval: "Owner approval", allowlist: "Contact registration / allowlist", policy: "Spending limits",
    pause: "Pause switch", deposit: "Money added" }[p.kind] || "Transaction";
  const rc = p.receipt;
  const receipt = rc ? `<section class="receipt">
      <div class="receipt-head"><div class="seal small" aria-hidden="true">守</div>
        <div><b>Shouhu payment receipt</b><span>交易凭证 · No. ${esc(rc.number)}</span></div>
        ${rc.tier ? `<span class="tag t${rc.tier}">Tier ${rc.tier} · ${rc.tier === 2 ? "parent approval" : "within policy"}</span>` : ""}</div>
      <dl class="receipt-rows">
        <dt>Paid to</dt><dd><b>${esc(rc.paid_to || "an address")}</b><span class="addr">${esc(rc.address)}</span></dd>
        <dt>Amount</dt><dd class="amt">${esc(rc.amount)}</dd>
        <dt>Date</dt><dd>${esc(when(rc.time))}</dd>
        <dt>From</dt><dd>Family wallet <span class="addr">${esc(rc.from_wallet)}</span></dd>
        ${rc.memo ? `<dt>Memo</dt><dd>${esc(rc.memo)}</dd>` : ""}
        ${rc.approval_tx ? `<dt>Approval</dt><dd>The parent's one-time approval: <a href="${proofUrl(rc.approval_tx)}">${esc(short(rc.approval_tx))} →</a></dd>` : ""}
        <dt>Status</dt><dd>${p.success ? "Confirmed" : "Reverted"} on ${esc(p.chain)}, block ${p.block.toLocaleString("en-US")}</dd>
      </dl>
      <p class="receipt-foot">tUSDC is a test token with no value. This receipt is rebuilt from the chain each time it is opened.</p>
    </section>` : "";
  const verify = `<section class="panel"><h3>Check it yourself</h3>
      <ol class="steps">
        ${p.explorer ? `<li>Open it on the public explorer: <a href="${p.explorer}" target="_blank" rel="noopener">Etherscan ↗</a>. Look for status Success and, under Logs, the events listed here.</li>`
          : `<li>This is the local test chain, so there is no public explorer; this page reads the node directly.</li>`}
        <li>From the repository, with no keys at all: <code class="copy" data-copy="${esc(p.verify_command)}" title="Click to copy">${esc(p.verify_command.replace(p.tx_hash, short(p.tx_hash, 10, 6)))}</code></li>
        ${p.intent_id ? `<li>The intent id on-chain is the keccak-256 hash of the policy decision in the audit log, so the decision shown here cannot be swapped afterwards.</li>` : ""}
      </ol></section>`;
  const facts = [
    ["Transaction hash", copyable(p.tx_hash)],
    ["Status", p.success ? `<span class="ok-mark">✓ success</span>` : `<span class="no-mark">reverted</span>`],
    ["Block", `${p.block.toLocaleString("en-US")} · ${p.confirmations.toLocaleString("en-US")} confirmation${p.confirmations === 1 ? "" : "s"}`],
    ["Block time", esc(when(p.block_time))],
    ["Block hash", `<span class="addr">${esc(short(p.block_hash, 12, 10))}</span>`],
    ["From", addr(p.from, p.from_label)],
    ["To", addr(p.to, p.to_label)],
    ["Nonce · gas used · fee", `${p.nonce} · ${p.gas_used.toLocaleString("en-US")} · ${esc(p.fee_eth)} ETH`],
    ["Network", `${esc(p.chain)} (chain id ${p.chain_id})`],
  ];
  if (p.intent_id) facts.splice(1, 0, ["Intent id", copyable(p.intent_id)]);
  const ev = (p.events || []).map((e) => `<div class="event"><b>${esc(e.name)}</b><dl>${Object.entries(e.args).map(([k, v]) => `<dt>${esc(k)}</dt><dd class="${String(v).startsWith("0x") ? "addr" : ""}">${esc(String(v))}</dd>`).join("")}</dl></div>`).join("");
  const d = p.decision;
  const decision = d ? `<section class="panel"><h3>Policy decision behind this payment</h3>
      <p class="small">The intent id written on-chain is the keccak-256 hash of this audit-log entry, so the record cannot be swapped after the fact.</p>
      <dl class="facts">
        <dt>What the student asked</dt><dd>${esc(d.user_message || "—")}</dd>
        <dt>Decision</dt><dd><b>${esc(d.action)}</b> · Tier ${esc(d.tier)}</dd>
        <dt>Reasons</dt><dd>${esc((d.reasons || []).join("; ") || "—")}</dd>
        ${(d.warnings || []).length ? `<dt>Warnings</dt><dd>${esc(d.warnings.join("; "))}</dd>` : ""}
        <dt>Logged</dt><dd>${esc(when(d.ts))} · session ${esc(d.session)} · entry #${esc(d.seq)}</dd>
      </dl></section>` : "";
  const r = p.request;
  const req = r ? `<section class="panel"><h3>Approval request ${esc(r.id)}</h3>
      <dl class="facts">
        <dt>Amount</dt><dd>${esc(r.amount)} to ${esc(r.name || r.to)}</dd>
        <dt>Why it needed the parent</dt><dd>${esc((r.reasons || []).join("; "))}</dd>
        <dt>Status</dt><dd><span class="st ${esc(r.status)}">${esc(r.status)}</span></dd>
        ${r.approve_tx ? `<dt>Owner approval</dt><dd><a href="${proofUrl(r.approve_tx)}">${esc(short(r.approve_tx))} →</a></dd>` : ""}
        ${r.exec_tx ? `<dt>Payment</dt><dd><a href="${proofUrl(r.exec_tx)}">${esc(short(r.exec_tx))} →</a></dd>` : ""}
      </dl></section>` : "";
  $("out").innerHTML = `
    <div class="verdict ${p.all_ok ? "ok" : "bad"}">
      <div class="mark">${p.all_ok ? "✓" : "!"}</div>
      <div><div class="small kind">${esc(kindTag)}</div><h2>${esc(p.title)}</h2>
        <p>${p.all_ok ? "Verified on-chain: every check below passed." : "Some checks did not pass; see below."} Checked ${esc(when(p.verified_at))}.</p></div>
    </div>
    ${receipt}
    <div class="actions no-print">
      ${p.explorer ? `<a class="btn" href="${p.explorer}" target="_blank" rel="noopener">Open on Etherscan ↗</a>` : `<span class="small">Local chain: no public explorer. This page is the record.</span>`}
      <button class="btn" id="print" type="button">Print or save as PDF</button>
      <button class="btn" id="dl" type="button">Download JSON</button>
    </div>
    <div class="proof-grid">
      <section class="panel"><h3>Checks</h3><ul class="checks">${p.checks.map((c) => `<li class="${c.ok ? "ok" : "bad"}"><span>${c.ok ? "✓" : "✗"}</span>${esc(c.text)}</li>`).join("")}</ul></section>
      <section class="panel"><h3>Transaction</h3><dl class="facts">${facts.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl></section>
      ${ev ? `<section class="panel"><h3>Events emitted by the contract</h3>${ev}</section>` : ""}
      ${decision}${req}${verify}
    </div>`;
  $("print").onclick = () => window.print();
  $("dl").onclick = () => {
    const blob = new Blob([JSON.stringify(last, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `shouhu-proof-${last.tx_hash.slice(0, 12)}.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  };
}

async function verify(h) {
  h = (h || "").trim();
  if (!h) return;
  $("tx").value = h;
  history.replaceState(null, "", proofUrl(h));
  $("out").innerHTML = `<div class="empty">Reading the transaction, its receipt and its block from ${esc($("chainName").textContent)}…</div>`;
  const r = await fetch(`/api/proof?tx=${encodeURIComponent(h)}`);
  if (r.status === 401) return window.ShouhuAuth.expired();
  const p = await r.json().catch(() => ({ found: false, error: `HTTP ${r.status}` }));
  if (p.error && p.found === undefined) p.found = false;
  render(p);
  $("dot").className = "dot";
}

document.addEventListener("click", (e) => {
  const c = e.target.closest("[data-copy]");
  if (c) navigator.clipboard?.writeText(c.dataset.copy).then(() => toast("Copied"), () => {});
});
$("lookup").addEventListener("submit", (e) => { e.preventDefault(); verify($("tx").value); });
window.ShouhuAuth.ready(() => {
  const h = new URLSearchParams(location.search).get("tx");
  if (h) verify(h); else $("tx").focus();
});
