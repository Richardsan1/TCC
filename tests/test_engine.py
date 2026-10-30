from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest

from trilha.engine import (
    AlvoInvalido,
    CurriculoInvalido,
    ItemForaDoEscopo,
    ItemInvalido,
    Motor,
    RespostaInvalida,
    SessaoNaoEncontrada,
)
from trilha.repo import Repositorio

ALVO = "funcao_quadratica"
SESSAO_INEXISTENTE = "00000000-0000-0000-0000-000000000000"


@pytest.fixture()
def motor(repo: Repositorio) -> Motor:
    return Motor(repo)


def test_criar_sessao_monta_diagnostico_e_plano(motor: Motor) -> None:
    sessao = motor.criar_sessao(ALVO, "Ana")
    curriculo = motor.curriculo
    esperados = {
        "numeros_inteiros",
        "expressoes_algebricas",
        "potenciacao_radiciacao",
        "produtos_notaveis",
        "equacao_1grau",
        "equacao_2grau",
        "funcao_afim",
        ALVO,
    }

    assert sessao["target_id"] == ALVO
    assert sessao["diagnostico"], "diagnóstico não pode ser vazio"
    assert {q["kc_id"] for q in sessao["diagnostico"]} == esperados
    assert sessao["plano"]["passos"][-1]["kc_id"] == ALVO
    assert sessao["plano"]["podados"] == len(curriculo) - len(esperados)
    assert sessao["plano"]["alcancado"] is False


def test_diagnostico_nao_vaza_gabarito(motor: Motor) -> None:
    sessao = motor.criar_sessao(ALVO)
    for questao in sessao["diagnostico"]:
        assert "correta" not in questao


def test_alvo_invalido_na_criacao(motor: Motor) -> None:
    with pytest.raises(AlvoInvalido):
        motor.criar_sessao("nao_existe")


def test_resposta_correta_atualiza_bkt_e_persiste(motor: Motor) -> None:
    sessao = motor.criar_sessao(ALVO)
    sessao_id = sessao["sessao_id"]
    questao = sessao["diagnostico"][0]
    gabarito = motor.repo.obter_item(questao["item_id"]).correta  # type: ignore[union-attr]

    resultado = motor.responder(sessao_id, questao["item_id"], gabarito)

    assert resultado["correta"] is True
    assert resultado["p_depois"] > resultado["p_antes"]
    assert resultado["p_antes"] == pytest.approx(0.1)

    estado = motor.estado(sessao_id)
    assert len(estado["tentativas"]) == 1
    assert estado["dominio"][questao["kc_id"]] == pytest.approx(resultado["p_depois"], abs=1e-5)


def test_resposta_errada_reduz_probabilidade(motor: Motor) -> None:
    sessao = motor.criar_sessao(ALVO)
    questao = sessao["diagnostico"][0]
    item = motor.repo.obter_item(questao["item_id"])
    assert item is not None

    errada = next(letra for letra in "abcd" if letra != item.correta)
    resultado = motor.responder(sessao["sessao_id"], item.id, errada)

    assert resultado["correta"] is False
    assert resultado["p_depois"] > 0.0


def test_nao_sei_conta_como_erro_e_fica_registrado(motor: Motor) -> None:
    sessao = motor.criar_sessao(ALVO)
    questao = sessao["diagnostico"][0]
    item = motor.repo.obter_item(questao["item_id"])
    assert item is not None
    errada = next(letra for letra in "abcd" if letra != item.correta)

    nao_sei = motor.responder(sessao["sessao_id"], item.id, "?")
    outra = motor.criar_sessao(ALVO)
    erro = motor.responder(outra["sessao_id"], item.id, errada)

    assert nao_sei["correta"] is False
    assert nao_sei["nao_sei"] is True
    assert erro["nao_sei"] is False
    assert nao_sei["p_depois"] == pytest.approx(erro["p_depois"])
    assert nao_sei["p_depois"] < 0.5
    tentativa = motor.estado(sessao["sessao_id"])["tentativas"][0]
    assert tentativa["escolha"] == "?"


def test_proximo_item_varia_entre_questoes_do_kc(motor: Motor) -> None:
    sessao_id = motor.criar_sessao(ALVO)["sessao_id"]

    vistos = []
    for _ in range(3):
        questao = motor.proximo_item(sessao_id)["questao"]
        assert "correta" not in questao
        vistos.append(questao["item_id"])
        motor.responder(sessao_id, questao["item_id"], "?")

    kc = motor.repo.obter_item(vistos[0]).kc_id  # type: ignore[union-attr]
    assert len(set(vistos)) == 3
    assert {motor.repo.obter_item(i).kc_id for i in vistos} == {kc}  # type: ignore[union-attr]


def test_proximo_item_vazio_quando_alvo_alcancado(motor: Motor) -> None:
    sessao_id = motor.criar_sessao("numeros_inteiros")["sessao_id"]
    for _ in range(20):
        resposta = motor.proximo_item(sessao_id)
        if resposta["questao"] is None:
            break
        item = motor.repo.obter_item(resposta["questao"]["item_id"])
        motor.responder(sessao_id, item.id, item.correta)  # type: ignore[union-attr]

    assert motor.proximo_item(sessao_id) == {"passo": None, "questao": None}


def test_item_invalido(motor: Motor) -> None:
    sessao_id = motor.criar_sessao(ALVO)["sessao_id"]
    with pytest.raises(ItemInvalido):
        motor.responder(sessao_id, 999_999, "a")


