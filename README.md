# QuantOS V1 — Minimal Viable Trading System

**QuantOS V1** is a local, modular, research‑first trading engine built for **Binance Spot** (BTCUSDT, ETHUSDT) with **1‑minute candles**, starting capital of **20 USDT**.  
It is designed as a **monolith** (Clean Architecture) that runs entirely on your local workstation – no cloud, no microservices.

The project implements a complete workflow from raw market data to paper trading:

1. **Market Data** – fetch, validate, and store 1‑minute OHLCV candles (Parquet).
2. **Feature Engineering** – compute 13 deterministic, causal features.
3. **Model Training** – train a single LightGBM classifier with a fixed target (price direction over 5 minutes).
4. **Honest Backtesting** – chronological walk‑forward evaluation with transaction costs and Monte Carlo simulation.
5. **Paper Trading** – run continuously against real Binance market data, simulating all orders locally.

> **⚠️ Important**: This system is **paper‑trading only**. It never submits real orders to Binance. Live trading is **explicitly gated** and not included in this version.

---

## 📁 Documentation (Frozen Source of Truth)

All design decisions are frozen in the `docs/` folder. **Read them first** before making any changes:

- `000_READ_FIRST.md` – overview and principles
- `001_PRODUCT_REQUIREMENTS.md` – product scope
- `002_SYSTEM_ARCHITECTURE.md` – Clean Architecture & module boundaries
- `003_DATA_ARCHITECTURE.md` – market data, Parquet, DuckDB
- `004_FEATURE_ENGINE_SPECIFICATION.md` – feature design and 13‑feature set
- `005_ALPHA_ENGINE.md` – model/signal pipeline
- `006_RISK_EXECUTION_SPECIFICATION.md` – risk & execution (paper)
- `007_VALIDATION_BACKTESTING.md` – backtesting and evaluation
- `008_IMPLEMENTATION_GUIDE.md` – implementation roadmap

These documents are **immutable** – do not modify them.

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10 or higher
- `pip` and `virtualenv` (optional but recommended)
- Git

### 1. Fork & Clone the Repository
```bash
git clone https://github.com/BaileyVu/quant-bot-DeepSeek-build.git
cd quant-bot-DeepSeek-build
```

### 2. Create a Virtual Environment
```bash
python -m venv venv
source venv/bin/activate       # Linux/macOS
# or
venv\Scripts\activate          # Windows
```

### 3. Install the Package

```bash
pip install -e .[dev]
```
This installs all dependencies (pandas, duckdb, lightgbm, loguru, etc.) and makes the quantos CLI command available.

### 4. (Optional) Configure
Edit config/config.yaml to change symbols, timeframes, capital, fee/slippage assumptions, or paper trading parameters.
Default values are suitable for the MVP.

📊 CLI Commands
All commands are run via the quantos CLI.

`quantos start`: Verify that the application starts and logs correctly.
`quantos config`: Show the current configuration (JSON).
`quantos fetch --symbol BTCUSDT --days 30`: Download historical 1‑minute candles from Binance and store as Parquet.
`quantos compute_features --symbol BTCUSDT --version v1.0`: Compute the 13 features from candles and save to Parquet.
`quantos train --symbol BTCUSDT --version v1.0`: Train a LightGBM model using the feature set.
`quantos backtest --symbol BTCUSDT --version v1.0`: Run a full backtest (including walk‑forward and Monte Carlo) and generate reports in `reports/`.
`quantos paper --symbol BTCUSDT`: Start the paper trading runtime (live Binance data, simulated execution). Press Ctrl+C to stop.
`quantos live --symbol BTCUSDT`: (Read‑only) Print live completed candles to console (no trading).
For full options, use `--help`, e.g. `quantos fetch --help`.

🧪 Running Tests
Run the entire test suite (unit + integration) with:

```bash
pytest
```
All tests should pass. They cover configuration, domain validations, feature computation, model training, backtesting, and paper trading logic.

📂 Project Structure

quant-bot-DeepSeek-build/
├── config/                 # YAML configuration
├── docs/                   # Frozen specifications (read first!)
├── src/quantos/            # Main package
│   ├── adapters/           # Binance REST/WebSocket
│   ├── domain/             # Entities (Candle, FeatureVector)
│   ├── infrastructure/     # Parquet storage, DuckDB
│   ├── market_data/        # Fetch, validate, live feed
│   ├── feature_engine/     # 13‑feature pipeline
│   ├── model/              # Target, trainer, artifacts
│   ├── backtest/           # Engine, metrics, walk‑forward, Monte Carlo
│   └── paper/              # Runtime, portfolio, risk, state persistence
├── tests/                  # All test files
├── pyproject.toml          # Dependencies and build config
└── README.md               # This file

🔒 Safety & Paper‑Only Guarantee
*Paper trading is the default and only operational mode in this release.
The system never connects to Binance’s trading endpoints – only public market‑data streams are used.
A `SafetyBarrier` class explicitly raises an exception if any real order‑submission method is called.
Even if environment variables `BINANCE_API_KEY/SECRET` are set, they are ignored.

📈 Current Status
Milestones 0–5 are complete.

The system is ready for paper trading on BTCUSDT and ETHUSDT.
The model is a simple LightGBM classifier; performance depends on the quality and quantity of data.
No live trading – this is a research/educational tool.

🤝 Contributing
This project is frozen per the specifications in `docs/.`
If you wish to extend it, please read the documentation first and respect the design decisions.

📄 License
This project is proprietary – see `LICENSE` for details.

🙏 Acknowledgements
Built according to the QuantOS V1 specifications – all credit to the project’s architecture team.
