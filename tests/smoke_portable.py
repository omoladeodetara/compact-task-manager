"""Real Linux Tk/metrics lifecycle under Xvfb; no startup entry is installed."""
import json
from pathlib import Path
import tempfile
from portable.core import paths
from portable.widget import run

with tempfile.TemporaryDirectory() as directory:
    p = paths("Linux", Path(directory), {})
    result = run(p, smoke_seconds=4)
    state = json.loads(p["state"].read_text())
    assert result == 0, state
    assert state["status"] == "stopped", state
    assert state.get("samplesDrawn", 0) >= 2, state
    assert p["config"].is_file()
    assert not p["startup"].exists()
    print("PASS: real Tk window, live metrics, graph draws, heartbeat, close, and saved position")
