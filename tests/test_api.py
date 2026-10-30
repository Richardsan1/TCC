from __future__ import annotations

import psycopg
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from trilha.api import app  # noqa: E402
from trilha.engine import Motor  # noqa: E402

ALVO = "funcao_quadratica"


@pytest.fixture()
def cliente(banco_limpo: str, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", banco_limpo)
    with TestClient(app) as c:
        yield c


def test_health(cliente: TestClient) -> None:
    resposta = cliente.get("/health")
    assert resposta.status_code == 200
    assert resposta.json()["db"] == "ok"
    assert resposta.json()["kcs"] == 25


def test_graph(cliente: TestClient) -> None:
    corpo = cliente.get("/graph").json()

    assert len(corpo["kcs"]) == 25
    assert ["numeros_inteiros", "fracoes_racionais"] in corpo["arestas"]


def test_cria_sessao_e_consulta_trilha(cliente: TestClient) -> None:
    criada = cliente.post("/sessions", json={"target_id": ALVO, "aluno": "Ana"})
    assert criada.status_code == 201
    sessao_id = criada.json()["sessao_id"]

    trilha = cliente.get(f"/sessions/{sessao_id}/path")
    assert trilha.status_code == 200
    assert trilha.json()["passos"][-1]["kc_id"] == ALVO


def test_responde_item(cliente: TestClient) -> None:
    sessao = cliente.post("/sessions", json={"target_id": ALVO}).json()
    primeira = sessao["diagnostico"][0]

    resposta = cliente.post(
        f"/sessions/{sessao['sessao_id']}/answers",
        json={"item_id": primeira["item_id"], "escolha": "a"},
    )

    assert resposta.status_code == 200
    assert resposta.json()["kc_id"] == primeira["kc_id"]
    assert "p_depois" in resposta.json()


def test_nao_sei_e_aceito(cliente: TestClient) -> None:
    sessao = cliente.post("/sessions", json={"target_id": ALVO}).json()
    primeira = sessao["diagnostico"][0]

    resposta = cliente.post(
        f"/sessions/{sessao['sessao_id']}/answers",
        json={"item_id": primeira["item_id"], "escolha": "?"},
    )

    assert resposta.status_code == 200
    assert resposta.json()["nao_sei"] is True
    assert resposta.json()["correta"] is False


def test_proximo_item(cliente: TestClient) -> None:
    sessao = cliente.post("/sessions", json={"target_id": ALVO}).json()

    resposta = cliente.get(f"/sessions/{sessao['sessao_id']}/next-item")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["questao"]["kc_id"] == corpo["passo"]["kc_id"]
    assert "correta" not in corpo["questao"]


def test_alvo_invalido_retorna_422(cliente: TestClient) -> None:
    resposta = cliente.post("/sessions", json={"target_id": "nao_existe"})
    assert resposta.status_code == 422


def test_sessao_inexistente_retorna_404(cliente: TestClient) -> None:
    resposta = cliente.get("/sessions/00000000-0000-0000-0000-000000000000/path")
    assert resposta.status_code == 404


def test_item_inexistente_retorna_404(cliente: TestClient) -> None:
    sessao_id = cliente.post("/sessions", json={"target_id": ALVO}).json()["sessao_id"]
    resposta = cliente.post(
        f"/sessions/{sessao_id}/answers",
        json={"item_id": 999_999, "escolha": "a"},
    )
    assert resposta.status_code == 404


def test_alternativa_invalida_retorna_422(cliente: TestClient) -> None:
    sessao_id = cliente.post("/sessions", json={"target_id": ALVO}).json()["sessao_id"]
    resposta = cliente.post(
        f"/sessions/{sessao_id}/answers",
        json={"item_id": 1, "escolha": "z"},
    )
    assert resposta.status_code == 422


def test_item_fora_do_escopo_retorna_422(cliente: TestClient) -> None:
    sessao_id = cliente.post("/sessions", json={"target_id": "logaritmo"}).json()["sessao_id"]
    resposta = cliente.post(
        f"/sessions/{sessao_id}/answers",
        json={"item_id": 25, "escolha": "a"},  # medidas_tendencia
    )

    assert resposta.status_code == 422
    assert "não pertence" in resposta.json()["detail"]


def test_limite_de_tentativas(cliente: TestClient) -> None:
    sessao = cliente.post("/sessions", json={"target_id": ALVO}).json()
    sessao_id = sessao["sessao_id"]
    item_id = sessao["diagnostico"][0]["item_id"]

    for _ in range(5):
        assert cliente.post(
            f"/sessions/{sessao_id}/answers",
            json={"item_id": item_id, "escolha": "a"},
        ).status_code == 200

    corpo = cliente.get(f"/sessions/{sessao_id}?limite=2").json()
    assert len(corpo["tentativas"]) == 2
    assert corpo["total_tentativas"] == 5
    assert cliente.get(f"/sessions/{sessao_id}?limite=0").status_code == 422


def test_banco_indisponivel_retorna_503(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explodir(_: Motor, __: str) -> dict:
        raise psycopg.OperationalError("conexão caiu")

    monkeypatch.setattr(Motor, "trilha", explodir)

    resposta = cliente.get("/sessions/00000000-0000-0000-0000-000000000000/path")
    assert resposta.status_code == 503
    assert "indisponível" in resposta.json()["detail"]


def test_raiz_redireciona_para_interface(cliente: TestClient) -> None:
    resposta = cliente.get("/", follow_redirects=False)

    assert resposta.status_code in (302, 307)
    assert resposta.headers["location"] == "/app/"


def test_interface_web_e_servida(cliente: TestClient) -> None:
    resposta = cliente.get("/app/")

    assert resposta.status_code == 200
    assert "Trilhas de Aprendizagem Adaptativas" in resposta.text
    assert "/sessions" in resposta.text
