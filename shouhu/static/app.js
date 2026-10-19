"use strict";
const BOOT = window.SHOUHU || {};
const $ = (id) => document.getElementById(id);
{ const t = new URLSearchParams(location.search).get("theme"); if (t === "light" || t === "dark") document.documentElement.dataset.theme = t; }
let STATE = null;
let busy = false;
let lastRequests = "";

// ------------------------------------------------------------------ helpers
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const short = (h, a = 6, b = 4) => (h && h.length > a + b + 2 ? `${h.slice(0, a)}…${h.slice(-b)}` : h || "");
const txUrl = (h) => (STATE && STATE.tx_explorer ? STATE.tx_explorer.replace("{}", h) : null);
const proofUrl = (h) => `/proof?tx=${encodeURIComponent(h)}`;

async function api(path, body) {
  const opt = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json", "X-Shouhu-Token": BOOT.token }, body: JSON.stringify(body),
  };
  const r = await fetch(path, opt);
  const j = await r.json().catch(() => ({ error: `HTTP ${r.status}` }));
  if (r.status === 401) window.ShouhuAuth.expired();
  if (!r.ok && !j.error) j.error = `HTTP ${r.status}`;
  return j;
}

function toast(text, ms = 3200) {
  const t = $("toast");
  t.textContent = text;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.hidden = true), ms);
}

// A small, safe markdown subset: escape first, then bold, code, bullet lists, hashes as explorer links.
function md(text) {
  const lines = esc(text).split(/\n/);
  let html = "", list = false;
  for (const raw of lines) {
    let l = raw
      .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/(^|[^\w/])(0x[0-9a-fA-F]{64})(?![\w])/g, (m, pre, h) => {
        const u = txUrl(h);
        return u ? `${pre}<a href="${u}" target="_blank" rel="noopener" class="mono" title="${h}">${short(h, 10, 6)}</a>` : `${pre}<code title="${h}">${short(h, 10, 6)}</code>`;
      });
    const bullet = /^\s*[-*•]\s+(.*)/.exec(l);
    if (bullet) {
      if (!list) { html += "<ul>"; list = true; }
      html += `<li>${bullet[1]}</li>`;
      continue;
    }
    if (list) { html += "</ul>"; list = false; }
    if (l.trim()) html += `<p>${l}</p>`;
  }
  if (list) html += "</ul>";
  return html || "<p></p>";
}

// ------------------------------------------------------------------ chat rendering
const stream = $("stream");
const scrollDown = () => (stream.scrollTop = stream.scrollHeight);

function addUser(text) {
  $("welcome")?.remove();
  const el = document.createElement("div");
  el.className = "msg user";
  el.innerHTML = `<div class="bubble">${esc(text).replace(/\n/g, "<br>")}</div>`;
  stream.appendChild(el);
  scrollDown();
}

function cardHtml(c) {
  const tierTag = c.tier === 1 ? `<span class="tag t1">Tier 1 · within policy</span>`
    : c.tier === 2 ? `<span class="tag t2">Tier 2 · owner approval</span>`
    : c.tier === 0 ? `<span class="tag t0">blocked</span>` : "";
  let extra = "";
  if (c.kind === "paid" && c.tx) {
    const u = c.explorer || txUrl(c.tx);
    extra += `<div class="row small">tx ${u ? `<a class="hash" href="${u}" target="_blank" rel="noopener">${short(c.tx, 10, 8)} ↗</a>` : `<span class="hash">${short(c.tx, 10, 8)}</span>`}
      <span>· intent <span class="hash" title="${esc(c.intent)}">${short(c.intent, 8, 4)}</span></span>
      <a class="proof-link" href="${proofUrl(c.tx)}" target="_blank" rel="noopener">Proof of transaction →</a></div>`;
  }
  if (c.kind === "request" && BOOT.owner_url) {
    extra += `<div class="row small" style="margin-top:4px">Waiting for the owner. <a href="${BOOT.owner_url}" target="_blank" rel="noopener">Open the owner console ↗</a></div>`;
  }
  const lines = [...(c.lines || []), ...(c.warnings || []).map((w) => `⚠ ${w}`)].filter(Boolean);
  const list = c.kind === "read" || !lines.length ? "" : `<ul>${lines.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>`;
  const trace = `<details class="trace"><summary>${esc(c.tool)}(${esc(JSON.stringify(c.args))})</summary><pre>${esc(JSON.stringify(c.result, null, 2))}</pre></details>`;
  return `<div class="card ${c.kind}"><div class="row"><span class="title">${esc(c.title)}</span>${tierTag}</div>${extra}${list}${trace}</div>`;
}

