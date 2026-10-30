from __future__ import annotations

import os


def database_url() -> str:
    return os.getenv("DATABASE_URL", "postgresql://tcc:tcc@localhost:5432/tcc")


def database_url_testes() -> str:
    return os.getenv("DATABASE_URL_TESTES", "postgresql://tcc:tcc@localhost:5432/tcc_test")


def threshold() -> float:
    return float(os.getenv("MASTERY_THRESHOLD", "0.95"))
