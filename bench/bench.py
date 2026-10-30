"""Benchmark do planejador em DAGs sintéticos (sem banco de dados).

Uso: PYTHONPATH=src python bench/bench.py
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trilha.graph import ancestor_closure, detect_cycle  # noqa: E402
from trilha.models import KC, Curriculum  # noqa: E402
from trilha.planner import plan  # noqa: E402


def dag_sintetico(n: int, saltos: int = 3, semente: int = 42) -> Curriculum:
    """Camadas encadeadas com arestas extras para frente (sempre acíclico)."""

    rng = random.Random(semente)
    kcs = [
        KC(
            id=f"kc{i:05d}",
            nome=f"Conceito {i}",
            area=f"area{i % 5}",
            dificuldade=1 + i % 5,
        )
        for i in range(n)
    ]
    arestas: set[tuple[str, str]] = set()
    for i in range(n):
        if i + 1 < n:
            arestas.add((f"kc{i:05d}", f"kc{i + 1:05d}"))
        for _ in range(saltos):
            destino = i + rng.randint(2, 12)
            if destino < n:
                arestas.add((f"kc{i:05d}", f"kc{destino:05d}"))
    return Curriculum.from_edges(kcs, sorted(arestas))


def medir(n: int, repeticoes: int = 20) -> dict[str, float]:
    curriculo = dag_sintetico(n)
    alvo = f"kc{int(n * 0.6):05d}"

    t0 = time.perf_counter()
    for _ in range(repeticoes):
        detect_cycle(curriculo)
    t_ciclo = (time.perf_counter() - t0) / repeticoes

    t0 = time.perf_counter()
    for _ in range(repeticoes):
        ancestor_closure(curriculo, alvo)
    t_closure = (time.perf_counter() - t0) / repeticoes

    dominio_vazio = {kc_id: 0.10 for kc_id in curriculo.kcs}
    t0 = time.perf_counter()
    for _ in range(repeticoes):
        plano = plan(curriculo, alvo, dominio_vazio)
    t_plano = (time.perf_counter() - t0) / repeticoes

    dominio_meio = {
        kc_id: (0.99 if indice % 2 == 0 else 0.10)
        for indice, kc_id in enumerate(sorted(curriculo.kcs))
    }
    t0 = time.perf_counter()
    for _ in range(repeticoes):
        plano_meio = plan(curriculo, alvo, dominio_meio)
    t_replan = (time.perf_counter() - t0) / repeticoes

    return {
        "n": n,
        "arestas": sum(len(v) for v in curriculo.dependents.values()),
        "ciclo_ms": t_ciclo * 1000,
        "closure_ms": t_closure * 1000,
        "plano_ms": t_plano * 1000,
        "replano_ms": t_replan * 1000,
        "passos": len(plano.passos),
        "passos_meio": len(plano_meio.passos),
        "podados": plano.podados,
    }


def main() -> None:
    print(
        f"{'nós':>6} {'arestas':>8} {'ciclo(ms)':>10} {'closure(ms)':>12} "
        f"{'plano(ms)':>10} {'replano(ms)':>12} {'passos':>7}"
    )
    for n in (100, 500, 1000, 5000):
        resultado = medir(n)
        print(
            f"{resultado['n']:>6} {resultado['arestas']:>8} "
            f"{resultado['ciclo_ms']:>10.3f} {resultado['closure_ms']:>12.3f} "
            f"{resultado['plano_ms']:>10.3f} {resultado['replano_ms']:>12.3f} "
            f"{resultado['passos']:>7}"
        )


if __name__ == "__main__":
    main()
