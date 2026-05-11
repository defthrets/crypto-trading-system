"""
0xrex License Validation
Validates license keys via LemonSqueezy's API.
Stores activation locally in data/license.json.
"""

import hashlib
import json
import os
import platform
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx
from loguru import logger

# ── Paths ──────────────────────────────────────────
# Store license in a persistent user directory so it survives app updates
if platform.system() == "Windows":
    _APP_DATA = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
elif platform.system() == "Darwin":
    _APP_DATA = Path.home() / "Library" / "Application Support"
else:
    _APP_DATA = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))

LICENSE_DIR = _APP_DATA / "0xrex"
LICENSE_DIR.mkdir(parents=True, exist_ok=True)
LICENSE_FILE = LICENSE_DIR / "license.json"

# ── LemonSqueezy API ──────────────────────────────
LEMON_ACTIVATE_URL = "https://api.lemonsqueezy.com/v1/licenses/activate"
LEMON_VALIDATE_URL = "https://api.lemonsqueezy.com/v1/licenses/validate"
LEMON_DEACTIVATE_URL = "https://api.lemonsqueezy.com/v1/licenses/deactivate"

# Revalidate online every 30 days
REVALIDATION_DAYS = 30

# ── Master admin key (hash-verified, bypasses LemonSqueezy) ──────
_MASTER_KEY_HASH = os.getenv("0xrex_MASTER_KEY_HASH", "")


def _is_master_key(key: str) -> bool:
    """Check if the provided key matches the master key via hash comparison."""
    return hashlib.sha256(key.strip().encode()).hexdigest() == _MASTER_KEY_HASH


def _fnv32(data: str, seed: int = 0x811C9DC5) -> int:
    """FNV-32 hash — must match the JS implementation on the website."""
    h = seed & 0xFFFFFFFF
    for ch in data:
        h ^= ord(ch)
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def _is_valid_pro_key(key: str) -> bool:
    """
    Validate a 0XREX-PRO key.
    New format (6 parts): 0XREX-PRO-XXXX-XXXX-XXXX-CHCK — verifies FNV-32 checksum.
    Old format (5 parts): 0XREX-PRO-XXXX-XXXX-XXXX — accepts if segments are valid hex.
    """
    parts = key.strip().upper().split("-")
    if len(parts) not in (5, 6):
        return False
    if parts[0] != "0XREX" or parts[1] != "PRO":
        return False
    # Each segment after PRO must be 4 hex chars
    for seg in parts[2:]:
        if len(seg) != 4:
            return False
        try:
            int(seg, 16)
        except ValueError:
            return False
    # New format: verify checksum
    if len(parts) == 6:
        raw = (parts[2] + parts[3] + parts[4]).lower()
        expected = _fnv32(raw, 0x811C9DC5) & 0xFFFF
        actual = int(parts[5], 16)
        return expected == actual
    # Old format: valid hex segments is enough
    return True


