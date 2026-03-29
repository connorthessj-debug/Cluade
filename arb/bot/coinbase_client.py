"""
Coinbase Advanced Trade API client with JWT authentication.
Handles order placement, account queries, and market data.
"""

import os
import time
import json
import secrets
import logging
from pathlib import Path

import requests
import jwt
from cryptography.hazmat.primitives import serialization

logger = logging.getLogger("coinbase")

BASE_URL = "https://api.coinbase.com"


class CoinbaseClient:
    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        # Unescape literal \n in PEM keys
        self.api_secret = api_secret.replace("\\n", "\n")
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def _build_jwt(self, method: str, path: str) -> str:
        uri = f"{method.upper()} {BASE_URL.replace('https://', '')}{path}"
        now = int(time.time())
        payload = {
            "sub": self.api_key,
            "iss": "cdp",
            "aud": ["cdp_service"],
            "nbf": now,
            "exp": now + 120,
            "uris": [uri],
        }
        private_key = serialization.load_pem_private_key(
            self.api_secret.encode("utf-8"), password=None
        )
        token = jwt.encode(
            payload, private_key, algorithm="ES256",
            headers={"kid": self.api_key, "nonce": secrets.token_hex(16), "typ": "JWT"},
        )
        return token

    def _request(self, method: str, path: str, params=None, body=None):
        token = self._build_jwt(method, path)
        headers = {"Authorization": f"Bearer {token}"}

        url = BASE_URL + path
        if method == "GET":
            resp = self.session.get(url, params=params, headers=headers, timeout=10)
        elif method == "POST":
            resp = self.session.post(url, json=body, headers=headers, timeout=10)
        else:
            raise ValueError(f"Unsupported method: {method}")

        if resp.status_code != 200:
            logger.error(f"API {method} {path} -> {resp.status_code}: {resp.text}")
        resp.raise_for_status()
        return resp.json()

    # --- Market Data ---

    def get_product(self, product_id: str) -> dict:
        return self._request("GET", f"/api/v3/brokerage/products/{product_id}")

    def get_best_bid_ask(self, product_id: str) -> dict:
        data = self._request("GET", "/api/v3/brokerage/best_bid_ask",
                             params={"product_ids": product_id})
        books = data.get("pricebooks", [])
        if books:
            book = books[0]
            bids = book.get("bids", [])
            asks = book.get("asks", [])
            return {
                "bid": float(bids[0]["price"]) if bids else 0,
                "ask": float(asks[0]["price"]) if asks else 0,
                "bid_size": float(bids[0]["size"]) if bids else 0,
                "ask_size": float(asks[0]["size"]) if asks else 0,
            }
        return {"bid": 0, "ask": 0, "bid_size": 0, "ask_size": 0}

    def get_candles(self, product_id: str, start: int, end: int, granularity: str = "ONE_HOUR") -> list:
        data = self._request("GET", f"/api/v3/brokerage/products/{product_id}/candles",
                             params={"start": str(start), "end": str(end), "granularity": granularity})
        return data.get("candles", [])

    # --- Accounts ---

    def get_accounts(self) -> list:
        data = self._request("GET", "/api/v3/brokerage/accounts", params={"limit": "100"})
        return data.get("accounts", [])

    def get_balance(self, currency: str) -> float:
        accounts = self.get_accounts()
        for acc in accounts:
            if acc.get("currency") == currency:
                return float(acc.get("available_balance", {}).get("value", 0))
        return 0.0

    # --- Orders ---

    def place_limit_order(self, product_id: str, side: str, price: float,
                          base_size: float, client_order_id: str = None) -> dict:
        """Place a limit order (0% maker fee on Coinbase Advanced)."""
        if not client_order_id:
            client_order_id = secrets.token_hex(16)

        body = {
            "client_order_id": client_order_id,
            "product_id": product_id,
            "side": side.upper(),
            "order_configuration": {
                "limit_limit_gtc": {
                    "base_size": f"{base_size:.2f}",
                    "limit_price": f"{price:.3f}",
                    "post_only": True,  # Ensure maker fee (0%)
                }
            }
        }
        logger.info(f"Placing {side} limit order: {base_size:.2f} {product_id} @ ${price:.3f}")
        return self._request("POST", "/api/v3/brokerage/orders", body=body)

    def place_market_order(self, product_id: str, side: str,
                           quote_size: float = None, base_size: float = None,
                           client_order_id: str = None) -> dict:
        """Place a market order. Use quote_size for USD amount, base_size for coin amount."""
        if not client_order_id:
            client_order_id = secrets.token_hex(16)

        market_config = {}
        if quote_size:
            market_config["quote_size"] = f"{quote_size:.2f}"
        elif base_size:
            market_config["base_size"] = f"{base_size:.2f}"

        body = {
            "client_order_id": client_order_id,
            "product_id": product_id,
            "side": side.upper(),
            "order_configuration": {
                "market_market_ioc": market_config
            }
        }
        logger.info(f"Placing {side} market order: {product_id} {'$' + str(quote_size) if quote_size else str(base_size) + ' coins'}")
        return self._request("POST", "/api/v3/brokerage/orders", body=body)

    def get_order(self, order_id: str) -> dict:
        return self._request("GET", f"/api/v3/brokerage/orders/historical/{order_id}")

    def list_orders(self, product_id: str = None, status: str = None, limit: int = 50) -> list:
        params = {"limit": str(limit)}
        if product_id:
            params["product_id"] = product_id
        if status:
            params["order_status"] = status
        data = self._request("GET", "/api/v3/brokerage/orders/historical", params=params)
        return data.get("orders", [])

    def cancel_orders(self, order_ids: list) -> dict:
        body = {"order_ids": order_ids}
        return self._request("POST", "/api/v3/brokerage/orders/batch_cancel", body=body)


def load_client() -> CoinbaseClient:
    """Load client from environment / .env file."""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip().strip("\"'"))

    api_key = os.environ.get("COINBASE_API_KEY")
    api_secret = os.environ.get("COINBASE_API_SECRET")
    if not api_key or not api_secret:
        raise ValueError("COINBASE_API_KEY and COINBASE_API_SECRET must be set in arb/.env")

    return CoinbaseClient(api_key, api_secret)
