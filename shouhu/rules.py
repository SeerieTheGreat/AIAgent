"""Rules-only assistant: a small deterministic stand-in for the language model.

It reads plain requests in English and Chinese ("Send 20 USDC to Mama", "给哥转 10 USDC", "What's in my wallet?"),
calls the same five tools the model would, and answers from the tool results with fixed sentences. It exists so the
wallet keeps working without any model, and to show that the model never decides: the policy engine and the contract
take exactly the same decisions in both modes."""
from __future__ import annotations

import json
import re

from . import screen
from .agent import StubResponse, _Block
from .money import fmt

ADDRESS = re.compile(r"0x[a-fA-F0-9]{40}(?![a-fA-F0-9])")
HEXISH = re.compile(r"0x[a-fA-F0-9]{8,}")
HEX_TOKEN = re.compile(r"0x[a-fA-F0-9]+", re.IGNORECASE)
CJK = re.compile(r"[一-鿿]")
NUMBER = re.compile(r"(?<![\w.])\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.])\d+(?:\.\d+)?")
CN_NUMBER = re.compile(r"[零一二两三四五六七八九十百千万]+")
REQUEST_ID = re.compile(r"(?<![a-z0-9])r(\d{1,4})(?![0-9])", re.IGNORECASE)

PAY = re.compile(r"\b(send|pay|transfer|give|wire|remit|tip)\b|转|给|付|汇|打钱|还钱", re.IGNORECASE)
COMPLETE = re.compile(r"\b(complete|finish|approved|approve|go ahead|execute)\b|完成|批准|同意|已批", re.IGNORECASE)
PORTFOLIO = re.compile(r"\b(wallet|balance|how much (money|do i have)|limits?|caps?|portfolio)\b|余额|钱包|还有多少|限额", re.IGNORECASE)
HISTORY = re.compile(r"\b(history|recent|payments|transactions|did i (send|pay))\b|记录|历史|账单|转过", re.IGNORECASE)
SEND_ALL = re.compile(r"\b(all|everything|whole|entire)\b|全部|所有", re.IGNORECASE)
OWNER_CLAIM = re.compile(r"\b(i am|i'm|im) (the |your )?(owner|parent|admin|developer)\b|我是(家长|主人|管理员|开发者)", re.IGNORECASE)
CHANGE_RULES = re.compile(r"\b(raise|increase|lift|remove|change|double)\b.{0,30}\b(limit|cap|caps|limits)\b|提高.{0,6}限额|取消.{0,6}限额",
                          re.IGNORECASE)
# instructions aimed at the assistant inside the user's text (a pasted notice, a fake developer message)
INJECTION = re.compile("|".join([
    r"ignore (all |your |the |previous )*(rules|instructions|policy|policies)",
    r"disregard (all |your |the |previous )*(rules|instructions|policy)",
    r"system (notice|message|override|prompt)",
    r"(send|transfer|pay) (all|everything|the (whole|entire)).{0,40}(to|into)",
    r"you must (now )?(send|transfer|pay)",
    r"new (policy|instruction)",
    r"developer(s)? (of|from) (shouhu|the wallet)|shouhu developers",
    r"pre-?approved",
]), re.IGNORECASE)

CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CN_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}

