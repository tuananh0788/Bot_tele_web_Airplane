import requests
from flask import Flask, request
from telegram import Bot, Update, ReplyKeyboardMarkup
from telegram.ext import Dispatcher, MessageHandler, Filters
from datetime import datetime, timedelta
import os
import unicodedata
import re

import os, json
import gspread
from google.oauth2.service_account import Credentials

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

# --- Danh sách sân bay và alias giữ nguyên như bạn gửi ---
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

# Hàm chuẩn hóa chuỗi: loại bỏ dấu, khoảng cách, chuyển về chữ thường
def normalize_string(s):
    s = ''.join(c for c in unicodedata.normalize('NFKD', s.lower()) if not unicodedata.combining(c))
    s = re.sub(r'[\s\-\_\.]', '', s)
    return s

# Dictionary ánh xạ mã sân bay với các alias
airport_aliases = {
    "ANH": ["an giang", "châu đốc", "chau doc"],  # Sân bay Châu Đốc (đề xuất)
    "BGG": ["bắc giang", "bac giang", "quế võ", "que vo"],  # Quế Võ (đề xuất)
    "BHA": ["biên hòa", "bien hoa", "đồng nai", "dong nai"],  # Quân sự
    "BLU": ["bạc liêu", "bac lieu"],
    "BMV": ["buôn ma thuột", "buon ma thuot", "đắk lắk", "dak lak"],
    "BNN": ["bắc ninh", "bac ninh"],
    "BPH": ["bình phước", "binh phuoc"],
    "CAH": ["cà mau", "ca mau"],
    "CXR": ["cam ranh", "khánh hòa", "khanh hoa", "nha trang"],
    "DAD": ["đà nẵng", "da nang"],
    "DIN": ["điện biên", "dien bien"],
    "DLI": ["liên khương", "lien khuong", "đà lạt", "da lat", "lâm đồng", "lam dong"],
    "DNO": ["đắk nông", "dak nong"],
    "GLI": ["gia lâm", "gia lam"],  # Quân sự
    "HAN": ["nội bài", "noi bai", "hà nội", "ha noi"],
    "HGG": ["hà giang", "ha giang"],  # Đang nghiên cứu
    "HNM": ["hà nam", "ha nam"],
    "HPH": ["cát bi", "cat bi", "hải phòng", "hai phong"],
    "HTV": ["hà tiên", "ha tien", "kiên giang", "kien giang"],  # Đề xuất
    "HUI": ["phú bài", "phu bai", "huế", "hue"],
    "HYN": ["hưng yên", "hung yen"],
    "KTM": ["kon tum"],
    "LCH": ["lai châu", "lai chau"],
    "LSN": ["lạng sơn", "lang son"],
    "LTG": ["long thành", "long thanh", "đồng nai", "dong nai"],  # Dự kiến
    "NBH": ["ninh bình", "ninh binh"],
    "NDH": ["nam định", "nam dinh"],
    "NHA": ["nha trang", "khánh hòa", "khanh hoa"],  # Quân sự
    "PHH": ["phan thiết", "phan thiet", "bình thuận", "binh thuan"],  # Dự kiến
    "PQC": ["phú quốc", "phu quoc", "kiên giang", "kien giang"],
    "PRG": ["phan rang", "ninh thuận", "ninh thuan"],  # Quân sự
    "PXU": ["pleiku", "gia lai"],
    "QTG": ["quảng trị", "quang tri"],  # Dự kiến
    "SGN": ["tân sơn nhất", "tan son nhat", "sài gòn", "sai gon", "tp hcm", "hồ chí minh", "ho chi minh"],
    "SOA": ["sóc trăng", "soc trang"],
    "SPP": ["sa pa", "lào cai", "lao cai"],  # Dự kiến
    "SQH": ["nà sản", "na san", "sơn la", "son la"],
    "TBB": ["tuy hòa", "tuy hoa", "phú yên", "phu yen"],
    "TBH": ["thái bình", "thai binh"],
    "THD": ["sao vàng", "sao vang", "thọ xuân", "tho xuan", "thanh hóa", "thanh hoa"],
    "TNN": ["thái nguyên", "thai nguyen", "tây ninh", "tay ninh"],  # Tây Ninh quy hoạch
    "TQN": ["tuyên quang", "tuyen quang"],
    "TVH": ["trà vinh", "tra vinh"],
    "UIH": ["phù cát", "phu cat", "quy nhơn", "quy nhon", "bình định", "binh dinh"],
    "VCA": ["cần thơ", "can tho"],
    "VCL": ["chu lai", "quảng nam", "quang nam"],
    "VCS": ["côn đảo", "con dao", "bà rịa vũng tàu", "ba ria vung tau"],
    "VDH": ["đồng hới", "dong hoi", "quảng bình", "quang binh"],
    "VDO": ["vân đồn", "van don", "quảng ninh", "quang ninh"],
    "VII": ["vinh", "nghệ an", "nghe an"],
    "VKG": ["rạch giá", "rach gia", "kiên giang", "kien giang"],
    "VPH": ["vĩnh phúc", "vinh phuc"],
    "VTG": ["vũng tàu", "vung tau"],
    "YBI": ["yên bái", "yen bai"],
}

