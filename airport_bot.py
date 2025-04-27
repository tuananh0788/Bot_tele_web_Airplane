import requests
from flask import Flask, request
from telegram import Bot, Update, ReplyKeyboardMarkup
from telegram.ext import Dispatcher, MessageHandler, Filters
from datetime import datetime, timedelta
import unicodedata
import re
import os, json
import gspread
from google.oauth2.service_account import Credentials


API_USAGE_FILE = "api_usage.txt"

# --- Google Sheets setup ---
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
creds_json = os.environ["GOOGLE_SHEETS_CREDS_JSON"]
creds_dict = json.loads(creds_json)
creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
gc = gspread.authorize(creds)

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
sheet = gc.open_by_key(SPREADSHEET_ID).worksheet("API Usage Counter")


TOKEN = '8051795674:AAHuqYMmC47CzFsd-Li-y0_kEH3bSZi01Uk'
API_KEY = 'ac2469df44587ed7b51f78729f69bd30'
API_USAGE_FILE = "api_usage.txt"

# Sau các import, ngay trước khi khởi tạo app:
STATUS_MAP = {
    "scheduled": {"vn": "Đã lên lịch",    "en": "Scheduled"},
    "active":    {"vn": "Đang bay",       "en": "En route"},
    "landed":    {"vn": "Đã hạ cánh",    "en": "Landed"},
    "cancelled": {"vn": "Đã hủy",        "en": "Cancelled"},
    "incident":  {"vn": "Sự cố",          "en": "Incident"},
    "diverted":  {"vn": "Bay lệch hướng", "en": "Diverted"},
    "delayed":   {"vn": "Chậm giờ",       "en": "Delayed"},
}


app = Flask(__name__)
bot = Bot(token=TOKEN)
dispatcher = Dispatcher(bot, None, workers=0)

user_states = {}

# 1) Ngôn ngữ khởi tạo
LANGUAGE_OPTIONS = ['🇻🇳 Tiếng Việt', '🇬🇧 English']

# 2) Menu chính bổ sung 3 lựa chọn và 1 nút đổi ngôn ngữ
MAIN_MENU = {
    'vn': [
        ['🔎 Tra mã chuyến bay', '📍 Tra theo điểm đến', '🛫 Tra theo điểm đi'],
        ['🔄 Đổi ngôn ngữ']
    ],
    'en': [
        ['🔎 Search by flight code', '📍 Search by destination', '🛫 Search by origin'],
        ['🔄 Change language']
    ]
}

# --- Danh sách sân bay và alias ---
airport_names = {
    # Các sân bay thương mại đang hoạt động
    "HAN": "Nội Bài",
    "SGN": "Tân Sơn Nhất",
    "DAD": "Đà Nẵng",
    "CXR": "Cam Ranh",
    "VCA": "Cần Thơ",
    "HUI": "Huế",
    "PXU": "Pleiku",
    "VDH": "Đồng Hới",
    "VII": "Vinh",
    "THD": "Thanh Hóa",
    "DLI": "Liên Khương (Đà Lạt)",
    "PQC": "Phú Quốc",
    "BMV": "Buôn Ma Thuột",
    "VKG": "Rạch Giá",
    "VCL": "Chu Lai",
    "TBB": "Tuy Hòa",
    "VCS": "Côn Đảo",
    "HPH": "Cát Bi (Hải Phòng)",
    "DIN": "Điện Biên Phủ",
    "UIH": "Phù Cát (Quy Nhơn)",

    # Sân bay quân sự, dân dụng hạn chế hoặc quy hoạch
    "BLV": "Bảo Lộc (đề xuất)",
    "HGN": "Hà Giang (quy hoạch)",
    "NHF": "Ninh Hòa (quy hoạch - sân bay quân sự Cam Lâm)",
    "LBP": "Lai Châu (quy hoạch)",
    "HBB": "Hòa Bình (quy hoạch)",
    "SQH": "Nà Sản (Sơn La - quân sự, quy hoạch dân dụng)",
    "HTV": "Hà Tiên (quy hoạch)",
    "TNN": "Tây Ninh (quy hoạch)",
    "BGG": "Bắc Giang (quy hoạch)",
    "BNN": "Bắc Ninh (quy hoạch)",
    "HGG": "Hà Giang (quy hoạch)",
    "TQN": "Tuyên Quang (quy hoạch)",
    "LSN": "Lạng Sơn (quy hoạch)",
    "YBI": "Yên Bái (quy hoạch)",
    "CDG": "Châu Đốc (An Giang - quy hoạch)",
    "SOA": "Sóc Trăng (quy hoạch)",
    "TVH": "Trà Vinh (quy hoạch)",
    "BLU": "Bạc Liêu (quy hoạch)",
    "HNM": "Hà Nam (quy hoạch)",
    "HYN": "Hưng Yên (quy hoạch)",
    "NDH": "Nam Định (quy hoạch)",
    "NBH": "Ninh Bình (quy hoạch)",
    "TBH": "Thái Bình (quy hoạch)",
    "VPH": "Vĩnh Phúc (quy hoạch)",
    "BPH": "Bình Phước (quy hoạch)",
    "DNO": "Đắk Nông (quy hoạch)",
    "KTM": "Kon Tum (đề xuất dân dụng)",
}

