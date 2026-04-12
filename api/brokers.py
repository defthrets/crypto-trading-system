"""
0xrex -- Broker Implementations
Real exchange API integrations for live/paper trading.
Supported: IBKR, Binance, Bybit, Kraken, OKX, Coinbase, KuCoin, CoinSpot, MEXC, Bitfinex
"""

import asyncio
import hashlib
import hmac
import json
import time
import urllib.parse
import base64
from datetime import datetime
from typing import Optional

import httpx
from loguru import logger

from api.utils import _EXECUTOR, _encrypt_creds, _decrypt_creds
from api.state import DATA_DIR


# ══════════════════════════════════════════════════════════
#  BASE CLASS
# ══════════════════════════════════════════════════════════

class BrokerBase:
    name: str = "base"
    supports_short: bool = False
    _reconnect_attempts: int = 0
    _max_reconnect: int = 5
    _last_credentials: dict = {}

    def is_connected(self) -> bool: raise NotImplementedError
    async def connect(self, **kwargs) -> None: raise NotImplementedError
    async def get_account(self) -> dict: raise NotImplementedError
    async def place_order(self, ticker: str, side: str, qty: float, price: Optional[float]) -> dict: raise NotImplementedError
    async def get_positions(self) -> list: raise NotImplementedError
    async def get_history(self) -> list: raise NotImplementedError
    async def close_position(self, ticker: str) -> dict: raise NotImplementedError

    def _store_credentials(self, **kwargs):
        """Store credentials for auto-reconnect (strips None values)."""
        self._last_credentials = {k: v for k, v in kwargs.items() if v is not None}
        self._reconnect_attempts = 0

    async def _heartbeat(self) -> bool:
        """Check broker connectivity. Returns True if healthy."""
        try:
            await asyncio.wait_for(self.get_account(), timeout=10.0)
            self._reconnect_attempts = 0
            return True
        except Exception:
            self._connected = False
            return False

    async def _auto_reconnect(self) -> bool:
        """Attempt to reconnect with exponential backoff."""
        if not self._last_credentials or self._reconnect_attempts >= self._max_reconnect:
            return False
        delay = min(2 ** self._reconnect_attempts * 5, 120)
        logger.info(f"Broker {self.name}: reconnect attempt {self._reconnect_attempts + 1} in {delay}s")
        await asyncio.sleep(delay)
        try:
            await self.connect(**self._last_credentials)
            self._reconnect_attempts = 0
            logger.info(f"Broker {self.name}: reconnected successfully")
            return True
        except Exception as e:
            self._reconnect_attempts += 1
            logger.warning(f"Broker {self.name}: reconnect failed: {e}")
            return False


# ══════════════════════════════════════════════════════════
#  IBKR (Interactive Brokers)
# ══════════════════════════════════════════════════════════

class IBKRBroker(BrokerBase):
    name = "ibkr"
    supports_short = True

    def __init__(self):
        self._ib = None
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected and self._ib is not None

    async def connect(self, host: str = "127.0.0.1", port: int = 7497, client_id: int = 1, **kwargs) -> None:
        try:
            from ib_insync import IB
        except ImportError:
            raise ImportError("ib_insync not installed. Run: pip install ib_insync")
        ib = IB()
        await asyncio.get_running_loop().run_in_executor(_EXECUTOR, lambda: ib.connect(host, int(port), clientId=int(client_id), timeout=10))
        self._ib = ib
        self._connected = True
        self._store_credentials(host=host, port=port, client_id=client_id)
        logger.info(f"IBKR connected -- {host}:{port}")

    async def get_account(self) -> dict:
        if not self.is_connected(): raise RuntimeError("IBKR not connected")
        summary = await asyncio.get_running_loop().run_in_executor(_EXECUTOR, self._ib.accountSummary)
        vals = {row.tag: row.value for row in summary}
        return {"broker": "ibkr", "account_value": float(vals.get("NetLiquidation", 0)),
                "buying_power": float(vals.get("BuyingPower", 0)), "cash": float(vals.get("TotalCashValue", 0)), "currency": "AUD"}

    async def place_order(self, ticker: str, side: str, qty: float, price: Optional[float] = None) -> dict:
        if not self.is_connected(): raise RuntimeError("IBKR not connected")
        from ib_insync import Stock, MarketOrder, LimitOrder
        contract = Stock(ticker, "SMART", "USD")
        order = LimitOrder(side.upper(), qty, price) if price else MarketOrder(side.upper(), qty)
        trade = await asyncio.get_running_loop().run_in_executor(_EXECUTOR, self._ib.placeOrder, contract, order)
        return {"order_id": trade.order.orderId, "ticker": ticker, "side": side, "qty": qty,
                "price": price, "status": trade.orderStatus.status, "timestamp": datetime.utcnow().isoformat()}

    async def get_positions(self) -> list:
        if not self.is_connected(): raise RuntimeError("IBKR not connected")
        raw = await asyncio.get_running_loop().run_in_executor(_EXECUTOR, self._ib.positions)
        return [{"ticker": p.contract.symbol, "qty": p.position, "avg_cost": round(p.avgCost, 4),
                 "market_val": None, "pnl": None, "side": "LONG" if p.position > 0 else "SHORT"} for p in raw]

    async def get_history(self) -> list:
        if not self.is_connected(): raise RuntimeError("IBKR not connected")
        fills = await asyncio.get_running_loop().run_in_executor(_EXECUTOR, self._ib.fills)
        return [{"ticker": f.contract.symbol, "side": f.execution.side, "qty": f.execution.shares,
                 "price": f.execution.price, "timestamp": str(f.execution.time)} for f in fills]

    async def close_position(self, ticker: str) -> dict:
        positions = await self.get_positions()
        pos = next((p for p in positions if p["ticker"].upper() == ticker.upper()), None)
        if not pos: raise ValueError(f"No open IBKR position in {ticker}")
        side = "SELL" if pos["qty"] > 0 else "BUY"
        return await self.place_order(ticker, side, abs(pos["qty"]), None)


# ══════════════════════════════════════════════════════════
#  BINANCE
# ══════════════════════════════════════════════════════════

