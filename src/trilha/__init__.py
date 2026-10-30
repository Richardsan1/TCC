"""Motor de trilhas de aprendizagem personalizadas.

O núcleo (grafos, BKT e planejador) não importa driver de banco; ``Motor``
é resolvido sob demanda para manter os testes puros independentes de psycopg.
"""

from __future__ import annotations

from .bkt import aplicar, dominado, update
from .graph import (
    ancestor_closure,
    critical_path_lengths,
    detect_cycle,
    topological_order,
    topological_order_dfs,
)
from .models import KC, Curriculum, Item, Plan, PlanStep, THRESHOLD_PADRAO
from .planner import plan

__all__ = [
    "KC",
    "Curriculum",
    "Item",
    "Motor",
    "Plan",
    "PlanStep",
    "THRESHOLD_PADRAO",
    "ancestor_closure",
    "aplicar",
    "critical_path_lengths",
    "detect_cycle",
    "dominado",
    "plan",
    "topological_order",
    "topological_order_dfs",
    "update",
]


def __getattr__(nome: str):
    if nome == "Motor":
        from .engine import Motor

        return Motor
    raise AttributeError(f"module {__name__!r} has no attribute {nome!r}")