# Hàm chuẩn hóa chuỗi: loại bỏ dấu và chuyển về chữ thường
def normalize_text(text):
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    return text.lower()

airport_aliases = {
    # Hà Nội
    "nội bài": "HAN", "noi bai": "HAN", "hà nội": "HAN", "ha noi": "HAN",
    # TP. Hồ Chí Minh
    "tân sơn nhất": "SGN", "tan son nhat": "SGN", "sài gòn": "SGN", "sai gon": "SGN", "tp hcm": "SGN", "hồ chí minh": "SGN", "ho chi minh": "SGN",
    # Đà Nẵng
    "đà nẵng": "DAD", "da nang": "DAD",
    # Hải Phòng
    "cát bi": "HPH", "cat bi": "HPH", "hải phòng": "HPH", "hai phong": "HPH",
    # Cần Thơ
    "cần thơ": "VCA", "can tho": "VCA",
    # Huế
    "phú bài": "HUI", "phu bai": "HUI", "huế": "HUI", "hue": "HUI",
    # Cam Ranh
    "cam ranh": "CXR", "khánh hòa": "CXR", "khanh hoa": "CXR", "nha trang": "CXR",
    # Phú Quốc
    "phú quốc": "PQC", "phu quoc": "PQC", "kiên giang": "PQC", "kien giang": "PQC",
    # Đà Lạt
    "liên khương": "DLI", "lien khuong": "DLI", "đà lạt": "DLI", "da lat": "DLI", "lâm đồng": "DLI", "lam dong": "DLI",
    # Buôn Ma Thuột
    "buôn ma thuột": "BMV", "buon ma thuot": "BMV", "đắk lắk": "BMV", "dak lak": "BMV",
    
    # Pleiku
    "pleiku": "PXU", "gia lai": "PXU",
    
    # Vinh
    "vinh": "VII", "nghệ an": "VII", "nghe an": "VII",
    
    # Đồng Hới
    "đồng hới": "VDH", "dong hoi": "VDH", "quảng bình": "VDH", "quang binh": "VDH",
    
    # Thanh Hóa
    "sao vàng": "THD", "sao vang": "THD", "thanh hóa": "THD", "thanh hoa": "THD",
    
    # Chu Lai
    "chu lai": "VCL", "quảng nam": "VCL", "quang nam": "VCL",
    
    # Tuy Hòa
    "tuy hòa": "TBB", "tuy hoa": "TBB", "phú yên": "TBB", "phu yen": "TBB",
    
    # Côn Đảo
    "côn đảo": "VCS", "con dao": "VCS", "bà rịa vũng tàu": "VCS", "ba ria vung tau": "VCS",
    
    # Điện Biên
    "điện biên": "DIN", "dien bien": "DIN",
    
    # Rạch Giá
    "rạch giá": "VKG", "rach gia": "VKG", "kiên giang": "VKG", "kien giang": "VKG",
    
    # Cà Mau
    "cà mau": "CAH", "ca mau": "CAH",
    
    # Vũng Tàu
    "vũng tàu": "VTG", "vung tau": "VTG",
    
    # Nà Sản
    "nà sản": "SQH", "na san": "SQH", "sơn la": "SQH", "son la": "SQH",
    
    # Phù Cát
    "phù cát": "UIH", "phu cat": "UIH", "quy nhơn": "UIH", "quy nhon": "UIH", "bình định": "UIH", "binh dinh": "UIH",
    
    # Long Thành (dự kiến)
    "long thành": "LTG", "long thanh": "LTG", "đồng nai": "LTG", "dong nai": "LTG",
    
    # Vân Đồn
    "vân đồn": "VDO", "van don": "VDO", "quảng ninh": "VDO", "quang ninh": "VDO",
    
    # Phan Thiết (dự kiến)
    "phan thiết": "PHH", "phan thiet": "PHH", "bình thuận": "PHH", "binh thuan": "PHH",
    
    # Sa Pa (dự kiến)
    "sa pa": "SPP", "lào cai": "SPP", "lao cai": "SPP",
    
    # Quảng Trị (dự kiến)
    "quảng trị": "QTG", "quang tri": "QTG",
    
    # Gia Lâm
    "gia lâm": "GLI", "gia lam": "GLI",
    
    # Nha Trang (quân sự)
    "nha trang": "NHA", "khánh hòa": "NHA", "khanh hoa": "NHA",
    
    # Biên Hòa (quân sự)
    "biên hòa": "BHA", "bien hoa": "BHA", "đồng nai": "BHA", "dong nai": "BHA",
    
    # Phan Rang (quân sự)
    "phan rang": "PRG", "ninh thuận": "PRG", "ninh thuan": "PRG",
    
    # Thọ Xuân
    "thọ xuân": "THD", "tho xuan": "THD", "thanh hóa": "THD", "thanh hoa": "THD",

    # Kiên Giang – sân bay Hà Tiên (đề xuất)
    "hà tiên": "HTV", "ha tien": "HTV", "kiên giang": "HTV", "kien giang": "HTV",

    # Tây Ninh – chưa có sân bay thương mại, nhưng đang quy hoạch
    "tây ninh": "TNN", "tay ninh": "TNN",

    # Bắc Giang (Quế Võ – đề xuất)
    "bắc giang": "BGG", "bac giang": "BGG", "quế võ": "BGG", "que vo": "BGG",

    # Bắc Ninh
    "bắc ninh": "BNN", "bac ninh": "BNN",

    # Hà Giang – chưa có sân bay, nhưng đang nghiên cứu khả thi
    "hà giang": "HGG", "ha giang": "HGG",

    # Tuyên Quang
    "tuyên quang": "TQN", "tuyen quang": "TQN",

    # Lạng Sơn
    "lạng sơn": "LSN", "lang son": "LSN",

    # Yên Bái
    "yên bái": "YBI", "yen bai": "YBI",

    # Lai Châu
    "lai châu": "LCH", "lai chau": "LCH",

    # Kon Tum
    "kon tum": "KTM",

    # An Giang (đề xuất sân bay Châu Đốc)
    "an giang": "CDG", "châu đốc": "CDG", "chau doc": "CDG",

    # Sóc Trăng (sân bay Sóc Trăng đang quy hoạch)
    "sóc trăng": "SOA", "soc trang": "SOA",

    # Trà Vinh
    "trà vinh": "TVH", "tra vinh": "TVH",

    # Bạc Liêu
    "bạc liêu": "BLU", "bac lieu": "BLU",

    # Hà Nam
    "hà nam": "HNM", "ha nam": "HNM",

    # Hưng Yên
    "hưng yên": "HYN", "hung yen": "HYN",

    # Nam Định
    "nam định": "NDH", "nam dinh": "NDH",

    # Ninh Bình
    "ninh bình": "NBH", "ninh binh": "NBH",

    # Thái Bình
    "thái bình": "TBH", "thai binh": "TBH",

    # Thái Nguyên
    "thái nguyên": "TNN", "thai nguyen": "TNN",

    # Vĩnh Phúc
    "vĩnh phúc": "VPH", "vinh phuc": "VPH",

    # Bình Phước
    "bình phước": "BPH", "binh phuoc": "BPH",

    # Đắk Nông
    "đắk nông": "DNO", "dak nong": "DNO",
}