class BinanceBroker(BrokerBase):
    """Binance Spot REST API — full trading support."""
    name = "binance"
    supports_short = True
    _BASE = "https://api.binance.com"

    def __init__(self):
        self._api_key: Optional[str] = None
        self._api_secret: Optional[str] = None
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def _sign(self, params: dict) -> str:
        query = urllib.parse.urlencode(params)
        return hmac.new(self._api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()

    def _headers(self) -> dict:
        return {"X-MBX-APIKEY": self._api_key}

    async def connect(self, api_key: str, api_secret: str, **kwargs) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        async with httpx.AsyncClient(timeout=10.0) as c:
            params = {"timestamp": int(time.time() * 1000)}
            params["signature"] = self._sign(params)
            r = await c.get(f"{self._BASE}/api/v3/account", params=params, headers=self._headers())
            if r.status_code == 401 or r.status_code == 403:
                raise RuntimeError("Invalid API key or signature")
            r.raise_for_status()
        self._connected = True
        self._store_credentials(api_key=api_key, api_secret=api_secret)
        logger.info("Binance connected")

    async def get_account(self) -> dict:
        if not self._connected: raise RuntimeError("Binance not connected")
        async with httpx.AsyncClient(timeout=10.0) as c:
            params = {"timestamp": int(time.time() * 1000)}
            params["signature"] = self._sign(params)
            r = await c.get(f"{self._BASE}/api/v3/account", params=params, headers=self._headers())
            r.raise_for_status()
            d = r.json()
        balances = {b["asset"]: float(b["free"]) + float(b["locked"]) for b in d.get("balances", []) if float(b["free"]) + float(b["locked"]) > 0}
        usdt = float(next((b["free"] for b in d["balances"] if b["asset"] == "USDT"), 0))
        total = usdt  # simplified — full calc would need prices for each asset
        return {"broker": "binance", "account_value": round(total, 2), "buying_power": round(usdt, 2),
                "cash": round(usdt, 2), "currency": "USDT"}

    async def place_order(self, ticker: str, side: str, qty: float, price: Optional[float] = None) -> dict:
        if not self._connected: raise RuntimeError("Binance not connected")
        symbol = ticker.replace("-", "").replace("/", "").upper()
        params = {
            "symbol": symbol, "side": side.upper(), "quantity": qty,
            "type": "LIMIT" if price else "MARKET",
            "timestamp": int(time.time() * 1000),
        }
        if price:
            params["price"] = price
            params["timeInForce"] = "GTC"
        params["signature"] = self._sign(params)
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(f"{self._BASE}/api/v3/order", params=params, headers=self._headers())
            r.raise_for_status()
            d = r.json()
        return {"order_id": str(d.get("orderId")), "ticker": ticker, "side": side.upper(), "qty": qty,
                "price": price or float(d.get("fills", [{}])[0].get("price", 0)),
                "status": d.get("status", "NEW"), "timestamp": datetime.utcnow().isoformat()}

    async def get_positions(self) -> list:
        if not self._connected: raise RuntimeError("Binance not connected")
        async with httpx.AsyncClient(timeout=10.0) as c:
            params = {"timestamp": int(time.time() * 1000)}
            params["signature"] = self._sign(params)
            r = await c.get(f"{self._BASE}/api/v3/account", params=params, headers=self._headers())
            r.raise_for_status()
            d = r.json()
        positions = []
        for b in d.get("balances", []):
            total = float(b["free"]) + float(b["locked"])
            if total > 0 and b["asset"] not in ("USDT", "BUSD", "USD"):
                positions.append({"ticker": f"{b['asset']}USDT", "qty": total, "avg_cost": 0,
                                  "market_val": None, "pnl": None, "side": "LONG"})
        return positions

    async def get_history(self) -> list:
        return []  # Binance requires symbol-specific history queries

    async def close_position(self, ticker: str) -> dict:
        positions = await self.get_positions()
        symbol = ticker.replace("-", "").replace("/", "").upper()
        pos = next((p for p in positions if p["ticker"].upper() == symbol), None)
        if not pos: raise ValueError(f"No open Binance position in {ticker}")
        return await self.place_order(ticker, "SELL", pos["qty"], None)


# ══════════════════════════════════════════════════════════
#  BYBIT
# ══════════════════════════════════════════════════════════

class BybitBroker(BrokerBase):
    """Bybit V5 Unified API — spot + derivatives trading."""
    name = "bybit"
    supports_short = True
    _BASE = "https://api.bybit.com"

    def __init__(self):
        self._api_key: Optional[str] = None
        self._api_secret: Optional[str] = None
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def _sign(self, ts: str, params_str: str) -> str:
        payload = ts + self._api_key + "5000" + params_str
        return hmac.new(self._api_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

    def _auth_headers(self, params_str: str = "") -> dict:
        ts = str(int(time.time() * 1000))
        return {
            "X-BAPI-API-KEY": self._api_key,
            "X-BAPI-TIMESTAMP": ts,
            "X-BAPI-RECV-WINDOW": "5000",
            "X-BAPI-SIGN": self._sign(ts, params_str),
            "Content-Type": "application/json",
        }

    async def connect(self, api_key: str, api_secret: str, **kwargs) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        async with httpx.AsyncClient(timeout=10.0) as c:
            params = "accountType=UNIFIED"
            r = await c.get(f"{self._BASE}/v5/account/wallet-balance?{params}", headers=self._auth_headers(params))
            d = r.json()
            if d.get("retCode") != 0:
                raise RuntimeError(f"Bybit auth failed: {d.get('retMsg', 'invalid API key')}")
        self._connected = True
        self._store_credentials(api_key=api_key, api_secret=api_secret)
        logger.info("Bybit connected")

    async def get_account(self) -> dict:
        if not self._connected: raise RuntimeError("Bybit not connected")
        async with httpx.AsyncClient(timeout=10.0) as c:
            params = "accountType=UNIFIED"
            r = await c.get(f"{self._BASE}/v5/account/wallet-balance?{params}", headers=self._auth_headers(params))
            d = r.json()
        acct = d.get("result", {}).get("list", [{}])[0]
        equity = float(acct.get("totalEquity", 0))
        available = float(acct.get("totalAvailableBalance", 0))
        return {"broker": "bybit", "account_value": round(equity, 2), "buying_power": round(available, 2),
                "cash": round(available, 2), "currency": "USDT"}

    async def place_order(self, ticker: str, side: str, qty: float, price: Optional[float] = None) -> dict:
        if not self._connected: raise RuntimeError("Bybit not connected")
        symbol = ticker.replace("-", "").replace("/", "").upper()
        body = {
            "category": "spot", "symbol": symbol, "side": side.capitalize(),
            "orderType": "Limit" if price else "Market", "qty": str(qty),
        }
        if price:
            body["price"] = str(price)
        body_str = json.dumps(body)
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(f"{self._BASE}/v5/order/create", content=body_str, headers=self._auth_headers(body_str))
            d = r.json()
        if d.get("retCode") != 0:
            raise RuntimeError(f"Bybit order failed: {d.get('retMsg')}")
        result = d.get("result", {})
        return {"order_id": result.get("orderId", ""), "ticker": ticker, "side": side.upper(), "qty": qty,
                "price": price, "status": "NEW", "timestamp": datetime.utcnow().isoformat()}

    async def get_positions(self) -> list:
        if not self._connected: raise RuntimeError("Bybit not connected")
        async with httpx.AsyncClient(timeout=10.0) as c:
            params = "accountType=UNIFIED"
            r = await c.get(f"{self._BASE}/v5/account/wallet-balance?{params}", headers=self._auth_headers(params))
            d = r.json()
        coins = d.get("result", {}).get("list", [{}])[0].get("coin", [])
        positions = []
        for coin in coins:
            qty = float(coin.get("walletBalance", 0))
            if qty > 0 and coin["coin"] not in ("USDT", "USDC"):
                positions.append({"ticker": f"{coin['coin']}USDT", "qty": qty, "avg_cost": 0,
                                  "market_val": float(coin.get("usdValue", 0)),
                                  "pnl": float(coin.get("unrealisedPnl", 0)), "side": "LONG"})
        return positions

    async def get_history(self) -> list:
        if not self._connected: raise RuntimeError("Bybit not connected")
        async with httpx.AsyncClient(timeout=10.0) as c:
            params = "category=spot&limit=50"
            r = await c.get(f"{self._BASE}/v5/order/history?{params}", headers=self._auth_headers(params))
            d = r.json()
        orders = d.get("result", {}).get("list", [])
        return [{"ticker": o.get("symbol"), "side": o.get("side"), "qty": float(o.get("qty", 0)),
                 "price": float(o.get("avgPrice", 0)), "timestamp": o.get("createdTime")} for o in orders if o.get("orderStatus") == "Filled"]

    async def close_position(self, ticker: str) -> dict:
        positions = await self.get_positions()
        symbol = ticker.replace("-", "").replace("/", "").upper()
        pos = next((p for p in positions if p["ticker"].upper() == symbol), None)
        if not pos: raise ValueError(f"No open Bybit position in {ticker}")
        return await self.place_order(ticker, "SELL", pos["qty"], None)


# ══════════════════════════════════════════════════════════
#  KRAKEN
# ══════════════════════════════════════════════════════════

class KrakenBroker(BrokerBase):
    """Kraken REST API — spot + margin trading."""
    name = "kraken"
    supports_short = True
    _BASE = "https://api.kraken.com"

    def __init__(self):
        self._api_key: Optional[str] = None
        self._api_secret: Optional[str] = None
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def _sign(self, url_path: str, data: dict) -> str:
        nonce = data["nonce"]
        post_data = urllib.parse.urlencode(data)
        encoded = (str(nonce) + post_data).encode()
        message = url_path.encode() + hashlib.sha256(encoded).digest()
        sig = hmac.new(base64.b64decode(self._api_secret), message, hashlib.sha512)
        return base64.b64encode(sig.digest()).decode()

    def _auth_headers(self, url_path: str, data: dict) -> dict:
        return {"API-Key": self._api_key, "API-Sign": self._sign(url_path, data),
                "Content-Type": "application/x-www-form-urlencoded"}

    async def connect(self, api_key: str, api_secret: str, **kwargs) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        path = "/0/private/Balance"
        data = {"nonce": int(time.time() * 1000)}
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(f"{self._BASE}{path}", data=data, headers=self._auth_headers(path, data))
            d = r.json()
            if d.get("error"):
                raise RuntimeError(f"Kraken auth failed: {d['error']}")
        self._connected = True
        self._store_credentials(api_key=api_key, api_secret=api_secret)
        logger.info("Kraken connected")

    async def get_account(self) -> dict:
        if not self._connected: raise RuntimeError("Kraken not connected")
        path = "/0/private/Balance"
        data = {"nonce": int(time.time() * 1000)}
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(f"{self._BASE}{path}", data=data, headers=self._auth_headers(path, data))
            d = r.json()
        balances = d.get("result", {})
        # ZUSD = USD on Kraken
        usd = float(balances.get("ZUSD", balances.get("USDT", 0)))
        total = sum(float(v) for v in balances.values()) if balances else 0
        return {"broker": "kraken", "account_value": round(total, 2), "buying_power": round(usd, 2),
                "cash": round(usd, 2), "currency": "USD"}

    async def place_order(self, ticker: str, side: str, qty: float, price: Optional[float] = None) -> dict:
        if not self._connected: raise RuntimeError("Kraken not connected")
        pair = ticker.replace("-", "").replace("/", "").upper()
        path = "/0/private/AddOrder"
        data = {
            "nonce": int(time.time() * 1000),
            "pair": pair, "type": side.lower(), "ordertype": "limit" if price else "market",
            "volume": str(qty),
        }
        if price:
            data["price"] = str(price)
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(f"{self._BASE}{path}", data=data, headers=self._auth_headers(path, data))
            d = r.json()
        if d.get("error"):
            raise RuntimeError(f"Kraken order failed: {d['error']}")
        txid = d.get("result", {}).get("txid", [""])[0]
        return {"order_id": txid, "ticker": ticker, "side": side.upper(), "qty": qty,
                "price": price, "status": "NEW", "timestamp": datetime.utcnow().isoformat()}

    async def get_positions(self) -> list:
        if not self._connected: raise RuntimeError("Kraken not connected")
        path = "/0/private/Balance"
        data = {"nonce": int(time.time() * 1000)}
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(f"{self._BASE}{path}", data=data, headers=self._auth_headers(path, data))
            d = r.json()
        positions = []
        stables = ("ZUSD", "USDT", "USDC", "USD")
        for asset, bal in d.get("result", {}).items():
            qty = float(bal)
            if qty > 0 and asset not in stables:
                clean = asset.lstrip("XZ") if len(asset) == 4 and asset[0] in "XZ" else asset
                positions.append({"ticker": f"{clean}USD", "qty": qty, "avg_cost": 0,
                                  "market_val": None, "pnl": None, "side": "LONG"})
        return positions

    async def get_history(self) -> list:
        if not self._connected: raise RuntimeError("Kraken not connected")
        path = "/0/private/TradesHistory"
        data = {"nonce": int(time.time() * 1000)}
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(f"{self._BASE}{path}", data=data, headers=self._auth_headers(path, data))
            d = r.json()
        trades = d.get("result", {}).get("trades", {})
        return [{"ticker": t.get("pair"), "side": t.get("type", "").upper(), "qty": float(t.get("vol", 0)),
                 "price": float(t.get("price", 0)), "timestamp": str(t.get("time"))} for t in trades.values()]

    async def close_position(self, ticker: str) -> dict:
        positions = await self.get_positions()
        symbol = ticker.replace("-", "").replace("/", "").upper()
        pos = next((p for p in positions if symbol in p["ticker"].upper()), None)
        if not pos: raise ValueError(f"No open Kraken position in {ticker}")
        return await self.place_order(ticker, "SELL", pos["qty"], None)


# ══════════════════════════════════════════════════════════
#  OKX
# ══════════════════════════════════════════════════════════

class OKXBroker(BrokerBase):
    """OKX V5 REST API — spot + derivatives trading."""
    name = "okx"
    supports_short = True
    _BASE = "https://www.okx.com"

    def __init__(self):
        self._api_key: Optional[str] = None
        self._api_secret: Optional[str] = None
        self._passphrase: Optional[str] = None
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def _sign(self, ts: str, method: str, path: str, body: str = "") -> str:
        message = ts + method + path + body
        return base64.b64encode(hmac.new(self._api_secret.encode(), message.encode(), hashlib.sha256).digest()).decode()

    def _auth_headers(self, method: str, path: str, body: str = "") -> dict:
        ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        return {
            "OK-ACCESS-KEY": self._api_key,
            "OK-ACCESS-SIGN": self._sign(ts, method, path, body),
            "OK-ACCESS-TIMESTAMP": ts,
            "OK-ACCESS-PASSPHRASE": self._passphrase or "",
            "Content-Type": "application/json",
        }

    async def connect(self, api_key: str, api_secret: str, passphrase: str = "", **kwargs) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._passphrase = passphrase
        path = "/api/v5/account/balance"
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"{self._BASE}{path}", headers=self._auth_headers("GET", path))
            d = r.json()
            if d.get("code") != "0":
                raise RuntimeError(f"OKX auth failed: {d.get('msg', 'invalid API key')}")
        self._connected = True
        self._store_credentials(api_key=api_key, api_secret=api_secret, passphrase=passphrase)
        logger.info("OKX connected")

    async def get_account(self) -> dict:
        if not self._connected: raise RuntimeError("OKX not connected")
        path = "/api/v5/account/balance"
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"{self._BASE}{path}", headers=self._auth_headers("GET", path))
            d = r.json()
        acct = d.get("data", [{}])[0]
        equity = float(acct.get("totalEq", 0))
        available = float(acct.get("availBal", acct.get("availEq", 0)))
        return {"broker": "okx", "account_value": round(equity, 2), "buying_power": round(available, 2),
                "cash": round(available, 2), "currency": "USDT"}

    async def place_order(self, ticker: str, side: str, qty: float, price: Optional[float] = None) -> dict:
        if not self._connected: raise RuntimeError("OKX not connected")
        inst_id = ticker.replace("/", "-").upper()
        if "-" not in inst_id:
            # Convert BTCUSDT → BTC-USDT
            for stable in ("USDT", "USDC", "USD"):
                if inst_id.endswith(stable):
                    inst_id = inst_id[:-len(stable)] + "-" + stable
                    break
        path = "/api/v5/trade/order"
        body = {
            "instId": inst_id, "tdMode": "cash", "side": side.lower(),
            "ordType": "limit" if price else "market", "sz": str(qty),
        }
        if price:
            body["px"] = str(price)
        body_str = json.dumps(body)
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(f"{self._BASE}{path}", content=body_str, headers=self._auth_headers("POST", path, body_str))
            d = r.json()
        if d.get("code") != "0":
            raise RuntimeError(f"OKX order failed: {d.get('msg')}")
        result = d.get("data", [{}])[0]
        return {"order_id": result.get("ordId", ""), "ticker": ticker, "side": side.upper(), "qty": qty,
                "price": price, "status": "NEW", "timestamp": datetime.utcnow().isoformat()}

    async def get_positions(self) -> list:
        if not self._connected: raise RuntimeError("OKX not connected")
        path = "/api/v5/account/balance"
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"{self._BASE}{path}", headers=self._auth_headers("GET", path))
            d = r.json()
        details = d.get("data", [{}])[0].get("details", [])
        positions = []
        for coin in details:
            qty = float(coin.get("availBal", 0)) + float(coin.get("frozenBal", 0))
            if qty > 0 and coin["ccy"] not in ("USDT", "USDC"):
                positions.append({"ticker": f"{coin['ccy']}-USDT", "qty": qty, "avg_cost": 0,
                                  "market_val": float(coin.get("eqUsd", 0)),
                                  "pnl": None, "side": "LONG"})
        return positions

    async def get_history(self) -> list:
        if not self._connected: raise RuntimeError("OKX not connected")
        path = "/api/v5/trade/orders-history-archive?instType=SPOT&limit=50"
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"{self._BASE}{path}", headers=self._auth_headers("GET", path))
            d = r.json()
        orders = d.get("data", [])
        return [{"ticker": o.get("instId"), "side": o.get("side", "").upper(), "qty": float(o.get("fillSz", 0)),
                 "price": float(o.get("fillPx", 0)), "timestamp": o.get("uTime")} for o in orders if o.get("state") == "filled"]

    async def close_position(self, ticker: str) -> dict:
        positions = await self.get_positions()
        inst = ticker.replace("/", "-").upper()
        pos = next((p for p in positions if inst in p["ticker"].upper()), None)
        if not pos: raise ValueError(f"No open OKX position in {ticker}")
        return await self.place_order(ticker, "SELL", pos["qty"], None)


