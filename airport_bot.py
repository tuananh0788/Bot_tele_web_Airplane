import os
import requests
import sqlite3
from flask import Flask, request
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
API_KEY = os.getenv("AVIATIONSTACK_API_KEY")

app = Flask(__name__)

conn = sqlite3.connect("flights.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT,
        flight_code TEXT,
        info TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
''')
conn.commit()

# Kết nối đến cơ sở dữ liệu SQLite
conn = sqlite3.connect('flights_data.db')  # Thay 'flights_data.db' bằng tên cơ sở dữ liệu của bạn
cursor = conn.cursor()

# Thêm dữ liệu vào bảng flights
cursor.execute('''
INSERT INTO flights (timestamp, flight_code, airline, departure, arrival, status)
VALUES ('2025-04-17 09:00:00', 'VJ123', 'VietJet', 'HAN', 'SGN', 'On Time')
''')

# Đóng kết nối
conn.commit()

AIRPORTS_VN = {
    "HAN": "Nội Bài", "SGN": "Tân Sơn Nhất", "DAD": "Đà Nẵng", "CXR": "Cam Ranh",
    "HUI": "Phú Bài", "VCL": "Chu Lai", "VII": "Vinh", "PQC": "Phú Quốc",
    "BMV": "Buôn Ma Thuột", "DLI": "Liên Khương", "VCA": "Cần Thơ", "THD": "Thọ Xuân",
    "TBB": "Tuy Hòa", "VDH": "Đồng Hới", "VCS": "Côn Đảo", "PXU": "Pleiku",
    "HPH": "Cát Bi", "DIN": "Điện Biên"
}

def get_airport_name(iata):
    return AIRPORTS_VN.get(iata, iata)

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

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.username or update.message.from_user.full_name
    flight_code = update.message.text.strip().upper()

    info = get_flight_info(flight_code)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=info)
    cursor.execute("INSERT INTO history (user, flight_code, info) VALUES (?, ?, ?)", (user, flight_code, info))
    conn.commit()

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
