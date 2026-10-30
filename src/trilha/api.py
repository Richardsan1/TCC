"""API mínima (transporte) sobre o motor de trilhas."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import psycopg
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from psycopg_pool import PoolTimeout
from pydantic import BaseModel, Field

from .config import database_url, threshold
from .engine import (
    ErroMotor,
    ItemInvalido,
    Motor,
    RespostaInvalida,
    SessaoNaoEncontrada,
)
from .repo import Repositorio


@asynccontextmanager
async def lifespan(app: FastAPI):
    repo = Repositorio(database_url())
    app.state.motor = Motor(repo, threshold())
    yield
    repo.fechar()


app = FastAPI(
    title="Motor de Trilhas Adaptativas",
    description="DAG curricular + BKT + ordenação topológica",
    version="0.1.0",
    lifespan=lifespan,
)

DIR_WEB = Path(__file__).resolve().parents[2] / "web"


@app.get("/", include_in_schema=False)
def raiz() -> RedirectResponse:
    return RedirectResponse(url="/app/")


if DIR_WEB.is_dir():
    app.mount("/app", StaticFiles(directory=DIR_WEB, html=True), name="web")


class NovaSessao(BaseModel):
    target_id: str = Field(min_length=1)
    aluno: str = "anônimo"


class Resposta(BaseModel):
    item_id: int = Field(gt=0)
    escolha: str = Field(pattern=r"^([a-dA-D]|\?)$", description="a-d ou '?' (não sei)")


class NovoAlvo(BaseModel):
    target_id: str = Field(min_length=1)


def obter_motor(request: Request) -> Motor:
    return request.app.state.motor


@app.exception_handler(ErroMotor)
async def tratar_erro_motor(_: Request, exc: ErroMotor) -> JSONResponse:
    if isinstance(exc, (SessaoNaoEncontrada, ItemInvalido)):
        status = 404
    else:
        status = 422
    return JSONResponse(status_code=status, content={"detail": str(exc)})


@app.exception_handler(psycopg.OperationalError)
@app.exception_handler(PoolTimeout)
async def tratar_banco_indisponivel(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "banco de dados indisponível", "erro": str(exc)},
    )


@app.get("/health")
def health(request: Request) -> dict[str, Any]:
    motor: Motor = obter_motor(request)
    try:
        ok = motor.repo.ping()
    except (psycopg.OperationalError, PoolTimeout) as exc:
        return JSONResponse(
            status_code=503,
            content={"db": "indisponivel", "erro": str(exc)},
        )
    return {"db": "ok" if ok else "indisponivel", "kcs": len(motor.curriculo)}


@app.get("/graph")
def graph(request: Request) -> dict[str, Any]:
    motor: Motor = obter_motor(request)
    curriculo = motor.curriculo
    arestas = [
        [origem, destino]
        for origem in curriculo.node_ids
        for destino in curriculo.dependents[origem]
    ]
    return {
        "kcs": [
            {
                "id": kc.id,
                "nome": kc.nome,
                "area": kc.area,
                "dificuldade": kc.dificuldade,
                "prereqs": list(curriculo.prereqs[kc.id]),
            }
            for kc in (curriculo.kcs[kc_id] for kc_id in curriculo.node_ids)
        ],
        "arestas": arestas,
    }


@app.post("/sessions", status_code=201)
def criar_sessao(corpo: NovaSessao, request: Request) -> dict[str, Any]:
    return obter_motor(request).criar_sessao(corpo.target_id, corpo.aluno)


@app.get("/sessions/{sessao_id}")
def estado(
    sessao_id: str,
    request: Request,
    limite: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    return obter_motor(request).estado(sessao_id, limite)


@app.get("/sessions/{sessao_id}/path")
def trilha(sessao_id: str, request: Request) -> dict[str, Any]:
    return obter_motor(request).trilha(sessao_id)


@app.get("/sessions/{sessao_id}/next-item")
def proximo_item(sessao_id: str, request: Request) -> dict[str, Any]:
    return obter_motor(request).proximo_item(sessao_id)


@app.post("/sessions/{sessao_id}/answers")
def responder(sessao_id: str, corpo: Resposta, request: Request) -> dict[str, Any]:
    return obter_motor(request).responder(sessao_id, corpo.item_id, corpo.escolha)


@app.put("/sessions/{sessao_id}/target")
def trocar_alvo(sessao_id: str, corpo: NovoAlvo, request: Request) -> dict[str, Any]:
    return obter_motor(request).definir_target(sessao_id, corpo.target_id)
