"use strict";
// Sign-up and sign-in screen shared by the student app, the owner console, the transactions page and the proof page.
// It also draws the page navigation. ShouhuAuth.ready(fn) runs fn(account) once the person is signed in.
(function () {
  const BOOT = window.SHOUHU || {};
  const owner = BOOT.side === "owner";
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const short = (h) => (h && h.length > 14 ? `${h.slice(0, 6)}…${h.slice(-4)}` : h || "");
  const params = new URLSearchParams(location.search);
  const theme = params.get("theme");
  const keep = theme ? `?theme=${encodeURIComponent(theme)}` : "";
  let account = null;
  const waiting = [];

  async function post(path, body) {
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", "X-Shouhu-Token": BOOT.token }, body: JSON.stringify(body) });
    return r.json().catch(() => ({ error: `HTTP ${r.status}` }));
  }

  // ------------------------------------------------------------------ navigation
  function renderNav() {
    const nav = document.getElementById("nav");
    if (!nav) return;
    const items = owner ? [["/", "Console"], ["/transactions", "Transactions"], ["/proof", "Verify"]]
      : [["/", "Chat"], ["/transactions", "Transactions"], ["/proof", "Verify"]];
    const here = location.pathname === "/index.html" ? "/" : location.pathname;
    nav.innerHTML = items.map(([href, label]) => `<a href="${href}${keep}" class="${here === href ? "on" : ""}">${label}</a>`).join("");
  }

  // ------------------------------------------------------------------ the screen
  const chainName = BOOT.chain === "anvil" ? "the local test chain (Anvil)" : BOOT.chain === "sepolia" ? "Ethereum Sepolia" : BOOT.chain;

  function hero(fam) {
    const line = (ok, text) => `<div class="status-line ${ok ? "ok" : "wait"}"><span class="dot${ok ? "" : " off"}"></span>${text}</div>`;
    const parentLine = fam.owner_registered
      ? line(true, `Parent registered: <b>${esc(fam.owner_name)}</b>${fam.owner_verified ? " · owner key verified" : ""}`)
      : !owner ? line(false, "Waiting for the parent to register in the owner console")
      : BOOT.read_only ? line(false, "No owner key on this computer, so the console cannot sign")
      : line(true, "Owner key loaded on this computer, ready to sign");
    const studentLine = fam.student_registered ? line(true, "Student account active") : line(false, "Student not registered yet: they sign up with your invite code");
    const points = owner ? [
      ["Sign with the owner key", "The console signs a short statement and checks it against the owner stored in the smart contract."],
      ["Set the spending limits", "Optional. New limits are written on-chain in the same step, with a proof."],
      ["Invite your student", "You get a one-time code. Only that code can create the student's account."],
    ] : [
      ["Pays inside the limits", "Per-payment and daily caps and an allowlist, enforced by a smart contract."],
      ["Your parent approves the rest", "Once, for exactly that payment, with their own key."],
      ["A proof for every payment", "Re-read from the blockchain and linked to your own words."],
    ];
    return `<aside class="auth-hero ${owner ? "owner" : ""}">
      <div class="hero-brand"><div class="seal" ${owner ? 'style="background:var(--gold)"' : ""} aria-hidden="true">${owner ? "家长" : "守护"}</div>
        <div><div class="hero-name">${owner ? "Parent console" : "Shouhu 守护"}</div><div class="hero-sub">${owner ? "家长控制台" : "Policy-guarded AI agent wallet"}</div></div></div>
      <h2>${owner ? "You hold the owner key. Registering proves it." : "Your family wallet, guarded."}</h2>
      <p class="hero-lead">${owner ? "This console runs as its own program and is the only place the owner key is used."
        : "Shouhu pays your contacts for you, in English or Chinese, but only inside the limits your parent set on-chain."}</p>
      <ol class="hero-points">${points.map(([h, b], i) => `<li><span class="n">${i + 1}</span><div><b>${h}</b><span>${b}</span></div></li>`).join("")}</ol>
      <div class="hero-status">${parentLine}${owner ? studentLine : ""}
        <div class="status-line"><span class="dot ink"></span>Wallet <span class="mono">${esc(short(BOOT.wallet))}</span> on ${esc(chainName)}</div></div>
      <p class="hero-foot">Test network only: tUSDC has no value.</p>
    </aside>`;
  }

  const pw = (name, label, auto, extra = "") =>
    `<label>${label}<span class="pw"><input name="${name}" type="password" required ${extra} autocomplete="${auto}"><button type="button" class="pw-eye" tabindex="-1" aria-label="Show password">Show</button></span></label>`;

  function screen(me, msg) {
    const el = document.getElementById("auth");
    const fam = me.family || {};
    const registered = me.registered;
    let form;
    if (registered) {
      form = `<form class="auth-card" id="authForm" data-mode="login">
        <h2>${owner ? "Parent sign-in · 家长登录" : "Student sign-in · 学生登录"}</h2>
        <p class="lead">${owner ? "Review requests, manage contacts and limits, approve payments." : "Chat with Shouhu and see your payments."}</p>
        ${pw("password", "Password", "current-password", "autofocus")}
        <div class="auth-err" id="authErr">${esc(msg || "")}</div>
        <button class="btn primary wide" type="submit">Sign in</button>
        <p class="small center">Forgot it? Restart with <code>uv run shouhu-web --reset-accounts</code> and register again.</p>
      </form>`;
    } else if (owner) {
      form = `<form class="auth-card" id="authForm" data-mode="register">
        <h2>Parent sign-up · 家长注册</h2>
        <p class="lead">Step 1 of 2 for the family: you register here, then you invite your student.</p>
        ${BOOT.read_only ? `<div class="auth-note">This console has no owner key (<code>.owner.env</code>), so it cannot sign the registration. Add the key and restart.</div>` : ""}
        <label>Your name<input name="name" required minlength="2" maxlength="40" autocomplete="name" placeholder="e.g. Lin Jianguo" autofocus></label>
        <div class="two">${pw("password", "Password", "new-password", 'minlength="8" placeholder="8+ characters"')}${pw("password2", "Repeat password", "new-password", 'minlength="8"')}</div>
        <fieldset><legend>Spending limits for Shouhu (optional)</legend>
          <div class="two"><label>Per payment, tUSDC<input name="per_transfer_cap" inputmode="decimal" placeholder="keep current"></label>
          <label>Per 24 hours, tUSDC<input name="rolling_cap" inputmode="decimal" placeholder="keep current"></label></div>
          <p class="small">Leave a field empty to keep that limit as it is in the contract.</p>
        </fieldset>
        <div class="auth-err" id="authErr">${esc(msg || "")}</div>
        <button class="btn primary wide" type="submit">Sign with the owner key and register</button>
        <p class="small center">Stored only on this computer; the password as a salted scrypt hash.</p>
      </form>`;
    } else {
      const invite = (params.get("invite") || "").toUpperCase();
      form = `<form class="auth-card" id="authForm" data-mode="register">
        <h2>Student sign-up · 学生注册</h2>
        <p class="lead">Step 2 of 2 for the family: use the invite code your parent got when they registered.</p>
        ${fam.owner_registered ? "" : `<div class="auth-note">Your parent has not registered yet. Ask them to open the owner console first; it gives them your invite code.</div>`}
        <label>Invite code from your parent<input name="invite" class="mono invite" required maxlength="9" autocomplete="off" spellcheck="false" placeholder="e.g. K7Q-M2F" value="${esc(invite)}"></label>
        <div class="two"><label>Your name<input name="name" required minlength="2" maxlength="40" autocomplete="name" placeholder="e.g. Lin Xiaoyu" ${invite ? "autofocus" : ""}></label>
          <label>Chinese name (optional)<input name="chinese_name" maxlength="12" placeholder="e.g. 林小雨"></label></div>
        <div class="two">${pw("password", "Password", "new-password", 'minlength="8" placeholder="8+ characters"')}${pw("password2", "Repeat password", "new-password", 'minlength="8"')}</div>
        <div class="auth-err" id="authErr">${esc(msg || "")}</div>
        <button class="btn primary wide" type="submit">Create my account</button>
        <p class="small center">You never hold a key. Stored only on this computer; the password as a salted scrypt hash.</p>
      </form>`;
    }
    el.innerHTML = `<div class="auth-wrap">${hero(fam)}${form}</div>`;
    el.hidden = false;
    document.body.classList.add("locked");
    const f = document.getElementById("authForm");
    f.querySelectorAll(".pw-eye").forEach((b) => b.addEventListener("click", () => {
      const show = b.textContent === "Show";
      f.querySelectorAll('input[type="password"], input[data-pw]').forEach((i) => { i.type = show ? "text" : "password"; i.dataset.pw = "1"; });
      f.querySelectorAll(".pw-eye").forEach((x) => { x.textContent = show ? "Hide" : "Show"; });
    }));
    const inv = f.querySelector("input.invite");
    if (inv) inv.addEventListener("input", () => { inv.value = inv.value.toUpperCase(); });
    f.addEventListener("submit", async (e) => {
      e.preventDefault();
      const data = Object.fromEntries(new FormData(f).entries());
      const btn = f.querySelector("button[type=submit]");
      const label = btn.textContent;
      btn.disabled = true;
      btn.textContent = f.dataset.mode === "login" ? "Signing in…" : owner && (data.per_transfer_cap || data.rolling_cap) ? "Signing and waiting for the block…" : "Registering…";
      const r = await post(f.dataset.mode === "login" ? "/api/login" : "/api/register", data).catch((err) => ({ error: String(err) }));
      btn.disabled = false;
      btn.textContent = label;
      if (r.error) { document.getElementById("authErr").textContent = r.error; return; }
      if (params.get("invite")) history.replaceState(null, "", location.pathname + keep);   // the code is spent; keep it out of the address bar
      done(r.account, f.dataset.mode === "register");
    });
    (f.querySelector("[autofocus]") || f.querySelector("input"))?.focus();
  }

  function done(acct, fresh) {
    account = acct;
    const el = document.getElementById("auth");
    el.hidden = true;
    el.innerHTML = "";
    document.body.classList.remove("locked");
    const chip = document.getElementById("userChip");
    if (chip) {
      chip.hidden = false;
      chip.innerHTML = `<span class="avatar sm">${esc((acct.chinese_name || acct.name || "?")[0])}</span><span class="hide-sm">${esc(acct.name)}</span>
        <button class="linkish" id="signOut" type="button">Sign out</button>`;
      document.getElementById("signOut").onclick = async () => { await post("/api/logout", {}); location.reload(); };
    }
    if (fresh) window.dispatchEvent(new CustomEvent("shouhu-registered", { detail: acct }));
    while (waiting.length) waiting.shift()(acct);
  }

  async function start() {
    renderNav();
    const me = await fetch("/api/me").then((r) => r.json()).catch(() => null);
    if (!me) { screen({ registered: false, family: {} }, "Cannot reach the Shouhu server. Is shouhu-web still running?"); return; }
    if (me.signed_in) done(me.account, false); else screen(me);
  }

  window.ShouhuAuth = {
    ready(fn) { if (account) fn(account); else waiting.push(fn); },
    get account() { return account; },
    async expired() {
      if (!document.getElementById("auth").hidden) return;     // already showing the screen; keep what is typed
      const me = await fetch("/api/me").then((r) => r.json()).catch(() => ({ registered: true, family: {} }));
      account = null;
      screen(me, me.registered ? "Your session ended. Sign in again." : "This account was removed by the parent.");
    },
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
