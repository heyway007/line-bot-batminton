"""
LINE Bot - ลงชื่อตีแบด v2
requirements.txt:
  flask
  line-bot-sdk>=3.0.0

คำสั่งทั้งหมด:
--- สร้างเซสชัน ---
!สร้าง              → เริ่มสร้างเซสชันใหม่ (step by step)

--- ลงชื่อ ---
+ชื่อ               → ลงชื่อ
+ชื่อ 2             → ลงชื่อพร้อมเพื่อน
-ชื่อ               → ลบชื่อออก

--- ดูข้อมูล ---
!รายชื่อ            → ดูรายชื่อ + ข้อมูลเซสชัน
!เซสชัน             → ดูข้อมูลเซสชันปัจจุบัน
!เคลียร์            → ล้างรายชื่อ (Admin)
!ยกเลิกเซสชัน       → ลบเซสชัน (Admin)

--- Admin จัดการสถานที่ ---
!เพิ่มสถานที่ ชื่อ   → เพิ่มสถานที่
!ลบสถานที่ ชื่อ     → ลบสถานที่
!สถานที่             → ดูสถานที่ทั้งหมด
"""

import os
import re
from datetime import datetime
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
ADMIN_USER_IDS = [x for x in os.environ.get("ADMIN_USER_IDS", "").split(",") if x]
MAX_PLAYERS = int(os.environ.get("MAX_PLAYERS", 20))

configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# ข้อมูลแต่ละกลุ่ม
# group_data[gid] = {
#   "venues": ["สนาม A", "สนาม B"],
#   "session": { "venue": "", "date": "", "time": "", "courts": 1 } or None,
#   "players": [{"name": "", "slots": 1}],
#   "pending": { "step": "venue"|"date"|"time"|"courts", "data": {} } or None
# }
group_data = {}

DEFAULT_VENUES = ["สนามกีฬาในร่ม", "สนาม A", "สนาม B"]


def get_gd(gid):
    if gid not in group_data:
        group_data[gid] = {
            "venues": list(DEFAULT_VENUES),
            "session": None,
            "players": [],
            "pending": None
        }
    return group_data[gid]


def is_admin(user_id):
    return not ADMIN_USER_IDS or user_id in ADMIN_USER_IDS


def reply_msg(reply_token, text):
    with ApiClient(configuration) as api_client:
        api = MessagingApi(api_client)
        api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=text)]
            )
        )


# ─── Session ────────────────────────────────────────────

def format_session(gid):
    gd = get_gd(gid)
    s = gd["session"]
    if not s:
        return "❌ ยังไม่มีเซสชัน\nพิมพ์ !สร้าง เพื่อสร้างเซสชันใหม่"
    courts_str = f"{s['courts']} สนาม"
    return (
        f"📍 สถานที่: {s['venue']}\n"
        f"📅 วันที่: {s['date']}\n"
        f"⏰ เวลา: {s['time']}\n"
        f"🏸 จำนวนสนาม: {courts_str}\n"
        f"👥 รับได้: {s['courts'] * 4} คน"
    )


def start_create_session(gid):
    gd = get_gd(gid)
    venues = gd["venues"]
    if not venues:
        return "❌ ยังไม่มีสถานที่ กรุณา Admin เพิ่มสถานที่ก่อนด้วย !เพิ่มสถานที่ ชื่อ"

    gd["pending"] = {"step": "venue", "data": {}}
    lines = ["🏸 สร้างเซสชันใหม่\n\nเลือกสถานที่ (พิมพ์ตัวเลข):"]
    for i, v in enumerate(venues, 1):
        lines.append(f"{i}. {v}")
    return "\n".join(lines)


