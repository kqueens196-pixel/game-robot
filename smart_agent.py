import os
import time
import asyncio
import requests
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from playwright.async_api import async_playwright

# GitHub Secrets se values aayengi (Code me khula nahi rahega)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
GAME_URL = os.getenv("GAME_URL")
CSV_FILE = "game_memory.csv"

# 5 ghante 25 minute (19500 sec) chalne ke baad gracefully band hoga taaki data save ho sake
MAX_RUNTIME = 19500
start_time = time.time()

def send_telegram(msg):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=5)
    except Exception as e:
        print("Telegram error:", e)

def load_memory():
    if os.path.exists(CSV_FILE):
        return pd.read_csv(CSV_FILE).to_dict('records')
    return []

def save_memory(dataset):
    pd.DataFrame(dataset).to_csv(CSV_FILE, index=False)

def train_and_predict(history_df, current_features):
    if len(history_df) < 30:
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

async def run_smart_agent():
    dataset = load_memory()
    rounds_since_last_50x = dataset[-1]['gap_50x'] if dataset else 0
    recent_mults = [d['target_mult'] for d in dataset[-10:]] if len(dataset) >= 10 else []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(GAME_URL, timeout=60000)
        
        send_telegram(f"🤖 *24/7 AI Watcher Active*\nPurane Saved Rounds: `{len(dataset)}`")
        last_mult = None

        while (time.time() - start_time) < MAX_RUNTIME:
            try:
                mult_str = await page.inner_text('.payouts-block .payout:first-child')
                current_mult = float(mult_str.replace('x', '').strip())

                players_str = await page.inner_text('.all-bets-block .bets-count')
                current_players = int(players_str.strip())

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

                    if len(dataset) >= 30:
                        df = pd.DataFrame(dataset)
                        next_input = [
                            recent_mults[-1], recent_mults[-2], recent_mults[-3],
                            recent_mults[-4], recent_mults[-5],
                            np.mean(recent_mults[-10:]), current_players, rounds_since_last_50x
                        ]
                        chance_pct, est_x = train_and_predict(df, next_input)

                        if chance_pct and chance_pct >= 70.0:
                            send_telegram(
                                f"🔥 *AI HIGH MULTIPLIER SIGNAL* 🔥\n"
                                f"📊 *Pattern Match:* `{chance_pct:.1f}%`\n"
                                f"🚀 *Estimated Range:* `{est_x:.2f}x`\n"
                                f"👥 *Players:* `{current_players}` | ⏳ *50x Gap:* `{rounds_since_last_50x}`"
                            )
            except Exception:
                pass

            await asyncio.sleep(2)

        await browser.close()
        send_telegram("🔄 *Shift Complete:* AI apni memory save karke agle 5.5 ghante ke cycle me restart ho raha hai...")

asyncio.run(run_smart_agent())
