# LINE Bot ลงชื่อตีแบด — ติดตั้งและใช้งาน

## ติดตั้ง

```bash
pip install flask line-bot-sdk
```

## ตั้งค่า Environment Variables

```bash
export LINE_CHANNEL_ACCESS_TOKEN="ใส่ token จาก LINE Developers"
export LINE_CHANNEL_SECRET="ใส่ secret จาก LINE Developers"
export ADMIN_USER_IDS="Uxxxx,Uyyy"   # userId ของ Admin (ดูได้จาก event log)
export MAX_PLAYERS=20                 # จำนวนคนสูงสุด
```

## รันบอท

```bash
python badminton_bot.py
```

## Deploy บน Render (ฟรี)

1. push โค้ดขึ้น GitHub
2. ไปที่ render.com → New Web Service
3. ใส่ Environment Variables ด้านบน
4. Webhook URL จะได้มาเป็น: `https://your-app.onrender.com/callback`
5. นำ URL ไปใส่ใน LINE Developers → Messaging API → Webhook URL

## คำสั่งในกลุ่ม LINE

| คำสั่ง | ความหมาย |
|--------|----------|
| `+สมชาย` | ลงชื่อ สมชาย |
| `+สมชาย 2` | ลงชื่อ สมชาย พร้อมเพื่อน 1 คน (รวม 2 slot) |
| `-สมชาย` | ลบชื่อ สมชาย ออก (ลำดับเรียงใหม่อัตโนมัติ!) |
| `!รายชื่อ` | ดูรายชื่อทั้งหมดพร้อมลำดับ |
| `!เคลียร์` | ล้างรายชื่อทั้งหมด (Admin เท่านั้น) |
| `!ช่วยเหลือ` | ดูคำสั่งทั้งหมด |

## ตัวอย่างผลลัพธ์

```
🏸 รายชื่อตีแบด
────────────────────
1. สมชาย
2. สมหญิง
3. ประยุทธ์
4. ประยุทธ์ (แถม 1)   ← จอง 2 slot
5. วิชัย
────────────────────
รวม: 5/20 คน
```

เมื่อลบ สมหญิง ออก → ลำดับจะเรียงใหม่เป็น 1,2,3,4 ทันที ไม่ต้องแก้ด้วยตนเอง!
