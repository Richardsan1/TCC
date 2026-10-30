"""Bayesian Knowledge Tracing com quatro parâmetros.

Modelo de Corbett & Anderson (1994) sobre um HMM de dois estados
(dominado / não dominado) por Knowledge Component.
"""

from __future__ import annotations

from .models import KC


def update(
    p_dominio: float,
    acertou: bool,
    *,
    p_learn: float,
    p_slip: float,
    p_guess: float,
) -> float:
    """Aplica um passo de BKT e devolve a nova probabilidade de domínio.

    ``p_slip`` é a chance de errar sabendo; ``p_guess`` é a chance de acertar
    sem saber; ``p_learn`` é a chance de aprender entre duas interações.
    """

    p = min(max(p_dominio, 0.0), 1.0)

    if acertou:
        numerador = p * (1.0 - p_slip)
        denominador = numerador + (1.0 - p) * p_guess
    else:
        numerador = p * p_slip
        denominador = numerador + (1.0 - p) * (1.0 - p_guess)

    posterior = numerador / denominador if denominador > 0.0 else p
    return posterior + (1.0 - posterior) * p_learn


def aplicar(p_dominio: float, acertou: bool, kc: KC) -> float:
    """Conveniência: aplica o update usando os parâmetros do próprio KC."""

    return update(
        p_dominio,
        acertou,
        p_learn=kc.p_learn,
        p_slip=kc.p_slip,
        p_guess=kc.p_guess,
    )


def dominado(p_dominio: float, threshold: float) -> bool:
    return p_dominio >= threshold