# Danh sách sân bay chính cho các tỉnh có nhiều sân bay
priority_airports = {
    "kiên giang": "PQC",  # Phú Quốc ưu tiên hơn Rạch Giá (VKG) và Hà Tiên (HTV)
    "đồng nai": "LTG",    # Long Thành ưu tiên hơn Biên Hòa (BHA)
    "khánh hòa": "CXR",   # Cam Ranh ưu tiên hơn Nha Trang (NHA)
    "thanh hóa": "THD",   # Sao Vàng/Thọ Xuân (THD) là sân bay chính
    "hà nội": "HAN",      # Nội Bài ưu tiên hơn Gia Lâm (GLI)
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
    if cnt >= 80:
        # thay 'your_chat_id' bằng chat_id thật của bạn
        bot.send_message(chat_id='your_chat_id',
                         text=f"⚠️ Đã dùng {cnt}/100 API calls!")
    return cnt

# --- Hàm tìm chuyến theo mã (unchanged) ---
def get_flight_info(code, lang="vn"):
    url = f"http://api.aviationstack.com/v1/flights?access_key={API_KEY}&flight_iata={code}"
    res = requests.get(url)
    data = res.json()
    log_api_usage()

    if not data['data']:
        return "Không tìm thấy chuyến bay." if lang == "vn" else "Flight not found."

    flight = data['data'][0]
    # (xử lý giống ban đầu)
    airline = flight['airline']['name']
    dep_iata = flight['departure']['iata']
    arr_iata = flight['arrival']['iata']
    dep_name = airport_names.get(dep_iata, dep_iata)
    arr_name = airport_names.get(arr_iata, arr_iata)

    est_dep = fmt_time(flight['departure'].get('estimated', ''))
    act_dep = fmt_time(flight['departure'].get('actual', ''))
    est_arr = fmt_time(flight['arrival'].get('estimated', ''))
    act_arr = fmt_time(flight['arrival'].get('actual', ''))

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
        # Lấy time, fallback sang scheduled nếu estimated không có
        dep_time_str = f["departure"].get("estimated") or f["departure"].get("scheduled")
        arr_time_str = f["arrival"].get("estimated")   or f["arrival"].get("scheduled")
        dep_est = fmt_time(dep_time_str)
        arr_est = fmt_time(arr_time_str)
        if not dep_est or not arr_est:
            continue

        # Xác định status
        status_code = f.get("flight_status", "scheduled")
        if status_code not in STATUS_MAP:
            if arr_est < now:
                status_code = "landed"
            elif arr_est > dep_est:
                status_code = "delayed"
            else:
                status_code = "scheduled"
        status_text = STATUS_MAP[status_code][lang]

        # Lưu theo thời gian khởi hành để sort
        results.append((dep_est, f, status_text))

    results.sort(key=lambda x: x[0])

    # Thông báo nếu không có kết quả
    no_results = "Không có chuyến bay phù hợp." if lang == "vn" else "No suitable flights found."
    if not results:
        return no_results

    # Chọn label song ngữ
    if lang == "vn":
        from_label, to_label, status_label = "🛫 Từ", "🛬 Đến", "📊 Trạng thái"
    else:
        from_label, to_label, status_label = "🛫 From", "🛬 To", "📊 Status"

    msgs = []
    for dep_est, f, status in results[:20]:
        # Tái tính các timestamp
        dep_val = f["departure"].get("actual") or f["departure"].get("estimated") or f["departure"].get("scheduled")
        arr_val = f["arrival"].get("actual") or f["arrival"].get("estimated")   or f["arrival"].get("scheduled")
        dep_time = fmt_time(dep_val)
        arr_time = fmt_time(arr_val)

        fc = f['flight']['iata']
        al = f['airline']['name']
        dc = f['departure']['iata']
        dn = airport_names.get(dc, dc)
        ac = f['arrival']['iata']
        an = airport_names.get(ac, ac)

        dep_str = dep_time.strftime("%d/%m/%Y %H:%M") if dep_time else "N/A"
        arr_str = arr_time.strftime("%d/%m/%Y %H:%M") if arr_time else "N/A"

        msgs.append(
            f"✈️ {fc} - {al}\n"
            f"{from_label}: {dn} | {dep_str}\n"
            f"{to_label}: {an} | {arr_str}\n"
            f"{status_label}: {status}"
        )
    return "\n\n".join(msgs)

# +++ NEW: lọc chuyến theo điểm xuất phát +++
def get_flights_by_origin(code, lang="vn"):
    url = f"http://api.aviationstack.com/v1/flights?access_key={API_KEY}&dep_iata={code}"
    res = requests.get(url)
    data = res.json()
    log_api_usage()

    results = []
    now = datetime.utcnow()
    for f in data.get("data", []):
        # Lấy time khởi hành, fallback sang scheduled nếu estimated không có
        dep_time_str = f["departure"].get("estimated") or f["departure"].get("scheduled")
        dep_est = fmt_time(dep_time_str)
        arr_time_str = f["arrival"].get("estimated")   or f["arrival"].get("scheduled")
        arr_est = fmt_time(arr_time_str)
        if not dep_est or not arr_est:
            continue

        # Xác định status
        status_code = f.get("flight_status", "scheduled")
        if status_code not in STATUS_MAP:
            if dep_est < now:
                status_code = "landed"
            elif dep_est > arr_est:
                status_code = "delayed"
            else:
                status_code = "scheduled"
        status_text = STATUS_MAP[status_code][lang]

        results.append((dep_est, f, status_text))

    results.sort(key=lambda x: x[0])

    # Thông báo nếu không có kết quả
    no_results = "Không có chuyến bay phù hợp." if lang == "vn" else "No suitable flights found."
    if not results:
        return no_results

    # Chọn label song ngữ
    if lang == "vn":
        from_label, to_label, status_label = "🛫 Từ", "🛬 Đến", "📊 Trạng thái"
    else:
        from_label, to_label, status_label = "🛫 From", "🛬 To", "📊 Status"

    msgs = []
    for dep_est, f, status in results[:20]:
        dep_val = f["departure"].get("actual") or f["departure"].get("estimated") or f["departure"].get("scheduled")
        arr_val = f["arrival"].get("actual") or f["arrival"].get("estimated")   or f["arrival"].get("scheduled")
        dep_time = fmt_time(dep_val)
        arr_time = fmt_time(arr_val)

        fc = f['flight']['iata']
        al = f['airline']['name']
        dc = f['departure']['iata']
        dn = airport_names.get(dc, dc)
        ac = f['arrival']['iata']
        an = airport_names.get(ac, ac)

        dep_str = dep_time.strftime("%d/%m/%Y %H:%M") if dep_time else "N/A"
        arr_str = arr_time.strftime("%d/%m/%Y %H:%M") if arr_time else "N/A"

        msgs.append(
            f"✈️ {fc} - {al}\n"
            f"{from_label}: {dn} | {dep_str}\n"
            f"{to_label}: {an} | {arr_str}\n"
            f"{status_label}: {status}"
        )
    return "\n\n".join(msgs)

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
            else "Enter destination city or airport name"
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
