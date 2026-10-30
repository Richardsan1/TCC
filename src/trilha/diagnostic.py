"""Seleção de itens para a avaliação diagnóstica inicial."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .graph import ancestor_closure, critical_path_lengths
from .models import Curriculum, Item


@dataclass(frozen=True, slots=True)
class QuestaoDiagnostica:
    item_id: int
    kc_id: str
    kc_nome: str
    enunciado: str
    alternativas: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "item_id": self.item_id,
            "kc_id": self.kc_id,
            "kc_nome": self.kc_nome,
            "enunciado": self.enunciado,
            "alternativas": list(self.alternativas),
        }


def selecionar(
    itens: Sequence[Item],
    curriculum: Curriculum,
    target: str,
    limite_por_kc: int = 1,
) -> list[QuestaoDiagnostica]:
    """Um item por KC do fechamento de pré-requisitos do alvo.

    A ordem segue o caminho crítico (mais distante do alvo primeiro), de modo
    que o diagnóstico comece pelas bases do currículo.
    """

    subgrafo = ancestor_closure(curriculum, target)
    dist = critical_path_lengths(curriculum, target, subgrafo)

    por_kc: dict[str, list[Item]] = {}
    for item in itens:
        if item.kc_id in subgrafo:
            por_kc.setdefault(item.kc_id, []).append(item)

    questoes: list[QuestaoDiagnostica] = []
    for kc_id in sorted(por_kc, key=lambda k: (-dist[k], k)):
        for item in sorted(por_kc[kc_id], key=lambda i: i.id)[:limite_por_kc]:
            questoes.append(
                QuestaoDiagnostica(
                    item_id=item.id,
                    kc_id=kc_id,
                    kc_nome=curriculum.kcs[kc_id].nome,
                    enunciado=item.enunciado,
                    alternativas=item.alternativas,
                )
            )
    return questoes
