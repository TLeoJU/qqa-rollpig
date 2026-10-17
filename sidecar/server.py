"""RollPig headless NoneBot sidecar for QQ Agent.

The original plugin is a NoneBot 2 / OneBot v11 plugin.  This process loads it
unchanged, feeds it OneBot v11 events received from the QQ Agent plugin, and
turns every outbound OneBot API call into an item in an HTTP outbox.  The QQ
Agent plugin polls the outbox and performs the actual send through QQ Agent's
own SendQueue, so rate limiting / serialisation / logging stay intact.

Only localhost is exposed; there is no authentication because the port is
bound to 127.0.0.1.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import os
import re
import time
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any

SERVICE_DIR = Path(__file__).resolve().parent
os.environ.setdefault("ROLLPIG_CONFIG_FILE", str(SERVICE_DIR / "rollpig_config.json"))
os.environ.setdefault("TZ", "Asia/Shanghai")

import nonebot  # noqa: E402
from aiohttp import web  # noqa: E402
from nonebot.adapters.onebot.v11 import (  # noqa: E402
    Adapter,
    Bot,
    Message,
    MessageSegment,
)
from nonebot.adapters.onebot.v11.event import (  # noqa: E402
    GroupMessageEvent,
    PrivateMessageEvent,
    Reply,
    Sender,
)
from nonebot.log import logger  # noqa: E402
from nonebot.message import handle_event  # noqa: E402

# Host media directory.  Files are written here; the value below is what the
# QQA process must be able to read.
#
#   Docker / two containers : QQA_MEDIA_URL_PREFIX=/media
#   Native (same host)       : QQA_MEDIA_URL_PREFIX=<absolute media dir>
#
# The old hard-coded /media only worked when the host media directory was
# bind-mounted into the qq-agent and snowluma containers at /media.
MEDIA_BASE = Path(os.environ.get(
    "QQA_MEDIA_DIR",
    str(Path(os.environ.get("QQA_HOME", "/opt/qq-agent")) / "media"),
)).expanduser()
MEDIA_URL_PREFIX = os.environ.get("QQA_MEDIA_URL_PREFIX", "/media").rstrip("/")
MEDIA_ROOT = MEDIA_BASE / "rollpig"
OUTBOX_MEDIA = MEDIA_ROOT / "outbox"
OUTBOX_MEDIA.mkdir(parents=True, exist_ok=True)

PORT = int(os.environ.get("ROLLPIG_PORT", "18765"))
MAX_OUTBOX = 800
OUTBOX_KEEP_SECONDS = 900

CQ_RE = re.compile(r"\[CQ:([a-zA-Z0-9_]+)((?:,[^\]]*)?)\]")


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, bytes):
        return {"__bytes__": base64.b64encode(value).decode("ascii")}
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    return str(value)


def _segments(message: Any) -> list[dict[str, Any]]:
    if message is None:
        return []
    if isinstance(message, str):
        return [{"type": "text", "data": {"text": message}}]
    if isinstance(message, MessageSegment):
        return [{"type": message.type, "data": _jsonable(message.data)}]
    if isinstance(message, Message):
        return [{"type": seg.type, "data": _jsonable(seg.data)} for seg in message]
    if isinstance(message, dict):
        if "type" in message:
            return [{"type": str(message.get("type")), "data": _jsonable(message.get("data") or {})}]
        return []
    if isinstance(message, (list, tuple)):
        out: list[dict[str, Any]] = []
        for item in message:
            out.extend(_segments(item))
        return out
    return [{"type": "text", "data": {"text": str(message)}}]


def _parse_cq(text: str) -> list[dict[str, Any]]:
    """Best-effort CQ string parser used only when get_msg returns a string."""
    out: list[dict[str, Any]] = []
    pos = 0
    for match in CQ_RE.finditer(text):
        if match.start() > pos:
            out.append({"type": "text", "data": {"text": text[pos:match.start()]}})
        seg_type = match.group(1)
        data: dict[str, Any] = {}
        raw = match.group(2).lstrip(",")
        if raw:
            for pair in raw.split(","):
                if "=" not in pair:
                    continue
                key, value = pair.split("=", 1)
                data[key] = value.replace("&#44;", ",").replace("&#91;", "[").replace("&#93;", "]")
        out.append({"type": seg_type, "data": data})
        pos = match.end()
    if pos < len(text):
        out.append({"type": "text", "data": {"text": text[pos:]}})
    return out or [{"type": "text", "data": {"text": text}}]


def _media_url(path: str) -> str:
    """Map a host path under MEDIA_BASE to the path QQA should send.

    Docker mode returns /media/... (the bind mount inside qq-agent).
    Native mode returns the absolute host path (QQA can read it directly).
    """
    try:
        rel = Path(path).expanduser().resolve().relative_to(MEDIA_BASE.resolve())
    except (ValueError, OSError):
        return path
    # Windows 下 Path 用反斜杠；QQA 的 toFileUri 能处理，但 OneBot 的
    # sendMedia 不会转换，所以统一成 /，避免 C:\... 和 C:/... 混用。
    prefix = MEDIA_URL_PREFIX.replace("\\", "/").rstrip("/")
    return f"{prefix}/{rel.as_posix()}"


def _materialize_image(file_ref: Any) -> Any:
    """Turn base64 image data into a file QQA can read.

    In Docker the media directory is shared with the qq-agent container at
    /media; in a native install the absolute path is used instead.  Both are
    selected with QQA_MEDIA_URL_PREFIX, so this is not tied to Docker.
    """
    if not isinstance(file_ref, str):
        return file_ref
    raw = file_ref.strip()
    payload: bytes | None = None
    if raw.startswith("base64://"):
        try:
            payload = base64.b64decode(raw[len("base64://"):], validate=False)
        except (binascii.Error, ValueError):
            return file_ref
    elif raw.startswith("data:image/") and ";base64," in raw:
        try:
            payload = base64.b64decode(raw.split(";base64,", 1)[1], validate=False)
        except (binascii.Error, ValueError):
            return file_ref
    if payload is None:
        if raw.startswith("file://"):
            return _media_url(raw[len("file://"):])
        return _media_url(raw)

    name = f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:10]}.png"
    target = OUTBOX_MEDIA / name
    target.write_bytes(payload)
    return _media_url(str(target))


def _normalize_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for seg in segments:
        seg_type = str(seg.get("type") or "")
        data = dict(seg.get("data") or {})
        if seg_type == "image" and "file" in data:
            data["file"] = _materialize_image(data["file"])
        out.append({"type": seg_type, "data": data})
    return out


def _serialize_forward_nodes(nodes: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for node in nodes if isinstance(nodes, (list, tuple)) else []:
        if isinstance(node, dict) and "type" in node:
            data = dict(node.get("data") or {})
        elif isinstance(node, MessageSegment):
            data = dict(node.data)
            node = {"type": node.type, "data": data}
        else:
            continue
        content = data.get("content")
        if content is not None:
            data["content"] = _normalize_segments(_segments(content))
        result.append({"type": str(node.get("type") or "node"), "data": data})
    return result


class State:
    def __init__(self) -> None:
        self.bot: FakeBot | None = None
        self.self_id = "0"
        self.groups: list[dict[str, Any]] = []
        self.members: dict[str, list[dict[str, Any]]] = {}
        self.outbox: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
        self.fake_to_item: dict[str, str] = {}
        self.real_to_fake: dict[str, str] = {}
        self.counter = 0
        self.lock = asyncio.Lock()

    def next_id(self) -> int:
        self.counter += 1
        return self.counter

    def enqueue(self, api: str, params: dict[str, Any]) -> dict[str, Any]:
        n = self.next_id()
        item_id = f"o-{n}"
        fake_id = f"rp-{n}"
        item = {
            "id": item_id,
            "api": api,
            "params": _jsonable(params),
            "fake_message_id": fake_id,
            "ts": time.time(),
        }
        self.outbox[item_id] = item
        self.fake_to_item[fake_id] = item_id
        while len(self.outbox) > MAX_OUTBOX:
            old_id, _ = self.outbox.popitem(last=False)
            self.fake_to_item.pop(f"rp-{old_id.split('-')[-1]}", None)
        return item

    def ack(self, item_id: str, real_message_id: Any) -> None:
        item = self.outbox.get(item_id)
        if item is None:
            return
        item["acked_at"] = time.time()
        item["real_message_id"] = str(real_message_id) if real_message_id is not None else None
        if real_message_id is not None:
            self.real_to_fake[str(real_message_id)] = item["fake_message_id"]

    def pending(self) -> list[dict[str, Any]]:
        now = time.time()
        for item_id, item in list(self.outbox.items()):
            acked = item.get("acked_at")
            if acked and now - acked > OUTBOX_KEEP_SECONDS:
                self.outbox.pop(item_id, None)
        return [item for item in self.outbox.values() if not item.get("acked_at")]


state = State()


class FakeBot(Bot):
    """A Bot that never touches the network; it records API calls."""

    def __init__(self, adapter: Adapter, self_id: str) -> None:
        super().__init__(adapter, self_id)
        self._login_nickname = "RollPig"

    async def call_api(self, api: str, **data: Any) -> Any:  # type: ignore[override]
        if api == "send_msg":
            if data.get("message_type") == "group" or data.get("group_id") is not None:
                api = "send_group_msg"
            else:
                api = "send_private_msg"
        if api in {"send_group_msg", "send_private_msg", "send_group_forward_msg", "set_msg_emoji_like"}:
            params = dict(data)
            if api in {"send_group_msg", "send_private_msg"}:
                params["message"] = _normalize_segments(_segments(params.get("message")))
            elif api == "send_group_forward_msg":
                params["messages"] = _serialize_forward_nodes(params.get("messages"))
            item = state.enqueue(api, params)
            return {"message_id": item["fake_message_id"], "message_id_str": item["fake_message_id"]}

        if api == "get_login_info":
            return {"user_id": _as_int(state.self_id), "nickname": self._login_nickname}
        if api == "get_group_list":
            return state.groups
        if api == "get_group_member_list":
            group_id = str(data.get("group_id") or "")
            return state.members.get(group_id, [])
        if api == "get_group_member_info":
            group_id = str(data.get("group_id") or "")
            user_id = str(data.get("user_id") or "")
            for member in state.members.get(group_id, []):
                if str(member.get("user_id")) == user_id:
                    return member
            if user_id == str(state.self_id):
                return {
                    "group_id": _as_int(group_id),
                    "user_id": _as_int(user_id),
                    "nickname": self._login_nickname,
                    "card": "",
                    "role": "member",
                }
            return {"group_id": _as_int(group_id), "user_id": _as_int(user_id), "nickname": "", "card": "", "role": "member"}
        if api == "get_status":
            return {"online": True, "good": True}
        if api == "get_version_info":
            return {"app_name": "nonebot", "app_version": "2.5.0", "protocol_version": "v11"}
        if api.startswith(("get_", "can_", "check_")):
            return {}
        # Unknown write API: let the QQ Agent plugin pass it through.
        item = state.enqueue("call_api", {"api": api, "params": dict(data)})
        return {"message_id": item["fake_message_id"]}


def _build_message(payload: dict[str, Any]) -> Message:
    raw_message = payload.get("message")
    if isinstance(raw_message, str):
        segs = _parse_cq(raw_message)
    elif isinstance(raw_message, list):
        segs = raw_message
    else:
        segs = []
    if not segs:
        text = str(payload.get("text") or "")
        segs = [{"type": "text", "data": {"text": text}}] if text else []

    reply_info = payload.get("reply") if isinstance(payload.get("reply"), dict) else None
    reply_id = None
    if reply_info and reply_info.get("message_id") is not None:
        real_id = str(reply_info.get("message_id"))
        reply_id = state.real_to_fake.get(real_id, real_id)

    result: list[MessageSegment] = []
    seen_reply = False
    for seg in segs:
        if not isinstance(seg, dict):
            continue
        seg_type = str(seg.get("type") or "")
        data = dict(seg.get("data") or {})
        if seg_type == "reply":
            rid = str(data.get("id") or "")
            data["id"] = state.real_to_fake.get(rid, rid)
            seen_reply = True
        elif seg_type == "at":
            data["qq"] = str(data.get("qq") or "")
        result.append(MessageSegment(type=seg_type, data=data))
    if reply_id and not seen_reply:
        result.insert(0, MessageSegment(type="reply", data={"id": reply_id}))
    return Message(result)


def _sender(payload: dict[str, Any]) -> Sender:
    sender = payload.get("sender") if isinstance(payload.get("sender"), dict) else {}
    role = str(sender.get("role") or "member")
    if role not in {"owner", "admin", "member"}:
        role = "member"
    return Sender(
        user_id=_as_int(payload.get("user_id")),
        nickname=str(sender.get("nickname") or ""),
        card=str(sender.get("card") or ""),
        role=role,
    )


def _build_reply(payload: dict[str, Any]) -> Reply | None:
    info = payload.get("reply")
    if not isinstance(info, dict) or info.get("message_id") is None:
        return None
    real_id = str(info.get("message_id"))
    fake_id = state.real_to_fake.get(real_id, real_id)
    sender_id = _as_int(info.get("sender_id"))
    if not sender_id and payload.get("reply_to_self"):
        sender_id = _as_int(payload.get("self_id"))
    return Reply(
        time=_as_int(payload.get("time"), int(time.time())),
        message_type="group" if payload.get("kind") == "group" else "private",
        message_id=_as_int(fake_id),
        real_id=_as_int(fake_id),
        sender=Sender(user_id=sender_id, nickname="", card="", role="member"),
        message=Message(),
    )


def _build_event(payload: dict[str, Any]) -> GroupMessageEvent | PrivateMessageEvent:
    kind = str(payload.get("kind") or "group")
    self_id = _as_int(payload.get("self_id"))
    user_id = _as_int(payload.get("user_id"))
    message_id = _as_int(payload.get("message_id"))
    message = _build_message(payload)
    reply = _build_reply(payload)
    sender = _sender(payload)
    text = str(payload.get("text") or "")
    to_me = bool(payload.get("at_me") or payload.get("reply_to_self") or kind == "private")

    if kind == "private":
        return PrivateMessageEvent(
            time=_as_int(payload.get("time"), int(time.time())),
            self_id=self_id,
            post_type="message",
            sub_type="friend",
            user_id=user_id,
            message_type="private",
            message_id=message_id,
            message=message,
            original_message=message,
            raw_message=text,
            font=0,
            sender=sender,
            to_me=to_me,
        )
    return GroupMessageEvent(
        time=_as_int(payload.get("time"), int(time.time())),
        self_id=self_id,
        post_type="message",
        sub_type="normal",
        user_id=user_id,
        message_type="group",
        message_id=message_id,
        message=message,
        original_message=message,
        raw_message=text,
        font=0,
        sender=sender,
        to_me=to_me,
        reply=reply,
        group_id=_as_int(payload.get("group_id")),
    )


def _update_caches(payload: dict[str, Any]) -> None:
    self_id = str(payload.get("self_id") or "")
    if self_id and self_id != "0":
        state.self_id = self_id
        if state.bot is not None:
            state.bot.self_id = self_id
    kind = str(payload.get("kind") or "")
    if kind == "group":
        group_id = str(payload.get("group_id") or "")
        if group_id:
            if not any(str(g.get("group_id")) == group_id for g in state.groups):
                state.groups.append({"group_id": _as_int(group_id), "group_name": ""})
            members = payload.get("members")
            if isinstance(members, list) and members:
                state.members[group_id] = [m for m in members if isinstance(m, dict)]


async def event_handler(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid json"}, status=400)
    if not isinstance(payload, dict):
        return web.json_response({"ok": False, "error": "payload must be object"}, status=400)

    _update_caches(payload)
    if state.bot is None:
        return web.json_response({"ok": False, "error": "bot not ready"}, status=503)

    try:
        event = _build_event(payload)
    except Exception as error:
        logger.exception(f"[rollpig-sidecar] build event failed: {error}")
        return web.json_response({"ok": False, "error": str(error)}, status=400)

    try:
        async with state.lock:
            await handle_event(state.bot, event)
    except Exception as error:
        logger.exception(f"[rollpig-sidecar] handle_event failed: {error}")
        return web.json_response({"ok": False, "error": str(error)}, status=500)
    return web.json_response({"ok": True, "pending": len(state.pending())})


async def outbox_handler(request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "items": state.pending()})


async def ack_handler(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid json"}, status=400)
    item_id = str(payload.get("id") or "")
    if not item_id:
        return web.json_response({"ok": False, "error": "missing id"}, status=400)
    state.ack(item_id, payload.get("message_id"))
    return web.json_response({"ok": True})


async def groups_handler(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid json"}, status=400)
    groups = payload.get("groups")
    if isinstance(groups, list):
        state.groups = [g for g in groups if isinstance(g, dict) and g.get("group_id") is not None]
    return web.json_response({"ok": True, "count": len(state.groups)})


async def config_handler(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid json"}, status=400)
    self_id = str(payload.get("self_id") or "")
    if self_id and self_id != "0":
        state.self_id = self_id
        if state.bot is not None:
            state.bot.self_id = self_id
    superusers = payload.get("superusers")
    if isinstance(superusers, list):
        driver = nonebot.get_driver()
        driver.config.superusers = {str(x) for x in superusers if str(x).strip()}
    return web.json_response({"ok": True, "self_id": state.self_id})


async def health_handler(request: web.Request) -> web.Response:
    return web.json_response({
        "ok": True,
        "self_id": state.self_id,
        "groups": len(state.groups),
        "members": {k: len(v) for k, v in state.members.items()},
        "outbox": len(state.outbox),
        "pending": len(state.pending()),
        "uptime": time.time() - STARTED_AT,
    })


STARTED_AT = time.time()


def _load_superusers() -> set[str]:
    raw = os.environ.get("ROLLPIG_SUPERUSERS", "")
    return {item.strip() for item in raw.split(",") if item.strip()}


async def main() -> None:
    nonebot.init(
        command_start={"", "/"},
        command_sep={"."},
        superusers=_load_superusers(),
        log_level="INFO",
    )
    driver = nonebot.get_driver()
    driver.register_adapter(Adapter)
    adapter = nonebot.get_adapter(Adapter)

    bot = FakeBot(adapter, state.self_id)
    state.bot = bot
    driver._bots[bot.self_id] = bot

    plugin = nonebot.load_plugin("nonebot_plugin_rollpig_plus")
    if plugin is None:
        raise RuntimeError("failed to load nonebot_plugin_rollpig_plus")
    logger.info("[rollpig-sidecar] plugin loaded")

    from nonebot_plugin_apscheduler import scheduler
    if not scheduler.running:
        scheduler.start()
    logger.info("[rollpig-sidecar] scheduler started")

    # The normal NoneBot driver startup hooks never run in this headless setup.
    # Call the plugin's startup hooks explicitly (they only schedule background
    # work, so awaiting them is cheap).
    try:
        from nonebot_plugin_rollpig_plus import jobs as rollpig_jobs
        for name in (
            "startup_data_maintenance",
            "startup_pighub_refresh",
            "startup_resource_sync",
            "startup_protection_recovery",
            "startup_daily_report_recovery",
        ):
            hook = getattr(rollpig_jobs, name, None)
            if hook is None:
                continue
            try:
                result = hook()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as error:
                logger.warning(f"[rollpig-sidecar] startup hook {name} failed: {error}")
    except Exception as error:
        logger.warning(f"[rollpig-sidecar] startup hooks unavailable: {error}")

    app = web.Application(client_max_size=32 * 1024 * 1024)
    app.router.add_post("/event", event_handler)
    app.router.add_get("/outbox", outbox_handler)
    app.router.add_post("/ack", ack_handler)
    app.router.add_post("/groups", groups_handler)
    app.router.add_post("/config", config_handler)
    app.router.add_get("/health", health_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", PORT)
    await site.start()
    logger.info(f"[rollpig-sidecar] listening on http://127.0.0.1:{PORT}")

    stop = asyncio.Event()

    async def _shutdown() -> None:
        stop.set()

    try:
        import signal
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(_shutdown()))
            except NotImplementedError:
                pass
    except Exception:
        pass

    await stop.wait()
    logger.info("[rollpig-sidecar] shutting down")
    try:
        scheduler.shutdown(wait=False)
    except Exception:
        pass
    await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
