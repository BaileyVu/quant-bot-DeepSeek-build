"""Generate structured reports (JSON and human‑readable)."""

import json
from typing import Dict, Any
from datetime import datetime
from pathlib import Path
from loguru import logger

from quantos.config import get_config


class ReportGenerator:
    """
    Generate machine‑readable (JSON) and human‑readable (text) reports.
    """

    @staticmethod
    def generate(result: Dict[str, Any], symbol: str, version: str) -> Dict[str, str]:
        """
        Create both JSON and Markdown reports.
        Returns dict with keys "json" and "markdown" containing the report content.
        """
        config = get_config()

        # Prepare report structure
        report = {
            "report_metadata": {
                "generated_at": datetime.utcnow().isoformat(),
                "symbol": symbol,
                "version": version,
                "model_target_horizon": config.model.target_horizon,
                "backtest_config": {
                    "fee_bps": config.backtest.fee_bps,
                    "slippage_bps": config.backtest.slippage_bps,
                    "initial_capital": config.backtest.initial_capital,
                    "signal_threshold": config.backtest.signal_threshold,
                },
            },
            "backtest_results": result.get("backtest", {}),
            "walkforward_results": result.get("walkforward", {}),
            "monte_carlo_results": result.get("montecarlo", {}),
            "status": result.get("status", "unknown"),
        }

        # JSON report
        json_report = json.dumps(report, indent=2, default=str)

        # Markdown report
        markdown = f"""
# QuantOS V1 — Backtest Report

## Summary
- **Symbol**: {symbol}
- **Feature Version**: {version}
- **Target Horizon**: {config.model.target_horizon} minutes
- **Evaluation Period**: {result.get('backtest', {}).get('start_time', 'N/A')} to {result.get('backtest', {}).get('end_time', 'N/A')}
- **Initial Capital**: ${config.backtest.initial_capital:.2f}
- **Fee**: {config.backtest.fee_bps:.2f} bps
- **Slippage**: {config.backtest.slippage_bps:.2f} bps
- **Status**: {report['status']}

## Backtest Metrics
"""
        bt = result.get("backtest", {})
        metrics = bt.get("metrics", {})
        if metrics:
            for k, v in metrics.items():
                markdown += f"- **{k}**: {v:.4f}\n"
        else:
            markdown += "- No metrics available.\n"

        markdown += "\n## Walk-Forward Validation\n"
        wf = result.get("walkforward", {})
        if wf.get("status") == "success":
            markdown += f"- Number of windows: {wf.get('num_windows', 0)}\n"
            agg = wf.get("aggregated", {})
            for k, v in agg.items():
                if v is not None:
                    markdown += f"- **{k}**: {v:.4f}\n"
        else:
            markdown += f"- Status: {wf.get('status', 'unknown')}\n"

        markdown += "\n## Monte Carlo Simulation\n"
        mc = result.get("montecarlo", {})
        if mc.get("status") == "success":
            markdown += f"- Iterations: {mc.get('n_iterations', 0)}\n"
            markdown += f"- Seed: {mc.get('seed', 0)}\n"
            dist = mc.get("distributions", {})
            for key, vals in dist.items():
                if isinstance(vals, dict):
                    markdown += f"- **{key}**: mean={vals.get('mean', 0):.4f}, std={vals.get('std', 0):.4f}, 5%={vals.get('q05', 0):.4f}, 95%={vals.get('q95', 0):.4f}\n"
        else:
            markdown += f"- Status: {mc.get('status', 'unknown')}\n"

        markdown += "\n## Data Sufficiency\n"
        bt_data = bt.get("data_sufficiency", {})
        if bt_data:
            for k, v in bt_data.items():
                markdown += f"- **{k}**: {v}\n"
        else:
            markdown += "- No data sufficiency info.\n"

        markdown += "\n## Final Status\n"
        markdown += f"**{report['status']}**\n"

        return {"json": json_report, "markdown": markdown}

    @staticmethod
    def save(report_dict: Dict[str, str], output_dir: Path, symbol: str, version: str) -> None:
        """Save JSON and Markdown reports to disk."""
        output_dir.mkdir(parents=True, exist_ok=True)
        # Save JSON
        json_path = output_dir / f"{symbol}_{version}_report.json"
        with open(json_path, "w") as f:
            f.write(report_dict["json"])
        logger.info(f"JSON report saved to {json_path}")
        # Save Markdown
        md_path = output_dir / f"{symbol}_{version}_report.md"
        with open(md_path, "w") as f:
            f.write(report_dict["markdown"])
        logger.info(f"Markdown report saved to {md_path}")