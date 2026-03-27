"""Configuration loader for the trading bot system.

Loads config.yaml and .env, resolves environment variable placeholders,
validates required settings, and exposes typed access via the Config class.
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from dotenv import load_dotenv


_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")


def _resolve_env_vars(value: Any) -> Any:
    """Recursively resolve ${VAR} placeholders in config values."""
    if isinstance(value, str):
        def _replace(match):
            var_name = match.group(1)
            env_val = os.environ.get(var_name, "")
            return env_val
        return _ENV_VAR_PATTERN.sub(_replace, value)
    elif isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_resolve_env_vars(item) for item in value]
    return value


class ExchangeConfig:
    """Typed access for a single exchange configuration."""

    def __init__(self, name: str, data: Dict[str, Any]):
        self.name = name
        self.api_key: str = data.get("api_key", "")
        self.secret: str = data.get("secret", "")
        self.sandbox: bool = data.get("sandbox", False)
        self.rate_limit: int = data.get("rate_limit", 1200)
        self.options: Dict[str, Any] = data.get("options", {})


class OandaConfig:
    """Typed access for OANDA configuration."""

    def __init__(self, data: Dict[str, Any]):
        self.account_id: str = data.get("account_id", "")
        self.access_token: str = data.get("access_token", "")
        self.environment: str = data.get("environment", "practice")
        self.practice_url: str = data.get("practice_url", "https://api-fxpractice.oanda.com")
        self.live_url: str = data.get("live_url", "https://api-fxtrade.oanda.com")
        self.stream_practice_url: str = data.get("stream_practice_url", "https://stream-fxpractice.oanda.com")
        self.stream_live_url: str = data.get("stream_live_url", "https://stream-fxtrade.oanda.com")
        self.instruments: List[str] = data.get("instruments", [])

    @property
    def base_url(self) -> str:
        if self.environment == "live":
            return self.live_url
        return self.practice_url

    @property
    def stream_url(self) -> str:
        if self.environment == "live":
            return self.stream_live_url
        return self.stream_practice_url


class ArbitrageConfig:
    """Typed access for arbitrage settings."""

    def __init__(self, data: Dict[str, Any]):
        self.pairs: List[str] = data.get("pairs", [])
        self.min_spread: float = data.get("min_spread", 0.0005)
        self.poll_interval: float = data.get("poll_interval", 1.5)
        self.max_position: float = data.get("max_position", 10000)
        self.exchanges: List[str] = data.get("exchanges", [])


class ScalperConfig:
    """Typed access for scalper settings."""

    def __init__(self, data: Dict[str, Any]):
        self.timeframes: Dict[str, str] = data.get("timeframes", {})
        self.min_confluence: int = data.get("min_confluence", 60)
        self.max_risk_pct: float = data.get("max_risk_pct", 0.5)
        self.min_rr: float = data.get("min_rr", 2.0)
        self.max_positions: int = data.get("max_positions", 3)
        self.cooldown_seconds: int = data.get("cooldown_seconds", 300)


class SwingConfig:
    """Typed access for swing trading settings."""

    def __init__(self, data: Dict[str, Any]):
        self.timeframes: Dict[str, str] = data.get("timeframes", {})
        self.min_confluence: int = data.get("min_confluence", 65)
        self.max_risk_pct: float = data.get("max_risk_pct", 1.0)
        self.min_rr: float = data.get("min_rr", 3.0)
        self.max_positions: int = data.get("max_positions", 2)
        self.partial_tp: List[float] = data.get("partial_tp", [])


class RiskConfig:
    """Typed access for risk management settings."""

    def __init__(self, data: Dict[str, Any]):
        self.global_max_drawdown_pct: float = data.get("global_max_drawdown_pct", 5.0)
        self.kill_switch_enabled: bool = data.get("kill_switch_enabled", True)
        self.max_daily_loss_pct: float = data.get("max_daily_loss_pct", 2.0)
        self.correlation_check: bool = data.get("correlation_check", True)


class DashboardConfig:
    """Typed access for dashboard settings."""

    def __init__(self, data: Dict[str, Any]):
        self.host: str = data.get("host", "0.0.0.0")
        self.port: int = data.get("port", 8080)
        self.ws_port: int = data.get("ws_port", 8081)


class LearningConfig:
    """Typed access for learning/optimization settings."""

    def __init__(self, data: Dict[str, Any]):
        self.analysis_interval_hours: int = data.get("analysis_interval_hours", 24)
        self.min_sample_size: int = data.get("min_sample_size", 20)
        self.max_param_change_pct: int = data.get("max_param_change_pct", 10)


class Config:
    """Master configuration for the trading bot system.

    Loads config.yaml and .env from the project root, resolves environment
    variable placeholders, and exposes typed properties for each section.
    """

    def __init__(self, config_path: Optional[str] = None, env_path: Optional[str] = None):
        project_root = Path(__file__).resolve().parent.parent
        if config_path is None:
            config_path = str(project_root / "config.yaml")
        if env_path is None:
            env_path = str(project_root / ".env")

        # Load .env into os.environ
        load_dotenv(env_path)

        # Load and resolve YAML
        with open(config_path, "r") as f:
            raw = yaml.safe_load(f)

        self._data: Dict[str, Any] = _resolve_env_vars(raw)
        self._validate()

        # Build typed sub-configs
        self._exchanges: Dict[str, ExchangeConfig] = {
            name: ExchangeConfig(name, cfg)
            for name, cfg in self._data.get("exchanges", {}).items()
        }
        self._oanda = OandaConfig(self._data.get("oanda", {}))
        self._arbitrage = ArbitrageConfig(self._data.get("arbitrage", {}))
        self._scalper = ScalperConfig(self._data.get("scalper", {}))
        self._swing = SwingConfig(self._data.get("swing", {}))
        self._risk = RiskConfig(self._data.get("risk", {}))
        self._dashboard = DashboardConfig(self._data.get("dashboard", {}))
        self._learning = LearningConfig(self._data.get("learning", {}))

    def _validate(self) -> None:
        """Validate that required configuration sections exist."""
        required_sections = ["exchanges", "oanda", "arbitrage", "scalper", "swing", "risk"]
        missing = [s for s in required_sections if s not in self._data]
        if missing:
            raise ValueError(f"Missing required config sections: {missing}")

    @property
    def exchanges(self) -> Dict[str, ExchangeConfig]:
        return self._exchanges

    @property
    def oanda(self) -> OandaConfig:
        return self._oanda

    @property
    def arbitrage(self) -> ArbitrageConfig:
        return self._arbitrage

    @property
    def scalper(self) -> ScalperConfig:
        return self._scalper

    @property
    def swing(self) -> SwingConfig:
        return self._swing

    @property
    def risk(self) -> RiskConfig:
        return self._risk

    @property
    def dashboard(self) -> DashboardConfig:
        return self._dashboard

    @property
    def learning(self) -> LearningConfig:
        return self._learning

    @property
    def raw(self) -> Dict[str, Any]:
        """Access the raw resolved config dictionary."""
        return self._data
