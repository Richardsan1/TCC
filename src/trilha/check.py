"""Validação de integridade do currículo carregado do banco.

Uso: PYTHONPATH=src python -m trilha.check
Sai com código 1 (e lista os problemas) se o currículo não estiver apto.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from .config import database_url
from .graph import detect_cycle
from .models import Curriculum, Item
from .repo import Repositorio

LETRAS_VALIDAS = frozenset("abcd")


def validar(curriculo: Curriculum, itens: Sequence[Item]) -> list[str]:
    problemas: list[str] = []

    ciclo = detect_cycle(curriculo)
    if ciclo is not None:
        problemas.append("ciclo detectado: " + " -> ".join(ciclo))

    kcs_com_item = {item.kc_id for item in itens}
    for kc_id in curriculo.node_ids:
        if kc_id not in kcs_com_item:
            problemas.append(f"KC sem item de diagnóstico: {kc_id}")

    for item in itens:
        if item.kc_id not in curriculo.kcs:
            problemas.append(f"item {item.id} aponta para KC inexistente: {item.kc_id}")
            continue
        if len(item.alternativas) != 4:
            problemas.append(
                f"item {item.id} deve ter 4 alternativas (tem {len(item.alternativas)})"
            )
        if item.correta not in LETRAS_VALIDAS:
            problemas.append(f"item {item.id} tem gabarito inválido: {item.correta!r}")

    return problemas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Valida o currículo no banco")
    parser.add_argument("--dsn", default=None, help="DSN do Postgres")
    args = parser.parse_args(argv)

    with Repositorio(args.dsn or database_url()) as repo:
        curriculo = repo.carregar_curriculo()
        itens = repo.listar_itens(curriculo.kcs)

    problemas = validar(curriculo, itens)

    if problemas:
        print(f"currículo INVÁLIDO ({len(problemas)} problema(s)):", file=sys.stderr)
        for problema in problemas:
            print(f"  - {problema}", file=sys.stderr)
        return 1

    arestas = sum(len(destinos) for destinos in curriculo.dependents.values())
    print(
        f"currículo OK: {len(curriculo)} KCs, {arestas} arestas, "
        f"{len(itens)} itens, DAG acíclico"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
