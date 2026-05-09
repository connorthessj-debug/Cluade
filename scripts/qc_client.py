"""
qc_client.py — Gate 2: QuantConnect Cloud REST API client.

Auth: SHA-256(api_token:unix_timestamp) → Base64 Basic auth.
Full workflow: create project → upload file → compile → backtest → poll → results → cleanup.

Env vars required (set in Render dashboard or .env):
    QC_USER_ID  — your numeric QuantConnect user ID
    QC_API_KEY  — your QuantConnect API token (from account settings)

QuantConnect API docs: https://www.quantconnect.com/docs/v2/our-platform/api-reference
"""

import hashlib
import base64
import time
import json
import os
import requests
from datetime import datetime, timezone
from typing import Any

QC_BASE = "https://www.quantconnect.com/api/v2"


class QCError(Exception):
    pass


class QCClient:
    def __init__(self, user_id: str | None = None, api_key: str | None = None):
        self.user_id = user_id or os.environ.get("QC_USER_ID", "")
        self.api_key = api_key or os.environ.get("QC_API_KEY", "")
        if not self.user_id or not self.api_key:
            raise QCError("QC_USER_ID and QC_API_KEY must be set")

    # ── auth ──────────────────────────────────────────────────────────────────

    def _auth_headers(self) -> dict:
        ts = str(int(time.time()))
        hashed = hashlib.sha256(f"{self.api_key}:{ts}".encode()).hexdigest()
        token  = base64.b64encode(f"{self.user_id}:{hashed}".encode()).decode()
        return {
            "Authorization": f"Basic {token}",
            "Timestamp":     ts,
        }

    def _get(self, path: str, params: dict | None = None) -> dict:
        resp = requests.get(f"{QC_BASE}/{path.lstrip('/')}",
                            headers=self._auth_headers(),
                            params=params or {}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success", True):
            raise QCError(f"QC API error: {data.get('errors', data)}")
        return data

    def _post(self, path: str, payload: dict) -> dict:
        resp = requests.post(f"{QC_BASE}/{path.lstrip('/')}",
                             headers=self._auth_headers(),
                             json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success", True):
            raise QCError(f"QC API error: {data.get('errors', data)}")
        return data

    def _delete(self, path: str, payload: dict) -> dict:
        resp = requests.delete(f"{QC_BASE}/{path.lstrip('/')}",
                               headers=self._auth_headers(),
                               json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()

    # ── project lifecycle ────────────────────────────────────────────────────

    def create_project(self, name: str, language: str = "Py") -> int:
        data = self._post("/projects/create", {"name": name, "language": language})
        return data["projects"][0]["projectId"]

    def delete_project(self, project_id: int) -> None:
        self._delete("/projects/delete", {"projectId": project_id})

    def add_file(self, project_id: int, filename: str, content: str) -> None:
        self._post("/files/create", {
            "projectId": project_id,
            "name":      filename,
            "content":   content,
        })

    def update_file(self, project_id: int, filename: str, content: str) -> None:
        self._post("/files/update", {
            "projectId": project_id,
            "name":      filename,
            "content":   content,
        })

    # ── compile ───────────────────────────────────────────────────────────────

    def compile(self, project_id: int, max_wait: int = 60) -> str:
        data = self._post("/compile/create", {"projectId": project_id})
        compile_id = data["compileId"]

        deadline = time.time() + max_wait
        while time.time() < deadline:
            status = self._get("/compile/read",
                               {"projectId": project_id, "compileId": compile_id})
            state = status.get("state", "")
            if state == "BuildSuccess":
                return compile_id
            if state == "BuildError":
                errors = status.get("logs", status.get("errors", "unknown"))
                raise QCError(f"Compilation failed: {errors}")
            time.sleep(2)

        raise QCError(f"Compilation timed out after {max_wait}s")

    # ── backtest ──────────────────────────────────────────────────────────────

    def create_backtest(self, project_id: int, compile_id: str,
                        name: str = "trading-ops") -> str:
        data = self._post("/backtests/create", {
            "projectId":    project_id,
            "compileId":    compile_id,
            "backtestName": name,
        })
        return data["backtest"]["backtestId"]

    def poll_backtest(self, project_id: int, backtest_id: str,
                      max_wait: int = 1800, poll_interval: int = 8) -> dict:
        deadline = time.time() + max_wait
        while time.time() < deadline:
            data = self._get("/backtests/read",
                             {"projectId": project_id, "backtestId": backtest_id})
            bt = data.get("backtest", {})
            completed = bt.get("completed", False)
            progress  = bt.get("progress", 0)
            print(f"[qc_client] Backtest progress: {progress*100:.0f}%", flush=True)
            if completed:
                return bt
            time.sleep(poll_interval)

        raise QCError(f"Backtest timed out after {max_wait}s")

    # ── result parsing ────────────────────────────────────────────────────────

    def parse_results(self, bt: dict, symbol: str, strategy: str,
                      resolution: str) -> dict:
        stats   = bt.get("result", {}).get("Statistics", {})
        charts  = bt.get("result", {}).get("Charts", {})
        rt_stats = bt.get("result", {}).get("RuntimeStatistics", {})

        def _f(key: str, default: float = 0.0) -> float:
            try:
                v = stats.get(key, rt_stats.get(key, default))
                return float(str(v).replace("%", "").strip())
            except (ValueError, TypeError):
                return default

        def _pct(key: str) -> float:
            v = _f(key)
            # QC returns some stats as ratios, some as percentages
            return v if abs(v) <= 1 else v / 100

        equity_curve = []
        equity_series = (charts.get("Strategy Equity", {})
                               .get("Series", {})
                               .get("Equity", {})
                               .get("Values", []))
        for p in equity_series:
            equity_curve.append({"t": p["x"], "v": p["y"]})

        dd_series = (charts.get("Drawdown", {})
                          .get("Series", {})
                          .get("Drawdown", {})
                          .get("Values", []))

        return {
            "source":               "qc_cloud",
            "symbol":               symbol,
            "strategy":             strategy,
            "resolution":           resolution,
            "run_at":               datetime.now(timezone.utc).isoformat(),
            "backtest_id":          bt.get("backtestId", ""),
            "total_return_pct":     round(_f("Net Profit"), 4) * 100,
            "cagr_pct":             round(_f("Compounding Annual Return"), 4) * 100,
            "sharpe_ratio":         round(_f("Sharpe Ratio"), 3),
            "sortino_ratio":        round(_f("Sortino Ratio"), 3),
            "max_drawdown_pct":     round(-abs(_f("Drawdown")), 2),
            "win_rate_pct":         round(_f("Win Rate") * 100, 1),
            "profit_factor":        round(_f("Profit-Loss Ratio"), 3),
            "n_trades":             int(_f("Total Trades")),
            "alpha":                round(_f("Alpha"), 4),
            "beta":                 round(_f("Beta"), 4),
            "information_ratio":    round(_f("Information Ratio"), 3),
            "probabilistic_sharpe": round(_f("Probabilistic Sharpe Ratio"), 3),
            "total_fees":           round(_f("Total Fees"), 2),
            "capacity":             stats.get("Estimated Strategy Capacity", "—"),
            "equity_curve":         equity_curve,
            "drawdown_series":      [{"t": p["x"], "v": p["y"]} for p in dd_series],
            "rolling_stats":        bt.get("result", {}).get("RollingStatistics", []),
        }

    # ── full workflow ─────────────────────────────────────────────────────────

    def run_backtest(
        self,
        symbol: str,
        strategy: str,
        resolution: str,
        algorithm_code: str,
        project_prefix: str = "trading-ops",
    ) -> dict:
        """
        Full QC Cloud backtest workflow:
        create project → upload code → compile → backtest → parse → cleanup.
        Returns parsed result dict compatible with our verdict format.
        """
        project_name = f"{project_prefix}-{symbol}-{strategy}-{int(time.time())}"
        project_id   = None

        try:
            print(f"[qc_client] Creating project: {project_name}", flush=True)
            project_id = self.create_project(project_name)

            print("[qc_client] Uploading algorithm...", flush=True)
            self.add_file(project_id, "main.py", algorithm_code)

            print("[qc_client] Compiling...", flush=True)
            compile_id = self.compile(project_id)

            print("[qc_client] Starting backtest...", flush=True)
            backtest_id = self.create_backtest(project_id, compile_id, project_name)

            print(f"[qc_client] Backtest ID: {backtest_id} — polling...", flush=True)
            bt = self.poll_backtest(project_id, backtest_id)

            return self.parse_results(bt, symbol, strategy, resolution)

        finally:
            if project_id is not None:
                try:
                    self.delete_project(project_id)
                    print("[qc_client] Project cleaned up.", flush=True)
                except Exception:
                    pass
