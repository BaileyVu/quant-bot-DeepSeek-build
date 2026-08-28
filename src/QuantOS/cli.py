"""CLI for QuantOS commands."""

import click
import time
from datetime import datetime, timedelta

from quantos.main import main as app_main
from quantos.logging import setup_logging
from quantos.config import get_config
from quantos.market_data.fetcher import MarketDataFetcher
from quantos.infrastructure.duckdb_interface import DuckDBInterface
from quantos.market_data.live import LiveMarketData
from quantos.feature_engine.engine import FeatureEngine
from quantos.feature_engine.storage import FeatureStore
from quantos.model.trainer import ModelTrainer

@click.group()
def cli():
    """QuantOS V1 command-line interface."""
    pass

@cli.command()
def start():
    """Start QuantOS (foundation check)."""
    setup_logging()
    app_main()

@cli.command()
def config():
    """Show current configuration."""
    cfg = get_config()
    click.echo(cfg.json(indent=2))

@cli.command()
@click.option("--symbol", default="BTCUSDT", help="Symbol")
@click.option("--days", default=30, help="Number of days to fetch (past)")
@click.option("--interval", default="1m", help="Interval")
def fetch(symbol, days, interval):
    """Fetch historical data from Binance and store as Parquet."""
    logger = setup_logging()
    start = datetime.utcnow() - timedelta(days=days)
    end = datetime.utcnow()
    fetcher = MarketDataFetcher()
    logger.info(f"Fetching {days} days of {symbol} {interval} data from {start} to {end}")
    candles = fetcher.fetch_historical(symbol, interval, start, end)
    click.echo(f"Fetched {len(candles)} candles for {symbol}")

@cli.command()
@click.option("--symbol", default="BTCUSDT", help="Symbol")
@click.option("--start", default=None, help="Start time ISO format")
@click.option("--end", default=None, help="End time ISO format")
def query(symbol, start, end):
    """Query stored candles via DuckDB."""
    db = DuckDBInterface()
    start_dt = datetime.fromisoformat(start) if start else None
    end_dt = datetime.fromisoformat(end) if end else None
    df = db.get_candles(symbol, start_dt, end_dt)
    click.echo(df.head(10).to_string())

@cli.command()
@click.option("--symbol", default="BTCUSDT", help="Symbol")
def live(symbol):
    """Start live feed and print completed candles (Ctrl+C to stop)."""
    logger = setup_logging()
    live = LiveMarketData(symbol)
    def print_candle(candle):
        logger.info(f"Live candle: {candle.timestamp} O:{candle.open} H:{candle.high} L:{candle.low} C:{candle.close} V:{candle.volume}")
    live.on_candle(print_candle)
    try:
        live.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        live.stop()
        click.echo("Stopped.")

@cli.command()
@click.option("--symbol", default="BTCUSDT", help="Symbol")
@click.option("--start", default=None, help="Start time ISO format")
@click.option("--end", default=None, help="End time ISO format")
@click.option("--version", default="v1.0", help="Feature set version")
def compute_features(symbol, start, end, version):
    """Compute features for a given symbol and date range."""
    logger = setup_logging()
    cfg = get_config()
    engine = FeatureEngine(version=version)
    store = FeatureStore()
    start_dt = datetime.fromisoformat(start) if start else None
    end_dt = datetime.fromisoformat(end) if end else None
    db = DuckDBInterface()
    df_candles = db.get_candles(symbol, start_dt, end_dt)
    if df_candles.empty:
        click.echo("No candles found for the given range.")
        return
    features_df = engine.compute_features(df_candles, symbol=symbol)
    count = store.save_features(features_df, symbol=symbol, version=version)
    click.echo(f"Computed and stored {count} feature rows for {symbol} (version {version}).")

@cli.command()
@click.option("--symbol", default="BTCUSDT", help="Symbol")
@click.option("--version", default="v1.0", help="Feature set version")
@click.option("--horizon", default=None, type=int, help="Prediction horizon in minutes (overrides config)")
def train(symbol, version, horizon):
    """Train a predictive model using feature data."""
    logger = setup_logging()
    try:
        trainer = ModelTrainer(symbol, version, horizon)
        metrics = trainer.train()
        click.echo("Training completed successfully.")
        click.echo("Metrics:")
        for k, v in metrics.items():
            click.echo(f"  {k}: {v:.4f}")
        click.echo(f"Artifacts saved in: data/parquet/models/{symbol}/{version}/")
    except Exception as e:
        logger.error(f"Training failed: {e}")
        click.echo(f"Error: {e}", err=True)

@cli.command()
@click.option("--symbol", default="BTCUSDT", help="Symbol")
@click.option("--version", default="v1.0", help="Feature/Model version")
@click.option("--start", default=None, help="Start time ISO format")
@click.option("--end", default=None, help="End time ISO format")
@click.option("--output-dir", default="reports", help="Directory to save reports")
def backtest(symbol, version, start, end, output_dir):
    """Run backtest, walk‑forward, and Monte Carlo evaluation."""
    logger = setup_logging()
    from quantos.backtest.engine import BacktestEngine
    from quantos.backtest.walkforward import WalkForwardValidator
    from quantos.backtest.montecarlo import MonteCarloSimulator
    from quantos.backtest.report import ReportGenerator
    from pathlib import Path

    try:
        start_dt = datetime.fromisoformat(start) if start else None
        end_dt = datetime.fromisoformat(end) if end else None
        engine = BacktestEngine(symbol, version, start_dt, end_dt)
        bt_result = engine.run()

        wf = WalkForwardValidator(symbol, version)
        wf_result = wf.run()

        trades = bt_result.get("trades", [])
        initial_cap = bt_result.get("initial_capital", 20.0)
        monte = MonteCarloSimulator(trades, initial_cap)
        mc_result = monte.run()

        combined = {
            "backtest": bt_result,
            "walkforward": wf_result,
            "montecarlo": mc_result,
            "status": "PASS" if bt_result.get("num_trades", 0) > 10 else "WARNING",
        }
        if bt_result.get("num_trades", 0) == 0:
            combined["status"] = "NO-GO"

        report_gen = ReportGenerator()
        report_dict = report_gen.generate(combined, symbol, version)
        out_path = Path(output_dir)
        report_gen.save(report_dict, out_path, symbol, version)

        click.echo(f"Reports generated in {out_path}")
        click.echo(f"Status: {combined['status']}")
        if "metrics" in bt_result:
            click.echo("Backtest metrics:")
            for k, v in bt_result["metrics"].items():
                click.echo(f"  {k}: {v:.4f}")

    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        click.echo(f"Error: {e}", err=True)

@cli.command()
@click.option("--symbol", default="BTCUSDT", help="Symbol")
@click.option("--version", default="v1.0", help="Model/Feature version")
@click.option("--horizon", default=None, type=int, help="Prediction horizon (overrides config)")
def paper(symbol, version, horizon):
    """Start paper trading with live market data."""
    logger = setup_logging()
    from quantos.paper.runtime import PaperRuntime
    try:
        runtime = PaperRuntime(symbol, version, horizon)
        runtime.run_forever()
    except KeyboardInterrupt:
        logger.info("Paper trading stopped by user")
    except Exception as e:
        logger.error(f"Paper runtime error: {e}")
        click.echo(f"Error: {e}", err=True)

if __name__ == "__main__":
    cli()