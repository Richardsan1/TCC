"""Planejador: gera a trilha mínima até um nó-objetivo."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from .bkt import dominado
from .graph import ancestor_closure, critical_path_lengths, topological_order
from .models import Plan, PlanStep, Curriculum, THRESHOLD_PADRAO


def plan(
    curriculum: Curriculum,
    target: str,
    dominio: Mapping[str, float],
    threshold: float = THRESHOLD_PADRAO,
    avaliaveis: Iterable[str] | None = None,
) -> Plan:
    """Monta a trilha de estudo personalizada.

    Passos:
      1. poda tudo que não é ancestral do alvo;
      2. remove KCs sem item de avaliação (não há como medi-los);
      3. remove KCs já dominados;
      4. ordena topologicamente o restante, com desempate por
         menor probabilidade de domínio e maior caminho crítico.
    """

    if target not in curriculum.kcs:
        raise ValueError(f"KC alvo inexistente: {target!r}")

    alvo = curriculum.kcs[target]
    subgrafo = ancestor_closure(curriculum, target)
    permitidos = None if avaliaveis is None else frozenset(avaliaveis)

    def p(no: str) -> float:
        return dominio.get(no, curriculum.kcs[no].p_init)

    pendentes: set[str] = set()
    sem_item = 0
    for no in subgrafo:
        if permitidos is not None and no not in permitidos:
            sem_item += 1
            continue
        if not dominado(p(no), threshold):
            pendentes.add(no)

    dist = critical_path_lengths(curriculum, target, subgrafo)

    def prioridade(no: str) -> tuple[float, int]:
        return (p(no), -dist[no])

    ordem = topological_order(curriculum, nodes=pendentes, prioridade=prioridade)

    passos = []
    for no in ordem:
        dependentes_pendentes = [
            destino for destino in curriculum.dependents[no] if destino in pendentes
        ]
        if no == target:
            motivo = "objetivo"
        elif dependentes_pendentes:
            motivo = "pré-requisito de " + ", ".join(sorted(dependentes_pendentes))
        else:
            motivo = "revisão"

        passos.append(PlanStep(kc=curriculum.kcs[no], p_atual=p(no), motivo=motivo))

    alvo_avaliavel = permitidos is None or target in permitidos

    return Plan(
        target=alvo,
        passos=tuple(passos),
        alcancado=alvo_avaliavel and target not in pendentes,
        podados=len(curriculum.kcs) - len(subgrafo),
        pendentes=len(pendentes),
        sem_item=sem_item,
    )


def proximo_passo(
    curriculum: Curriculum,
    target: str,
    dominio: Mapping[str, float],
    threshold: float = THRESHOLD_PADRAO,
    avaliaveis: Iterable[str] | None = None,
) -> PlanStep | None:
    trilha = plan(curriculum, target, dominio, threshold, avaliaveis)
    return trilha.passos[0] if trilha.passos else None