# ══════════════════════════════════════════════════════════
#  COINBASE (Advanced Trade API)
# ══════════════════════════════════════════════════════════

class CoinbaseBroker(BrokerBase):
    """Coinbase Advanced Trade REST API — spot only."""
    name = "coinbase"
    supports_short = False
    _BASE = "https://api.coinbase.com"

    def __init__(self):
        self._api_key: Optional[str] = None
        self._api_secret: Optional[str] = None
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def _sign(self, ts: str, method: str, path: str, body: str = "") -> str:
        message = ts + method + path + body
        return hmac.new(self._api_secret.encode(), message.encode(), hashlib.sha256).hexdigest()

    def _auth_headers(self, method: str, path: str, body: str = "") -> dict:
        ts = str(int(time.time()))
        return {
            "CB-ACCESS-KEY": self._api_key,
            "CB-ACCESS-SIGN": self._sign(ts, method, path, body),
            "CB-ACCESS-TIMESTAMP": ts,
            "Content-Type": "application/json",
        }

    async def connect(self, api_key: str, api_secret: str, **kwargs) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        path = "/api/v3/brokerage/accounts"
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"{self._BASE}{path}", headers=self._auth_headers("GET", path))
            if r.status_code in (401, 403):
                raise RuntimeError("Invalid Coinbase API key or signature")
            r.raise_for_status()
        self._connected = True
        self._store_credentials(api_key=api_key, api_secret=api_secret)
        logger.info("Coinbase connected")

    async def get_account(self) -> dict:
        if not self._connected: raise RuntimeError("Coinbase not connected")
        path = "/api/v3/brokerage/accounts"
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"{self._BASE}{path}", headers=self._auth_headers("GET", path))
            r.raise_for_status()
            d = r.json()
        accounts = d.get("accounts", [])
        usd = sum(float(a.get("available_balance", {}).get("value", 0)) for a in accounts if a.get("currency") in ("USD", "USDT"))
        total = sum(float(a.get("available_balance", {}).get("value", 0)) for a in accounts)
        return {"broker": "coinbase", "account_value": round(total, 2), "buying_power": round(usd, 2),
                "cash": round(usd, 2), "currency": "USD"}

    async def place_order(self, ticker: str, side: str, qty: float, price: Optional[float] = None) -> dict:
        if not self._connected: raise RuntimeError("Coinbase not connected")
        product_id = ticker.replace("/", "-").upper()
        if "-" not in product_id:
            for stable in ("USDT", "USDC", "USD"):
                if product_id.endswith(stable):
                    product_id = product_id[:-len(stable)] + "-" + stable
                    break
        import uuid
        path = "/api/v3/brokerage/orders"
        body = {
            "client_order_id": str(uuid.uuid4()),
            "product_id": product_id,
            "side": side.upper(),
        }
        if price:
            body["order_configuration"] = {"limit_limit_gtc": {"base_size": str(qty), "limit_price": str(price)}}
        else:
            if side.upper() == "BUY":
                body["order_configuration"] = {"market_market_ioc": {"quote_size": str(qty)}}
            else:
                body["order_configuration"] = {"market_market_ioc": {"base_size": str(qty)}}
        body_str = json.dumps(body)
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(f"{self._BASE}{path}", content=body_str, headers=self._auth_headers("POST", path, body_str))
            r.raise_for_status()
            d = r.json()
        return {"order_id": d.get("order_id", ""), "ticker": ticker, "side": side.upper(), "qty": qty,
                "price": price, "status": "NEW", "timestamp": datetime.utcnow().isoformat()}

    async def get_positions(self) -> list:
        if not self._connected: raise RuntimeError("Coinbase not connected")
        path = "/api/v3/brokerage/accounts"
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"{self._BASE}{path}", headers=self._auth_headers("GET", path))
            r.raise_for_status()
            d = r.json()
        positions = []
        for a in d.get("accounts", []):
            bal = float(a.get("available_balance", {}).get("value", 0))
            ccy = a.get("currency", "")
            if bal > 0 and ccy not in ("USD", "USDT", "USDC"):
                positions.append({"ticker": f"{ccy}-USD", "qty": bal, "avg_cost": 0,
                                  "market_val": None, "pnl": None, "side": "LONG"})
        return positions

    async def get_history(self) -> list:
        if not self._connected: raise RuntimeError("Coinbase not connected")
        path = "/api/v3/brokerage/orders/historical/fills?limit=50"
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"{self._BASE}{path}", headers=self._auth_headers("GET", path))
            r.raise_for_status()
            d = r.json()
        return [{"ticker": f.get("product_id"), "side": f.get("side", "").upper(), "qty": float(f.get("size", 0)),
                 "price": float(f.get("price", 0)), "timestamp": f.get("trade_time")} for f in d.get("fills", [])]

    async def close_position(self, ticker: str) -> dict:
        positions = await self.get_positions()
        product = ticker.replace("/", "-").upper()
        pos = next((p for p in positions if product in p["ticker"].upper()), None)
        if not pos: raise ValueError(f"No open Coinbase position in {ticker}")
        return await self.place_order(ticker, "SELL", pos["qty"], None)