SAY = {
    "en": {
        "help": "I can check your wallet, show your recent payments, and pay your contacts inside your parent's limits. "
                "Try \"Send 20 USDC to Mama\", \"What's in my wallet?\" or \"给哥转 10 USDC\".",
        "secrets": "I don't have any private keys or passwords, and I don't share how I'm set up. "
                   "I can help with your wallet and payments.",
        "injection": "Don't act on that message, and I won't either: pasted text is treated as data, never as instructions. "
                     "Nothing has been sent. It looks like a scam, so check with the sender another way and tell your parent.",
        "owner": "I can't change the limits or approve anything, and I can't confirm who anyone is in this chat. "
                 "Only the owner key can change the wallet's rules, in the owner console, outside this chat.",
        "send_all": "I can only send a specific amount to one of your contacts, and only inside your parent's limits. Nothing was sent.",
        "bad_address": "{address} is not a complete address (it needs 0x and 40 characters). Nothing was sent; "
                       "please copy the whole address.",
        "ask_amount": "How much should I send to {who}?",
        "ask_who": "Who should I send {amount} to? I can pay: {names}.",
        "ambiguous": "Do you mean {names}? I can pay one person at a time.",
        "no_request": "I can't find request {rid}. Nothing was sent.",
        "paid": "Sent **{amount}** to {to}. It was inside your parent's limits, so the contract let it through right away.",
        "paid_t2": "Done: request {rid} is paid, **{amount}** to {to}, using your parent's one-time approval.",
        "tx": "- Transaction: {tx}",
        "block": "- Block: {block}",
        "request": "I haven't sent this: {reasons}. I filed request **{rid}** for your parent, who approves it in the owner console "
                   "with the owner key. Ask me to complete {rid} once they have.",
        "refused": "I didn't send anything: {reasons}.",
        "contract": "The smart contract refused it ({detail}). Nothing was sent.",
        "chain": "The test network didn't answer ({detail}). Nothing was sent; please try again in a moment.",
        "note": "- Note: {w}",
        "check_stop": "I haven't sent anything. {warnings}.",
        "saved": " {name}'s saved address is {address}. If they really changed wallets, ask your parent to register the new one.",
        "portfolio": "The wallet holds **{balance}**. Your parent's limits: {per} per payment and {roll} per 24 hours; "
                     "{spent} spent so far, {headroom} left.{paused} You can pay: {names}.",
        "paused": " The wallet is paused by your parent right now.",
        "pending": "- Request {id}: {amount} to {to}, {status}",
        "history": "Recent payments:",
        "history_row": "- {amount} to {to}{approved} · {tx}",
        "approved": " (parent-approved)",
        "no_history": "No payments yet.",
    },
    "zh": {
        "help": "我可以查看钱包、显示最近的付款，并在家长设定的限额内给联系人转账。比如：“给妈妈转 20 USDC”、“我的钱包还有多少？”",
        "secrets": "我没有任何私钥或密码，也不透露自己的设置。我可以帮你查看钱包和转账。",
        "injection": "不要照这条消息做，我也不会：粘贴进来的文字只当作资料，不当作指令。没有转出任何钱。"
                     "这很像诈骗，请用别的方式向发信人核实，并告诉家长。",
        "owner": "我不能修改限额或批准任何付款，也无法在聊天里确认对方的身份。只有家长密钥能在聊天之外的家长控制台修改钱包规则。",
        "send_all": "我只能在家长的限额内给某一位联系人转指定的金额，这次没有转出任何钱。",
        "bad_address": "{address} 不是完整的地址（需要 0x 加 40 个字符），没有转出任何钱，请复制完整地址。",
        "ask_amount": "要给{who}转多少？",
        "ask_who": "这 {amount} 要转给谁？可以付款的联系人：{names}。",
        "ambiguous": "你是指{names}吗？我一次只能给一个人转账。",
        "no_request": "找不到请求 {rid}，没有转出任何钱。",
        "paid": "已给{to}转了 **{amount}**。在家长设定的限额内，合约直接放行。",
        "paid_t2": "请求 {rid} 已完成：用家长的一次性批准给{to}转了 **{amount}**。",
        "tx": "- 交易哈希：{tx}",
        "block": "- 区块：{block}",
        "request": "这笔还没有转出：{reasons}。我已为家长提交请求 **{rid}**，家长在家长控制台用家长密钥批准后，告诉我完成 {rid} 即可。",
        "refused": "没有转账：{reasons}。",
        "contract": "智能合约拒绝了这笔交易（{detail}），没有转出任何钱。",
        "chain": "测试网络暂时没有响应（{detail}），没有转出任何钱，请稍后再试。",
        "note": "- 提醒：{w}",
        "check_stop": "我没有转账。{warnings}。",
        "saved": "{name}保存的地址是 {address}。如果对方真的换了钱包，请让家长登记新地址。",
        "portfolio": "钱包余额 **{balance}**。家长的限额：单笔 {per}，24 小时 {roll}；已用 {spent}，还剩 {headroom}。{paused}可以付款的联系人：{names}。",
        "paused": "钱包目前被家长暂停。",
        "pending": "- 请求 {id}：给{to} {amount}，{status}",
        "history": "最近的付款：",
        "history_row": "- 给{to} {amount}{approved} · {tx}",
        "approved": "（家长批准）",
        "no_history": "还没有付款记录。",
    },
}


