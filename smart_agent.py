import os
import time
import hashlib
import requests
import numpy as np
import pandas as pd

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
CSV_FILE = "game_memory.csv"

MAX_RUNTIME = 19500
start_time = time.time()

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        print("Telegram error:", e)

def verify_provably_fair(combined_seed, given_hash):
    """Check karta hai ki game ka SHA-256 hash asli (Fair) hai ya fake"""
    calculated_hash = hashlib.sha256(combined_seed.encode('utf-8')).hexdigest()
    if calculated_hash.lower() == given_hash.lower():
        return f"✅ *100% FAIR PLAY VERIFIED!*\nWebsite ka hash bilkul asli hai:\n`{calculated_hash[:30]}...`"
    else:
        return f"🚨 *WARNING: HASH MISMATCH!*\nYeh game fair formula match nahi kar rahi!\nAsli Hash hona chahiye: `{calculated_hash[:25]}...`"

def analyze_rtp_and_volatility(mults):
    """Pichle rounds dekh kar batata hai ki abhi game kitna RTP de rahi hai"""
    if len(mults) < 5:
        return f"📥 Round Saved (`{len(mults)}/5`). कम से कम 5 rounds bhejein!"
    
    arr = np.array(mults[-20:])
    above_2x = np.sum(arr >= 2.0) / len(arr) * 100
    instant_crashes = np.sum(arr <= 1.20) / len(arr) * 100
    avg_mult = np.mean(arr)

    # Fair Aviator me 2x+ aane ka mathematical chance ~48.5% hota hai
    if above_2x >= 45:
        status = "🟢 *FAIR / HOT SESSION* (Game normal 97% RTP ke aas-paas chal rahi hai)"
    elif instant_crashes >= 50:
        status = "🔴 *COLD / HIGH DRAIN SESSION* (Abhi 1.20x se niche bahut crash ho rahe hain, mat khelo!)"
    else:
        status = "🟡 *AVERAGE SESSION* (Normal volatility chal rahi hai)"

    return (
        f"{status}\n\n"
        f"📊 *Last {len(arr)} Rounds Report:*\n"
        f"• *2.0x+ Success Rate:* `{above_2x:.1f}%` (Fair Standard: ~48.5%)\n"
        f"• *Low Crash (<1.20x) Rate:* `{instant_crashes:.1f}%`\n"
        f"• *Average Multiplier:* `{avg_mult:.2f}x`"
    )

def run_bot():
    mults = []
    if os.path.exists(CSV_FILE):
        df = pd.read_csv(CSV_FILE)
        mults = df['mult'].tolist()

    send_telegram(
        "🛡️ *Fair Play & RTP Auditor Bot Active!*\n\n"
        "Aap is bot se 2 kaam kar sakte hain:\n"
        "1️⃣ *Session Fairness Check:* Bas multipliers bhejein (jaise `1.20 3.40 1.05 2.10` ya ek-ek karke `1.50`), bot batayega ki abhi game Fair 97% RTP de rahi hai ya paise kaat rahi hai (Cold Session).\n\n"
        "2️⃣ *Hash Check:* `/check seed hash` likh kar check karein ki website asli Provably Fair hai ya fake."
    )

    last_update_id = 0
    while (time.time() - start_time) < MAX_RUNTIME:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={last_update_id + 1}&timeout=10"
            res = requests.get(url, timeout=15).json()

            for update in res.get("result", []):
                last_update_id = update["update_id"]
                text = update.get("message", {}).get("text", "").strip()

                if text.startswith("/check"):
                    parts = text.split()
                    if len(parts) == 3:
                        send_telegram(verify_provably_fair(parts[1], parts[2]))
                    else:
                        send_telegram("👉 Format: `/check <combined_seed> <hash>`")
                else:
                    # Ek sath kai numbers ya single number accept karega
                    nums = [float(x.replace('x', '')) for x in text.split() if x.replace('.', '').replace('x', '').isdigit()]
                    if nums:
                        mults.extend(nums)
                        pd.DataFrame({'mult': mults}).to_csv(CSV_FILE, index=False)
                        send_telegram(analyze_rtp_and_volatility(mults))
                    else:
                        send_telegram("⚠️ Multipliers likh kar bhejein! Jaise: `1.10 2.50 1.05 1.80 4.20`")
        except Exception:
            pass
        time.sleep(1)

if __name__ == "__main__":
    run_bot()