# ══════════════════════════════════════════════════════════
#  KUCOIN
# ══════════════════════════════════════════════════════════

class KucoinBroker(BrokerBase):
    """KuCoin REST API — spot + margin trading."""
    name = "kucoin"
    supports_short = True
    _BASE = "https://api.kucoin.com"

    def __init__(self):
        self._api_key: Optional[str] = None
        self._api_secret: Optional[str] = None
        self._passphrase: Optional[str] = None
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def _sign(self, ts: str, method: str, path: str, body: str = "") -> str:
        message = ts + method + path + body
        return base64.b64encode(hmac.new(self._api_secret.encode(), message.encode(), hashlib.sha256).digest()).decode()

    def _auth_headers(self, method: str, path: str, body: str = "") -> dict:
        ts = str(int(time.time() * 1000))
        passphrase_sign = base64.b64encode(
            hmac.new(self._api_secret.encode(), (self._passphrase or "").encode(), hashlib.sha256).digest()
        ).decode()
        return {
            "KC-API-KEY": self._api_key,
            "KC-API-SIGN": self._sign(ts, method, path, body),
            "KC-API-TIMESTAMP": ts,
            "KC-API-PASSPHRASE": passphrase_sign,
            "KC-API-KEY-VERSION": "2",
            "Content-Type": "application/json",
        }

    async def connect(self, api_key: str, api_secret: str, passphrase: str = "", **kwargs) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._passphrase = passphrase
        path = "/api/v1/accounts"
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"{self._BASE}{path}", headers=self._auth_headers("GET", path))
            d = r.json()
            if d.get("code") != "200000":
                raise RuntimeError(f"KuCoin auth failed: {d.get('msg', 'invalid API key')}")
        self._connected = True
        self._store_credentials(api_key=api_key, api_secret=api_secret, passphrase=passphrase)
        logger.info("KuCoin connected")

    async def get_account(self) -> dict:
        if not self._connected: raise RuntimeError("KuCoin not connected")
        path = "/api/v1/accounts"
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"{self._BASE}{path}", headers=self._auth_headers("GET", path))
            d = r.json()
        accounts = d.get("data", [])
        usdt = sum(float(a.get("balance", 0)) for a in accounts if a.get("currency") == "USDT" and a.get("type") == "trade")
        total = sum(float(a.get("balance", 0)) for a in accounts if a.get("type") == "trade")
        return {"broker": "kucoin", "account_value": round(total, 2), "buying_power": round(usdt, 2),
                "cash": round(usdt, 2), "currency": "USDT"}

    async def place_order(self, ticker: str, side: str, qty: float, price: Optional[float] = None) -> dict:
        if not self._connected: raise RuntimeError("KuCoin not connected")
        import uuid
        symbol = ticker.replace("/", "-").upper()
        if "-" not in symbol:
            for stable in ("USDT", "USDC"):
                if symbol.endswith(stable):
                    symbol = symbol[:-len(stable)] + "-" + stable
                    break
        path = "/api/v1/orders"
        body = {
            "clientOid": str(uuid.uuid4()), "side": side.lower(), "symbol": symbol,
            "type": "limit" if price else "market",
        }
        if price:
            body["price"] = str(price)
            body["size"] = str(qty)
        else:
            if side.upper() == "BUY":
                body["funds"] = str(qty)
            else:
                body["size"] = str(qty)
        body_str = json.dumps(body)
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(f"{self._BASE}{path}", content=body_str, headers=self._auth_headers("POST", path, body_str))
            d = r.json()
        if d.get("code") != "200000":
            raise RuntimeError(f"KuCoin order failed: {d.get('msg')}")
        return {"order_id": d.get("data", {}).get("orderId", ""), "ticker": ticker, "side": side.upper(), "qty": qty,
                "price": price, "status": "NEW", "timestamp": datetime.utcnow().isoformat()}

    async def get_positions(self) -> list:
        if not self._connected: raise RuntimeError("KuCoin not connected")
        path = "/api/v1/accounts"
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"{self._BASE}{path}", headers=self._auth_headers("GET", path))
            d = r.json()
        positions = []
        for a in d.get("data", []):
            bal = float(a.get("balance", 0))
            ccy = a.get("currency", "")
            if bal > 0 and ccy not in ("USDT", "USDC", "USD") and a.get("type") == "trade":
                positions.append({"ticker": f"{ccy}-USDT", "qty": bal, "avg_cost": 0,
                                  "market_val": None, "pnl": None, "side": "LONG"})
        return positions

    async def get_history(self) -> list:
        if not self._connected: raise RuntimeError("KuCoin not connected")
        path = "/api/v1/fills?pageSize=50"
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"{self._BASE}{path}", headers=self._auth_headers("GET", path))
            d = r.json()
        items = d.get("data", {}).get("items", [])
        return [{"ticker": f.get("symbol"), "side": f.get("side", "").upper(), "qty": float(f.get("size", 0)),
                 "price": float(f.get("price", 0)), "timestamp": f.get("createdAt")} for f in items]

    async def close_position(self, ticker: str) -> dict:
        positions = await self.get_positions()
        symbol = ticker.replace("/", "-").upper()
        pos = next((p for p in positions if symbol in p["ticker"].upper()), None)
        if not pos: raise ValueError(f"No open KuCoin position in {ticker}")
        return await self.place_order(ticker, "SELL", pos["qty"], None)


