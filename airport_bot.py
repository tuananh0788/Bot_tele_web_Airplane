import os
import requests
import sqlite3
from flask import Flask, request
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
API_KEY = os.getenv("AVIATIONSTACK_API_KEY")

app = Flask(__name__)

# Sử dụng một cơ sở dữ liệu duy nhất cho cả hai bảng history và flights
DATABASE = 'flights_data.db'
conn = sqlite3.connect(DATABASE, check_same_thread=False)
cursor = conn.cursor()

# Tạo bảng history nếu chưa có
cursor.execute('''
    CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT,
        flight_code TEXT,
        info TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
''')

# Tạo bảng flights nếu chưa có
cursor.execute('''
    CREATE TABLE IF NOT EXISTS flights (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        flight_code TEXT,
        airline TEXT,
        departure TEXT,
        arrival TEXT,
        status TEXT
    )
''')
conn.commit()

# Hàm lấy thông tin chuyến bay từ AviationStack
def get_flight_info(flight_code):
    url = f"http://api.aviationstack.com/v1/flights?access_key={API_KEY}&flight_iata={flight_code}"
    response = requests.get(url)
    data = response.json()

    if not data.get("data"):
        return f"Không tìm thấy thông tin cho chuyến bay {flight_code}."

    flight = data["data"][0]
    airline = flight["airline"]["name"]
    dep_iata = flight["departure"]["iata"]
    arr_iata = flight["arrival"]["iata"]
    dep_sch = flight["departure"].get("scheduled", "")[11:16]
    dep_est = flight["departure"].get("estimated", "")[11:16]
    arr_est = flight["arrival"].get("estimated", "")[11:16]
    status = flight.get("flight_status", "Không rõ")

    altitude = flight.get("live", {}).get("altitude")
    speed = flight.get("live", {}).get("speed_horizontal")

    msg = f"✈️ {flight_code.upper()} - {airline}\n"
    msg += f"🛫 Từ: {dep_iata} ({get_airport_name(dep_iata)})\n"
    msg += f"🛬 Đến: {arr_iata} ({get_airport_name(arr_iata)})\n"
    msg += f"🕐 Lịch khởi hành: {dep_sch} (dự kiến), {dep_est} (thực tế)\n"
    msg += f"🕑 Dự kiến đến: {arr_est}\n"
    msg += f"📊 Trạng thái: {status.capitalize()}\n"

    if altitude and speed:
        msg += f"📍 Máy bay đang bay ở độ cao {int(altitude)}m, tốc độ {int(speed)}km/h"

    return msg

# Lưu thông tin chuyến bay vào lịch sử và gửi thông báo qua Telegram
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.username or update.message.from_user.full_name
    flight_code = update.message.text.strip().upper()

    info = get_flight_info(flight_code)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=info)
    
    # Lưu thông tin vào bảng history
    cursor.execute("INSERT INTO history (user, flight_code, info) VALUES (?, ?, ?)", (user, flight_code, info))
    conn.commit()

# Cấu hình Telegram bot
telegram_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def telegram_webhook():
    update = Update.de_json(request.get_json(force=True), telegram_app.bot)
    telegram_app.update_queue.put(update)
    return "OK"

@app.route("/")
def show_history():
    cursor.execute("SELECT user, flight_code, info, timestamp FROM history ORDER BY timestamp DESC LIMIT 20")
    rows = cursor.fetchall()
    html = "<h2>Lịch sử tra cứu</h2><ul>"
    for user, code, info, ts in rows:
        html += f"<li><b>{ts}</b> - @{user} - {code}<br>{info}</li><br>"
    html += "</ul>"
    return html

if __name__ == "__main__":
    app.run(debug=True)
