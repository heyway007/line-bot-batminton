"""
LINE Bot - ลงชื่อตีแบด (linebot v3)
requirements.txt:
  flask
  linebot[v3]
"""

import os
import re
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    ReplyMessageRequest, TextMessage
)
from linebot.v3.webhooks import (
    MessageEvent, TextMessageContent, JoinEvent
)

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")
ADMIN_USER_IDS = os.environ.get("ADMIN_USER_IDS", "").split(",")
MAX_PLAYERS = int(os.environ.get("MAX_PLAYERS", 20))

configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# { "group_id": [{"name": "สมชาย", "slots": 1}, ...] }
signup_lists = {}


def get_list(gid):
    return signup_lists.get(gid, [])


def format_list(gid):
    players = get_list(gid)
    if not players:
        return "📋 ยังไม่มีรายชื่อ\nพิมพ์ +ชื่อ เพื่อลงชื่อ"
    lines = ["🏸 รายชื่อตีแบด\n" + "─" * 20]
    num = 1
    for p in players:
        for i in range(p["slots"]):
            if i == 0:
                lines.append(f"{num}. {p['name']}")
            else:
                lines.append(f"{num}. {p['name']} (+{i})")
            num += 1
    total = sum(p["slots"] for p in players)
    lines.append("─" * 20)
    lines.append(f"รวม: {total}/{MAX_PLAYERS} คน")
    if total >= MAX_PLAYERS:
        lines.append("⚠️ เต็มแล้ว!")
    return "\n".join(lines)


def get_summary(gid):
    players = get_list(gid)
    total = sum(p["slots"] for p in players)
    return f"รวม {total}/{MAX_PLAYERS} คน"


def get_player_num(gid, name):
    num = 1
    for p in get_list(gid):
        if p["name"] == name:
            return num
        num += p["slots"]
    return None


def add_player(gid, name, slots=1):
    if gid not in signup_lists:
        signup_lists[gid] = []
    players = signup_lists[gid]
    total = sum(p["slots"] for p in players)
    for p in players:
        if p["name"] == name:
            return f"⚠️ '{name}' ลงชื่อไปแล้ว (ลำดับที่ {get_player_num(gid, name)})"
    if total + slots > MAX_PLAYERS:
        remaining = MAX_PLAYERS - total
        if remaining <= 0:
            return f"❌ เต็มแล้ว! ({MAX_PLAYERS}/{MAX_PLAYERS} คน)"
        return f"❌ รับได้อีกแค่ {remaining} คน (ขอ {slots} คน)"
    players.append({"name": name, "slots": slots})
    num = get_player_num(gid, name)
    if slots == 1:
        return f"✅ เพิ่ม '{name}' ลำดับที่ {num}\n{get_summary(gid)}"
    else:
        return f"✅ เพิ่ม '{name}' ({slots} คน) ลำดับที่ {num}-{num+slots-1}\n{get_summary(gid)}"


def remove_player(gid, name):
    if gid not in signup_lists:
        return "❌ ยังไม่มีรายชื่อ"
    players = signup_lists[gid]
    for i, p in enumerate(players):
        if p["name"] == name:
            players.pop(i)
            return f"🗑️ ลบ '{name}' ออกแล้ว\n{get_summary(gid)}"
    return f"❌ ไม่พบชื่อ '{name}' ในรายชื่อ"


def clear_list(gid):
    signup_lists[gid] = []
    return "🗑️ ล้างรายชื่อทั้งหมดแล้ว"


def help_message():
    return (
        "🏸 คำสั่งลงชื่อตีแบด\n\n"
        "+ชื่อ → ลงชื่อ\n"
        "   เช่น: +สมชาย\n\n"
        "+ชื่อ 2 → ลงชื่อพร้อมเพื่อน\n"
        "   เช่น: +สมชาย 2\n\n"
        "-ชื่อ → ลบชื่อออก\n"
        "   เช่น: -สมชาย\n\n"
        "!รายชื่อ → ดูรายชื่อทั้งหมด\n"
        "!เคลียร์ → ล้างรายชื่อ (Admin)\n"
        "!ช่วยเหลือ → ดูคำสั่ง"
    )


def process_message(gid, text, user_id):
    text = text.strip()

    if text in ["!รายชื่อ", "!list"]:
        return format_list(gid)
    if text in ["!เคลียร์", "!clear", "!ล้าง"]:
        if not ADMIN_USER_IDS[0] or user_id in ADMIN_USER_IDS:
            return clear_list(gid)
        return "❌ เฉพาะ Admin เท่านั้น"
    if text in ["!ช่วยเหลือ", "!help", "!คำสั่ง"]:
        return help_message()

    add_match = re.match(r"^\+(.+?)(?:\s+(\d+))?$", text)
    if add_match:
        name = add_match.group(1).strip()
        slots = int(add_match.group(2)) if add_match.group(2) else 1
        slots = min(slots, 10)
        return add_player(gid, name, slots)

    remove_match = re.match(r"^-(.+)$", text)
    if remove_match:
        name = remove_match.group(1).strip()
        return remove_player(gid, name)

    return None


def reply(reply_token, text):
    with ApiClient(configuration) as api_client:
        api = MessagingApi(api_client)
        api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=text)]
            )
        )


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    src = event.source
    if src.type == "group":
        gid = src.group_id
    elif src.type == "room":
        gid = src.room_id
    else:
        gid = src.user_id

    user_id = src.user_id
    text = event.message.text
    response = process_message(gid, text, user_id)
    if response:
        reply(event.reply_token, response)


@handler.add(JoinEvent)
def handle_join(event):
    reply(event.reply_token, "🏸 สวัสดีครับ! บอทลงชื่อตีแบดพร้อมแล้ว\n\nพิมพ์ !ช่วยเหลือ เพื่อดูคำสั่งทั้งหมด")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
