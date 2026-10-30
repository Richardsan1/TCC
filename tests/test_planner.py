from __future__ import annotations

import pytest

from trilha.models import KC, Curriculum
from trilha.planner import plan, proximo_passo

DOMINIO_VAZIO: dict[str, float] = {}


def montar() -> Curriculum:
    kcs = [
        KC(id="base1", nome="Base 1", area="teste", dificuldade=1),
        KC(id="base2", nome="Base 2", area="teste", dificuldade=2),
        KC(id="meio", nome="Meio", area="teste", dificuldade=3),
        KC(id="alvo", nome="Alvo", area="teste", dificuldade=4),
        KC(id="fora", nome="Fora do caminho", area="teste", dificuldade=1),
    ]
    arestas = [
        ("base1", "meio"),
        ("base2", "meio"),
        ("meio", "alvo"),
        ("base1", "alvo"),
    ]
    return Curriculum.from_edges(kcs, arestas)


def test_plano_poda_nos_fora_do_caminho() -> None:
    trilha = plan(montar(), "alvo", DOMINIO_VAZIO)

    assert trilha.podados == 1
    assert trilha.pendentes == 4
    assert trilha.alcancado is False
    assert {passo.kc.id for passo in trilha.passos} == {"base1", "base2", "meio", "alvo"}


def test_plano_respeita_ordem_topologica() -> None:
    curriculo = montar()
    trilha = plan(curriculo, "alvo", DOMINIO_VAZIO)
    ordem = [passo.kc.id for passo in trilha.passos]

    posicao = {no: indice for indice, no in enumerate(ordem)}
    for origem in ordem:
        for destino in curriculo.dependents[origem]:
            if destino in posicao:
                assert posicao[origem] < posicao[destino]

    assert ordem[-1] == "alvo"


def test_justificativa_de_cada_passo() -> None:
    trilha = plan(montar(), "alvo", DOMINIO_VAZIO)
    motivos = {passo.kc.id: passo.motivo for passo in trilha.passos}

    assert motivos["alvo"] == "objetivo"
    assert motivos["meio"] == "pré-requisito de alvo"
    assert motivos["base1"] == "pré-requisito de alvo, meio"
    assert motivos["base2"] == "pré-requisito de meio"


def test_kc_dominado_sai_da_trilha() -> None:
    trilha = plan(montar(), "alvo", {"base1": 0.99})

    ids = [passo.kc.id for passo in trilha.passos]
    assert "base1" not in ids
    assert trilha.pendentes == 3


def test_objetivo_alcancado_gera_trilha_vazia() -> None:
    dominio = {no: 0.99 for no in ("base1", "base2", "meio", "alvo")}
    trilha = plan(montar(), "alvo", dominio)

    assert trilha.alcancado is True
    assert trilha.passos == ()
    assert proximo_passo(montar(), "alvo", dominio) is None


def test_ponto_de_entrada_prioriza_maior_lacuna() -> None:
    trilha = plan(montar(), "alvo", {"base1": 0.5, "base2": 0.1})

    assert trilha.passos[0].kc.id == "base2"


def test_desempate_por_caminho_critico() -> None:
    kcs = [
        KC(id="a", nome="A", area="t", dificuldade=1),
        KC(id="b", nome="B", area="t", dificuldade=1),
        KC(id="c", nome="C", area="t", dificuldade=1),
        KC(id="alvo", nome="Alvo", area="t", dificuldade=1),
    ]
    curriculo = Curriculum.from_edges(
        kcs,
        [("a", "b"), ("b", "alvo"), ("c", "alvo")],
    )
    trilha = plan(curriculo, "alvo", DOMINIO_VAZIO)

    assert trilha.passos[0].kc.id == "a"
    assert [passo.kc.id for passo in trilha.passos] == ["a", "b", "c", "alvo"]


def test_plano_e_deterministico() -> None:
    primeiro = plan(montar(), "alvo", DOMINIO_VAZIO)
    segundo = plan(montar(), "alvo", DOMINIO_VAZIO)

    assert [p.kc.id for p in primeiro.passos] == [p.kc.id for p in segundo.passos]


def test_threshold_configuravel() -> None:
    dominio = {"base2": 0.9, "meio": 0.9, "alvo": 0.9, "base1": 0.9}

    assert plan(montar(), "alvo", dominio, threshold=0.95).pendentes == 4
    assert plan(montar(), "alvo", dominio, threshold=0.9).alcancado is True


def test_alvo_inexistente_falha() -> None:
    with pytest.raises(ValueError):
        plan(montar(), "nao_existe", DOMINIO_VAZIO)


def test_kc_sem_item_nao_entra_na_trilha() -> None:
    trilha = plan(montar(), "alvo", DOMINIO_VAZIO, avaliaveis={"base1", "base2", "alvo"})

    ids = [passo.kc.id for passo in trilha.passos]
    assert "meio" not in ids
    assert trilha.sem_item == 1
    assert trilha.alcancado is False
    # o alvo continua na trilha, mas sem o pré-requisito não avaliável
    assert ids[-1] == "alvo"


def test_alvo_sem_item_nao_e_considerado_alcancado() -> None:
    trilha = plan(montar(), "alvo", DOMINIO_VAZIO, avaliaveis={"base1", "base2", "meio"})

    ids = [passo.kc.id for passo in trilha.passos]
    assert "alvo" not in ids
    assert trilha.alcancado is False
    assert trilha.sem_item == 1
