from __future__ import annotations

import pytest

from trilha.erros import SessaoNaoEncontrada
from trilha.graph import detect_cycle
from trilha.models import Curriculum
from trilha.repo import Interacao, Repositorio

SESSAO_INEXISTENTE = "00000000-0000-0000-0000-000000000000"


def test_carrega_curriculo_do_banco(repo: Repositorio) -> None:
    curriculo = repo.carregar_curriculo()

    assert isinstance(curriculo, Curriculum)
    assert len(curriculo) == 25
    assert curriculo.prereqs["funcao_quadratica"] == ("equacao_2grau", "funcao_afim")


def test_curriculo_do_banco_e_aciclico(repo: Repositorio) -> None:
    assert detect_cycle(repo.carregar_curriculo()) is None


def test_itens_por_kc(repo: Repositorio) -> None:
    itens = repo.listar_itens(["equacao_1grau"])

    assert len(itens) == 3
    for item in itens:
        assert item.kc_id == "equacao_1grau"
        assert len(item.alternativas) == 4
        assert item.correta in {"a", "b", "c", "d"}


def test_todo_kc_tem_tres_itens(repo: Repositorio) -> None:
    curriculo = repo.carregar_curriculo()
    itens = repo.listar_itens(curriculo.kcs)

    por_kc: dict[str, int] = {}
    for item in itens:
        por_kc[item.kc_id] = por_kc.get(item.kc_id, 0) + 1
    assert por_kc == dict.fromkeys(curriculo.kcs, 3)


def test_obter_item_inexistente(repo: Repositorio) -> None:
    assert repo.obter_item(999_999) is None


def test_kcs_com_itens(repo: Repositorio) -> None:
    kcs = repo.kcs_com_itens()

    assert len(kcs) == 25
    assert "funcao_quadratica" in kcs


def test_sessao_round_trip(repo: Repositorio) -> None:
    sessao_id = repo.criar_sessao(
        "Ana",
        "funcao_quadratica",
        {"numeros_inteiros": 0.1, "equacao_1grau": 0.1},
    )

    sessao = repo.obter_sessao(sessao_id)
    assert sessao is not None
    assert sessao["aluno"] == "Ana"
    assert sessao["target_id"] == "funcao_quadratica"
    assert repo.obter_dominio(sessao_id) == {
        "numeros_inteiros": 0.1,
        "equacao_1grau": 0.1,
    }


def test_sessao_inexistente(repo: Repositorio) -> None:
    assert repo.obter_sessao(SESSAO_INEXISTENTE) is None


def test_interagir_persiste_dominio_tentativa_e_evento(repo: Repositorio) -> None:
    sessao_id = repo.criar_sessao("Bia", "medidas_tendencia", {"medidas_tendencia": 0.1})

    def calcular(target: str, dominio: dict[str, float]) -> Interacao:
        assert target == "medidas_tendencia"
        assert dominio["medidas_tendencia"] == 0.1
        return Interacao(
            kc_id="medidas_tendencia",
            item_id=25,
            escolha="a",
            correta=True,
            p_antes=0.1,
            p_depois=0.53,
            evento_tipo="replanejamento",
            evento={"gatilho": "teste"},
        )

    repo.interagir(sessao_id, calcular)

    assert repo.obter_dominio(sessao_id)["medidas_tendencia"] == 0.53
    tentativas = repo.listar_tentativas(sessao_id)
    assert len(tentativas) == 1
    assert tentativas[0]["correta"] is True
    assert tentativas[0]["p_depois"] == 0.53
    assert repo.contar_tentativas(sessao_id) == 1
    assert repo.listar_eventos(sessao_id)[0]["payload"]["gatilho"] == "teste"


def test_interagir_reverte_tudo_em_falha(repo: Repositorio) -> None:
    sessao_id = repo.criar_sessao("Caio", "medidas_tendencia", {"medidas_tendencia": 0.1})

    def calcular(_: str, __: dict[str, float]) -> Interacao:
        return Interacao(
            kc_id="medidas_tendencia",
            item_id=25,
            escolha="a",
            correta=True,
            p_antes=0.1,
            p_depois=0.53,
            evento_tipo="replanejamento",
            evento={"quebrado": object()},  # não é serializável em jsonb
        )

    with pytest.raises(Exception):
        repo.interagir(sessao_id, calcular)

    assert repo.obter_dominio(sessao_id)["medidas_tendencia"] == 0.1
    assert repo.contar_tentativas(sessao_id) == 0
    assert repo.listar_eventos(sessao_id) == []


def test_interagir_sessao_inexistente(repo: Repositorio) -> None:
    def calcular(_: str, __: dict[str, float]) -> Interacao:
        raise AssertionError("não deveria ser chamada")

    with pytest.raises(SessaoNaoEncontrada):
        repo.interagir(SESSAO_INEXISTENTE, calcular)


def test_limite_de_tentativas(repo: Repositorio) -> None:
    sessao_id = repo.criar_sessao("Duda", "medidas_tendencia", {"medidas_tendencia": 0.1})

    for indice in range(3):
        p = 0.1 + indice / 100

        def calcular(_: str, __: dict[str, float], p=p) -> Interacao:
            return Interacao(
                kc_id="medidas_tendencia",
                item_id=25,
                escolha="a",
                correta=True,
                p_antes=0.1,
                p_depois=p,
            )

        repo.interagir(sessao_id, calcular)

    assert repo.contar_tentativas(sessao_id) == 3
    assert len(repo.listar_tentativas(sessao_id, limite=2)) == 2