function botShell() {
  const el = document.createElement("div");
  el.className = "msg bot";
  el.innerHTML = `<div class="seal small" aria-hidden="true">守</div><div class="body"><div class="cards"></div><div class="bubble typing" aria-label="Shouhu is thinking"><i></i><i></i><i></i></div></div>`;
  stream.appendChild(el);
  scrollDown();
  return el;
}

function fillBot(el, turn) {
  const body = el.querySelector(".body");
  body.querySelector(".cards").innerHTML = (turn.cards || []).map(cardHtml).join("");
  const bubble = body.querySelector(".bubble");
  bubble.classList.remove("typing");
  bubble.removeAttribute("aria-label");
  if (turn.error) {
    bubble.innerHTML = `<p class="err">${esc(turn.error)}</p>`;
  } else {
    bubble.innerHTML = md(turn.reply || "(no reply)");
  }
  if (turn.seconds !== undefined) {
    const m = document.createElement("div");
    m.className = "meta";
    m.textContent = `${turn.seconds}s · ${(turn.cards || []).length} tool call${(turn.cards || []).length === 1 ? "" : "s"}`;
    body.appendChild(m);
  }
  scrollDown();
}

async function send(text) {
  text = (text || "").trim();
  if (!text || busy) return;
  if (BOOT.offline) { toast(BOOT.offline, 5000); return; }
  busy = true;
  $("send").disabled = true;
  $("input").value = "";
  autosize();
  addUser(text);
  const el = botShell();
  const poll = setInterval(async () => {
    const p = await api("/api/progress").catch(() => null);
    if (p && p.cards) { el.querySelector(".cards").innerHTML = p.cards.map(cardHtml).join(""); scrollDown(); }
  }, 800);
  let turn;
  try {
    turn = await api("/api/chat", { text });
  } catch (e) {
    turn = { error: String(e) };
  }
  clearInterval(poll);
  fillBot(el, turn);
  busy = false;
  $("send").disabled = false;
  $("input").focus();
  if ((turn.cards || []).some((c) => c.kind === "paid")) loadHistory(true);
  refresh(true);
}

