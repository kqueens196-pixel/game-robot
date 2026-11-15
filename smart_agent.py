import os
import re
import time
import asyncio
import requests
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from camoufox.async_api import AsyncCamoufox

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
GAME_URL = os.getenv("GAME_URL")
GAME_USER = os.getenv("GAME_USER")
GAME_PASS = os.getenv("GAME_PASS")
CSV_FILE = "game_memory.csv"

MAX_RUNTIME = 19500
start_time = time.time()

def send_telegram(msg):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        print("Telegram error:", e)

def send_photo(photo_path, caption):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    try:
        with open(photo_path, "rb") as img:
            requests.post(url, data={"chat_id": CHAT_ID, "caption": caption}, files={"photo": img}, timeout=15)
    except Exception as e:
        print("Photo send error:", e)

def load_memory():
    if os.path.exists(CSV_FILE):
        return pd.read_csv(CSV_FILE).to_dict('records')
    return []

def save_memory(dataset):
    pd.DataFrame(dataset).to_csv(CSV_FILE, index=False)

def train_and_predict(history_df, current_features):
    if len(history_df) < 20:
        return None, None

    feature_cols = ['m1', 'm2', 'm3', 'm4', 'm5', 'avg_last_10', 'players', 'gap_50x']
    X = history_df[feature_cols]
    
    y_high_chance = (history_df['target_mult'] >= 10.0).astype(int)
    clf = RandomForestClassifier(n_estimators=100, random_state=42)
    clf.fit(X, y_high_chance)

    y_exact_mult = np.clip(history_df['target_mult'], 1.0, 100.0)
    reg = RandomForestRegressor(n_estimators=100, random_state=42)
    reg.fit(X, y_exact_mult)

    live_df = pd.DataFrame([current_features], columns=feature_cols)
    prob_high = clf.predict_proba(live_df)[0][1] * 100 if len(clf.classes_) > 1 else 0.0
    estimated_x = reg.predict(live_df)[0]
    
    return prob_high, estimated_x

async def auto_login(page):
    send_telegram("🕵️ *Stealth Browser se Website khol raha hoon...*")
    try:
        await page.wait_for_timeout(6000)
        await page.screenshot(path="step1_stealth.png")
        send_photo("step1_stealth.png", "📸 Step 1: Stealth Mode me website aisi dikh rahi hai")

        # Agar 'Begin' button dikhe toh click karein
        begin_btn = page.locator("button:has-text('Begin')").first
        if await begin_btn.is_visible(timeout=5000):
            await begin_btn.click()
            await page.wait_for_timeout(5000)

        # Login form kholna
        login_open_btn = page.locator("text=/log in|login|sign in/i").first
        if await login_open_btn.is_visible(timeout=5000):
            await login_open_btn.click()
            await page.wait_for_timeout(3000)

        # ID aur Password bharna
        user_box = page.locator("input[type='text'], input[type='tel'], input[type='number']").first
        await user_box.fill(GAME_USER, timeout=15000)
        await page.wait_for_timeout(1000)

        pass_box = page.locator("input[type='password']").first
        await pass_box.fill(GAME_PASS, timeout=10000)
        await page.wait_for_timeout(1000)

        submit_btn = page.locator("button[type='submit'], button:has-text('Log in'), button:has-text('Login')").last
        await submit_btn.click()

        await page.wait_for_timeout(8000)
        await page.screenshot(path="login_done.png")
        send_photo("login_done.png", "✅ Step 2: Login ke baad ki screen!")

    except Exception as e:
        await page.screenshot(path="error_screen.png")
        send_photo("error_screen.png", f"⚠️ Abhi screen par yeh hai: {str(e)[:100]}")

async def run_smart_agent():
    dataset = load_memory()
    rounds_since_last_50x = dataset[-1]['gap_50x'] if dataset else 0
    recent_mults = [d['target_mult'] for d in dataset[-10:]] if len(dataset) >= 10 else []

    # Camoufox Anti-Detect Browser (403 Forbidden bypass karne ke liye)
    async with AsyncCamoufox(headless=True, humanize=True) as browser:
        page = await browser.new_page()
        await page.goto(GAME_URL, timeout=60000)

        if GAME_USER and GAME_PASS:
            await auto_login(page)

        send_telegram(f"🤖 *Live Watcher Chalu Hai*\nSaved Rounds: `{len(dataset)}`")
        last_mult = None

        while (time.time() - start_time) < MAX_RUNTIME:
            try:
                mult_locator = page.locator('.payouts-block .payout:first-child, .result-history .item:first-child').first
                players_locator = page.locator('.all-bets-block .bets-count').first

                if not await mult_locator.is_visible(timeout=1000):
                    for frame in page.frames:
                        if await frame.locator('.payouts-block .payout:first-child').count() > 0:
                            mult_locator = frame.locator('.payouts-block .payout:first-child').first
                            players_locator = frame.locator('.all-bets-block .bets-count').first
                            break

                mult_str = await mult_locator.inner_text(timeout=2000)
                clean_mult = re.findall(r"\d+\.\d+", mult_str)
                if not clean_mult:
                    await asyncio.sleep(2)
                    continue
                current_mult = float(clean_mult[0])

                try:
                    players_str = await players_locator.inner_text(timeout=1000)
                    current_players = int(re.sub(r"\D", "", players_str) or 200)
                except Exception:
                    current_players = 200

                if current_mult != last_mult:
                    last_mult = current_mult

                    if len(recent_mults) >= 10:
                        row = {
                            'm1': recent_mults[-1], 'm2': recent_mults[-2],
                            'm3': recent_mults[-3], 'm4': recent_mults[-4],
                            'm5': recent_mults[-5],
                            'avg_last_10': np.mean(recent_mults[-10:]),
                            'players': current_players,
                            'gap_50x': rounds_since_last_50x,
                            'target_mult': current_mult
                        }
                        dataset.append(row)
                        save_memory(dataset)

                    recent_mults.append(current_mult)
                    rounds_since_last_50x = 0 if current_mult >= 50.0 else rounds_since_last_50x + 1

                    if len(dataset) >= 20:
                        df = pd.DataFrame(dataset)
                        next_input = [
                            recent_mults[-1], recent_mults[-2], recent_mults[-3],
                            recent_mults[-4], recent_mults[-5],
                            np.mean(recent_mults[-10:]), current_players, rounds_since_last_50x
                        ]
                        chance_pct, est_x = train_and_predict(df, next_input)

                        if chance_pct and chance_pct >= 65.0:
                            send_telegram(
                                f"🔥 *LIVE AI SIGNAL* 🔥\n"
                                f"📊 *Pattern Match:* `{chance_pct:.1f}%`\n"
                                f"🚀 *Estimated Plane Range:* `{est_x:.2f}x`\n"
                                f"👥 *Players:* `{current_players}` | ⏳ *50x Gap:* `{rounds_since_last_50x}`\n"
                                f"📉 *Last 3 Rounds:* `{recent_mults[-3:]}`"
                            )
            except Exception:
                pass

            await asyncio.sleep(2)

asyncio.run(run_smart_agent())
