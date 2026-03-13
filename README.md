### Automated BTC 5-Minute Prediction Market Trader on Polymarket


<div align="center">
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Polymarket](https://img.shields.io/badge/Polymarket-CLOB_API-00C2FF?style=for-the-badge)](https://polymarket.com)
[![Telegram](https://img.shields.io/badge/Telegram-Bot_Dashboard-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://telegram.org)
[![License](https://img.shields.io/badge/License-MIT-22C55E?style=for-the-badge)](LICENSE)

</div>

---

## What is 5Min?

**5Min** is a fully automated trading bot that monitors, enters, and manages positions on **BTC 5-minute prediction markets** on Polymarket. It runs a multi-rule trend-following strategy — buying UP or DOWN tokens based on real-time price movement — and lets you run **live trading and paper (simulated) trading simultaneously**, all controlled through a Telegram bot.

---

## Features at a Glance

| | Feature |
|---|---|
| 📡 | **Auto market discovery** — polls Gamma API for active BTC 5-minute markets |
| ⚡ | **Dual-mode** — live and paper trading run in parallel on the same price feed |
| 🧠 | **4-rule decision engine** — trend-following logic with dynamic position sizing |
| 📉 | **Size reduction near expiry** — automatically scales down orders as markets close |
| 💬 | **Telegram dashboard** — real-time alerts, trade logs, P&L, and bot controls |
| 🗄️ | **SQLite paper analytics** — full session history and performance tracking |
| 🛑 | **Graceful shutdown** — archives sessions and notifies on exit |

---

## Strategy

Every tick, the bot reads price history for each active market and runs a decision engine across five rules:

```
R0 — Size Reduction     If time_remaining < SIZE_REDUCE_AFTER_SECS → scale down order size
R1 — No Position        UP rising → Buy UP   |   DOWN rising → Buy DOWN
R2 — UP Only            Lock with DOWN if cost/pair is profitable, or expand if DOWN is lagging
R3 — DOWN Only          Lock with UP if cost/pair is profitable, or expand if UP is lagging
R4 — Both Sides         Lock the weaker side, or expand the side with rising trend & lagging PnL
```

> Trend detection uses a rolling window of price history. A side is "rising" when the latest price exceeds the oldest and up-moves outnumber down-moves.

---

## Architecture

```
5Min/
│
├── main.py                      ← Bot orchestrator & entry point
│
├── api/
│   ├── auth.py                  ← Polymarket wallet + API auth
│   └── clob_client.py           ← CLOB REST client (prices, orders)
│
├── monitor/
│   ├── market_finder.py         ← Gamma API polling & market registration
│   └── closure_checker.py       ← Detects resolved markets, archives positions
│
├── strategy/
│   ├── trend.py                 ← Rising / falling / flat trend detection
│   ├── decision.py              ← R1–R4 decision engine
│   └── position.py              ← Position state & PnL calculations
│
├── trader/
│   └── executor.py              ← Live order execution via CLOB
│
├── paper_trading/
│   ├── paper_clob.py            ← Simulated CLOB (uses real price feed)
│   ├── paper_executor.py        ← Paper order execution
│   ├── paper_store.py           ← In-memory paper state
│   ├── paper_db.py              ← SQLite session persistence
│   └── paper_analytics.py      ← P&L and session analytics
│
├── state/
│   └── store.py                 ← Live market & position state
│
├── telegram_bot/
│   ├── bot.py                   ← Bot runner & command routing
│   ├── dashboard.py             ← Interactive Telegram dashboard
│   └── notifier.py              ← Log & trade channel notifications
│
├── utils/
│   └── logger.py                ← Structured logging
│
└── config.py                    ← All environment variable loading
```

---

## Quickstart

### 1. Clone & Install

```bash
git clone https://github.com/ayusharyaneth/5Min.git
cd 5Min
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
```

Open `.env` and fill in your credentials (see [Configuration](#configuration) below).

### 3. Run

```bash
python main.py
```

On startup the bot will validate your config, initialize all components, send a startup message to your Telegram log channel, and begin trading.

Press `Ctrl+C` to stop — the bot will archive the current paper session before exiting.

---

## Configuration

### Credentials

| Variable | Description |
|---|---|
| `POLYMARKET_PRIVATE_KEY` | Wallet private key — hex string, **no** `0x` prefix |
| `POLYMARKET_WALLET_ADDRESS` | Wallet address (`0x...`) |
| `POLYMARKET_API_KEY` | Polymarket API key |
| `POLYMARKET_API_SECRET` | Polymarket API secret |
| `POLYMARKET_API_PASSPHRASE` | Polymarket API passphrase |
| `TELEGRAM_BOT_TOKEN` | Bot token from [@BotFather](https://t.me/botfather) |
| `TELEGRAM_LOGS_CHANNEL_ID` | Channel ID for system logs (e.g. `-100xxxxxxxxx`) |
| `TELEGRAM_TRADES_CHANNEL_ID` | Channel ID for trade alerts |
| `TELEGRAM_ALLOWED_USER_ID` | Your numeric Telegram user ID — restricts dashboard access |

### Trading Mode

| Variable | Description | Default |
|---|---|---|
| `LIVE_TRADING` | Enable live order execution | `false` |
| `PAPER_TRADING` | Enable paper (simulated) trading | `false` |

> ⚠️ At least one of `LIVE_TRADING` or `PAPER_TRADING` must be `true`.

### Paper Trading

| Variable | Description | Default |
|---|---|---|
| `PAPER_STARTING_BALANCE` | Virtual starting balance in USD | `10000.0` |
| `PAPER_DB_PATH` | Path for SQLite session database | `paper_trades.db` |

### Risk & Strategy

| Variable | Description | Default |
|---|---|---|
| `DAILY_LOSS_LIMIT_USD` | Max daily loss allowed (USD) | `100.0` |
| `BASE_SIZE` | Base order size in shares | `24` |
| `COST_PER_PAIR_MAX` | Max acceptable cost per pair to trigger a lock | `1.0` |
| `MAX_BUYS_PER_TICK` | Max orders per market per tick | `2` |
| `COOLDOWN_SECS` | Sleep time between ticks (seconds) | `1` |
| `SIZE_REDUCE_AFTER_SECS` | Seconds remaining before size reduction kicks in | `240` |
| `SIZE_MIN_RATIO` | Minimum size ratio at expiry | `0.5` |
| `SIZE_MIN_SHARES` | Hard floor for order size | `6` |
| `TREND_WINDOW` | Price history window for trend detection | `5` |

### Polling Intervals

| Variable | Description | Default |
|---|---|---|
| `MARKET_POLL_INTERVAL` | Seconds between market discovery polls | `15` |
| `CLOSURE_CHECK_INTERVAL` | Seconds between market closure checks | `20` |
| `LOG_FILE` | Local log file path | `bot.log` |

---

## Telegram Commands

Once the bot is running, control it from your Telegram account:

| Command | Description |
|---|---|
| `/status` | Active markets and current positions |
| `/pnl` | Realized and unrealized P&L |
| `/paper` | Paper trading stats and session history |
| `/stop` | Gracefully stop the bot |

---

## Requirements

```
python-dotenv==1.0.0
requests==2.31.0
websocket-client==1.6.4
eth-account==0.10.0
web3==6.15.1
pydantic==2.5.3
python-dateutil==2.8.2
python-telegram-bot==20.7
```

---

## Prerequisites

- Python **3.10+**
- A funded Polymarket wallet with API credentials → [polymarket.com](https://polymarket.com)
- A Telegram bot → create one via [@BotFather](https://t.me/botfather)
- Two Telegram channels (logs + trades) with the bot added as admin

---

<div align="center">

**⚠️ Disclaimer**

This project is for educational and research purposes only.  
Automated trading involves significant financial risk.  
Use at your own risk.

---

Made with ☕ by [ayusharyaneth](https://github.com/ayusharyaneth)

</div>
