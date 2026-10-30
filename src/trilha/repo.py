"""Camada de persistência: Postgres via psycopg 3, SQL explícito.

Não há ORM: a lista de adjacências do currículo aparece literalmente nas
consultas, o que mantém o mapeamento do relatório visível no código.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from .erros import SessaoNaoEncontrada
from .models import Curriculum, Item, KC

DSN_PADRAO = "postgresql://tcc:tcc@localhost:5432/tcc"


def dsn() -> str:
    return os.getenv("DATABASE_URL", DSN_PADRAO)


@dataclass(frozen=True, slots=True)
class Interacao:
    """Resultado de uma resposta, produzido dentro da transação."""

    kc_id: str
    item_id: int
    escolha: str
    correta: bool
    p_antes: float
    p_depois: float
    evento_tipo: str | None = None
    evento: Mapping[str, Any] | None = None


class Repositorio:
    def __init__(self, conninfo: str | None = None, *, min_size: int = 1, max_size: int = 4):
        self._pool = ConnectionPool(
            conninfo or dsn(),
            min_size=min_size,
            max_size=max_size,
            open=True,
            kwargs={"row_factory": dict_row},
        )

    def fechar(self) -> None:
        self._pool.close()

    def __enter__(self) -> "Repositorio":
        return self

    def __exit__(self, *_: object) -> None:
        self.fechar()

    # ------------------------------------------------------------------ leitura

    def ping(self) -> bool:
        with self._pool.connection() as conn:
            linha = conn.execute("SELECT 1 AS ok").fetchone()
        return bool(linha and linha["ok"] == 1)

    def carregar_curriculo(self) -> Curriculum:
        with self._pool.connection() as conn:
            kcs = [
                KC(
                    id=linha["id"],
                    nome=linha["nome"],
                    area=linha["area"],
                    dificuldade=linha["dificuldade"],
                    p_init=float(linha["p_init"]),
                    p_learn=float(linha["p_learn"]),
                    p_slip=float(linha["p_slip"]),
                    p_guess=float(linha["p_guess"]),
                )
                for linha in conn.execute("SELECT * FROM kc ORDER BY id")
            ]
            arestas = [
                (linha["origem_id"], linha["destino_id"])
                for linha in conn.execute(
                    "SELECT origem_id, destino_id FROM kc_prereq ORDER BY origem_id, destino_id"
                )
            ]
        return Curriculum.from_edges(kcs, arestas)

    def kcs_com_itens(self) -> frozenset[str]:
        with self._pool.connection() as conn:
            linhas = conn.execute("SELECT DISTINCT kc_id FROM item").fetchall()
        return frozenset(linha["kc_id"] for linha in linhas)

    def listar_itens(self, kc_ids: Iterable[str]) -> list[Item]:
        ids = list(kc_ids)
        if not ids:
            return []
        with self._pool.connection() as conn:
            linhas = conn.execute(
                "SELECT id, kc_id, enunciado, alternativas, correta, dificuldade "
                "FROM item WHERE kc_id = ANY(%s) ORDER BY id",
                (ids,),
            ).fetchall()
        return [_item(linha) for linha in linhas]

    def obter_item(self, item_id: int) -> Item | None:
        with self._pool.connection() as conn:
            linha = conn.execute(
                "SELECT id, kc_id, enunciado, alternativas, correta, dificuldade "
                "FROM item WHERE id = %s",
                (item_id,),
            ).fetchone()
        return _item(linha) if linha else None

    def obter_sessao(self, sessao_id: str) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            linha = conn.execute(
                "SELECT id, aluno, target_id, criada_em, atualizada_em "
                "FROM sessao WHERE id = %s",
                (sessao_id,),
            ).fetchone()
        return _sessao(linha) if linha else None

    def obter_dominio(self, sessao_id: str) -> dict[str, float]:
        with self._pool.connection() as conn:
            linhas = conn.execute(
                "SELECT kc_id, p FROM dominio WHERE sessao_id = %s",
                (sessao_id,),
            ).fetchall()
        return {linha["kc_id"]: float(linha["p"]) for linha in linhas}

    def listar_tentativas(self, sessao_id: str, limite: int = 50) -> list[dict[str, Any]]:
        with self._pool.connection() as conn:
            linhas = conn.execute(
                "SELECT id, kc_id, item_id, escolha, correta, p_antes, p_depois, respondida_em "
                "FROM tentativa WHERE sessao_id = %s ORDER BY id DESC LIMIT %s",
                (sessao_id, limite),
            ).fetchall()
        return [
            {
                "id": linha["id"],
                "kc_id": linha["kc_id"],
                "item_id": linha["item_id"],
                "escolha": linha["escolha"],
                "correta": linha["correta"],
                "p_antes": float(linha["p_antes"]),
                "p_depois": float(linha["p_depois"]),
                "respondida_em": linha["respondida_em"].isoformat(),
            }
            for linha in linhas
        ]

    def contar_tentativas(self, sessao_id: str) -> int:
        with self._pool.connection() as conn:
            linha = conn.execute(
                "SELECT count(*) AS total FROM tentativa WHERE sessao_id = %s",
                (sessao_id,),
            ).fetchone()
        return int(linha["total"]) if linha else 0

    def contar_tentativas_por_item(self, sessao_id: str, kc_id: str) -> dict[int, int]:
        with self._pool.connection() as conn:
            linhas = conn.execute(
                "SELECT item_id, count(*) AS total FROM tentativa "
                "WHERE sessao_id = %s AND kc_id = %s GROUP BY item_id",
                (sessao_id, kc_id),
            ).fetchall()
        return {linha["item_id"]: int(linha["total"]) for linha in linhas}

    def listar_eventos(self, sessao_id: str, limite: int = 50) -> list[dict[str, Any]]:
        with self._pool.connection() as conn:
            linhas = conn.execute(
                "SELECT id, tipo, payload, criado_em FROM evento "
                "WHERE sessao_id = %s ORDER BY id DESC LIMIT %s",
                (sessao_id, limite),
            ).fetchall()
        return [
            {
                "id": linha["id"],
                "tipo": linha["tipo"],
                "payload": linha["payload"],
                "criado_em": linha["criado_em"].isoformat(),
            }
            for linha in linhas
        ]

    # ---------------------------------------------------------------- escrita

    def criar_sessao(
        self,
        aluno: str,
        target_id: str,
        dominio_inicial: Mapping[str, float],
        evento: Mapping[str, Any] | None = None,
    ) -> str:
        with self._pool.connection() as conn:
            linha = conn.execute(
                "INSERT INTO sessao (aluno, target_id) VALUES (%s, %s) RETURNING id",
                (aluno, target_id),
            ).fetchone()
            sessao_id = str(linha["id"])
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO dominio (sessao_id, kc_id, p) VALUES (%s, %s, %s)",
                    [
                        (sessao_id, kc_id, p)
                        for kc_id, p in sorted(dominio_inicial.items())
                    ],
                )
            if evento is not None:
                conn.execute(
                    "INSERT INTO evento (sessao_id, tipo, payload) VALUES (%s, %s, %s)",
                    (sessao_id, "replanejamento", Jsonb(dict(evento))),
                )
        return sessao_id

    def interagir(
        self,
        sessao_id: str,
        calcular: Callable[[str, dict[str, float]], Interacao],
    ) -> Interacao:
        """Executa uma resposta em transação única, com lock por sessão.

        A função ``calcular`` recebe o alvo atual e o vetor de domínio já
        carregados sob lock, devolvendo o resultado a ser persistido. Tudo
        (domínio, tentativa, atualização da sessão e evento) é confirmado de
        uma vez ou revertido por inteiro.
        """

        with self._pool.connection() as conn:
            linha = conn.execute(
                "SELECT id, target_id FROM sessao WHERE id = %s FOR UPDATE",
                (sessao_id,),
            ).fetchone()
            if linha is None:
                raise SessaoNaoEncontrada(f"sessão {sessao_id} não encontrada")

            dominio = {
                registro["kc_id"]: float(registro["p"])
                for registro in conn.execute(
                    "SELECT kc_id, p FROM dominio WHERE sessao_id = %s",
                    (sessao_id,),
                )
            }

            interacao = calcular(linha["target_id"], dominio)

            conn.execute(
                "INSERT INTO dominio (sessao_id, kc_id, p) VALUES (%s, %s, %s) "
                "ON CONFLICT (sessao_id, kc_id) DO UPDATE "
                "SET p = EXCLUDED.p, atualizada_em = now()",
                (sessao_id, interacao.kc_id, interacao.p_depois),
            )
            conn.execute(
                "INSERT INTO tentativa "
                "(sessao_id, kc_id, item_id, escolha, correta, p_antes, p_depois) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    sessao_id,
                    interacao.kc_id,
                    interacao.item_id,
                    interacao.escolha,
                    interacao.correta,
                    interacao.p_antes,
                    interacao.p_depois,
                ),
            )
            conn.execute(
                "UPDATE sessao SET atualizada_em = now() WHERE id = %s",
                (sessao_id,),
            )
            if interacao.evento is not None:
                conn.execute(
                    "INSERT INTO evento (sessao_id, tipo, payload) VALUES (%s, %s, %s)",
                    (
                        sessao_id,
                        interacao.evento_tipo or "evento",
                        Jsonb(dict(interacao.evento)),
                    ),
                )

        return interacao

    def trocar_target(
        self,
        sessao_id: str,
        target_id: str,
        dominio_novo: Mapping[str, float],
        evento: Mapping[str, Any],
    ) -> None:
        with self._pool.connection() as conn:
            linha = conn.execute(
                "SELECT id FROM sessao WHERE id = %s FOR UPDATE",
                (sessao_id,),
            ).fetchone()
            if linha is None:
                raise SessaoNaoEncontrada(f"sessão {sessao_id} não encontrada")

            if dominio_novo:
                with conn.cursor() as cur:
                    cur.executemany(
                        "INSERT INTO dominio (sessao_id, kc_id, p) VALUES (%s, %s, %s) "
                        "ON CONFLICT (sessao_id, kc_id) DO NOTHING",
                        [
                            (sessao_id, kc_id, p)
                            for kc_id, p in sorted(dominio_novo.items())
                        ],
                    )

            conn.execute(
                "UPDATE sessao SET target_id = %s, atualizada_em = now() WHERE id = %s",
                (target_id, sessao_id),
            )
            conn.execute(
                "INSERT INTO evento (sessao_id, tipo, payload) VALUES (%s, %s, %s)",
                (sessao_id, "replanejamento", Jsonb(dict(evento))),
            )


def _item(linha: Mapping[str, Any]) -> Item:
    return Item(
        id=linha["id"],
        kc_id=linha["kc_id"],
        enunciado=linha["enunciado"],
        alternativas=tuple(linha["alternativas"]),
        correta=linha["correta"],
        dificuldade=linha["dificuldade"],
    )


def _sessao(linha: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(linha["id"]),
        "aluno": linha["aluno"],
        "target_id": linha["target_id"],
        "criada_em": linha["criada_em"].isoformat(),
        "atualizada_em": linha["atualizada_em"].isoformat(),
    }
