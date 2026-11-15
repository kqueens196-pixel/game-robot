import os
import re
import time
import requests
import easyocr
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
CSV_FILE = "game_memory.csv"

MAX_RUNTIME = 19500
start_time = time.time()

# OCR Reader load karna (English numbers padhne ke liye)
print("Loading EasyOCR Model...")
reader = easyocr.Reader(['en'], gpu=False)

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        print("Telegram error:", e)

def load_memory():
    if os.path.exists(CSV_FILE):
        return pd.read_csv(CSV_FILE)['mult'].tolist()
    return []

def save_memory(mult_list):
    pd.DataFrame({'mult': mult_list}).to_csv(CSV_FILE, index=False)

def extract_multipliers_from_image(image_path):
    """Photo me se 1.25x, 2.40x jaise sare multipliers nikalna"""
    results = reader.readtext(image_path, detail=0)
    full_text = " ".join(results)
    
    # Text me se decimal numbers (jaise 1.20x, 14.50, 2.05x) dhundhna
    matches = re.findall(r'\b\d{1,4}\.\d{2}x?\b', full_text.lower())
    
    multipliers = []
    for m in matches:
        val = float(m.replace('x', ''))
        # Time (jaise 3.45) ya balance ko filter karne ke liye reasonable range
        if 1.00 <= val <= 5000.0:
            multipliers.append(val)
            
    return multipliers

def analyze_and_predict(all_mults, new_mults):
    if len(all_mults) < 10:
        return (
            f"📸 *Photo Read Ho Gayi!*\n"
            f"🔢 *Mile Huye Numbers:* `{new_mults}`\n"
            f"📚 *Total Memory:* `{len(all_mults)}/10` rounds.\n"
            f"Ek-do screenshots aur bhejo taaki AI ka 10 rounds ka data pura ho jaye!"
        )

    # Dataset taiyar karna (Pichle 5 numbers se agla number seekhna)
    X, y_class, y_reg = [], [], []
    for i in range(5, len(all_mults)):
        prev_5 = all_mults[i-5:i]
        target = all_mults[i]
        X.append(prev_5 + [np.mean(prev_5)])
        y_class.append(1 if target >= 2.0 else 0)
        y_reg.append(min(target, 50.0))

    X = np.array(X)
    y_class = np.array(y_class)
    y_reg = np.array(y_reg)

    # AI Model Train karna
    clf = RandomForestClassifier(n_estimators=100, random_state=42)
    clf.fit(X, y_class)

    reg = RandomForestRegressor(n_estimators=100, random_state=42)
    reg.fit(X, y_reg)

    # Abhi ke latest 5 multipliers se agla round predict karna
    last_5 = all_mults[-5:]
    live_input = np.array([last_5 + [np.mean(last_5)]])

    prob_2x = clf.predict_proba(live_input)[0][1] * 100 if len(clf.classes_) > 1 else 50.0
    est_mult = reg.predict(live_input)[0]

    # Session Health (RTP Check)
    recent_20 = np.array(all_mults[-20:])
    above_2x_rate = np.sum(recent_20 >= 2.0) / len(recent_20) * 100
    low_crash_rate = np.sum(recent_20 <= 1.20) / len(recent_20) * 100

    if prob_2x >= 65.0 and above_2x_rate >= 40:
        verdict = "🟢 *STRONG PATTERN MATCH (Good to Play)*"
    elif low_crash_rate >= 50:
        verdict = "🔴 *DANGER / COLD SESSION (Abhi Mat Khelo!)*"
    else:
        verdict = "🟡 *NORMAL / WAIT FOR CLEAR STREAK*"

    return (
        f"📸 *Screenshot Scanned Successfully!*\n"
        f"🆕 *Read Numbers:* `{new_mults[:8]}`\n\n"
        f"{verdict}\n"
        f"📊 *2.0x+ Pattern Confidence:* `{prob_2x:.1f}%`\n"
        f"🚀 *AI Estimated Range:* `{est_mult:.2f}x`\n\n"
        f"🛡️ *Fairness & RTP Check (Last {len(recent_20)}):*\n"
        f"• *2x+ Success Rate:* `{above_2x_rate:.1f}%` (Fair: ~48.5%)\n"
        f"• *Instant Crash (<1.20x):* `{low_crash_rate:.1f}%`\n"
        f"📚 *Total Memory:* `{len(all_mults)}` rounds"
    )

def download_telegram_photo(file_id):
    # File path nikalna
    info_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}"
    res = requests.get(info_url, timeout=10).json()
    file_path = res["result"]["file_path"]
    
    # Image download karna
    img_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
    img_data = requests.get(img_url, timeout=15).content
    with open("latest_screen.jpg", "wb") as f:
        f.write(img_data)
    return "latest_screen.jpg"

def run_bot():
    all_mults = load_memory()
    send_telegram(
        "📸 *AI Screenshot Scanner Active Hai!*\n\n"
        "Ab aapko kuch type karne ki zaroorat nahi hai:\n"
        "1️⃣ Apne phone me game kholo.\n"
        "2️⃣ Game ka *Screenshot* lo aur sidha yahan bhej do!\n"
        "3️⃣ AI photo me se sare multipliers padh kar aapko *Signal + Fairness Report* de dega!\n\n"
        f"📚 *Saved Memory:* `{len(all_mults)}` rounds"
    )

    last_update_id = 0
    while (time.time() - start_time) < MAX_RUNTIME:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={last_update_id + 1}&timeout=10"
            res = requests.get(url, timeout=15).json()

            for update in res.get("result", []):
                last_update_id = update["update_id"]
                msg = update.get("message", {})

                # Agar user ne Photo (Screenshot) bheji hai
                if "photo" in msg:
                    send_telegram("🔍 *Screenshot padh raha hoon, 3 second ruko...*")
                    # Sabse high quality photo ka file_id lena
                    file_id = msg["photo"][-1]["file_id"]
                    img_path = download_telegram_photo(file_id)
                    
                    new_mults = extract_multipliers_from_image(img_path)
                    if new_mults:
                        all_mults.extend(new_mults)
                        save_memory(all_mults)
                        reply = analyze_and_predict(all_mults, new_mults)
                        send_telegram(reply)
                    else:
                        send_telegram("⚠️ Photo me multipliers saaf nahi dikhe. Upar wale multipliers bar ko thoda crop karke bhejo!")

                # Agar user ne text me numbers bheje hain
                elif "text" in msg:
                    text = msg["text"]
                    nums = [float(x.replace('x', '')) for x in text.split() if x.replace('.', '').replace('x', '').isdigit()]
                    if nums:
                        all_mults.extend(nums)
                        save_memory(all_mults)
                        send_telegram(analyze_and_predict(all_mults, nums))

        except Exception as e:
            print("Loop error:", e)
        time.sleep(1)

if __name__ == "__main__":
    run_bot()
