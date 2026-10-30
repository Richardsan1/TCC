from __future__ import annotations

import pytest

from trilha.bkt import aplicar, dominado, update
from trilha.models import KC

PARAMS = {"p_learn": 0.30, "p_slip": 0.10, "p_guess": 0.20}


def test_acerto_com_valores_de_referencia() -> None:
    # posterior = 0.5*0.9 / (0.5*0.9 + 0.5*0.2) = 0.81818...
    # p_final = posterior + (1 - posterior) * p_learn = 0.87272...
    assert update(0.5, True, **PARAMS) == pytest.approx(0.87272727, abs=1e-7)


def test_erro_com_valores_de_referencia() -> None:
    # posterior = 0.5*0.1 / (0.5*0.1 + 0.5*0.8) = 0.11111...
    # p_final = 0.11111 + 0.88888 * 0.3 = 0.37777...
    assert update(0.5, False, **PARAMS) == pytest.approx(0.37777778, abs=1e-7)


def test_probabilidade_nunca_sai_do_intervalo() -> None:
    for p_inicial in (0.0, 0.01, 0.5, 0.99, 1.0):
        for acertou in (True, False):
            resultado = update(p_inicial, acertou, **PARAMS)
            assert 0.0 <= resultado <= 1.0


def test_acertos_repetidos_convergem_para_dominio() -> None:
    p = 0.1
    anteriores = [p]
    for _ in range(6):
        p = update(p, True, **PARAMS)
        anteriores.append(p)

    assert anteriores == sorted(anteriores)
    assert p > 0.95


def test_erros_repetidos_reduzem_a_probabilidade() -> None:
    p = 0.8
    for _ in range(4):
        novo = update(p, False, **PARAMS)
        assert novo < p
        p = novo


def test_aplicar_usa_parametros_do_kc() -> None:
    kc = KC(id="x", nome="X", area="t", dificuldade=1)
    assert aplicar(0.5, True, kc) == pytest.approx(update(0.5, True, **PARAMS))


@pytest.mark.parametrize(
    ("p", "esperado"),
    [(0.94, False), (0.95, True), (0.99, True), (0.5, False)],
)
def test_threshold_de_dominio(p: float, esperado: bool) -> None:
    assert dominado(p, 0.95) is esperado