def fmt_time(t):
    try:
        return datetime.strptime(t, "%Y-%m-%dT%H:%M:%S+00:00")
    except:
        return None

def get_api_usage():
    """Đọc giá trị count hiện tại ở ô A2."""
    try:
        value = sheet.acell("A2").value
        return int(value)
    except Exception:
        return 0

def log_api_usage():
    """Tăng count lên 1, ghi vào A2, và cảnh báo nếu ≥80."""
    cnt = get_api_usage() + 1
    sheet.update("A2", [[cnt]])
    if cnt in [50, 60, 70, 75, 80, 85, 90, 95]:
        bot.send_message(chat_id='7587598474',
                         text=f"⚠️ Đã dùng {cnt}/100 API calls!")
    return cnt

# --- Hàm tìm chuyến theo mã---
def get_flight_info(code, lang="vn"):
    url = f"http://api.aviationstack.com/v1/flights?access_key={API_KEY}&flight_iata={code}"
    res = requests.get(url)
    data = res.json()
    log_api_usage()

    if not data['data']:
        return "Không tìm thấy chuyến bay." if lang == "vn" else "Flight not found."

    flight = data['data'][0]
    airline = flight['airline']['name']
    dep_iata = flight['departure']['iata']
    arr_iata = flight['arrival']['iata']
    dep_name = airport_names.get(dep_iata, dep_iata)
    arr_name = airport_names.get(arr_iata, arr_iata)

    est_dep = fmt_time(flight['departure'].get('estimated', ''))
    act_dep = fmt_time(flight['departure'].get('actual', ''))
    est_arr = fmt_time(flight['arrival'].get('estimated', ''))
    act_arr = fmt_time(flight['arrival'].get('actual', ''))

    status_map = {
        "scheduled": "Đã lên lịch" if lang == "vn" else "Scheduled",
        "active":    "Đang bay"     if lang == "vn" else "En route",
        "landed":    "Đã hạ cánh"  if lang == "vn" else "Landed",
        "cancelled": "Đã hủy"      if lang == "vn" else "Cancelled",
        "incident":  "Sự cố"        if lang == "vn" else "Incident",
        "diverted":  "Bay lệch hướng" if lang == "vn" else "Diverted"
    }

    msg = f"✈️ {code.upper()} - {airline}\n"
    msg += f"🛫 {dep_iata} ({dep_name}) → 🛬 {arr_iata} ({arr_name})\n"
    if est_dep:
        msg += f"🕐 {est_dep.strftime('%H:%M')}"
        if act_dep:
            msg += (f", thực tế {act_dep.strftime('%H:%M')}" 
                    if lang == "vn" else f", actual {act_dep.strftime('%H:%M')}")
    if est_arr:
        msg += f"\n🕑 {est_arr.strftime('%H:%M')}"
        if act_arr:
            msg += f" (Actual: {act_arr.strftime('%H:%M')})"
    status = status_map.get(flight.get('flight_status'), "Không rõ")
    msg += f"\n📊 {status}"
    return msg

