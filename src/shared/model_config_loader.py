"""
model_config_loader.py — Central model configuration loader.

Loads model_control.csv as a lazy singleton. Load order:
  1. S3 override: s3://hyperplexity-storage/config/model_control.csv  (hot-swap, TTL 30 days)
  2. Bundled CSV:  model_config/model_control.csv  (in the Lambda package / local src/)

Usage:
    from model_config_loader import ModelConfig
    model = ModelConfig.get('clone_deepseek_t2')           # → 'deepseek-v3.2'
    fallbacks = ModelConfig.get_fallbacks('clone_deepseek_t2')  # → ['claude-sonnet-4-5']
    csv_text = ModelConfig.snapshot()                       # full CSV for per-run storage
    commit = ModelConfig.deploy_commit                      # git SHA from version.json
"""

import csv
import io
import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# S3 path for live override (bucket is read from env at call time)
_S3_OVERRIDE_KEY = "config/model_control.csv"
_S3_BUCKET_ENV   = "S3_UNIFIED_BUCKET"
_DEFAULT_BUCKET  = "hyperplexity-storage"

# Cache TTL: 30 days (Lambda process restarts reset this anyway)
CACHE_TTL_SECONDS = 30 * 24 * 3600

# Resolved paths for the bundled CSV and version.json
_THIS_DIR = Path(__file__).parent        # src/shared/
_PACKAGE_ROOT = _THIS_DIR.parent         # src/   (local dev)

# In the Lambda package, model_config/ sits at the package root alongside shared files.
# Locally it lives under src/model_config/.
def _find_bundled_csv() -> Optional[Path]:
    candidates = [
        _THIS_DIR / "model_config" / "model_control.csv",          # Lambda package: flat root
        _PACKAGE_ROOT / "model_config" / "model_control.csv",      # local dev: src/model_config/
        Path(__file__).parent.parent / "model_config" / "model_control.csv",  # any other depth
    ]
    for p in candidates:
        if p.exists():
            return p
    return None