# ══════════════════════════════════════════════════════════
#  COINSPOT (Australian Exchange)
# ══════════════════════════════════════════════════════════

class CoinSpotBroker(BrokerBase):
    """CoinSpot REST API v2 — Australian spot crypto exchange."""
    name = "coinspot"
    supports_short = False
    _BASE = "https://www.coinspot.com.au/api/v2"

    def __init__(self):
        self._api_key: Optional[str] = None
        self._api_secret: Optional[str] = None
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def _sign(self, body: str) -> str:
        return hmac.new(self._api_secret.encode(), body.encode(), hashlib.sha512).hexdigest()

    def _auth_headers(self, body: str) -> dict:
        return {
            "Content-Type": "application/json",
            "key": self._api_key,
            "sign": self._sign(body),
        }

    async def connect(self, api_key: str, api_secret: str, **kwargs) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        body = json.dumps({"nonce": int(time.time() * 1000)})
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(f"{self._BASE}/ro/my/balances", content=body, headers=self._auth_headers(body))
            d = r.json()
            if d.get("status") != "ok":
                raise RuntimeError(f"CoinSpot auth failed: {d.get('message', 'invalid API key')}")
        self._connected = True
        self._store_credentials(api_key=api_key, api_secret=api_secret)
        logger.info("CoinSpot connected")

    async def get_account(self) -> dict:
        if not self._connected: raise RuntimeError("CoinSpot not connected")
        body = json.dumps({"nonce": int(time.time() * 1000)})
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(f"{self._BASE}/ro/my/balances", content=body, headers=self._auth_headers(body))
            d = r.json()
        balances = d.get("balances", [])
        total_aud = 0.0
        aud_available = 0.0
        for bal_dict in balances:
            for coin, info in bal_dict.items():
                val = float(info.get("audbalance", 0))
                total_aud += val
                if coin.lower() == "aud":
                    aud_available = float(info.get("balance", 0))
        return {"broker": "coinspot", "account_value": round(total_aud, 2), "buying_power": round(aud_available, 2),
                "cash": round(aud_available, 2), "currency": "AUD"}

    async def place_order(self, ticker: str, side: str, qty: float, price: Optional[float] = None) -> dict:
        if not self._connected: raise RuntimeError("CoinSpot not connected")
        # CoinSpot uses lowercase coin names (e.g. "btc", "eth")
        coin = ticker.replace("-AUD", "").replace("-USD", "").replace("AUD", "").replace("USDT", "").lower()
        body_data = {"cointype": coin, "amount": qty, "nonce": int(time.time() * 1000)}
        if price:
            body_data["rate"] = price
        body = json.dumps(body_data)
        endpoint = f"/my/sell" if side.upper() == "SELL" else f"/my/buy"
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(f"{self._BASE}{endpoint}", content=body, headers=self._auth_headers(body))
            d = r.json()
        if d.get("status") != "ok":
            raise RuntimeError(f"CoinSpot order failed: {d.get('message', 'unknown error')}")
        return {"order_id": d.get("id", str(int(time.time()))), "ticker": ticker, "side": side.upper(), "qty": qty,
                "price": price or float(d.get("rate", 0)), "status": "FILLED", "timestamp": datetime.utcnow().isoformat()}

    async def get_positions(self) -> list:
        if not self._connected: raise RuntimeError("CoinSpot not connected")
        body = json.dumps({"nonce": int(time.time() * 1000)})
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(f"{self._BASE}/ro/my/balances", content=body, headers=self._auth_headers(body))
            d = r.json()
        positions = []
        for bal_dict in d.get("balances", []):
            for coin, info in bal_dict.items():
                bal = float(info.get("balance", 0))
                if bal > 0 and coin.lower() != "aud":
                    positions.append({"ticker": f"{coin.upper()}-AUD", "qty": bal, "avg_cost": 0,
                                      "market_val": float(info.get("audbalance", 0)),
                                      "pnl": None, "side": "LONG"})
        return positions

    async def get_history(self) -> list:
        if not self._connected: raise RuntimeError("CoinSpot not connected")
        body = json.dumps({"nonce": int(time.time() * 1000)})
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(f"{self._BASE}/ro/my/transactions", content=body, headers=self._auth_headers(body))
            d = r.json()
        txns = d.get("buyorders", []) + d.get("sellorders", [])
        return [{"ticker": f"{t.get('coin', '').upper()}-AUD", "side": "BUY" if t in d.get("buyorders", []) else "SELL",
                 "qty": float(t.get("amount", 0)), "price": float(t.get("rate", 0)),
                 "timestamp": t.get("solddate", t.get("created"))} for t in txns[:50]]

    async def close_position(self, ticker: str) -> dict:
        positions = await self.get_positions()
        coin = ticker.replace("-AUD", "").replace("AUD", "").upper()
        pos = next((p for p in positions if coin in p["ticker"].upper()), None)
        if not pos: raise ValueError(f"No open CoinSpot position in {ticker}")
        return await self.place_order(ticker, "SELL", pos["qty"], None)


