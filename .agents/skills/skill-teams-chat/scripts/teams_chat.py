"""Send and read 1:1 Teams chat messages via Chat Service API.

Usage:
  teams_chat.py send <email> <message ...>
  teams_chat.py read <email> [--limit N]
"""
from __future__ import annotations

import datetime, re, sys, urllib.parse
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / ".agents" / "skills" / "skill-m365-copilot-mail-search" / "scripts"))
import m365_mail_search_token as mst  # noqa: E402

CHAT_BASE = "https://teams.microsoft.com/api/chatsvc/emea/v1/users/ME/conversations"
GRAPH = "https://graph.microsoft.com/v1.0"


def _token_pair() -> tuple[str, str]:
    """Return (ic3_token, graph_token) from a single LevelDB scan."""
    records = mst._collect_token_records()
    rt = mst._best_refresh_token(records)
    if rt is None:
        raise RuntimeError("Kein RefreshToken im Teams-LocalStorage gefunden.")
    tenant = mst._tenant_id(records)
    ic3, _, _ = mst._refresh_access_token(rt, tenant, "https://ic3.teams.office.com/.default", ())
    graph, _, _ = mst._refresh_access_token(rt, tenant, "https://graph.microsoft.com/.default", ())
    return ic3, graph


def _resolve_recipient(email: str, graph_tok: str) -> str:
    """Resolve email → AAD object-id via Graph API."""
    r = requests.get(f"{GRAPH}/users/{urllib.parse.quote(email)}?$select=id",
                     headers={"Authorization": f"Bearer {graph_tok}"}, timeout=15)
    r.raise_for_status()
    return r.json()["id"]


def _conv_id(sender: str, recipient: str) -> str:
    a, b = sorted([sender, recipient])
    return f"19:{a}_{b}@unq.gbl.spaces"


def _find_self_chat(ic3: str, graph: str, sender: str) -> str:
    """Scan recent conversations to find self-chat thread id."""
    r = requests.get(f"{CHAT_BASE}?view=msnp24Equivalent&pageSize=50",
                     headers={"Authorization": f"Bearer {ic3}"}, timeout=15)
    r.raise_for_status()
    pat = re.compile(r"19:([0-9a-f-]+)_([0-9a-f-]+)@unq\.gbl\.spaces")
    for c in r.json().get("conversations", []):
        m = pat.match(c.get("id", ""))
        if not m:
            continue
        a, b = m.group(1), m.group(2)
        other = b if a == sender else a if b == sender else None
        if other and other != sender:
            if requests.get(f"{GRAPH}/users/{other}?$select=id",
                            headers={"Authorization": f"Bearer {graph}"}, timeout=10).status_code == 404:
                return c["id"]
    raise RuntimeError("Self-Chat-Konversation nicht gefunden.")


def _post_message(ic3: str, conv: str, sender: str, message: str) -> dict:
    now = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    html = "<p>" + message.replace("\n", "<br/>") + "</p>"
    payload = {
        "id": "-1", "type": "Message", "conversationid": conv,
        "from": f"8:orgid:{sender}", "composetime": now,
        "content": html, "messagetype": "RichText/Html", "contenttype": "Text",
        "clientmessageid": str(int(datetime.datetime.now(datetime.UTC).timestamp() * 1000)),
        "properties": {"importance": "", "subject": "", "cards": "[]",
                        "links": "[]", "mentions": "[]", "files": "[]"},
    }
    url = f"{CHAT_BASE}/{urllib.parse.quote(conv, safe='')}/messages"
    headers = {
        "Authorization": f"Bearer {ic3}", "Content-Type": "application/json",
        "behavioroverride": "redirectAs404",
        "x-ms-migration": "True", "x-ms-test-user": "False",
    }
    r = requests.post(url, headers=headers, json=payload, timeout=20)
    if r.status_code != 201:
        raise RuntimeError(f"Teams API {r.status_code}: {r.text[:300]}")
    return r.json()


def _resolve_conv(ic3: str, graph: str, sender: str, recipient: str) -> str:
    conv = _conv_id(sender, recipient)
    if sender == recipient:
        try:
            return _find_self_chat(ic3, graph, sender)
        except RuntimeError:
            return conv
    return conv


def send(email: str, message: str) -> dict:
    ic3, graph = _token_pair()
    sender = mst._decode_jwt_payload(ic3)["oid"]
    recipient = _resolve_recipient(email, graph)
    conv = _resolve_conv(ic3, graph, sender, recipient)
    return _post_message(ic3, conv, sender, message)


def read(email: str, limit: int = 20) -> list[dict]:
    ic3, graph = _token_pair()
    sender = mst._decode_jwt_payload(ic3)["oid"]
    recipient = _resolve_recipient(email, graph)
    conv = _resolve_conv(ic3, graph, sender, recipient)
    url = f"{CHAT_BASE}/{urllib.parse.quote(conv, safe='')}/messages?view=msnp24Equivalent&pageSize={limit}"
    r = requests.get(url, headers={"Authorization": f"Bearer {ic3}"}, timeout=15)
    r.raise_for_status()
    out = []
    for m in r.json().get("messages", []):
        if m.get("messagetype") != "RichText/Html":
            continue
        content = re.sub(r"<[^>]+>", "", m.get("content", "")).strip()
        out.append({"time": m.get("originalarrivaltime", ""), "from": m.get("imdisplayname", "?"), "text": content})
    return out


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__.strip(), file=sys.stderr); sys.exit(1)
    cmd, email = sys.argv[1], sys.argv[2]
    try:
        if cmd == "send":
            if len(sys.argv) < 4:
                print("Usage: teams_chat.py send <email> <message ...>", file=sys.stderr); sys.exit(1)
            data = send(email, " ".join(sys.argv[3:]))
            print(f"OK — gesendet an {email} (id={data.get('id', '?')})")
        elif cmd == "read":
            limit = int(sys.argv[sys.argv.index('--limit') + 1]) if '--limit' in sys.argv else 20
            for m in read(email, limit):
                print(f"[{m['time']}] {m['from']}: {m['text']}")
        else:
            print(__doc__.strip(), file=sys.stderr); sys.exit(1)
    except Exception as exc:
        print(f"FEHLER: {exc}", file=sys.stderr); sys.exit(1)


if __name__ == "__main__":
    main()
