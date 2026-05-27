"""
LINE Bot - ลงชื่อตีแบด v2
requirements.txt:
    flask
    line-bot-sdk>=3.0.0

คำสั่งทั้งหมด (รองรับหลายเซสชันต่อกลุ่ม):
--- สร้างเซสชัน ---
!สร้าง              → เริ่มสร้างเซสชันใหม่ (step by step)

--- ลงชื่อ ---
+ชื่อ               → ลงชื่อ (จะลงในเซสชันล่าสุดโดยค่าเริ่มต้น)
+ชื่อ 2             → ลงชื่อพร้อมเพื่อน
-ชื่อ               → ลบชื่อออก (จากเซสชันล่าสุด)

--- ดูข้อมูล ---
!รายชื่อ            → ดูรายชื่อของเซสชันล่าสุด
!เซสชัน             → ดูรายการเซสชันทั้งหมด
!เคลียร์            → ล้างรายชื่อในเซสชันล่าสุด (Admin)
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
#   "sessions": [
#       { "venue": "", "date": "", "time": "", "courts": 1, "players": [{"name":"","slots":1}] },
#       ...
#   ],
#   "pending": { "step": "venue"|"date"|"time"|"courts", "data": {} } or None
# }
group_data = {}

DEFAULT_VENUES = ["สนามแบดบางบอน BB3 ", "สนามแบดบางขุนเทียน คอร์ทเอกชัย 10/1", "สนามแบดบางขุนเทียน CC"]


def get_gd(gid):
    if gid not in group_data:
            group_data[gid] = {
                "venues": list(DEFAULT_VENUES),
                # support multiple sessions per group
                "sessions": [],  # each session: {venue,date,time,courts,players:[]}
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

def format_sessions_summary(gid):
    gd = get_gd(gid)
    sessions = gd["sessions"]
    if not sessions:
        return "❌ ยังไม่มีเซสชัน\nพิมพ์ !สร้าง เพื่อสร้างเซสชันใหม่"
    lines = ["🏸 เซสชันที่สร้างไว้:"]
    for i, s in enumerate(sessions, 1):
        courts_str = f"{s['courts']} สนาม"
        total = sum(p['slots'] for p in s.get('players', []))
        lines.append(f"{i}. {s['date']} {s['time']} | {s['venue']} | สนาม: {courts_str} | สมัคร: {total} คน")
    return "\n".join(lines)


def format_session_detail(gid, idx):
    gd = get_gd(gid)
    sessions = gd["sessions"]
    if not sessions or idx < 0 or idx >= len(sessions):
        return "❌ ไม่พบเซสชันที่ระบุ"
    s = sessions[idx]
    courts_str = f"{s['courts']} สนาม"
    lines = [
        f"📍 สถานที่: {s['venue']}",
        f"📅 วันที่: {s['date']}",
        f"⏰ เวลา: {s['time']}",
        f"🏸 จำนวนสนาม: {courts_str}",
        f"👥 รับได้: ไม่จำกัด",
        "─" * 22,
    ]
    players = s.get('players', [])
    if not players:
        lines.append("ยังไม่มีรายชื่อ")
    else:
        num = 1
        for p in players:
            for i in range(p['slots']):
                if i == 0:
                    lines.append(f"{num}. {p['name']}")
                else:
                    lines.append(f"{num}. {p['name']} (+{i})")
                num += 1
    lines.append("─" * 22)
    lines.append(f"รวม: {sum(p['slots'] for p in players)} คน")
    return "\n".join(lines)


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
        # รองรับหลายรูปแบบวันที่ เช่น 28.05.69, 28-05-2569, 28/05/69, 28/05/2569
        def _parse_date_token(tok: str):
            tok = tok.strip()
            # match DD<sep>MM<sep>YY(YY)
            m = re.match(r"^(\d{1,2})[\.\-/](\d{1,2})[\.\-/](\d{2,4})$", tok)
            if not m:
                return None
            d = int(m.group(1))
            mo = int(m.group(2))
            y_str = m.group(3)
            if not (1 <= d <= 31 and 1 <= mo <= 12):
                return None
            # Interpret 2-digit years as Buddhist Era (BE) e.g., 69 -> 2569
            if len(y_str) == 2:
                year = 2500 + int(y_str)
            else:
                year = int(y_str)
            return f"{d:02d}/{mo:02d}/{year}"

        parsed = _parse_date_token(text)
        if parsed is None:
            return (
                "❌ รูปแบบวันที่ไม่ถูกต้อง\n"
                "รองรับเช่น: 28.05.69, 28-05-69, 28/05/2569, 28.05.2569, 28-05-2569"
            )
        data["date"] = parsed
        pending["step"] = "time"
        return f"✅ วันที่: {data['date']}\n\nกรอกเวลา (เช่น 18:00-20:00 หรือ 18-20 หรือ 18.00-20.00)"

    elif step == "time":
        # รองรับรูปแบบเวลา: 17, 17.00, 17:00 และช่วงเวลาเช่น 17-20 หรือ 17:00-19:30
        def _norm_time_token(tok: str):
            tok = tok.strip()
            m = re.match(r"^(\d{1,2})(?:[:\.](\d{1,2}))?$", tok)
            if not m:
                return None
            h = int(m.group(1))
            mm = int(m.group(2)) if m.group(2) else 0
            if not (0 <= h <= 23 and 0 <= mm <= 59):
                return None
            return f"{h:02d}:{mm:02d}"

        parts = re.split(r"\s*[-–]\s*", text)
        if len(parts) == 1:
            t = _norm_time_token(parts[0])
            if not t:
                return "❌ รูปแบบเวลาไม่ถูกต้อง\nกรุณากรอก เช่น `17`, `17:00`, `17.00` หรือช่วง `17-20`"
            data["time"] = t
        elif len(parts) == 2:
            t1 = _norm_time_token(parts[0])
            t2 = _norm_time_token(parts[1])
            if not t1 or not t2:
                return "❌ รูปแบบช่วงเวลาไม่ถูกต้อง\nตัวอย่างที่ถูกต้อง: `17-20`, `17:00-19:30`, `17.00-20.00`"
            # ให้เรียงเวลาให้ถูก (เริ่มก่อน-จบหลัง)
            if t1 > t2:
                t1, t2 = t2, t1
            data["time"] = f"{t1} - {t2}"
        else:
            return "❌ รูปแบบช่วงเวลาไม่ถูกต้อง\nกรุณาใส่ช่วงเวลาในรูปแบบ `start-end`"

        pending["step"] = "courts"
        return f"✅ เวลา: {data['time']}\n\nกรอกจำนวนสนาม (เช่น 2)"

    elif step == "courts":
        if text.isdigit() and int(text) >= 1:
            data["courts"] = int(text)
            # สร้างเซสชัน
            session = {
                "venue": data["venue"],
                "date": data["date"],
                "time": data["time"],
                "courts": data["courts"],
                "players": []
            }
            gd["sessions"].append(session)
            gd["pending"] = None
            idx = len(gd["sessions"])  # 1-based index for users
            return (
                f"✅ สร้างเซสชันสำเร็จ! (หมายเลข {idx})\n\n"
                f"{format_session_detail(gid, idx-1)}\n\n"
                f"รับสมัคร: ไม่จำกัด\nพิมพ์ +ชื่อ เพื่อลงชื่อในเซสชันล่าสุด (หมายเลข {idx}) ได้เลยครับ 🏸"
            )
        else:
            return "❌ กรุณากรอกจำนวนสนามเป็นตัวเลข (เช่น 2)"

    return None


# ─── Players ────────────────────────────────────────────

def get_max(gid):
    gd = get_gd(gid)
    # Currently we treat sessions as having unlimited capacity.
    # This function returns None to indicate "no per-session limit".
    return None


def get_total(gid):
    # total for the most recent session
    gd = get_gd(gid)
    sessions = gd.get("sessions", [])
    if not sessions:
        return 0
    return sum(p["slots"] for p in sessions[-1].get("players", []))


def get_player_num(gid, name):
    # get number within most recent session
    gd = get_gd(gid)
    sessions = gd.get("sessions", [])
    if not sessions:
        return None
    num = 1
    for p in sessions[-1].get("players", []):
        if p["name"] == name:
            return num
        num += p["slots"]
    return None


def format_list(gid):
    gd = get_gd(gid)
    players = gd["players"]
    # format list for most recent session (เซสชันล่าสุด)
    sessions = gd.get("sessions", [])
    if not sessions:
        return "ยังไม่มีเซสชัน\nพิมพ์ !สร้าง เพื่อสร้างเซสชันใหม่"
    s = sessions[-1]
    players = s.get("players", [])
    max_p = get_max(gid)
    total = sum(p["slots"] for p in players)

    lines = []
    # แสดง session ถ้ามี
    # header for list: show session title for the latest session
    if sessions:
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
    if max_p is None:
        lines.append(f"รวม: {total} คน (เซสชันล่าสุด)")
    else:
        lines.append(f"รวม: {total}/{max_p} คน")
        if total >= max_p:
            lines.append("⚠️ เต็มแล้ว!")
    return "\n".join(lines)


def add_player(gid, name, slots=1):
    gd = get_gd(gid)
    sessions = gd.get("sessions", [])
    if not sessions:
        return "❌ ยังไม่มีเซสชันให้ลงชื่อ\nพิมพ์ !สร้าง เพื่อสร้างเซสชันใหม่"
    players = sessions[-1]["players"]
    max_p = get_max(gid)
    total = get_total(gid)

    for p in players:
        if p["name"] == name:
            return f"⚠️ '{name}' ลงชื่อไปแล้ว (ลำดับที่ {get_player_num(gid, name)})"

    # If max_p is None => unlimited, skip capacity check
    if max_p is not None and total + slots > max_p:
        remaining = max_p - total
        if remaining <= 0:
            return f"❌ เต็มแล้ว! ({max_p}/{max_p} คน)"
        return f"❌ รับได้อีกแค่ {remaining} คน (ขอ {slots} คน)"

    players.append({"name": name, "slots": slots})
    num = get_player_num(gid, name)
    total_new = get_total(gid)
    if max_p is None:
        if slots == 1:
            return f"✅ '{name}' ลำดับที่ {num} | รวม {total_new} คน"
        else:
            return f"✅ '{name}' ({slots} คน) ลำดับที่ {num}-{num+slots-1} | รวม {total_new} คน"
    else:
        if slots == 1:
            return f"✅ '{name}' ลำดับที่ {num} | รวม {total_new}/{max_p} คน"
        else:
            return f"✅ '{name}' ({slots} คน) ลำดับที่ {num}-{num+slots-1} | รวม {total_new}/{max_p} คน"


def remove_player(gid, name):
    gd = get_gd(gid)
    sessions = gd.get("sessions", [])
    if not sessions:
        return f"❌ ยังไม่มีเซสชัน"
    players = sessions[-1]["players"]
    for i, p in enumerate(players):
        if p["name"] == name:
            players.pop(i)
            total = get_total(gid)
            max_p = get_max(gid)
            if max_p is None:
                return f"🗑️ ลบ '{name}' ออกแล้ว | รวม {total} คน"
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
        "!รายชื่อ → ดูรายชื่อทั้งหมด (หรือ !รายชื่อ N เพื่อดูรายชื่อของเซสชัน N)\n"
        "!เซสชัน → ดูข้อมูลเซสชัน (หรือ !เซสชัน N เพื่อดูรายละเอียดเซสชัน N)\n"
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
    m = re.match(r"^!(?:รายชื่อ|list)(?:\s+(\d+))?$", text)
    if m:
        if m.group(1):
            idx = int(m.group(1)) - 1
            return format_session_detail(gid, idx)
        return format_list(gid)

    m = re.match(r"^!(?:เซสชัน|session)(?:\s+(\d+))?$", text)
    if m:
        if m.group(1):
            idx = int(m.group(1)) - 1
            return format_session_detail(gid, idx)
        return format_sessions_summary(gid)

    if text in ["!สถานที่", "!venue"]:
        return list_venues(gid)

    if text in ["!สร้าง", "!create"]:
        return start_create_session(gid)

    if text in ["!เคลียร์", "!clear"]:
        if not is_admin(user_id):
            return "❌ เฉพาะ Admin เท่านั้น"
        sessions = gd.get("sessions", [])
        if not sessions:
            return "❌ ยังไม่มีเซสชันให้ล้าง\nพิมพ์ !สร้าง เพื่อสร้างเซสชันใหม่"
        sessions[-1]["players"] = []
        return "🗑️ ล้างรายชื่อเซสชันล่าสุดแล้ว"

    if text in ["!ยกเลิกเซสชัน", "!cancelsession"]:
        if not is_admin(user_id):
            return "❌ เฉพาะ Admin เท่านั้น"
        sessions = gd.get("sessions", [])
        if not sessions:
            return "❌ ยังไม่มีเซสชันให้ยกเลิก"
        idx = len(sessions)
        sessions.pop()
        gd["pending"] = None
        return f"🗑️ ยกเลิกเซสชันหมายเลข {idx} แล้ว"

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
        # keep per-signup slot limit? remove min(...) if not desired
        # slots = min(slots, 10)
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