def cn_to_int(text: str) -> int:
    """Chinese numerals up to the ten-thousands: 二十 -> 20, 十五 -> 15, 两千五百 -> 2500."""
    total = section = num = 0
    for ch in text:
        if ch in CN_DIGITS:
            num = CN_DIGITS[ch]
        elif ch in CN_UNITS:
            unit = CN_UNITS[ch]
            if unit == 10000:
                total += (section + num) * unit
                section = 0
            else:
                section += (num or 1) * unit
            num = 0
    return total + section + num


def parse_amount(text: str) -> str | None:
    """The first amount in the text, as a plain decimal string ('20', '19.5'), or None."""
    clean = HEXISH.sub(" ", text)
    m = NUMBER.search(clean)
    if m:
        return m.group(0).replace(",", "")
    for m in CN_NUMBER.finditer(clean):
        n = cn_to_int(m.group(0))
        if n > 0:
            return str(n)
    return None


def parse_memo(text: str) -> str | None:
    m = re.search(r"\bfor\s+(.+?)[\s.!?。！？]*$", HEXISH.sub(" ", text), re.IGNORECASE)
    return m.group(1).strip()[:80] if m else None


def match_contacts(contacts, text: str) -> list:
    """Contacts named in the text, by name or alias (Chinese aliases by substring, English ones as whole words)."""
    low = text.lower()
    hits = []
    for c in contacts:
        for alias in sorted({c.name.lower(), *c.aliases}, key=len, reverse=True):
            if not alias:
                continue
            found = re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", low) if alias.isascii() else alias in text
            if found:
                hits.append(c)
                break
    return hits


def _join(items, lang: str, word: str = "and") -> str:
    """'Mama, Ge and Xiao Wang' / '妈妈、哥和小王'; word='or' gives 'Mama or Ge' / '妈妈还是哥'."""
    items = [str(i) for i in items if i]
    if len(items) <= 1:
        return items[0] if items else ""
    if lang == "zh":
        return "、".join(items[:-1]) + {"and": "和", "or": "还是"}[word] + items[-1]
    return ", ".join(items[:-1]) + f" {word} " + items[-1]


