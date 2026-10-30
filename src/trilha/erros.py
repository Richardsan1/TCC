"""Erros de domínio compartilhados entre motor, repositório e API.

Ficam em módulo próprio para evitar import circular entre ``engine`` e ``repo``.
"""

from __future__ import annotations


class ErroMotor(Exception):
    """Erro de domínio do motor (mapeado para HTTP na camada de API)."""


class SessaoNaoEncontrada(ErroMotor):
    pass


class AlvoInvalido(ErroMotor):
    pass


class ItemInvalido(ErroMotor):
    pass


class ItemForaDoEscopo(ErroMotor):
    pass


class RespostaInvalida(ErroMotor):
    pass


class CurriculoInvalido(ErroMotor):
    pass