def handle_pending(gid, text, user_id):
    gd = get_gd(gid)
    pending = gd["pending"]
    if not pending:
        return None

    step = pending["step"]
    data = pending["data"]

    if step == "venue":
        venues = gd["venues"]
        if text.isdigit() and 1 <= int(text) <= len(venues):
            data["venue"] = venues[int(text) - 1]
            pending["step"] = "date"
            return f"✅ สถานที่: {data['venue']}\n\nกรอกวันที่ (เช่น 28/05/2568 หรือ พรุ่งนี้)"
        else:
            lines = ["❌ กรุณาพิมพ์ตัวเลขให้ถูกต้อง\n\nเลือกสถานที่:"]
            for i, v in enumerate(venues, 1):
                lines.append(f"{i}. {v}")
            return "\n".join(lines)

    elif step == "date":
        data["date"] = text
        pending["step"] = "time"
        return f"✅ วันที่: {data['date']}\n\nกรอกเวลา (เช่น 18:00 หรือ 6 โมงเย็น)"

    elif step == "time":
        data["time"] = text
        pending["step"] = "courts"
        return f"✅ เวลา: {data['time']}\n\nกรอกจำนวนสนาม (เช่น 2)"

    elif step == "courts":
        if text.isdigit() and int(text) >= 1:
            data["courts"] = int(text)
            # สร้างเซสชัน
            gd["session"] = {
                "venue": data["venue"],
                "date": data["date"],
                "time": data["time"],
                "courts": data["courts"]
            }
            gd["players"] = []
            gd["pending"] = None
            max_p = data["courts"] * 4
            return (
                f"✅ สร้างเซสชันสำเร็จ!\n\n"
                f"{format_session(gid)}\n\n"
                f"รับสมัคร {max_p} คน\nพิมพ์ +ชื่อ เพื่อลงชื่อได้เลยครับ 🏸"
            )
        else:
            return "❌ กรุณากรอกจำนวนสนามเป็นตัวเลข (เช่น 2)"

    return None


# ─── Players ────────────────────────────────────────────

def get_max(gid):
    gd = get_gd(gid)
    if gd["session"]:
        return gd["session"]["courts"] * 4
    return MAX_PLAYERS


def get_total(gid):
    return sum(p["slots"] for p in get_gd(gid)["players"])


def get_player_num(gid, name):
    num = 1
    for p in get_gd(gid)["players"]:
        if p["name"] == name:
            return num
        num += p["slots"]
    return None


def format_list(gid):
    gd = get_gd(gid)
    players = gd["players"]
    max_p = get_max(gid)
    total = get_total(gid)

    lines = []
    # แสดง session ถ้ามี
    if gd["session"]:
        s = gd["session"]
        lines.append(f"🏸 ตีแบด | {s['date']} {s['time']}")
        lines.append(f"📍 {s['venue']} | {s['courts']} สนาม")
    else:
        lines.append("🏸 รายชื่อตีแบด")
    lines.append("─" * 22)

    if not players:
        lines.append("ยังไม่มีรายชื่อ")
    else:
        num = 1
        for p in players:
            for i in range(p["slots"]):
                if i == 0:
                    lines.append(f"{num}. {p['name']}")
                else:
                    lines.append(f"{num}. {p['name']} (+{i})")
                num += 1

    lines.append("─" * 22)
    lines.append(f"รวม: {total}/{max_p} คน")
    if total >= max_p:
        lines.append("⚠️ เต็มแล้ว!")
    return "\n".join(lines)


def add_player(gid, name, slots=1):
    gd = get_gd(gid)
    players = gd["players"]
    max_p = get_max(gid)
    total = get_total(gid)

    for p in players:
        if p["name"] == name:
            return f"⚠️ '{name}' ลงชื่อไปแล้ว (ลำดับที่ {get_player_num(gid, name)})"

    if total + slots > max_p:
        remaining = max_p - total
        if remaining <= 0:
            return f"❌ เต็มแล้ว! ({max_p}/{max_p} คน)"
        return f"❌ รับได้อีกแค่ {remaining} คน (ขอ {slots} คน)"

    players.append({"name": name, "slots": slots})
    num = get_player_num(gid, name)
    total_new = get_total(gid)
    if slots == 1:
        return f"✅ '{name}' ลำดับที่ {num} | รวม {total_new}/{max_p} คน"
    else:
        return f"✅ '{name}' ({slots} คน) ลำดับที่ {num}-{num+slots-1} | รวม {total_new}/{max_p} คน"


def remove_player(gid, name):
    gd = get_gd(gid)
    players = gd["players"]
    for i, p in enumerate(players):
        if p["name"] == name:
            players.pop(i)
            total = get_total(gid)
            max_p = get_max(gid)
            return f"🗑️ ลบ '{name}' ออกแล้ว | รวม {total}/{max_p} คน"
    return f"❌ ไม่พบชื่อ '{name}' ในรายชื่อ"


# ─── Venues ─────────────────────────────────────────────

def list_venues(gid):
    venues = get_gd(gid)["venues"]
    if not venues:
        return "❌ ยังไม่มีสถานที่\nAdmin เพิ่มได้ด้วย !เพิ่มสถานที่ ชื่อ"
    lines = ["📍 สถานที่ทั้งหมด:"]
    for i, v in enumerate(venues, 1):
        lines.append(f"{i}. {v}")
    return "\n".join(lines)


