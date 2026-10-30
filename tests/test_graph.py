from __future__ import annotations

import pytest

from trilha.graph import (
    ancestor_closure,
    critical_path_lengths,
    detect_cycle,
    topological_order,
    topological_order_dfs,
)
from trilha.models import KC, Curriculum


def kc(kc_id: str, dificuldade: int = 2) -> KC:
    return KC(id=kc_id, nome=kc_id.upper(), area="teste", dificuldade=dificuldade)


def montar(nos: list[str], arestas: list[tuple[str, str]]) -> Curriculum:
    return Curriculum.from_edges([kc(n) for n in nos], arestas)


def assert_ordem_valida(curriculum: Curriculum, ordem: list[str]) -> None:
    posicao = {no: indice for indice, no in enumerate(ordem)}
    for origem in ordem:
        for destino in curriculum.dependents[origem]:
            if destino in posicao:
                assert posicao[origem] < posicao[destino], (origem, destino)


def test_dag_sem_ciclo() -> None:
    curriculo = montar(["a", "b", "c"], [("a", "b"), ("b", "c")])
    assert detect_cycle(curriculo) is None


def test_detecta_ciclo_e_devolve_caminho_fechado() -> None:
    curriculo = montar(["a", "b", "c"], [("a", "b"), ("b", "c"), ("c", "a")])
    ciclo = detect_cycle(curriculo)

    assert ciclo is not None
    assert ciclo[0] == ciclo[-1]
    for origem, destino in zip(ciclo, ciclo[1:], strict=False):
        assert destino in curriculo.dependents[origem]


def test_auto_aresta_e_rejeitada() -> None:
    with pytest.raises(ValueError, match="auto-aresta"):
        montar(["a"], [("a", "a")])


def test_aresta_com_no_inexistente_e_rejeitada() -> None:
    with pytest.raises(ValueError, match="inexistente"):
        montar(["a"], [("a", "z")])


def test_fechamento_de_ancestrais() -> None:
    curriculo = montar(
        ["base", "meio", "alvo", "isola"],
        [("base", "meio"), ("meio", "alvo")],
    )
    assert ancestor_closure(curriculo, "alvo") == frozenset({"base", "meio", "alvo"})


def test_fechamento_de_alvo_inexistente_falha() -> None:
    curriculo = montar(["a"], [])
    with pytest.raises(ValueError):
        ancestor_closure(curriculo, "nao_existe")


def test_kahn_respeita_arestas() -> None:
    curriculo = montar(
        ["a", "b", "c", "d"],
        [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")],
    )
    ordem = topological_order(curriculo)

    assert sorted(ordem) == ["a", "b", "c", "d"]
    assert_ordem_valida(curriculo, ordem)
    assert ordem.index("a") == 0
    assert ordem.index("d") == 3


def test_kahn_e_deterministico() -> None:
    curriculo = montar(
        ["a", "b", "c", "d", "e"],
        [("a", "c"), ("b", "c"), ("c", "d"), ("c", "e")],
    )
    assert topological_order(curriculo) == topological_order(curriculo)


def test_kahn_respeita_prioridade() -> None:
    curriculo = montar(["a", "b", "c"], [])
    prioridade = {"a": 0.9, "b": 0.1, "c": 0.5}
    ordem = topological_order(curriculo, prioridade=lambda no: (prioridade[no],))
    assert ordem == ["b", "c", "a"]


def test_kahn_em_subconjunto_ignora_arestas_externas() -> None:
    curriculo = montar(["a", "b", "c"], [("a", "b"), ("b", "c")])
    ordem = topological_order(curriculo, nodes={"b", "c"})

    assert ordem == ["b", "c"]
    assert_ordem_valida(curriculo, ordem)


def test_kahn_falha_com_ciclo() -> None:
    curriculo = montar(["a", "b"], [("a", "b"), ("b", "a")])
    with pytest.raises(ValueError, match="ciclo"):
        topological_order(curriculo)


def test_dfs_e_referencia_valida_para_kahn() -> None:
    curriculo = montar(
        ["a", "b", "c", "d", "e", "f"],
        [
            ("a", "b"),
            ("a", "c"),
            ("b", "d"),
            ("c", "d"),
            ("d", "e"),
            ("a", "f"),
        ],
    )
    ordem_dfs = topological_order_dfs(curriculo)
    ordem_kahn = topological_order(curriculo)

    assert set(ordem_dfs) == set(curriculo.kcs)
    assert_ordem_valida(curriculo, ordem_dfs)
    assert set(ordem_kahn) == set(curriculo.kcs)
    assert_ordem_valida(curriculo, ordem_kahn)


def test_caminho_critico_em_cadeia() -> None:
    curriculo = montar(
        ["a", "b", "c", "alvo"],
        [("a", "b"), ("b", "c"), ("c", "alvo")],
    )
    dist = critical_path_lengths(curriculo, "alvo")

    assert dist["alvo"] == 0
    assert dist["c"] == 1
    assert dist["b"] == 2
    assert dist["a"] == 3


def test_caminho_critico_usa_o_caminho_mais_longo() -> None:
    curriculo = montar(
        ["curto", "longo1", "longo2", "alvo"],
        [("curto", "alvo"), ("longo1", "longo2"), ("longo2", "alvo")],
    )
    dist = critical_path_lengths(curriculo, "alvo")

    assert dist["curto"] == 1
    assert dist["longo1"] == 2
    assert dist["longo2"] == 1