# --- Lọc chuyến theo điểm đến ---
def get_flights_by_destination(code, lang="vn"):
    url = f"http://api.aviationstack.com/v1/flights?access_key={API_KEY}&arr_iata={code}"
    res = requests.get(url)
    data = res.json()
    log_api_usage()

    results = []
    now = datetime.utcnow()
    for f in data.get("data", []):
        arr_est = fmt_time(f["arrival"].get("estimated", ""))
        arr_act = fmt_time(f["arrival"].get("actual", ""))
        dep_est = fmt_time(f["departure"].get("estimated", ""))
        dep_act = fmt_time(f["departure"].get("actual", ""))
        if not arr_est:
            continue
        status = ("landed" if arr_act and arr_act < now - timedelta(hours=1)
                  else "scheduled")
        results.append((arr_est, f, status))

    results.sort(key=lambda x: x[0])
    msg = ""
    for est, f, status in results[:20]:
        flight_code = f['flight']['iata']
        airline     = f['airline']['name']
        dep_code    = f['departure']['iata']
        arr_code    = f['arrival']['iata']
        dep_name    = airport_names.get(dep_code, dep_code)
        arr_name    = airport_names.get(arr_code, arr_code)

        dep_time = fmt_time(f['departure'].get('actual', '')) or fmt_time(f['departure'].get('estimated', ''))
        arr_time = est
        dep_str = dep_time.strftime("%d/%m/%Y %H:%M") if dep_time else "N/A"
        arr_str = arr_time.strftime("%d/%m/%Y %H:%M")

        msg += f"✈️ {flight_code} - {airline}\n"
        msg += f"🛫 Từ: {dep_name} | {dep_str}\n"
        msg += f"🛬 Đến: {arr_name} | {arr_str}\n"
        msg += f"📊 Trạng thái: {status}\n\n"
    return msg or ("Không có chuyến bay phù hợp." if lang=="vn" else "No suitable flights found.")

