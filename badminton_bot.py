"""
LINE Bot - ลงชื่อตีแบด (Auto Numbering)
ติดตั้ง: pip install flask line-bot-sdk

คำสั่งในกลุ่ม LINE:
  +ชื่อ       → ลงชื่อ (เช่น +สมชาย)
  -ชื่อ       → ลบชื่อ (เช่น -สมชาย)
  +ชื่อ 2     → ลงชื่อพร้อมจอง 2 คน (เช่น +สมชาย 2)
  !รายชื่อ    → ดูรายชื่อทั้งหมด
  !เคลียร์    → ล้างรายชื่อทั้งหมด (Admin เท่านั้น)
  !ช่วยเหลือ  → ดูคำสั่งทั้งหมด
"""

import os
import re
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, JoinEvent
)

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "YOUR_TOKEN_HERE")
CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "YOUR_SECRET_HERE")

# User IDs ที่เป็น Admin (ใส่ userId ของ Admin ได้หลายคน)
ADMIN_USER_IDS = os.environ.get("ADMIN_USER_IDS", "").split(",")

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# เก็บรายชื่อแยกตาม group_id
# Format: { "group_id": [{"name": "สมชาย", "slots": 1}, ...] }
signup_lists = {}

MAX_PLAYERS = int(os.environ.get("MAX_PLAYERS", 20))  # จำนวนสูงสุด


def get_list(group_id):
    """ดึงรายชื่อของกลุ่ม"""
    return signup_lists.get(group_id, [])


def format_list(group_id):
    """แสดงรายชื่อพร้อมเลขลำดับอัตโนมัติ"""
    players = get_list(group_id)
    if not players:
        return "📋 ยังไม่มีรายชื่อ\nพิมพ์ +ชื่อ เพื่อลงชื่อ"

    lines = ["🏸 รายชื่อตีแบด\n" + "─" * 20]
    num = 1
    for p in players:
        if p["slots"] == 1:
            lines.append(f"{num}. {p['name']}")
            num += 1
        else:
            # จองหลายคน แสดงหลายบรรทัด
            for i in range(p["slots"]):
                if i == 0:
                    lines.append(f"{num}. {p['name']}")
                else:
                    lines.append(f"{num}. {p['name']} (แถม {i})")
                num += 1

    total = sum(p["slots"] for p in players)
    lines.append("─" * 20)
    lines.append(f"รวม: {total}/{MAX_PLAYERS} คน")

    if total >= MAX_PLAYERS:
        lines.append("⚠️ เต็มแล้ว!")

    return "\n".join(lines)


def add_player(group_id, name, slots=1):
    """เพิ่มชื่อในรายชื่อ"""
    if group_id not in signup_lists:
        signup_lists[group_id] = []

    players = signup_lists[group_id]
    total = sum(p["slots"] for p in players)

    # เช็คชื่อซ้ำ
    for p in players:
        if p["name"] == name:
            return f"⚠️ '{name}' ลงชื่อไปแล้ว (ลำดับที่ {get_player_num(group_id, name)})"

    # เช็คเต็ม
    if total + slots > MAX_PLAYERS:
        remaining = MAX_PLAYERS - total
        if remaining <= 0:
            return f"❌ เต็มแล้ว! ({MAX_PLAYERS}/{MAX_PLAYERS} คน)"
        return f"❌ รับได้อีกแค่ {remaining} คน (ขอ {slots} คน)"

    players.append({"name": name, "slots": slots})
    num = get_player_num(group_id, name)

    if slots == 1:
        return f"✅ เพิ่ม '{name}' ลำดับที่ {num}\n{get_summary(group_id)}"
    else:
        return f"✅ เพิ่ม '{name}' ({slots} คน) ลำดับที่ {num}-{num+slots-1}\n{get_summary(group_id)}"


def remove_player(group_id, name):
    """ลบชื่อออก — ลำดับจะเรียงใหม่อัตโนมัติ"""
    if group_id not in signup_lists:
        return f"❌ ไม่มีรายชื่อในกลุ่มนี้"

    players = signup_lists[group_id]
    for i, p in enumerate(players):
        if p["name"] == name:
            players.pop(i)
            return f"🗑️ ลบ '{name}' ออกแล้ว\n{get_summary(group_id)}"

    return f"❌ ไม่พบชื่อ '{name}' ในรายชื่อ"


def get_player_num(group_id, name):
    """หาลำดับของผู้เล่น"""
    players = get_list(group_id)
    num = 1
    for p in players:
        if p["name"] == name:
            return num
        num += p["slots"]
    return None


def get_summary(group_id):
    """สรุปจำนวน"""
    players = get_list(group_id)
    total = sum(p["slots"] for p in players)
    return f"รวม {total}/{MAX_PLAYERS} คน"


def clear_list(group_id):
    """ล้างรายชื่อทั้งหมด"""
    signup_lists[group_id] = []
    return "🗑️ ล้างรายชื่อทั้งหมดแล้ว"


def help_message():
    return """🏸 คำสั่งลงชื่อตีแบด

+ชื่อ → ลงชื่อ
   เช่น: +สมชาย

+ชื่อ 2 → ลงชื่อพร้อมเพื่อน
   เช่น: +สมชาย 2

-ชื่อ → ลบชื่อออก
   เช่น: -สมชาย

!รายชื่อ → ดูรายชื่อทั้งหมด
!เคลียร์ → ล้างรายชื่อ (Admin)
!ช่วยเหลือ → ดูคำสั่ง"""


def process_message(group_id, text, user_id):
    """ประมวลผลข้อความ"""
    text = text.strip()

    # คำสั่ง !
    if text == "!รายชื่อ" or text == "!list":
        return format_list(group_id)

    if text in ["!เคลียร์", "!clear", "!ล้าง"]:
        if user_id in ADMIN_USER_IDS or not ADMIN_USER_IDS[0]:
            return clear_list(group_id)
        return "❌ เฉพาะ Admin เท่านั้น"

    if text in ["!ช่วยเหลือ", "!help", "!คำสั่ง"]:
        return help_message()

    # + ลงชื่อ
    add_match = re.match(r"^\+(.+?)(?:\s+(\d+))?$", text)
    if add_match:
        name = add_match.group(1).strip()
        slots = int(add_match.group(2)) if add_match.group(2) else 1
        slots = min(slots, 10)  # จำกัดไม่เกิน 10 คนต่อครั้ง
        return add_player(group_id, name, slots)

    # - ลบชื่อ
    remove_match = re.match(r"^-(.+)$", text)
    if remove_match:
        name = remove_match.group(1).strip()
        return remove_player(group_id, name)

    return None  # ไม่ตอบถ้าไม่ใช่คำสั่ง


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    # รองรับทั้ง group และ room
    if event.source.type not in ["group", "room"]:
        # ถ้าเป็นแชทส่วนตัว ตอบแบบ demo
        source_id = event.source.user_id
    else:
        source_id = (
            event.source.group_id
            if event.source.type == "group"
            else event.source.room_id
        )

    user_id = event.source.user_id
    text = event.message.text

    reply = process_message(source_id, text, user_id)
    if reply:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply)
        )


@handler.add(JoinEvent)
def handle_join(event):
    """ทักทายเมื่อบอทเข้ากลุ่ม"""
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(
            text="🏸 สวัสดีครับ! บอทลงชื่อตีแบดพร้อมแล้ว\n\nพิมพ์ !ช่วยเหลือ เพื่อดูคำสั่งทั้งหมด"
        )
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