// ------------------------------------------------------------------ side panels
function renderState(s) {
  STATE = s;
  $("chainName").textContent = s.chain === "anvil" ? "Local chain (Anvil)" : s.chain === "sepolia" ? "Ethereum Sepolia" : s.chain;
  $("chainDot").className = "dot";
  const [amt, sym] = s.balance.split(" ");
  $("balance").innerHTML = `${esc(Number(amt).toLocaleString("en-US", { maximumFractionDigits: 2 }))}<small>${esc(sym)}</small>`;
  $("walletAddr").textContent = short(s.wallet, 6, 4);
  $("walletAddr").title = s.wallet;
  if (s.wallet_explorer) { $("walletLink").href = s.wallet_explorer; $("walletLink").hidden = false; } else $("walletLink").hidden = true;
  $("paused").textContent = s.paused ? "paused by the owner" : "active";
  $("paused").className = `status ${s.paused ? "bad" : "ok"}`;
  $("perCap").textContent = s.per_transfer_cap;
  $("rollCap").textContent = s.rolling_cap;
  const pct = s.rolling_cap_units ? Math.min(100, (100 * s.spent_24h_units) / s.rolling_cap_units) : 0;
  $("barFill").style.width = `${pct}%`;
  $("bar").className = `bar${pct > 80 ? " hot" : ""}`;
  $("spent").textContent = s.spent_24h;
  $("headroom").textContent = s.headroom;

  $("contacts").innerHTML = s.contacts.map((c) => `
    <div class="item"><div class="avatar">${esc(c.alias ? c.alias[0] : c.name[0])}</div>
      <div class="grow"><div><b>${esc(c.name)}</b> ${c.alias ? `<span class="small">${esc(c.alias)}</span>` : ""}</div>
      <div class="addr small" title="${esc(c.address)}">${c.explorer ? `<a href="${c.explorer}" target="_blank" rel="noopener">${short(c.address)}</a>` : short(c.address)}</div></div>
      ${c.allowlisted ? `<span class="ok-mark">✓ allowlisted</span>` : `<span class="no-mark">not allowlisted</span>`}</div>`).join("");

  const reqs = s.requests || [];
  $("requests").innerHTML = reqs.length ? reqs.slice(0, 8).map((r) => `
    <div class="item"><div class="grow"><div><b>${esc(r.id)}</b> · ${esc(r.amount)} → ${esc(r.name || short(r.to))}</div>
      <div class="small">${esc((r.reasons || []).join("; "))}</div>
      ${r.status === "approved" ? `<div style="margin-top:6px"><button class="btn jade" data-complete="${esc(r.id)}">Ask Shouhu to complete ${esc(r.id)}</button></div>` : ""}
      ${r.exec_tx ? `<div class="small"><a href="${proofUrl(r.exec_tx)}" target="_blank" rel="noopener">payment proof →</a>${r.approve_tx ? ` · <a href="${proofUrl(r.approve_tx)}" target="_blank" rel="noopener">approval proof →</a>` : ""}</div>` : ""}</div>
      <span class="st ${esc(r.status)}">${esc(r.status)}</span></div>`).join("")
    : `<div class="empty">None yet. Payments outside the limits appear here.</div>`;

  // tell the student when the owner acts in the other window
  const sig = reqs.map((r) => `${r.id}:${r.status}`).join(",");
  if (lastRequests && sig !== lastRequests) {
    const approved = reqs.find((r) => r.status === "approved" && !lastRequests.includes(`${r.id}:approved`));
    if (approved) toast(`The owner approved ${approved.id}. Ask Shouhu to complete it.`, 5000);
  }
  lastRequests = sig;
  renderChips();

  $("footnote").innerHTML = `Agent key <a href="${s.agent_explorer || "#"}" target="_blank" rel="noopener" class="addr">${short(s.agent)}</a> · gas ${s.agent_gas_eth} ETH<br>
    Owner <span class="addr">${short(s.owner)}</span> · RPC ${esc(new URL(s.rpc).host)}<br>This page holds no owner key. Approvals happen only in the owner console, a separate process.`;
}

async function refresh(force) {
  if (force) await api("/api/refresh", {}).catch(() => null);
  const s = await api("/api/state").catch(() => null);
  if (!s || s.error) {
    $("chainName").textContent = "chain unreachable, retrying";
    $("chainDot").className = "dot off";
    return;
  }
  renderState(s);
}

async function loadHistory(force) {
  if (force) await api("/api/refresh", {}).catch(() => null);
  const h = await api("/api/history").catch((e) => ({ error: String(e), payments: [] }));
  const rows = h.payments || [];
  $("history").innerHTML = rows.length ? rows.slice(0, 10).map((p) => `
    <div class="item"><div class="grow"><div><b>${esc(p.amount)}</b> → ${esc(p.name || short(p.to))} ${p.via_approval ? `<span class="tag t2">approval</span>` : ""}</div>
      <div class="small">block ${p.block} · ${p.explorer ? `<a class="addr" href="${p.explorer}" target="_blank" rel="noopener">${short(p.tx_hash, 10, 6)} ↗</a>` : `<span class="addr">${short(p.tx_hash, 10, 6)}</span>`}</div></div>
      <a class="proof-link" href="${proofUrl(p.tx_hash)}" target="_blank" rel="noopener">proof →</a></div>`).join("")
    : `<div class="empty">${h.error ? esc("History unavailable right now: " + h.error.slice(0, 140)) : "No payments yet."}</div>`;
}