def _machine_fingerprint() -> str:
    """Generate a unique machine fingerprint from hardware identifiers."""
    raw = f"{platform.node()}-{platform.machine()}-{platform.system()}-{uuid.getnode()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _load_license() -> Optional[dict]:
    """Load stored license data from disk."""
    if LICENSE_FILE.exists():
        try:
            return json.loads(LICENSE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return None
    return None


def _save_license(data: dict):
    """Persist license data to disk."""
    LICENSE_FILE.write_text(json.dumps(data, indent=2))


def _clear_license():
    """Remove stored license data."""
    if LICENSE_FILE.exists():
        LICENSE_FILE.unlink()


def is_licensed() -> bool:
    """Check if the app has a valid local activation."""
    lic = _load_license()
    if not lic:
        return False

    # Check machine fingerprint matches
    if lic.get("machine_id") != _machine_fingerprint():
        return False

    # Check if activation is present
    if not lic.get("activated"):
        return False

    return True


def needs_revalidation() -> bool:
    """Check if online revalidation is due. Master keys never need revalidation."""
    lic = _load_license()
    if not lic:
        return True
    if lic.get("is_master") or lic.get("is_pro"):
        return False

    last = lic.get("last_validated")
    if not last:
        return True

    try:
        last_dt = datetime.fromisoformat(last)
        return datetime.now() - last_dt > timedelta(days=REVALIDATION_DAYS)
    except (ValueError, TypeError):
        return True


async def activate_license(key: str) -> dict:
    """
    Activate a license key via LemonSqueezy API.
    Master key bypasses online validation entirely.
    Returns dict with 'success', 'message', and optionally 'data'.
    """
    fingerprint = _machine_fingerprint()

    # Master key — instant activation, no internet needed
    if _is_master_key(key):
        _save_license({
            "license_key": key,
            "instance_id": "master",
            "machine_id": fingerprint,
            "activated": True,
            "activated_at": datetime.now().isoformat(),
            "last_validated": datetime.now().isoformat(),
            "customer_name": "Admin",
            "customer_email": "admin",
            "product_name": "0xrex Master",
            "is_master": True,
        })
        logger.info("Master license activated")
        return {"success": True, "message": "Master license activated."}

    # Website-issued PRO key — validate checksum locally
    if _is_valid_pro_key(key):
        _save_license({
            "license_key": key,
            "instance_id": "pro-" + hashlib.sha256(key.encode()).hexdigest()[:12],
            "machine_id": fingerprint,
            "activated": True,
            "activated_at": datetime.now().isoformat(),
            "last_validated": datetime.now().isoformat(),
            "customer_name": "Pro User",
            "customer_email": "",
            "product_name": "0xrex Pro",
            "is_pro": True,
        })
        logger.info("PRO license activated via website key")
        return {"success": True, "message": "PRO license activated!"}

    # LemonSqueezy key — validate online
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                LEMON_ACTIVATE_URL,
                json={
                    "license_key": key,
                    "instance_name": f"0xrex-{platform.node()}",
                },
                headers={"Accept": "application/json"},
            )

        body = resp.json()

        if resp.status_code == 200 and body.get("activated"):
            # Store activation locally
            _save_license({
                "license_key": key,
                "instance_id": body.get("instance", {}).get("id", ""),
                "machine_id": fingerprint,
                "activated": True,
                "activated_at": datetime.now().isoformat(),
                "last_validated": datetime.now().isoformat(),
                "customer_name": body.get("meta", {}).get("customer_name", ""),
                "customer_email": body.get("meta", {}).get("customer_email", ""),
                "product_name": body.get("meta", {}).get("product_name", "0xrex"),
            })
            logger.info(f"License activated successfully for {platform.node()}")
            return {"success": True, "message": "License activated successfully!"}

        # Handle specific error cases
        error = body.get("error", "Activation failed")
        if "limit" in str(error).lower():
            return {"success": False, "message": "Device limit reached. Deactivate another device first or contact support."}
        if "invalid" in str(error).lower() or resp.status_code == 404:
            return {"success": False, "message": "Invalid license key. Please check and try again."}
        if "expired" in str(error).lower():
            return {"success": False, "message": "This license key has expired."}
        if "disabled" in str(error).lower():
            return {"success": False, "message": "This license key has been disabled."}

        return {"success": False, "message": str(error)}

    except httpx.ConnectError:
        return {"success": False, "message": "Cannot connect to activation server. Check your internet connection."}
    except httpx.TimeoutException:
        return {"success": False, "message": "Activation server timed out. Please try again."}
    except Exception as e:
        logger.error(f"License activation error: {e}")
        return {"success": False, "message": f"Activation error: {str(e)}"}


async def validate_license() -> dict:
    """
    Validate the stored license key online (periodic revalidation).
    Returns dict with 'valid' and 'message'.
    """
    lic = _load_license()
    if not lic or not lic.get("license_key"):
        return {"valid": False, "message": "No license found"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                LEMON_VALIDATE_URL,
                json={"license_key": lic["license_key"]},
                headers={"Accept": "application/json"},
            )

        body = resp.json()

        if resp.status_code == 200 and body.get("valid"):
            # Update last validated timestamp
            lic["last_validated"] = datetime.now().isoformat()
            _save_license(lic)
            return {"valid": True, "message": "License is valid"}

        # License revoked or expired — clear local activation
        _clear_license()
        return {"valid": False, "message": "License is no longer valid. Please re-activate."}

    except (httpx.ConnectError, httpx.TimeoutException):
        # Can't reach server — allow offline grace period
        logger.warning("Cannot reach license server for revalidation — allowing offline grace")
        return {"valid": True, "message": "Offline — using cached activation"}
    except Exception as e:
        logger.error(f"License validation error: {e}")
        return {"valid": True, "message": "Validation error — using cached activation"}


async def deactivate_license() -> dict:
    """Deactivate the current license (free up a device slot)."""
    lic = _load_license()
    if not lic or not lic.get("license_key"):
        return {"success": False, "message": "No license to deactivate"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                LEMON_DEACTIVATE_URL,
                json={
                    "license_key": lic["license_key"],
                    "instance_id": lic.get("instance_id", ""),
                },
                headers={"Accept": "application/json"},
            )

        if resp.status_code == 200:
            _clear_license()
            return {"success": True, "message": "License deactivated. You can activate on another device."}

        return {"success": False, "message": "Deactivation failed. Please try again."}

    except Exception as e:
        logger.error(f"License deactivation error: {e}")
        return {"success": False, "message": f"Deactivation error: {str(e)}"}


def get_license_status() -> dict:
    """Get current license status for the UI."""
    lic = _load_license()
    if not lic:
        return {"licensed": False}

    return {
        "licensed": is_licensed(),
        "customer_email": lic.get("customer_email", ""),
        "activated_at": lic.get("activated_at", ""),
        "last_validated": lic.get("last_validated", ""),
        "needs_revalidation": needs_revalidation(),
    }
