"""Fixtures compartilhadas.

Testes de integração dependem do Postgres do docker-compose. Se o banco não
estiver acessível, eles são marcados como *skip* com instrução de uso — os
testes puros (grafo, BKT, planejador) rodam sempre.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
DIR_INIT = RAIZ / "db" / "init"
DSN_TESTES_PADRAO = "postgresql://tcc:tcc@localhost:5432/tcc_test"


@pytest.fixture(scope="session")
def dsn_testes() -> str:
    return os.getenv("DATABASE_URL_TESTES", DSN_TESTES_PADRAO)


@pytest.fixture(scope="session")
def banco(dsn_testes: str) -> str:
    psycopg = pytest.importorskip("psycopg")
    try:
        with psycopg.connect(dsn_testes, connect_timeout=3) as conn:
            conn.execute((DIR_INIT / "001_schema.sql").read_text(encoding="utf-8"))
            conn.execute((DIR_INIT / "002_seed.sql").read_text(encoding="utf-8"))
    except psycopg.OperationalError as exc:
        pytest.skip(f"Postgres indisponível em {dsn_testes} (rode `make db-up`): {exc}")
    return dsn_testes


@pytest.fixture()
def banco_limpo(banco: str) -> str:
    psycopg = pytest.importorskip("psycopg")
    with psycopg.connect(banco, connect_timeout=3) as conn:
        conn.execute("TRUNCATE sessao CASCADE")
    return banco


@pytest.fixture()
def repo(banco_limpo: str):
    pytest.importorskip("psycopg")
    from trilha.repo import Repositorio

    repositorio = Repositorio(banco_limpo, min_size=1, max_size=4)
    try:
        yield repositorio
    finally:
        repositorio.fechar()