# +++lọc chuyến theo điểm xuất phát +++
def get_flights_by_origin(code, lang="vn"):
    url = f"http://api.aviationstack.com/v1/flights?access_key={API_KEY}&dep_iata={code}"
    res = requests.get(url)
    data = res.json()
    log_api_usage()

    results = []
    now = datetime.utcnow()
    for f in data.get("data", []):
        dep_est = fmt_time(f["departure"].get("estimated", ""))
        dep_act = fmt_time(f["departure"].get("actual", ""))
        arr_est = fmt_time(f["arrival"].get("estimated", ""))
        arr_act = fmt_time(f["arrival"].get("actual", ""))
        if not dep_est:
            continue
        status = ("landed" if dep_act and dep_act < now - timedelta(hours=1)
                  else "scheduled")
        results.append((dep_est, f, status))

    results.sort(key=lambda x: x[0])
    msg = ""
    for est, f, status in results[:20]:
        flight_code = f['flight']['iata']
        airline     = f['airline']['name']
        dep_code    = f['departure']['iata']
        arr_code    = f['arrival']['iata']
        dep_name    = airport_names.get(dep_code, dep_code)
        arr_name    = airport_names.get(arr_code, arr_code)

        dep_time = fmt_time(f['departure'].get('actual', '')) or est
        arr_time = fmt_time(f['arrival'].get('estimated', '')) or fmt_time(f['arrival'].get('actual', ''))
        dep_str = dep_time.strftime("%d/%m/%Y %H:%M") if dep_time else "N/A"
        arr_str = arr_time.strftime("%d/%m/%Y %H:%M") if arr_time else "N/A"

        msg += f"✈️ {flight_code} - {airline}\n"
        msg += f"🛫 Từ: {dep_name} | {dep_str}\n"
        msg += f"🛬 Đến: {arr_name} | {arr_str}\n"
        msg += f"📊 Trạng thái: {status}\n\n"
    return msg or ("Không có chuyến bay phù hợp." if lang=="vn" else "No suitable flights found.")

