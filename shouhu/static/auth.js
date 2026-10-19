"use strict";
// Sign-up and sign-in screen shared by the student app, the owner console and the proof page.
// ShouhuAuth.ready(fn) runs fn(account) once the person is signed in.
(function () {
  const BOOT = window.SHOUHU || {};
  const owner = BOOT.side === "owner";
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let account = null;
  const waiting = [];

  async function post(path, body) {
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", "X-Shouhu-Token": BOOT.token }, body: JSON.stringify(body) });
    return r.json().catch(() => ({ error: `HTTP ${r.status}` }));
  }

  const chainName = BOOT.chain === "anvil" ? "the local chain (Anvil)" : BOOT.chain === "sepolia" ? "Ethereum Sepolia" : BOOT.chain;
  const who = owner
    ? { title: "Parent sign-up · 家长注册", lead: `You are the owner of the family wallet on ${chainName}. Registering signs a statement with the owner key on this computer, and the console checks it against the owner recorded in the smart contract.`,
        seal: "家长", sealStyle: "background:var(--ink)" }
    : { title: "Student sign-up · 学生注册", lead: `Your account is linked to the family wallet on ${chainName}. You never hold a key: Shouhu pays for you inside the limits your parent set on-chain.`,
        seal: "守护", sealStyle: "" };

  function screen(registered, msg) {
    const el = document.getElementById("auth");
    const extra = owner ? `
      <fieldset><legend>Spending limits for Shouhu (optional)</legend>
        <div class="two"><label>Per transfer, tUSDC<input name="per_transfer_cap" inputmode="decimal" placeholder="keep current"></label>
        <label>Per 24 hours, tUSDC<input name="rolling_cap" inputmode="decimal" placeholder="keep current"></label></div>
        <p class="small">Leave both empty to keep the limits already in the contract. New limits are written on-chain as part of registration.</p>
      </fieldset>`
      : `<label>Chinese name (optional)<input name="chinese_name" maxlength="12" placeholder="e.g. 林小雨"></label>`;
    el.innerHTML = registered ? `
      <form class="auth-card" id="authForm" data-mode="login">
        <div class="seal" style="${who.sealStyle}" aria-hidden="true">${who.seal}</div>
        <h2>${owner ? "Parent sign-in · 家长登录" : "Student sign-in · 学生登录"}</h2>
        <p class="lead">${owner ? "Sign in to review requests, register contacts and approve payments." : "Sign in to chat with Shouhu."}</p>
        <label>Password<input name="password" type="password" autocomplete="current-password" required autofocus></label>
        <div class="auth-err" id="authErr">${esc(msg || "")}</div>
        <button class="btn primary wide" type="submit">Sign in</button>
        <p class="small">Forgot it? Restart with <code>uv run shouhu-web --reset-accounts</code> and register again.</p>
      </form>` : `
      <form class="auth-card" id="authForm" data-mode="register">
        <div class="seal" style="${who.sealStyle}" aria-hidden="true">${who.seal}</div>
        <h2>${who.title}</h2>
        <p class="lead">${who.lead}</p>
        <label>${owner ? "Your name" : "Your name"}<input name="name" required minlength="2" maxlength="40" autocomplete="name" placeholder="${owner ? "e.g. Lin Jianguo" : "e.g. Lin Xiaoyu"}" autofocus></label>
        ${owner ? "" : extra}
        <div class="two"><label>Password<input name="password" type="password" required minlength="8" autocomplete="new-password" placeholder="8+ characters"></label>
        <label>Repeat password<input name="password2" type="password" required minlength="8" autocomplete="new-password"></label></div>
        ${owner ? extra : ""}
        <div class="auth-err" id="authErr">${esc(msg || "")}</div>
        <button class="btn primary wide" type="submit">${owner ? "Sign with the owner key and register" : "Create my account"}</button>
        <p class="small">Stored only on this computer, password as a salted scrypt hash.</p>
      </form>`;
    el.hidden = false;
    document.body.classList.add("locked");
    const form = document.getElementById("authForm");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const data = Object.fromEntries(new FormData(form).entries());
      const btn = form.querySelector("button[type=submit]");
      const label = btn.textContent;
      btn.disabled = true;
      btn.textContent = form.dataset.mode === "login" ? "Signing in…" : owner && (data.per_transfer_cap || data.rolling_cap) ? "Signing and waiting for the block…" : "Registering…";
      const r = await post(form.dataset.mode === "login" ? "/api/login" : "/api/register", data).catch((err) => ({ error: String(err) }));
      btn.disabled = false;
      btn.textContent = label;
      if (r.error) { document.getElementById("authErr").textContent = r.error; return; }
      done(r.account, form.dataset.mode === "register");
    });
    form.querySelector("input")?.focus();
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
    const me = await fetch("/api/me").then((r) => r.json()).catch(() => null);
    if (!me) { screen(false, "Cannot reach the Shouhu server. Is shouhu-web still running?"); return; }
    if (me.signed_in) done(me.account, false); else screen(me.registered);
  }

  window.ShouhuAuth = {
    ready(fn) { if (account) fn(account); else waiting.push(fn); },
    get account() { return account; },
    expired() { screen(true, "Your session ended. Sign in again."); },
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
