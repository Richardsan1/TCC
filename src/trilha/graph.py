"""Algoritmos de grafo do motor: ciclos, fechamento e ordenação topológica."""

from __future__ import annotations

import heapq
from collections.abc import Callable, Iterable

from .models import Curriculum

Prioridade = Callable[[str], tuple]


def detect_cycle(curriculum: Curriculum) -> list[str] | None:
    """Busca em profundidade com três cores.

    Retorna o caminho do ciclo (fechado, com o nó inicial repetido no fim)
    ou ``None`` se o grafo for acíclico.
    """

    BRANCO, CINZA, PRETO = 0, 1, 2
    cor = dict.fromkeys(curriculum.kcs, BRANCO)

    for raiz in curriculum.node_ids:
        if cor[raiz] != BRANCO:
            continue

        cor[raiz] = CINZA
        caminho = [raiz]
        pilha: list[tuple[str, int]] = [(raiz, 0)]

        while pilha:
            no, indice = pilha[-1]
            vizinhos = curriculum.dependents[no]

            if indice < len(vizinhos):
                proximo = vizinhos[indice]
                pilha[-1] = (no, indice + 1)

                if cor[proximo] == CINZA:
                    inicio = caminho.index(proximo)
                    return caminho[inicio:] + [proximo]
                if cor[proximo] == BRANCO:
                    cor[proximo] = CINZA
                    caminho.append(proximo)
                    pilha.append((proximo, 0))
            else:
                cor[no] = PRETO
                pilha.pop()
                caminho.pop()

    return None


def ancestor_closure(curriculum: Curriculum, target: str) -> frozenset[str]:
    """Fechamento transitivo de pré-requisitos: tudo que o alvo exige."""

    if target not in curriculum.kcs:
        raise ValueError(f"KC alvo inexistente: {target!r}")

    vistos = {target}
    pilha = [target]
    while pilha:
        no = pilha.pop()
        for origem in curriculum.prereqs[no]:
            if origem not in vistos:
                vistos.add(origem)
                pilha.append(origem)
    return frozenset(vistos)


def topological_order(
    curriculum: Curriculum,
    nodes: Iterable[str] | None = None,
    prioridade: Prioridade | None = None,
) -> list[str]:
    """Algoritmo de Kahn restrito a um subconjunto de nós.

    O desempate é feito por ``prioridade(no)`` (tupla comparável) e, em
    último caso, pelo id do KC — o que torna a trilha determinística.
    Levanta ``ValueError`` se o subconjunto contiver ciclo.
    """

    subconjunto = set(curriculum.node_ids if nodes is None else nodes)
    for no in subconjunto:
        if no not in curriculum.kcs:
            raise ValueError(f"nó desconhecido: {no!r}")

    grau = {no: 0 for no in subconjunto}
    for no in subconjunto:
        for origem in curriculum.prereqs[no]:
            if origem in subconjunto:
                grau[no] += 1

    def chave(no: str) -> tuple:
        base = prioridade(no) if prioridade else ()
        return base + (no,)

    heap: list[tuple[tuple, str]] = []
    for no in subconjunto:
        if grau[no] == 0:
            heapq.heappush(heap, (chave(no), no))

    ordem: list[str] = []
    while heap:
        _, no = heapq.heappop(heap)
        ordem.append(no)
        for destino in curriculum.dependents[no]:
            if destino not in subconjunto:
                continue
            grau[destino] -= 1
            if grau[destino] == 0:
                heapq.heappush(heap, (chave(destino), destino))

    if len(ordem) != len(subconjunto):
        raise ValueError("subgrafo selecionado contém ciclo")
    return ordem


def topological_order_dfs(
    curriculum: Curriculum,
    nodes: Iterable[str] | None = None,
) -> list[str]:
    """Ordenação topológica por DFS (pós-ordem invertida).

    Implementação de referência usada nos testes para conferir o resultado
    de ``topological_order``.
    """

    subconjunto = set(curriculum.node_ids if nodes is None else nodes)
    visitados: set[str] = set()
    ordem: list[str] = []

    for raiz in sorted(subconjunto):
        if raiz in visitados:
            continue

        visitados.add(raiz)
        pilha: list[tuple[str, int]] = [(raiz, 0)]

        while pilha:
            no, indice = pilha[-1]
            vizinhos = [
                destino
                for destino in curriculum.dependents[no]
                if destino in subconjunto
            ]

            if indice < len(vizinhos):
                proximo = vizinhos[indice]
                pilha[-1] = (no, indice + 1)
                if proximo not in visitados:
                    visitados.add(proximo)
                    pilha.append((proximo, 0))
            else:
                ordem.append(no)
                pilha.pop()

    ordem.reverse()
    return ordem


def critical_path_lengths(
    curriculum: Curriculum,
    target: str,
    nodes: Iterable[str] | None = None,
) -> dict[str, int]:
    """Maior distância (em arestas) de cada nó até o alvo.

    Usado como heurística: entre duas lacunas com a mesma probabilidade de
    domínio, prioriza a que está mais longe do objetivo.
    """

    subconjunto = set(curriculum.node_ids if nodes is None else nodes)
    if target not in subconjunto:
        raise ValueError(f"alvo {target!r} fora do subconjunto")

    base = topological_order(curriculum, nodes=subconjunto)
    dist = dict.fromkeys(subconjunto, 0)

    for no in reversed(base):
        if no == target:
            continue
        dist[no] = max(
            (dist[destino] + 1 for destino in curriculum.dependents[no] if destino in subconjunto),
            default=0,
        )

    return dist
