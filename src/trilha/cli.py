"""Demonstração de terminal do motor de trilhas.

Uso:
    PYTHONPATH=src python -m trilha.cli --target funcao_quadratica
    PYTHONPATH=src python -m trilha.cli --target funcao_quadratica --auto
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from .config import database_url, threshold
from .engine import NAO_SEI, ErroMotor, Motor
from .models import Item
from .repo import Repositorio

LETRAS = ("a", "b", "c", "d")
LARGURA = 78


def _titulo(texto: str) -> None:
    print()
    print("=" * LARGURA)
    print(texto)
    print("=" * LARGURA)


def _secao(texto: str) -> None:
    print()
    print(f"-- {texto} " + "-" * max(0, LARGURA - len(texto) - 4))


def _p(valor: float) -> str:
    return f"{valor:0.2f}"


def _plano(plano: dict[str, Any]) -> None:
    status = "ALCANÇADO" if plano["alcancado"] else "PENDENTE"
    _secao(
        f"Trilha até {plano['target']['nome']} [{status}] "
        f"({plano['pendentes']} passos, {plano['podados']} KCs podados)"
    )
    if not plano["passos"]:
        print("  (nada a estudar: todos os pré-requisitos estão dominados)")
        return
    for indice, passo in enumerate(plano["passos"], start=1):
        print(
            f"  {indice:>2}. {passo['nome']:<44.44} "
            f"p={_p(passo['p_atual'])}  {passo['motivo']}"
        )


def _item_para(repo: Repositorio, kc_id: str, usados: set[int]) -> Item:
    itens = repo.listar_itens([kc_id])
    if not itens:
        raise ErroMotor(f"nenhum item cadastrado para o KC {kc_id!r}")
    novos = [item for item in itens if item.id not in usados]
    return (novos or itens)[0]


def _perguntar(item: Item, *, auto: bool) -> str:
    print()
    print(f"  [{item.kc_id}] {item.enunciado}")
    for letra, alternativa in zip(LETRAS, item.alternativas, strict=False):
        print(f"    {letra}) {alternativa}")

    if auto:
        print(f"    -> resposta automática: {item.correta}")
        return item.correta

    while True:
        try:
            escolha = input("    resposta (a-d, ? = não sei): ").strip().lower()
        except EOFError:
            raise SystemExit("\nentrada encerrada") from None
        if escolha in LETRAS or escolha == NAO_SEI:
            return escolha
        print("    escolha inválida, tente novamente")


def _executar(motor: Motor, repo: Repositorio, args: argparse.Namespace) -> None:
    sessao = motor.criar_sessao(args.target, args.aluno)
    sessao_id = sessao["sessao_id"]

    _titulo(f"Aluno: {args.aluno} | Objetivo: {sessao['target_id']}")
    print(f"sessão: {sessao_id}")
    print(f"threshold de domínio: {_p(motor.threshold)}")

    _plano(sessao["plano"])

    diagnosticos = sessao["diagnostico"][: args.limite_diagnostico]
    if diagnosticos:
        _secao(f"Avaliação diagnóstica ({len(diagnosticos)} itens)")

    usados: set[int] = set()
    acertos = 0
    total = 0

    for questao in diagnosticos:
        item = repo.obter_item(questao["item_id"])
        if item is None:
            continue
        escolha = _perguntar(item, auto=args.auto)
        resultado = motor.responder(sessao_id, item.id, escolha)
        usados.add(item.id)
        total += 1
        acertos += int(resultado["correta"])
        marca = "OK " if resultado["correta"] else "ERRO"
        print(
            f"    {marca} p: {_p(resultado['p_antes'])} -> {_p(resultado['p_depois'])}"
        )

    _plano(motor.trilha(sessao_id))

    interacoes = 0
    while interacoes < args.max_passos:
        plano = motor.trilha(sessao_id)
        if plano["alcancado"] or not plano["passos"]:
            break

        proximo = plano["passos"][0]
        item = _item_para(repo, proximo["kc_id"], usados)

        _secao(f"Passo {interacoes + 1}: {proximo['nome']} ({proximo['motivo']})")
        escolha = _perguntar(item, auto=args.auto)
        resultado = motor.responder(sessao_id, item.id, escolha)
        usados.add(item.id)
        interacoes += 1
        total += 1
        acertos += int(resultado["correta"])

        marca = "OK " if resultado["correta"] else "ERRO"
        estado = "dominado" if resultado["dominado"] else "em progresso"
        print(
            f"    {marca} p: {_p(resultado['p_antes'])} -> {_p(resultado['p_depois'])} "
            f"({estado})"
        )

    estado = motor.estado(sessao_id)
    plano = estado["plano"]

    _titulo("Resumo")
    print(f"interações: {total} | acertos: {acertos} | erros: {total - acertos}")
    print(f"alvo alcançado: {'sim' if plano['alcancado'] else 'não'}")
    print(f"pendentes até o alvo: {plano['pendentes']}")
    if plano["passos"]:
        print("próximos passos:")
        for passo in plano["passos"][:5]:
            print(f"  - {passo['nome']} (p={_p(passo['p_atual'])})")
    print()
    print(f"inspecionar no banco: SELECT * FROM tentativa WHERE sessao_id = '{sessao_id}';")


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Demo do motor de trilhas adaptativas")
    parser.add_argument("--target", default="funcao_quadratica", help="KC objetivo")
    parser.add_argument("--aluno", default="anônimo", help="nome do aluno")
    parser.add_argument(
        "--auto",
        action="store_true",
        help="responde automaticamente (usa o gabarito) para demo sem digitação",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=threshold(),
        help="probabilidade de domínio considerada suficiente",
    )
    parser.add_argument(
        "--max-passos",
        type=int,
        default=40,
        help="limite de interações após o diagnóstico",
    )
    parser.add_argument(
        "--limite-diagnostico",
        type=int,
        default=25,
        help="máximo de itens aplicados no diagnóstico",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    try:
        with Repositorio(database_url()) as repo:
            motor = Motor(repo, args.threshold)
            _executar(motor, repo, args)
    except ErroMotor as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