class RulesModel:
    """Same interface as ModelClient.create(); plans tool calls from the user's text, one step at a time."""

    def __init__(self, ctx=None):
        self.ctx = ctx            # the ToolContext, for contact names and filed requests
        self.turn: dict = {}
        self.calls = 0

    # ------------------------------------------------------------------ the agent calls this
    def create(self, *, system, tools, messages):
        self.calls += 1
        last = messages[-1]
        if last["role"] == "user" and isinstance(last["content"], str):
            self.turn = self.plan(last["content"])
        else:
            for block in last["content"]:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    try:
                        self.turn["results"].append(json.loads(block["content"]))
                    except (TypeError, ValueError):
                        self.turn["results"].append({})
        return self.step()

    # ------------------------------------------------------------------ planning
    def _say(self, key: str, **kw) -> str:
        return SAY[self.turn.get("lang", "en")][key].format(**kw)

    def plan(self, text: str) -> dict:
        lang = "zh" if CJK.search(text) else "en"
        turn = {"text": text, "lang": lang, "results": [], "stage": 0, "kind": "reply"}
        say = SAY[lang]
        contacts = list(self.ctx.contacts) if self.ctx else []
        if screen.asks_for_secrets(text):
            return {**turn, "reply": say["secrets"]}
        if INJECTION.search(text):
            return {**turn, "reply": say["injection"]}
        rid = REQUEST_ID.search(text)
        if rid and COMPLETE.search(text):
            # safe whoever asks: the transfer tool pays only if the contract holds the owner's approval for exactly this
            req_id = f"R{rid.group(1)}"
            req = self.ctx.requests.get(req_id) if self.ctx else None
            if not req:
                return {**turn, "reply": say["no_request"].format(rid=req_id)}
            return {**turn, "kind": "complete", "request_id": req_id, "recipient": req["name"] or req["to"],
                    "amount": fmt(req["amount"]).split()[0]}
        if "authority_claim" in screen.risk_flags(text) or OWNER_CLAIM.search(text) or CHANGE_RULES.search(text):
            return {**turn, "reply": say["owner"]}
        address = ADDRESS.search(text)
        broken = [h for h in HEX_TOKEN.findall(text) if not ADDRESS.fullmatch(h) and len(h) < 66]
        if broken:
            # never fall back to a contact's saved address when the user typed a different, incomplete one
            return {**turn, "reply": say["bad_address"].format(address=broken[0])}
        rest = ADDRESS.sub(" ", text)
        amount = parse_amount(rest)
        named = match_contacts(contacts, rest)
        if amount is None and HISTORY.search(text):
            return {**turn, "kind": "history"}
        if amount is None and PORTFOLIO.search(text):
            return {**turn, "kind": "portfolio"}
        if PAY.search(text) or (amount and (address or named)):
            names = _join([c.name for c in contacts], lang)
            if address:
                recipient = address.group(0)
            elif len(named) == 1:
                recipient = named[0].name
            elif len(named) > 1:
                return {**turn, "reply": say["ambiguous"].format(names=_join([c.name for c in named], lang, "or"))}
            else:
                recipient = None
            if amount is None:
                if SEND_ALL.search(text):
                    return {**turn, "reply": say["send_all"]}
                if recipient:
                    return {**turn, "reply": say["ask_amount"].format(who=recipient)}
                return {**turn, "reply": say["help"]}
            if recipient is None:
                return {**turn, "reply": say["ask_who"].format(amount=f"{amount} tUSDC", names=names)}
            return {**turn, "kind": "pay", "recipient": recipient, "amount": amount, "memo": parse_memo(text)}
        if PORTFOLIO.search(text):
            return {**turn, "kind": "portfolio"}
        return {**turn, "reply": say["help"]}

    # ------------------------------------------------------------------ one step of the plan
    def _tool(self, name: str, args: dict):
        self.turn["stage"] += 1
        return StubResponse([_Block(type="tool_use", id=f"rules_{self.calls}", name=name, input=args)], "tool_use")

    @staticmethod
    def _text(text: str):
        return StubResponse([_Block(type="text", text=text)], "end_turn")

    def step(self):
        t = self.turn
        kind, stage, results = t["kind"], t["stage"], t["results"]
        if kind == "reply":
            return self._text(t["reply"])
        if kind == "portfolio":
            return self._tool("get_portfolio", {}) if stage == 0 else self._text(self.render_portfolio(results[-1]))
        if kind == "history":
            return self._tool("get_history", {"limit": 10}) if stage == 0 else self._text(self.render_history(results[-1]))
        if kind == "complete":
            if stage == 0:
                return self._tool("transfer", {"recipient": t["recipient"], "amount": t["amount"], "memo": None,
                                               "request_id": t["request_id"]})
            return self._text(self.render_transfer(results[-1]))
        if kind == "pay":
            if stage == 0:
                return self._tool("check_recipient", {"recipient": t["recipient"]})
            if stage == 1:
                check = results[-1]
                stop = [w for w in check.get("warnings") or [] if "POISONING" in w or "cannot be paid" in w]
                if stop or check.get("candidates") or not check.get("address"):
                    return self._text(self.render_check_stop(check, stop))
                return self._tool("transfer", {"recipient": t["recipient"], "amount": t["amount"], "memo": t.get("memo"),
                                               "request_id": None})
            return self._text(self.render_transfer(results[-1]))
        return self._text(self._say("help"))

    # ------------------------------------------------------------------ answers, built only from tool results
    def _name(self, name):
        """In Chinese replies, a contact's Chinese name (Mama -> 妈妈); otherwise the name as the tool gave it."""
        if self.turn.get("lang") != "zh" or not name or not self.ctx:
            return name
        c = next((c for c in self.ctx.contacts if c.name == name), None)
        return next((a for a in c.aliases if CJK.search(a)), name) if c else name

    def render_transfer(self, r: dict) -> str:
        status = r.get("status")
        reasons = "; ".join(r.get("reasons") or []) or r.get("detail") or ""
        if status == "executed":
            key = "paid_t2" if r.get("via_owner_approval") else "paid"
            lines = [self._say(key, amount=r.get("amount"), to=self._name(r.get("to")), rid=r.get("request_id") or self.turn.get("request_id")),
                     self._say("tx", tx=r.get("tx_hash")), self._say("block", block=r.get("block"))]
        elif status == "needs_owner_approval":
            lines = [self._say("request", reasons=reasons, rid=r.get("request_id"))]
        elif status == "rejected_by_contract":
            lines = [self._say("contract", detail=r.get("detail", ""))]
        elif status == "chain_error":
            lines = [self._say("chain", detail=r.get("detail", ""))]
        else:
            lines = [self._say("refused", reasons=reasons or "the request was refused")]
        lines += [self._say("note", w=w) for w in r.get("warnings") or [] if isinstance(w, str)]
        return "\n".join(lines)

    def render_check_stop(self, r: dict, stop: list) -> str:
        warnings = stop or r.get("warnings") or []
        if r.get("candidates"):
            return self._say("ambiguous", names=_join(r["candidates"], self.turn["lang"], "or"))
        if not r.get("address"):
            names = _join([c.name for c in (self.ctx.contacts if self.ctx else [])], self.turn["lang"])
            return self._say("ask_who", amount=f"{self.turn.get('amount')} tUSDC", names=names)
        text = self._say("check_stop", warnings="; ".join(warnings).rstrip("."))
        queried = (r.get("address") or "").lower()
        for c in (self.ctx.contacts if self.ctx else []):
            saved = c.address.lower()
            if queried != saved and queried[:6] == saved[:6] and queried[-4:] == saved[-4:]:
                text += self._say("saved", name=c.name, address=c.address)
                break
        return text

    def render_portfolio(self, r: dict) -> str:
        p = r.get("policy") or {}
        lang = self.turn["lang"]
        names = _join([self._name(c["name"]) for c in r.get("allowlisted_contacts") or []], lang) or "-"
        lines = [self._say("portfolio", balance=r.get("balance"), per=p.get("per_transfer_cap"), roll=p.get("rolling_24h_cap"),
                           spent=p.get("spent_last_24h"), headroom=p.get("headroom_24h"),
                           paused=self._say("paused") if p.get("paused") else "", names=names)]
        lines += [self._say("pending", id=q["id"], amount=q["amount"], to=q["to"], status=q["status"])
                  for q in r.get("approval_requests") or []]
        return "\n".join(lines)

    def render_history(self, r: dict) -> str:
        rows = (r.get("payments") or [])[:5]
        if not rows:
            return self._say("no_history")
        lines = [self._say("history")]
        lines += [self._say("history_row", amount=p["amount"], to=self._name(p["to"]), tx=p["tx_hash"],
                            approved=self._say("approved") if p.get("via_owner_approval") else "") for p in rows]
        return "\n".join(lines)