def add_venue(gid, name, user_id):
    if not is_admin(user_id):
        return "❌ เฉพาะ Admin เท่านั้น"
    venues = get_gd(gid)["venues"]
    if name in venues:
        return f"⚠️ '{name}' มีอยู่แล้ว"
    venues.append(name)
    return f"✅ เพิ่มสถานที่ '{name}' แล้ว\n\n{list_venues(gid)}"


def del_venue(gid, name, user_id):
    if not is_admin(user_id):
        return "❌ เฉพาะ Admin เท่านั้น"
    venues = get_gd(gid)["venues"]
    if name not in venues:
        return f"❌ ไม่พบสถานที่ '{name}'"
    venues.remove(name)
    return f"✅ ลบสถานที่ '{name}' แล้ว\n\n{list_venues(gid)}"


# ─── Help ────────────────────────────────────────────────

def help_message():
    return (
        "🏸 คำสั่งลงชื่อตีแบด\n\n"
        "── สร้างเซสชัน ──\n"
        "!สร้าง → สร้างเซสชันใหม่\n\n"
        "── ลงชื่อ ──\n"
        "+ชื่อ → ลงชื่อ\n"
        "+ชื่อ 2 → ลงชื่อพร้อมเพื่อน\n"
        "-ชื่อ → ลบชื่อออก\n\n"
        "── ดูข้อมูล ──\n"
        "!รายชื่อ → ดูรายชื่อทั้งหมด\n"
        "!เซสชัน → ดูข้อมูลเซสชัน\n"
        "!สถานที่ → ดูสถานที่ทั้งหมด\n\n"
        "── Admin ──\n"
        "!เคลียร์ → ล้างรายชื่อ\n"
        "!ยกเลิกเซสชัน → ยกเลิกเซสชัน\n"
        "!เพิ่มสถานที่ ชื่อ → เพิ่มสถานที่\n"
        "!ลบสถานที่ ชื่อ → ลบสถานที่"
    )


# ─── Process ─────────────────────────────────────────────

def process_message(gid, text, user_id):
    text = text.strip()
    gd = get_gd(gid)

    # ถ้ากำลังรอ input สร้างเซสชัน
    if gd["pending"]:
        # ยกเว้นคำสั่งอื่นๆ
        if not text.startswith("!") and not text.startswith("+") and not text.startswith("-"):
            return handle_pending(gid, text, user_id)

    # คำสั่ง
    if text in ["!รายชื่อ", "!list"]:
        return format_list(gid)

    if text in ["!เซสชัน", "!session"]:
        return format_session(gid)

    if text in ["!สถานที่", "!venue"]:
        return list_venues(gid)

    if text in ["!สร้าง", "!create"]:
        return start_create_session(gid)

    if text in ["!เคลียร์", "!clear"]:
        if not is_admin(user_id):
            return "❌ เฉพาะ Admin เท่านั้น"
        gd["players"] = []
        return "🗑️ ล้างรายชื่อทั้งหมดแล้ว"

    if text in ["!ยกเลิกเซสชัน", "!cancelsession"]:
        if not is_admin(user_id):
            return "❌ เฉพาะ Admin เท่านั้น"
        gd["session"] = None
        gd["players"] = []
        gd["pending"] = None
        return "🗑️ ยกเลิกเซสชันแล้ว"

    if text in ["!ช่วยเหลือ", "!help"]:
        return help_message()

    # !เพิ่มสถานที่
    m = re.match(r"^!เพิ่มสถานที่\s+(.+)$", text)
    if m:
        return add_venue(gid, m.group(1).strip(), user_id)

    # !ลบสถานที่
    m = re.match(r"^!ลบสถานที่\s+(.+)$", text)
    if m:
        return del_venue(gid, m.group(1).strip(), user_id)

    # +ชื่อ
    m = re.match(r"^\+(.+?)(?:\s+(\d+))?$", text)
    if m:
        name = m.group(1).strip()
        slots = int(m.group(2)) if m.group(2) else 1
        slots = min(slots, 10)
        return add_player(gid, name, slots)

    # -ชื่อ
    m = re.match(r"^-(.+)$", text)
    if m:
        return remove_player(gid, m.group(1).strip())

    return None


# ─── Flask ───────────────────────────────────────────────

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
        reply_msg(event.reply_token, response)


@handler.add(JoinEvent)
def handle_join(event):
    # ไม่ส่งข้อความตอน join เพื่อป้องกัน error
    pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
