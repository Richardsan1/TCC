"""Modelos puros do motor de trilhas.

Nenhum módulo aqui depende de banco de dados ou de framework web, o que
mantém o núcleo algorítmico testável de forma isolada.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

THRESHOLD_PADRAO = 0.95


@dataclass(frozen=True, slots=True)
class KC:
    """Knowledge Component: vértice do DAG curricular."""

    id: str
    nome: str
    area: str
    dificuldade: int
    p_init: float = 0.10
    p_learn: float = 0.30
    p_slip: float = 0.10
    p_guess: float = 0.20

    def __post_init__(self) -> None:
        if not 1 <= self.dificuldade <= 5:
            raise ValueError(f"KC {self.id!r}: dificuldade deve estar entre 1 e 5")
        for campo in ("p_init", "p_learn", "p_slip", "p_guess"):
            valor = getattr(self, campo)
            if not 0.0 <= valor <= 1.0:
                raise ValueError(f"KC {self.id!r}: {campo} fora do intervalo [0, 1]")
        if self.p_slip >= 1.0 or self.p_guess >= 1.0:
            raise ValueError(f"KC {self.id!r}: p_slip e p_guess devem ser menores que 1")


@dataclass(frozen=True, slots=True)
class Item:
    """Item de avaliação diagnóstica associado a um KC.

    ``correta`` nunca é exposta ao cliente; apenas o motor a utiliza.
    """

    id: int
    kc_id: str
    enunciado: str
    alternativas: tuple[str, ...]
    correta: str
    dificuldade: int = 1


@dataclass(frozen=True, slots=True)
class Curriculum:
    """DAG curricular em lista de adjacências (nos dois sentidos).

    ``prereqs`` mapeia destino -> origens e ``dependents`` mapeia
    origem -> destinos. Ambos são normalizados e ordenados para garantir
    determinismo na geração das trilhas.
    """

    kcs: Mapping[str, KC]
    prereqs: Mapping[str, tuple[str, ...]]
    dependents: Mapping[str, tuple[str, ...]]

    @classmethod
    def from_edges(
        cls,
        kcs: Iterable[KC],
        edges: Iterable[tuple[str, str]],
    ) -> "Curriculum":
        mapa = {kc.id: kc for kc in kcs}
        if len(mapa) == 0:
            raise ValueError("currículo vazio")

        prereqs: dict[str, set[str]] = {kc_id: set() for kc_id in mapa}
        dependents: dict[str, set[str]] = {kc_id: set() for kc_id in mapa}

        for origem, destino in edges:
            if origem not in mapa or destino not in mapa:
                raise ValueError(
                    f"aresta {origem!r} -> {destino!r} referencia KC inexistente"
                )
            if origem == destino:
                raise ValueError(f"auto-aresta em {origem!r}")
            prereqs[destino].add(origem)
            dependents[origem].add(destino)

        return cls(
            kcs=mapa,
            prereqs={kc_id: tuple(sorted(v)) for kc_id, v in prereqs.items()},
            dependents={kc_id: tuple(sorted(v)) for kc_id, v in dependents.items()},
        )

    def __len__(self) -> int:
        return len(self.kcs)

    @property
    def node_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.kcs))

    def posicao_inicial(self, kc_id: str) -> float:
        return self.kcs[kc_id].p_init


@dataclass(frozen=True, slots=True)
class PlanStep:
    kc: KC
    p_atual: float
    motivo: str


@dataclass(frozen=True, slots=True)
class Plan:
    target: KC
    passos: tuple[PlanStep, ...]
    alcancado: bool
    podados: int
    pendentes: int
    sem_item: int = 0

    def to_dict(self) -> dict:
        return {
            "target": {"id": self.target.id, "nome": self.target.nome},
            "alcancado": self.alcancado,
            "podados": self.podados,
            "pendentes": self.pendentes,
            "sem_item": self.sem_item,
            "passos": [
                {
                    "kc_id": passo.kc.id,
                    "nome": passo.kc.nome,
                    "area": passo.kc.area,
                    "dificuldade": passo.kc.dificuldade,
                    "p_atual": round(passo.p_atual, 5),
                    "motivo": passo.motivo,
                }
                for passo in self.passos
            ],
        }
