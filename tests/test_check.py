from __future__ import annotations

from trilha.check import validar
from trilha.models import KC, Curriculum, Item


def kc(kc_id: str) -> KC:
    return KC(id=kc_id, nome=kc_id.upper(), area="teste", dificuldade=2)


def item(item_id: int, kc_id: str, alternativas: tuple[str, ...] = ("a", "b", "c", "d")) -> Item:
    return Item(
        id=item_id,
        kc_id=kc_id,
        enunciado="?",
        alternativas=alternativas,
        correta="a",
    )


def test_curriculo_valido_nao_tem_problemas() -> None:
    curriculo = Curriculum.from_edges([kc("a"), kc("b")], [("a", "b")])
    assert validar(curriculo, [item(1, "a"), item(2, "b")]) == []


def test_ciclo_e_reportado() -> None:
    curriculo = Curriculum.from_edges([kc("a"), kc("b")], [("a", "b"), ("b", "a")])
    problemas = validar(curriculo, [item(1, "a"), item(2, "b")])

    assert any("ciclo" in problema for problema in problemas)


def test_kc_sem_item_e_reportado() -> None:
    curriculo = Curriculum.from_edges([kc("a"), kc("b")], [("a", "b")])
    problemas = validar(curriculo, [item(1, "a")])

    assert problemas == ["KC sem item de diagnóstico: b"]


def test_item_com_kc_inexistente_e_reportado() -> None:
    curriculo = Curriculum.from_edges([kc("a")], [])
    problemas = validar(curriculo, [item(1, "a"), item(2, "z")])

    assert any("KC inexistente" in problema for problema in problemas)


def test_item_com_numero_de_alternativas_invalido() -> None:
    curriculo = Curriculum.from_edges([kc("a")], [])
    problemas = validar(curriculo, [item(1, "a", alternativas=("a", "b", "c"))])

    assert any("4 alternativas" in problema for problema in problemas)