def _find_version_json() -> Optional[Path]:
    candidates = [
        _THIS_DIR / "version.json",          # Lambda package root
        _PACKAGE_ROOT.parent / "version.json",  # project root (local dev)
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


class _ModelConfigSingleton:
    """Thread-safe lazy singleton for model configuration."""

    _instance: Optional["_ModelConfigSingleton"] = None

    def __init__(self):
        self._rows: Dict[str, Dict] = {}        # role → row dict
        self._raw_csv: str = ""
        self._loaded_at: float = 0.0
        self._source: str = "unloaded"
        self._deploy_commit: str = "unknown"
        self._deploy_info: Dict = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, role: str) -> str:
        """Return the primary model for *role*.  Raises KeyError if unknown."""
        self._ensure_loaded()
        if role not in self._rows:
            raise KeyError(f"ModelConfig: unknown role '{role}'. Check model_control.csv.")
        return self._rows[role]["model"]

    def get_with_default(self, role: str, default: str = "") -> str:
        """Return the primary model for *role*, or *default* if the role is missing."""
        try:
            return self.get(role)
        except KeyError:
            logger.warning(f"ModelConfig: role '{role}' not found, using default '{default}'")
            return default

    def get_fallbacks(self, role: str) -> List[str]:
        """Return ordered list of fallback models for *role* (may be empty)."""
        self._ensure_loaded()
        row = self._rows.get(role, {})
        fallbacks = []
        for key in ("fallback_1", "fallback_2"):
            val = row.get(key, "").strip()
            if val:
                fallbacks.append(val)
        return fallbacks

    def get_with_fallbacks(self, role: str) -> List[str]:
        """Return [primary] + fallbacks as a single ordered list."""
        return [self.get(role)] + self.get_fallbacks(role)

    def snapshot(self) -> str:
        """Return the full CSV text of the currently-loaded config."""
        self._ensure_loaded()
        return self._raw_csv

    @property
    def deploy_commit(self) -> str:
        self._ensure_version_loaded()
        return self._deploy_commit

    @property
    def deploy_info(self) -> Dict:
        self._ensure_version_loaded()
        return self._deploy_info

    @property
    def source(self) -> str:
        """Where the config was loaded from: 's3', 'bundled', or 'unloaded'."""
        return self._source

    # ------------------------------------------------------------------
    # Internal loading
    # ------------------------------------------------------------------

    def _ensure_loaded(self):
        now = time.time()
        if self._rows and (now - self._loaded_at) < CACHE_TTL_SECONDS:
            return
        self._load()

    def _load(self):
        csv_text = None

        # 1. Try S3 override
        try:
            bucket = os.environ.get(_S3_BUCKET_ENV, _DEFAULT_BUCKET)
            import boto3
            s3 = boto3.client("s3")
            resp = s3.get_object(Bucket=bucket, Key=_S3_OVERRIDE_KEY)
            csv_text = resp["Body"].read().decode("utf-8")
            self._source = "s3"
            logger.info(f"[ModelConfig] Loaded from S3: s3://{bucket}/{_S3_OVERRIDE_KEY}")
        except Exception as e:
            logger.debug(f"[ModelConfig] S3 override not available ({e}), using bundled CSV")

        # 2. Fall back to bundled CSV
        if csv_text is None:
            bundled = _find_bundled_csv()
            if bundled:
                csv_text = bundled.read_text(encoding="utf-8")
                self._source = "bundled"
                logger.info(f"[ModelConfig] Loaded bundled CSV from {bundled}")
            else:
                logger.error("[ModelConfig] No model_control.csv found — model roles unavailable!")
                self._source = "missing"
                return

        self._raw_csv = csv_text
        self._rows = self._parse_csv(csv_text)
        self._loaded_at = time.time()
        logger.info(f"[ModelConfig] Loaded {len(self._rows)} roles from {self._source}")

    def _parse_csv(self, csv_text: str) -> Dict[str, Dict]:
        rows = {}
        reader = csv.DictReader(io.StringIO(csv_text))
        for row in reader:
            role = row.get("role", "").strip()
            if not role or role.startswith("#"):
                continue
            # Normalize: strip whitespace from all values
            rows[role] = {k: (v or "").strip() for k, v in row.items()}
        return rows

    def _ensure_version_loaded(self):
        if self._deploy_commit != "unknown":
            return
        vj = _find_version_json()
        if vj:
            try:
                info = json.loads(vj.read_text(encoding="utf-8"))
                self._deploy_commit = info.get("commit", "unknown")
                self._deploy_info = info
            except Exception as e:
                logger.debug(f"[ModelConfig] Could not parse version.json: {e}")

    # ------------------------------------------------------------------
    # Singleton factory
    # ------------------------------------------------------------------

    @classmethod
    def instance(cls) -> "_ModelConfigSingleton":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


# ---------------------------------------------------------------------------
# Public module-level API — use this directly
# ---------------------------------------------------------------------------

class ModelConfig:
    """Convenience namespace; delegates to the lazy singleton."""

    @staticmethod
    def get(role: str) -> str:
        return _ModelConfigSingleton.instance().get(role)

    @staticmethod
    def get_with_default(role: str, default: str = "") -> str:
        return _ModelConfigSingleton.instance().get_with_default(role, default)

    @staticmethod
    def get_fallbacks(role: str) -> List[str]:
        return _ModelConfigSingleton.instance().get_fallbacks(role)

    @staticmethod
    def get_with_fallbacks(role: str) -> List[str]:
        return _ModelConfigSingleton.instance().get_with_fallbacks(role)

    @staticmethod
    def snapshot() -> str:
        return _ModelConfigSingleton.instance().snapshot()

    @property
    def deploy_commit(self) -> str:  # noqa: N802
        return _ModelConfigSingleton.instance().deploy_commit

    @property
    def deploy_info(self) -> Dict:
        return _ModelConfigSingleton.instance().deploy_info

    # Allow `ModelConfig.deploy_commit` as a class-level property too
    deploy_commit = property(lambda self: _ModelConfigSingleton.instance().deploy_commit)  # type: ignore[assignment]
    deploy_info   = property(lambda self: _ModelConfigSingleton.instance().deploy_info)    # type: ignore[assignment]


# Also expose at module level for convenience
def get_model(role: str) -> str:
    return ModelConfig.get(role)

def get_deploy_commit() -> str:
    return _ModelConfigSingleton.instance().deploy_commit
