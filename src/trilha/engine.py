"""Motor de orquestração: sessão, diagnóstico, respostas e replanejamento."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from . import bkt
from .diagnostic import QuestaoDiagnostica, selecionar
from .erros import (  # noqa: F401 - reexportados para conveniência dos consumidores
    AlvoInvalido,
    CurriculoInvalido,
    ErroMotor,
    ItemForaDoEscopo,
    ItemInvalido,
    RespostaInvalida,
    SessaoNaoEncontrada,
)
from .graph import ancestor_closure, detect_cycle
from .models import Curriculum, Plan, THRESHOLD_PADRAO
from .planner import plan
from .repo import Interacao, Repositorio

LETRAS_VALIDAS = frozenset("abcd")
# "Não sei": entra no BKT como erro (o aluno declara que não domina, sem chute)
# e fica gravado como '?' em tentativa.escolha para separar de um erro comum.
NAO_SEI = "?"


class Motor:
    def __init__(
        self,
        repo: Repositorio,
        threshold: float = THRESHOLD_PADRAO,
        *,
        cachear_curriculo: bool = True,
    ):
        self.repo = repo
        self.threshold = threshold
        self._cachear = cachear_curriculo
        self._curriculo: Curriculum | None = None
        self._avaliaveis: frozenset[str] | None = None

    # ---------------------------------------------------------------- currículo

    @property
    def curriculo(self) -> Curriculum:
        if self._curriculo is None or not self._cachear:
            self._curriculo = self._carregar_curriculo_validado()
            self._avaliaveis = self.repo.kcs_com_itens()
        return self._curriculo

    @property
    def avaliaveis(self) -> frozenset[str]:
        if self._avaliaveis is None or not self._cachear:
            self._avaliaveis = self.repo.kcs_com_itens()
        return self._avaliaveis

    def recarregar_curriculo(self) -> Curriculum:
        self._curriculo = self._carregar_curriculo_validado()
        self._avaliaveis = self.repo.kcs_com_itens()
        return self._curriculo

    def _carregar_curriculo_validado(self) -> Curriculum:
        curriculo = self.repo.carregar_curriculo()
        ciclo = detect_cycle(curriculo)
        if ciclo is not None:
            raise CurriculoInvalido("ciclo no currículo: " + " -> ".join(ciclo))
        return curriculo

    # ------------------------------------------------------------------ sessão

    def criar_sessao(self, target_id: str, aluno: str = "anônimo") -> dict[str, Any]:
        curriculo = self.curriculo
        self._validar_alvo(curriculo, target_id)

        subgrafo = ancestor_closure(curriculo, target_id)
        iniciais = {kc_id: curriculo.kcs[kc_id].p_init for kc_id in subgrafo}
        trilha = plan(
            curriculo,
            target_id,
            iniciais,
            self.threshold,
            self.avaliaveis,
        )

        sessao_id = self.repo.criar_sessao(
            aluno,
            target_id,
            iniciais,
            evento=_payload_replanejamento(trilha, "sessao_criada"),
        )

        itens = self.repo.listar_itens(subgrafo)
        diagnostico = selecionar(itens, curriculo, target_id)

        return {
            "sessao_id": sessao_id,
            "aluno": aluno,
            "target_id": target_id,
            "diagnostico": [q.to_dict() for q in diagnostico],
            "plano": trilha.to_dict(),
        }

    def estado(self, sessao_id: str, limite: int = 50) -> dict[str, Any]:
        sessao = self._obter_sessao(sessao_id)
        curriculo = self.curriculo
        dominio = self.repo.obter_dominio(sessao_id)
        trilha = plan(curriculo, sessao["target_id"], dominio, self.threshold, self.avaliaveis)

        return {
            "sessao": sessao,
            "dominio": {kc_id: round(p, 5) for kc_id, p in sorted(dominio.items())},
            "tentativas": self.repo.listar_tentativas(sessao_id, limite),
            "total_tentativas": self.repo.contar_tentativas(sessao_id),
            "limite": limite,
            "plano": trilha.to_dict(),
            "threshold": self.threshold,
        }

    def trilha(self, sessao_id: str) -> dict[str, Any]:
        sessao = self._obter_sessao(sessao_id)
        dominio = self.repo.obter_dominio(sessao_id)
        return plan(
            self.curriculo,
            sessao["target_id"],
            dominio,
            self.threshold,
            self.avaliaveis,
        ).to_dict()

    def definir_target(self, sessao_id: str, target_id: str) -> dict[str, Any]:
        sessao = self._obter_sessao(sessao_id)
        curriculo = self.curriculo
        self._validar_alvo(curriculo, target_id)

        dominio = self.repo.obter_dominio(sessao_id)
        faltantes = {
            kc_id: curriculo.kcs[kc_id].p_init
            for kc_id in ancestor_closure(curriculo, target_id)
            if kc_id not in dominio
        }
        dominio_atualizado = {**dominio, **faltantes}

        trilha = plan(
            curriculo,
            target_id,
            dominio_atualizado,
            self.threshold,
            self.avaliaveis,
        )
        self.repo.trocar_target(
            sessao_id,
            target_id,
            faltantes,
            _payload_replanejamento(trilha, "target_alterado"),
        )

        return {
            "sessao_id": sessao_id,
            "target_anterior": sessao["target_id"],
            "target_id": target_id,
            "plano": trilha.to_dict(),
        }

    # ------------------------------------------------------------- interações

    def responder(
        self,
        sessao_id: str,
        item_id: int,
        escolha: str,
    ) -> dict[str, Any]:
        escolha_normalizada = escolha.strip().lower()
        if escolha_normalizada not in LETRAS_VALIDAS and escolha_normalizada != NAO_SEI:
            raise RespostaInvalida(
                "escolha deve ser uma das alternativas a, b, c ou d, ou '?' (não sei)"
            )

        item = self.repo.obter_item(item_id)
        if item is None:
            raise ItemInvalido(f"item {item_id} não existe")

        curriculo = self.curriculo
        kc = curriculo.kcs[item.kc_id]
        correta = escolha_normalizada == item.correta
        capturado: dict[str, Any] = {}

        def calcular(target_id: str, dominio: dict[str, float]) -> Interacao:
            escopo = ancestor_closure(curriculo, target_id)
            if item.kc_id not in escopo:
                raise ItemForaDoEscopo(
                    f"KC {item.kc_id!r} não pertence ao caminho do alvo {target_id!r}"
                )

            p_antes = dominio.get(kc.id, kc.p_init)
            p_depois = bkt.aplicar(p_antes, correta, kc)
            dominio_novo = {**dominio, kc.id: p_depois}
            trilha = plan(
                curriculo,
                target_id,
                dominio_novo,
                self.threshold,
                self.avaliaveis,
            )

            capturado.update(plano=trilha, p_antes=p_antes, p_depois=p_depois)

            payload = _payload_replanejamento(trilha, "resposta")
            payload.update(item_id=item.id, kc_id=kc.id, correta=correta)

            return Interacao(
                kc_id=kc.id,
                item_id=item.id,
                escolha=escolha_normalizada,
                correta=correta,
                p_antes=p_antes,
                p_depois=p_depois,
                evento_tipo="replanejamento",
                evento=payload,
            )

        self.repo.interagir(sessao_id, calcular)

        p_antes = capturado["p_antes"]
        p_depois = capturado["p_depois"]
        trilha = capturado["plano"]

        return {
            "sessao_id": sessao_id,
            "item_id": item.id,
            "kc_id": kc.id,
            "kc_nome": kc.nome,
            "escolha": escolha_normalizada,
            "correta": correta,
            "nao_sei": escolha_normalizada == NAO_SEI,
            "p_antes": round(p_antes, 5),
            "p_depois": round(p_depois, 5),
            "dominado": bkt.dominado(p_depois, self.threshold),
            "plano": trilha.to_dict(),
        }

    def proximo_item(self, sessao_id: str) -> dict[str, Any]:
        """Questão para o primeiro passo da trilha.

        Entre os itens do KC, escolhe o menos respondido na sessão (empate pelo
        id), para o aluno não repetir sempre a mesma questão.
        """

        trilha = self.trilha(sessao_id)
        if trilha["alcancado"] or not trilha["passos"]:
            return {"passo": None, "questao": None}

        passo = trilha["passos"][0]
        itens = self.repo.listar_itens([passo["kc_id"]])
        if not itens:
            return {"passo": passo, "questao": None}

        usos = self.repo.contar_tentativas_por_item(sessao_id, passo["kc_id"])
        item = min(itens, key=lambda i: (usos.get(i.id, 0), i.id))
        questao = QuestaoDiagnostica(
            item_id=item.id,
            kc_id=item.kc_id,
            kc_nome=passo["nome"],
            enunciado=item.enunciado,
            alternativas=item.alternativas,
        )
        return {"passo": passo, "questao": questao.to_dict()}

    # ------------------------------------------------------------------- apoio

    def _obter_sessao(self, sessao_id: str) -> dict[str, Any]:
        sessao = self.repo.obter_sessao(sessao_id)
        if sessao is None:
            raise SessaoNaoEncontrada(f"sessão {sessao_id} não encontrada")
        return sessao

    def _validar_alvo(self, curriculo: Curriculum, target_id: str) -> None:
        if target_id not in curriculo.kcs:
            raise AlvoInvalido(f"KC alvo inexistente: {target_id!r}")


def _payload_replanejamento(trilha: Plan, gatilho: str) -> dict[str, Any]:
    return {
        "gatilho": gatilho,
        "target_id": trilha.target.id,
        "pendentes": trilha.pendentes,
        "sem_item": trilha.sem_item,
        "trilha": [passo.kc.id for passo in trilha.passos],
    }