function renderChips() {
  const approved = (STATE?.requests || []).filter((r) => r.status === "approved");
  const extra = approved.map((r) => ({ text: `The owner says they approved request ${r.id}. Please complete it.`, label: `complete ${r.id}`, hot: true }));
  const items = [...extra, ...(BOOT.examples || [])];
  $("chips").innerHTML = items.map((e, i) => `<button type="button" class="chip${e.hot ? " hot" : ""}" data-i="${i}" title="${esc(e.text)}">${esc(e.hot ? `✓ ${e.label}` : e.chip || e.text)}</button>`).join("");
  $("chips").onclick = (ev) => { const b = ev.target.closest(".chip"); if (b) send(items[+b.dataset.i].text); };
}

function renderExamples() {
  const ex = BOOT.examples || [];
  $("examples").innerHTML = ex.map((e, i) => `<button type="button" class="ex" data-i="${i}"><small>${e.n}. ${esc(e.label)}</small><span>${esc(e.text)}</span></button>`).join("");
  $("examples").onclick = (ev) => { const b = ev.target.closest(".ex"); if (b) send(ex[+b.dataset.i].text); };
}

// ------------------------------------------------------------------ wiring
function autosize() { const t = $("input"); t.style.height = "auto"; t.style.height = Math.min(140, t.scrollHeight) + "px"; }
$("input").addEventListener("input", autosize);
$("input").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send($("input").value); } });
$("form").addEventListener("submit", (e) => { e.preventDefault(); send($("input").value); });
$("traceToggle").addEventListener("change", (e) => {
  document.body.classList.toggle("show-trace", e.target.checked);
  try { localStorage.setItem("shouhu-trace", e.target.checked ? "1" : "0"); } catch (_) {}
});
try { if (localStorage.getItem("shouhu-trace") === "1") { $("traceToggle").checked = true; document.body.classList.add("show-trace"); } } catch (_) {}
$("requests").addEventListener("click", (e) => { const b = e.target.closest("[data-complete]"); if (b) send(`The owner says they approved request ${b.dataset.complete}. Please complete it.`); });
$("reloadHistory").addEventListener("click", (e) => { e.preventDefault(); loadHistory(true); });
$("newChat").addEventListener("click", async () => {
  if (busy) return;
  const r = await api("/api/new", {});
  if (r.error) return toast(r.error);
  location.reload();
});
if (BOOT.owner_url) {
  for (const id of ["ownerLink", "ownerLink2"]) { $(id).href = BOOT.owner_url; $(id).hidden = false; }
}
if (BOOT.offline) { $("offline").textContent = BOOT.offline; $("offline").hidden = false; }

renderExamples();
renderChips();
window.addEventListener("shouhu-registered", (e) => toast(`Welcome, ${e.detail.name}. Your account is linked to the family wallet.`, 4500));
window.ShouhuAuth.ready((acct) => {
  const hello = document.querySelector("#welcome h3");
  if (hello) hello.textContent = `你好 ${acct.chinese_name || acct.name}, I'm Shouhu.`;
  refresh();
  loadHistory();
  setInterval(() => { if (!busy && window.ShouhuAuth.account) refresh(); }, 8000);
  // restore the conversation after a reload
  api("/api/log").then((l) => {
    for (const t of l.turns || []) { addUser(t.user); fillBot(botShell(), t); }
  });
  $("input").focus();
});
