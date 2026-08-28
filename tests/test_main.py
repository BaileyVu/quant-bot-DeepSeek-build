import subprocess
import sys
from pathlib import Path

def test_main_startup():
    # This can be run as a subprocess or import main, but we'll test via CLI
    result = subprocess.run(
        [sys.executable, "-m", "quantos.cli", "start"],
        capture_output=True,
        text=True,
        env={"QUANTOS_CONFIG": str(Path("config/config.yaml"))},
    )
    assert result.returncode == 0
    assert "QuantOS started successfully" in result.stdout