# ══════════════════════════════════════════════════════════
#  MEXC
# ══════════════════════════════════════════════════════════

class MEXCBroker(BrokerBase):
    """MEXC Global V3 REST API — spot trading."""
    name = "mexc"
    supports_short = False
    _BASE = "https://api.mexc.com"

    def __init__(self):
        self._api_key: Optional[str] = None
        self._api_secret: Optional[str] = None
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def _sign(self, params: dict) -> str:
        query = urllib.parse.urlencode(params)
        return hmac.new(self._api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()

    def _headers(self) -> dict:
        return {"X-MEXC-APIKEY": self._api_key, "Content-Type": "application/json"}

    async def connect(self, api_key: str, api_secret: str, **kwargs) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        async with httpx.AsyncClient(timeout=10.0) as c:
            params = {"timestamp": int(time.time() * 1000)}
            params["signature"] = self._sign(params)
            r = await c.get(f"{self._BASE}/api/v3/account", params=params, headers=self._headers())
            if r.status_code in (401, 403):
                raise RuntimeError("Invalid MEXC API key or signature")
            r.raise_for_status()
        self._connected = True
        self._store_credentials(api_key=api_key, api_secret=api_secret)
        logger.info("MEXC connected")

    async def get_account(self) -> dict:
        if not self._connected: raise RuntimeError("MEXC not connected")
        async with httpx.AsyncClient(timeout=10.0) as c:
            params = {"timestamp": int(time.time() * 1000)}
            params["signature"] = self._sign(params)
            r = await c.get(f"{self._BASE}/api/v3/account", params=params, headers=self._headers())
            r.raise_for_status()
            d = r.json()
        balances = d.get("balances", [])
        usdt = float(next((b["free"] for b in balances if b["asset"] == "USDT"), 0))
        return {"broker": "mexc", "account_value": round(usdt, 2), "buying_power": round(usdt, 2),
                "cash": round(usdt, 2), "currency": "USDT"}

    async def place_order(self, ticker: str, side: str, qty: float, price: Optional[float] = None) -> dict:
        if not self._connected: raise RuntimeError("MEXC not connected")
        symbol = ticker.replace("-", "").replace("/", "").upper()
        params = {
            "symbol": symbol, "side": side.upper(), "type": "LIMIT" if price else "MARKET",
            "quantity": str(qty), "timestamp": int(time.time() * 1000),
        }
        if price:
            params["price"] = str(price)
        params["signature"] = self._sign(params)
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(f"{self._BASE}/api/v3/order", params=params, headers=self._headers())
            r.raise_for_status()
            d = r.json()
        return {"order_id": str(d.get("orderId", "")), "ticker": ticker, "side": side.upper(), "qty": qty,
                "price": price or float(d.get("price", 0)), "status": d.get("status", "NEW"),
                "timestamp": datetime.utcnow().isoformat()}

    async def get_positions(self) -> list:
        if not self._connected: raise RuntimeError("MEXC not connected")
        async with httpx.AsyncClient(timeout=10.0) as c:
            params = {"timestamp": int(time.time() * 1000)}
            params["signature"] = self._sign(params)
            r = await c.get(f"{self._BASE}/api/v3/account", params=params, headers=self._headers())
            r.raise_for_status()
            d = r.json()
        positions = []
        for b in d.get("balances", []):
            total = float(b.get("free", 0)) + float(b.get("locked", 0))
            if total > 0 and b["asset"] not in ("USDT", "USDC"):
                positions.append({"ticker": f"{b['asset']}USDT", "qty": total, "avg_cost": 0,
                                  "market_val": None, "pnl": None, "side": "LONG"})
        return positions

    async def get_history(self) -> list:
        return []

    async def close_position(self, ticker: str) -> dict:
        positions = await self.get_positions()
        symbol = ticker.replace("-", "").replace("/", "").upper()
        pos = next((p for p in positions if p["ticker"].upper() == symbol), None)
        if not pos: raise ValueError(f"No open MEXC position in {ticker}")
        return await self.place_order(ticker, "SELL", pos["qty"], None)


# ══════════════════════════════════════════════════════════
#  BITFINEX
# ══════════════════════════════════════════════════════════

class BitfinexBroker(BrokerBase):
    """Bitfinex V2 REST API — spot + margin trading."""
    name = "bitfinex"
    supports_short = True
    _BASE = "https://api.bitfinex.com"

    def __init__(self):
        self._api_key: Optional[str] = None
        self._api_secret: Optional[str] = None
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def _sign(self, path: str, body: str, nonce: str) -> dict:
        payload = f"/api/{path}{nonce}{body}"
        sig = hmac.new(self._api_secret.encode(), payload.encode(), hashlib.sha384).hexdigest()
        return {
            "bfx-nonce": nonce,
            "bfx-apikey": self._api_key,
            "bfx-signature": sig,
            "Content-Type": "application/json",
        }

    async def connect(self, api_key: str, api_secret: str, **kwargs) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        path = "v2/auth/r/wallets"
        body = "{}"
        nonce = str(int(time.time() * 1000000))
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(f"{self._BASE}/{path}", content=body, headers=self._sign(path, body, nonce))
            if r.status_code in (401, 403):
                raise RuntimeError("Invalid Bitfinex API key or signature")
            r.raise_for_status()
            d = r.json()
            if isinstance(d, list) and len(d) > 0 and d[0] == "error":
                raise RuntimeError(f"Bitfinex auth failed: {d}")
        self._connected = True
        self._store_credentials(api_key=api_key, api_secret=api_secret)
        logger.info("Bitfinex connected")

    async def get_account(self) -> dict:
        if not self._connected: raise RuntimeError("Bitfinex not connected")
        path = "v2/auth/r/wallets"
        body = "{}"
        nonce = str(int(time.time() * 1000000))
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(f"{self._BASE}/{path}", content=body, headers=self._sign(path, body, nonce))
            r.raise_for_status()
            d = r.json()
        # Wallet format: [WALLET_TYPE, CURRENCY, BALANCE, UNSETTLED_INTEREST, BALANCE_AVAILABLE]
        total = 0.0
        usd = 0.0
        for w in d:
            if isinstance(w, list) and len(w) >= 5 and w[0] == "exchange":
                bal = float(w[2] or 0)
                if w[1] in ("USD", "UST"):  # UST = USDT on Bitfinex
                    usd += bal
                total += bal
        return {"broker": "bitfinex", "account_value": round(total, 2), "buying_power": round(usd, 2),
                "cash": round(usd, 2), "currency": "USD"}

    async def place_order(self, ticker: str, side: str, qty: float, price: Optional[float] = None) -> dict:
        if not self._connected: raise RuntimeError("Bitfinex not connected")
        # Bitfinex uses tXXXYYY format (e.g. tBTCUSD)
        symbol = ticker.replace("-", "").replace("/", "").upper()
        if not symbol.startswith("t"):
            symbol = "t" + symbol
        path = "v2/auth/w/order/submit"
        amount = qty if side.upper() == "BUY" else -qty
        body_data = {
            "type": "EXCHANGE LIMIT" if price else "EXCHANGE MARKET",
            "symbol": symbol,
            "amount": str(amount),
        }
        if price:
            body_data["price"] = str(price)
        body = json.dumps(body_data)
        nonce = str(int(time.time() * 1000000))
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(f"{self._BASE}/{path}", content=body, headers=self._sign(path, body, nonce))
            r.raise_for_status()
            d = r.json()
        # Response: [MTS, TYPE, MESSAGE_ID, null, [ORDER_ARRAY], ...]
        order_id = ""
        if isinstance(d, list) and len(d) > 4 and isinstance(d[4], list):
            order_data = d[4][0] if isinstance(d[4][0], list) else d[4]
            order_id = str(order_data[0]) if order_data else ""
        return {"order_id": order_id, "ticker": ticker, "side": side.upper(), "qty": qty,
                "price": price, "status": "NEW", "timestamp": datetime.utcnow().isoformat()}

    async def get_positions(self) -> list:
        if not self._connected: raise RuntimeError("Bitfinex not connected")
        path = "v2/auth/r/wallets"
        body = "{}"
        nonce = str(int(time.time() * 1000000))
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(f"{self._BASE}/{path}", content=body, headers=self._sign(path, body, nonce))
            r.raise_for_status()
            d = r.json()
        positions = []
        for w in d:
            if isinstance(w, list) and len(w) >= 5 and w[0] == "exchange":
                bal = float(w[2] or 0)
                avail = float(w[4] or 0)
                ccy = w[1]
                if bal > 0 and ccy not in ("USD", "UST"):
                    positions.append({"ticker": f"t{ccy}USD", "qty": bal, "avg_cost": 0,
                                      "market_val": None, "pnl": None, "side": "LONG"})
        return positions

    async def get_history(self) -> list:
        if not self._connected: raise RuntimeError("Bitfinex not connected")
        path = "v2/auth/r/trades/hist"
        body = json.dumps({"limit": 50})
        nonce = str(int(time.time() * 1000000))
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(f"{self._BASE}/{path}", content=body, headers=self._sign(path, body, nonce))
            r.raise_for_status()
            d = r.json()
        # Trade format: [ID, PAIR, MTS_CREATE, ORDER_ID, EXEC_AMOUNT, EXEC_PRICE, ...]
        return [{"ticker": t[1] if len(t) > 1 else "", "side": "BUY" if float(t[4]) > 0 else "SELL",
                 "qty": abs(float(t[4])), "price": float(t[5]),
                 "timestamp": str(t[2])} for t in d if isinstance(t, list) and len(t) > 5]

    async def close_position(self, ticker: str) -> dict:
        positions = await self.get_positions()
        symbol = ticker.replace("-", "").replace("/", "").upper()
        if not symbol.startswith("t"):
            symbol = "t" + symbol
        pos = next((p for p in positions if symbol in p["ticker"].upper()), None)
        if not pos: raise ValueError(f"No open Bitfinex position in {ticker}")
        return await self.place_order(ticker, "SELL", pos["qty"], None)


# ══════════════════════════════════════════════════════════
#  BROKER REGISTRY
# ══════════════════════════════════════════════════════════

CONNECTED_BROKERS: dict[str, BrokerBase] = {}   # keyed by broker name
PRIMARY_BROKER: Optional[str] = None             # default for order routing


def get_broker(name: str = None) -> Optional[BrokerBase]:
    """Get a specific connected broker, or the primary."""
    if name:
        return CONNECTED_BROKERS.get(name)
    if PRIMARY_BROKER:
        return CONNECTED_BROKERS.get(PRIMARY_BROKER)
    for b in CONNECTED_BROKERS.values():
        if b.is_connected():
            return b
    return None


def get_all_connected() -> dict[str, BrokerBase]:
    """Return all connected broker instances."""
    return CONNECTED_BROKERS


# ── Broker credential persistence ───────────────────────
_BROKER_CREDS_FILE = DATA_DIR / "broker_credentials.json"


def _load_broker_creds() -> dict:
    if _BROKER_CREDS_FILE.exists():
        try:
            raw = json.loads(_BROKER_CREDS_FILE.read_text())
            return _decrypt_creds(raw)
        except Exception:
            return {}
    return {}


def _save_broker_creds(creds: dict):
    encrypted = _encrypt_creds(creds)
    _BROKER_CREDS_FILE.write_text(json.dumps(encrypted, indent=2))


# ── Broker map ──────────────────────────────────────────
BROKER_MAP = {
    "ibkr": IBKRBroker,
    "binance": BinanceBroker,
    "bybit": BybitBroker,
    "kraken": KrakenBroker,
    "okx": OKXBroker,
    "coinbase": CoinbaseBroker,
    "kucoin": KucoinBroker,
    "coinspot": CoinSpotBroker,
    "mexc": MEXCBroker,
    "bitfinex": BitfinexBroker,
}
