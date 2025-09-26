# File: app/core/oanda_client.py
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Any, Optional, List

import httpx


@dataclass
class OandaConfig:
    api_key: Optional[str]
    account_id: Optional[str]
    practice: bool = True  # default to practice (paper) environment

    @property
    def api_host(self) -> str:
        # v20 API hosts: practice/live
        return "https://api-fxpractice.oanda.com" if self.practice else "https://api-fxtrade.oanda.com"

    @property
    def stream_host(self) -> str:
        return "https://stream-fxpractice.oanda.com" if self.practice else "https://stream-fxtrade.oanda.com"

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


def load_oanda_config() -> OandaConfig:
    """Read env; default to PRACTICE and PAPER-ONLY if unset."""
    api_key = os.getenv("OANDA_API_KEY") or os.getenv("OANDA_TOKEN")
    account_id = os.getenv("OANDA_ACCOUNT_ID")
    practice_str = os.getenv("OANDA_PRACTICE", "1")
    practice = practice_str not in ("0", "false", "False", "FALSE")
    return OandaConfig(api_key=api_key, account_id=account_id, practice=practice)


class OandaClient:
    """
    Thin OANDA v20 REST wrapper (GET-only for now).
    PAPER-ONLY default. If no API key, returns dry-run placeholders with ok=False.
    """

    def __init__(self, cfg: Optional[OandaConfig] = None, timeout: float = 10.0):
        self.cfg = cfg or load_oanda_config()
        self.timeout = timeout

    # ------------ internal ------------
    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.cfg.api_key}"} if self.cfg.api_key else {}

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> httpx.Response:
        url = f"{self.cfg.api_host}{path}"
        return httpx.get(url, headers=self._headers(), params=params, timeout=self.timeout)

    # ------------ public surface ------------
    def status(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "provider": "oanda",
            "mode": "paper" if self.cfg.practice else "live",
            "configured": self.cfg.configured,
            "has_account_id": bool(self.cfg.account_id),
            "api_host": self.cfg.api_host,
            "stream_host": self.cfg.stream_host,
        }

    def server_time(self) -> Dict[str, Any]:
        # There isn't a standalone "time" endpoint in v20; use /accounts if configured,
        # otherwise just return local server timestamp as a lightweight health check.
        if not self.cfg.configured:
            return {"ok": False, "reason": "not_configured", "time": None}
        try:
            # ping a cheap endpoint; headers are validated server-side
            r = self._get("/v3/accounts")
            return {"ok": r.is_success, "status_code": r.status_code, "time": r.headers.get("Date")}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def accounts(self) -> Dict[str, Any]:
        if not self.cfg.configured:
            return {"ok": False, "reason": "not_configured", "accounts": []}
        try:
            r = self._get("/v3/accounts")
            if r.is_success:
                data = r.json()
                return {"ok": True, "accounts": data.get("accounts", [])}
            return {"ok": False, "status_code": r.status_code, "error": r.text}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def instruments(self, account_id: Optional[str] = None) -> Dict[str, Any]:
        if not self.cfg.configured:
            return {"ok": False, "reason": "not_configured", "instruments": []}
        acct = account_id or self.cfg.account_id
        if not acct:
            return {"ok": False, "reason": "missing_account_id"}
        try:
            r = self._get(f"/v3/accounts/{acct}/instruments")
            if r.is_success:
                data = r.json()
                return {"ok": True, "instruments": data.get("instruments", [])}
            return {"ok": False, "status_code": r.status_code, "error": r.text}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def prices(self, instruments: List[str], account_id: Optional[str] = None) -> Dict[str, Any]:
        if not self.cfg.configured:
            return {"ok": False, "reason": "not_configured", "prices": []}
        if not instruments:
            return {"ok": False, "reason": "no_instruments"}
        acct = account_id or self.cfg.account_id
        if not acct:
            return {"ok": False, "reason": "missing_account_id"}
        try:
            params = {"instruments": ",".join(instruments)}
            r = self._get(f"/v3/accounts/{acct}/pricing", params=params)
            if r.is_success:
                data = r.json()
                return {"ok": True, "prices": data.get("prices", [])}
            return {"ok": False, "status_code": r.status_code, "error": r.text}
        except Exception as e:
            return {"ok": False, "error": str(e)}