def get_airport_code_by_name(name):
    return airport_aliases.get(normalize_text(name))

def handle(update: Update, context):
    uid  = update.message.chat_id
    text = update.message.text.strip().lower()

    # 1) Nếu user chưa chọn ngôn ngữ
    if uid not in user_states:
        if text in ['🇻🇳 tiếng việt', 'vn']:
            user_states[uid] = {'lang': 'vn'}
            update.message.reply_text(
                "Bạn muốn tra cứu theo?",
                reply_markup=ReplyKeyboardMarkup(MAIN_MENU['vn'], resize_keyboard=True)
            )
        elif text in ['🇬🇧 english', 'en']:
            user_states[uid] = {'lang': 'en'}
            update.message.reply_text(
                "Choose option:",
                reply_markup=ReplyKeyboardMarkup(MAIN_MENU['en'], resize_keyboard=True)
            )
        else:
            update.message.reply_text(
                "Chọn ngôn ngữ / Choose language:",
                reply_markup=ReplyKeyboardMarkup([LANGUAGE_OPTIONS], resize_keyboard=True)
            )
        return

    # 2) Nếu user đã có state và gõ lệnh đổi ngôn ngữ
    if text in ['🔄 đổi ngôn ngữ', '🔄 change language']:
        user_states.pop(uid, None)
        update.message.reply_text(
            "Chọn ngôn ngữ / Choose language:",
            reply_markup=ReplyKeyboardMarkup([LANGUAGE_OPTIONS], resize_keyboard=True)
        )
        return

    # 3) Đến đây chắc chắn đã chọn ngôn ngữ, lấy thông tin
    lang  = user_states[uid]['lang']
    state = user_states[uid].get('state')

    # 4) Xử lý menu chính
    if text in ['🔎 tra mã chuyến bay', '🔎 search by flight code']:
        user_states[uid]['state'] = 'code'
        update.message.reply_text(
            "Nhập mã chuyến bay (ví dụ: VN123)" if lang=='vn'
            else "Enter flight code (e.g. VN123)"
        )
        return

    if text in ['📍 tra theo điểm đến', '📍 search by destination']:
        user_states[uid]['state'] = 'dest'
        update.message.reply_text(
            "Nhập tên thành phố/sân bay" if lang=='vn'
            else "Enter city or airport name"
        )
        return

    if text in ['🛫 tra theo điểm đi', '🛫 search by origin']:
        user_states[uid]['state'] = 'origin'
        update.message.reply_text(
            "Nhập tên thành phố/sân bay xuất phát" if lang=='vn'
            else "Enter departure city or airport name"
        )
        return

    # 5) Xử lý input dựa trên state
    if state == 'code':
        msg = get_flight_info(text.upper(), lang)
        update.message.reply_text(msg)
        return

    if state == 'dest':
        code = get_airport_code_by_name(text)
        if code:
            msg = get_flights_by_destination(code, lang)
            update.message.reply_text(msg)
        else:
            update.message.reply_text(
                "Không nhận diện được điểm đến." if lang=='vn'
                else "Could not recognize destination."
            )
        return

    if state == 'origin':
        code = get_airport_code_by_name(text)
        if code:
            msg = get_flights_by_origin(code, lang)
            update.message.reply_text(msg)
        else:
            update.message.reply_text(
                "Không nhận diện được điểm xuất phát." if lang=='vn'
                else "Could not recognize origin."
            )
        return

    # 6) Mặc định khi không hiểu
    update.message.reply_text(
        "Chọn lại chức năng." if lang=='vn'
        else "Please choose again."
    )

dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle))

# Route kiểm tra bot có đang chạy không
@app.route('/')
def home():
    return "Bot is running!"

# Route nhận Webhook từ Telegram
@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return 'OK'

@app.route('/usage')
def usage():
    return str(get_api_usage())

if __name__ == '__main__':
    pass  # tránh lỗi indentation