def test_alternativa_invalida(motor: Motor) -> None:
    sessao = motor.criar_sessao(ALVO)
    questao = sessao["diagnostico"][0]
    with pytest.raises(RespostaInvalida):
        motor.responder(sessao["sessao_id"], questao["item_id"], "z")


def test_sessao_inexistente(motor: Motor) -> None:
    with pytest.raises(SessaoNaoEncontrada):
        motor.estado(SESSAO_INEXISTENTE)
    with pytest.raises(SessaoNaoEncontrada):
        motor.responder(SESSAO_INEXISTENTE, 1, "a")


def test_replanejamento_encurta_trilha(motor: Motor) -> None:
    sessao = motor.criar_sessao(ALVO)
    sessao_id = sessao["sessao_id"]
    antes = len(motor.trilha(sessao_id)["passos"])

    for questao in sessao["diagnostico"]:
        item = motor.repo.obter_item(questao["item_id"])
        assert item is not None
        for _ in range(4):  # 4 acertos levam p acima do threshold
            motor.responder(sessao_id, item.id, item.correta)

    depois = motor.trilha(sessao_id)
    assert depois["alcancado"] is True
    assert len(depois["passos"]) < antes


def test_alterar_alvo_atualiza_sessao(motor: Motor) -> None:
    sessao_id = motor.criar_sessao(ALVO)["sessao_id"]

    resposta = motor.definir_target(sessao_id, "logaritmo")

    assert resposta["target_anterior"] == ALVO
    assert resposta["target_id"] == "logaritmo"
    assert resposta["plano"]["passos"][-1]["kc_id"] == "logaritmo"

    estado = motor.estado(sessao_id)
    assert estado["sessao"]["target_id"] == "logaritmo"
    assert "funcao_exponencial" in estado["dominio"]


def test_alterar_para_alvo_invalido(motor: Motor) -> None:
    sessao_id = motor.criar_sessao(ALVO)["sessao_id"]
    with pytest.raises(AlvoInvalido):
        motor.definir_target(sessao_id, "nao_existe")


def test_eventos_registram_replanejamentos(motor: Motor) -> None:
    sessao = motor.criar_sessao(ALVO)
    sessao_id = sessao["sessao_id"]
    questao = sessao["diagnostico"][0]
    item = motor.repo.obter_item(questao["item_id"])
    assert item is not None

    motor.responder(sessao_id, item.id, item.correta)

    eventos = motor.repo.listar_eventos(sessao_id)
    gatilhos = [evento["payload"]["gatilho"] for evento in eventos]
    assert "sessao_criada" in gatilhos
    assert "resposta" in gatilhos


def test_respostas_concorrentes_nao_perdem_atualizacao(motor: Motor) -> None:
    sessao = motor.criar_sessao(ALVO)
    sessao_id = sessao["sessao_id"]
    item = motor.repo.obter_item(sessao["diagnostico"][0]["item_id"])
    assert item is not None

    def responder_dez_vezes(_: int) -> None:
        for _ in range(10):
            motor.responder(sessao_id, item.id, item.correta)

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(responder_dez_vezes, range(2)))

    assert motor.repo.contar_tentativas(sessao_id) == 20

    referencia = motor.criar_sessao(ALVO)["sessao_id"]
    for _ in range(20):
        motor.responder(referencia, item.id, item.correta)

    assert motor.repo.obter_dominio(sessao_id)[item.kc_id] == pytest.approx(
        motor.repo.obter_dominio(referencia)[item.kc_id]
    )


def test_item_fora_do_escopo_e_rejeitado(motor: Motor) -> None:
    sessao_id = motor.criar_sessao("logaritmo")["sessao_id"]
    item = motor.repo.obter_item(25)  # medidas_tendencia
    assert item is not None

    with pytest.raises(ItemForaDoEscopo):
        motor.responder(sessao_id, item.id, "a")

    assert motor.repo.contar_tentativas(sessao_id) == 0


def test_resposta_atualiza_timestamp_da_sessao(motor: Motor) -> None:
    sessao = motor.criar_sessao(ALVO)
    sessao_id = sessao["sessao_id"]
    antes = motor.repo.obter_sessao(sessao_id)["atualizada_em"]  # type: ignore[index]

    time.sleep(0.01)
    item = motor.repo.obter_item(sessao["diagnostico"][0]["item_id"])
    assert item is not None
    motor.responder(sessao_id, item.id, item.correta)

    depois = motor.repo.obter_sessao(sessao_id)["atualizada_em"]  # type: ignore[index]
    assert depois != antes


def test_ciclo_no_banco_impede_a_carga(banco_limpo: str, repo: Repositorio) -> None:
    with psycopg.connect(banco_limpo) as conn:
        conn.execute(
            "INSERT INTO kc_prereq (origem_id, destino_id) "
            "VALUES ('logaritmo', 'numeros_inteiros')"
        )

    try:
        with pytest.raises(CurriculoInvalido):
            Motor(repo).curriculo
    finally:
        with psycopg.connect(banco_limpo) as conn:
            conn.execute(
                "DELETE FROM kc_prereq "
                "WHERE origem_id = 'logaritmo' AND destino_id = 'numeros_inteiros'"
            )


def test_estado_respeita_limite_de_tentativas(motor: Motor) -> None:
    sessao = motor.criar_sessao(ALVO)
    sessao_id = sessao["sessao_id"]
    item = motor.repo.obter_item(sessao["diagnostico"][0]["item_id"])
    assert item is not None

    for _ in range(5):
        motor.responder(sessao_id, item.id, item.correta)

    estado = motor.estado(sessao_id, limite=2)
    assert len(estado["tentativas"]) == 2
    assert estado["total_tentativas"] == 5
    assert estado["limite"] == 2
