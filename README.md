# Motor de Trilhas de Aprendizagem Personalizadas

MVP do artefato computacional do TCC **"Modelagem e Otimização de Trilhas de
Aprendizagem Personalizadas para o Ensino Médio: Abordagem Baseada em Grafos
Orientados Acíclicos (DAGs) e Ordenação Topológica"**.

O foco é o **motor**: modelagem do currículo como DAG, avaliação diagnóstica,
Knowledge Tracing bayesiano (BKT) e geração/replanejamento da trilha por
ordenação topológica. A camada HTTP existe como transporte e há uma interface
web de demonstração (uma página estática, sem build) em `/app`.

## O que está implementado

| Componente | Onde |
|---|---|
| Currículo como DAG em lista de adjacências (Postgres) | `db/init/001_schema.sql`, `src/trilha/repo.py` |
| Detecção de ciclos (DFS com três cores) | `src/trilha/graph.py` |
| Fechamento transitivo de pré-requisitos (poda do grafo) | `src/trilha/graph.py` |
| Ordenação topológica de Kahn com desempate heurístico | `src/trilha/graph.py` |
| DFS de referência para validação cruzada | `src/trilha/graph.py` |
| Caminho crítico restante até o alvo | `src/trilha/graph.py` |
| Bayesian Knowledge Tracing (4 parâmetros) | `src/trilha/bkt.py` |
| Trilha mínima com justificativa por passo | `src/trilha/planner.py` |
| Seleção de itens do diagnóstico | `src/trilha/diagnostic.py` |
| Sessão, respostas e replanejamento | `src/trilha/engine.py` |
| Validação de integridade do currículo | `src/trilha/check.py` |
| API mínima (FastAPI) | `src/trilha/api.py` |
| Interface web de demonstração | `web/index.html` |
| Demo interativa de terminal | `src/trilha/cli.py` |

Fora do escopo deste MVP, por decisão explícita: autenticação, dashboards,
DKT/redes neurais, A/B testing, deploy em nuvem e frontend em React/Next.

## Arquitetura

```
        ┌────────────┐      ┌──────────────┐
seed →  │  Postgres  │ ───→ │   repo.py    │  (SQL explícito, sem ORM)
        │  kc, edge  │      └──────┬───────┘
        └────────────┘             │ Curriculum (dataclasses)
                                   ▼
        ┌────────────────────────────────────────────┐
        │  graph.py   ← DFS / Kahn / fechamento      │
        │  bkt.py     ← atualização bayesiana        │
        │  planner.py ← trilha personalizada         │
        └───────────────────┬────────────────────────┘
                            │ Plan
              ┌─────────────┴─────────────┐
              ▼                           ▼
        cli.py (demo)              api.py (HTTP)
                                          │
                                   web/index.html
                                  (demo no navegador)
```

O núcleo (`graph`, `bkt`, `planner`, `models`) não importa `psycopg` nem
`fastapi`; por isso os testes desses módulos rodam sem banco.

## Como rodar

Pré-requisitos: Docker (com o daemon ativo) e Python 3.12+.

```bash
# 1. banco: sobe postgres:17-alpine, aplica schema e seed, cria tcc_test
make db-up

# 2. dependências Python
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# 3. valida o currículo e roda a suíte
make check
make test

# 4. sobe a aplicação (API + interface web)
make run
```

Com a aplicação no ar:

| Endereço | O que é |
|---|---|
| <http://localhost:8000/app/> | interface web de demonstração |
| <http://localhost:8000/docs> | Swagger com todas as rotas |
| `make demo` | trilha automática no terminal, sem API |

> Se a distribuição não trouxer `ensurepip` (caso do Debian/Ubuntu sem
> `python3-venv`), crie o venv com `python3 -m venv --without-pip .venv` e
> rode `curl -sSL https://bootstrap.pypa.io/get-pip.py | .venv/bin/python`.
> Alternativa equivalente: `sudo apt install python3-venv`.

Variáveis de ambiente (ver `.env.example`): `DATABASE_URL`,
`DATABASE_URL_TESTES`, `MASTERY_THRESHOLD`.

## Interface web

`web/index.html` é um arquivo único (HTML + CSS + JS, sem npm, sem build) que o
FastAPI serve em `/app`. Para usá-la, basta `make run` e abrir
<http://localhost:8000/app/>.

Fluxo da tela:

1. escolher o assunto-objetivo no seletor (o texto mostra quantos KCs entram no
   caminho e quantos são podados pelo grafo);
2. responder o diagnóstico (uma questão por KC do fechamento de pré-requisitos),
   ou clicar em **Não sei** em vez de chutar;
3. ver a trilha ordenada, com `P(domínio)` e a justificativa de cada passo;
4. estudar o próximo passo; cada resposta atualiza o BKT e redesenha a trilha
   (a questão vem de `/next-item`, que alterna entre os itens do KC);
5. ao dominar o objetivo, a tela mostra "Objetivo alcançado" e as estatísticas.

O `sessao_id` fica em `localStorage`, então recarregar a página retoma a sessão;
o botão "Nova sessão" começa do zero. Não há autenticação: é uma demo de
apresentação, não um produto.

A página reutiliza as rotas existentes — não há endpoint novo nem dependência
nova. Como ela é servida pela mesma origem da API, também não é preciso CORS.

## Algoritmo da trilha

1. **Validação**: `detect_cycle` roda DFS com três cores sobre o grafo
   carregado; o seed é rejeitado se houver ciclo (o currículo é um DAG por
   definição pedagógica).
2. **Poda**: `ancestor_closure(alvo)` mantém apenas o fechamento transitivo de
   pré-requisitos do nó-objetivo. KCs fora desse conjunto nunca entram na
   trilha.
3. **Filtro de domínio**: remove KCs com `P(domínio) >= threshold`
   (padrão `0.95`).
4. **Ordenação**: Kahn restrito ao subconjunto pendente. O heap usa como
   desempate:
   - menor `P(domínio)` primeiro (maior lacuna),
   - maior caminho crítico restante até o alvo,
   - `id` do KC (determinismo).
5. **Justificativa**: cada passo carrega o motivo (`objetivo` ou
   `pré-requisito de ...`).
6. **Replanejamento**: cada resposta atualiza o BKT e regenera a trilha numa
   **transação única** com lock da sessão (`SELECT ... FOR UPDATE`), gravando
   domínio, tentativa, timestamp e evento de forma atômica.

Complexidade: `O(V + E)` para detecção de ciclo, fechamento e Kahn;
`O(V log V + E)` com o heap de prioridade. `V = 25` no seed de Matemática.

### BKT

A cada interação com um KC:

```
P(L|correct) = P(L)(1-slip) / [P(L)(1-slip) + (1-P(L))guess]
P(L|wrong)   = P(L)slip     / [P(L)slip     + (1-P(L))(1-guess)]
P(L) ← P(L|obs) + (1 - P(L|obs)) · learn
```

Parâmetros por KC em `kc.p_init`, `p_learn`, `p_slip`, `p_guess`.

**"Não sei"** (`escolha: "?"`) entra como observação de erro: o aluno declara
que não domina o assunto, então o chute (`p_guess`) não infla a probabilidade.
A tentativa fica gravada com `escolha = '?'`, o que permite separar "não sei"
de erro nas análises.

### Limitação: parâmetros não calibrados

Os parâmetros do BKT (`p_init`, `p_learn`, `p_slip`, `p_guess`) foram
definidos com valores de referência da literatura, e os itens foram elaborados
pelos autores sem validação psicométrica. Calibrar esses parâmetros exige
registros reais de respostas (por exemplo, via Expectation-Maximization), que
só estarão disponíveis após a coleta prevista no TCC II. O sistema já persiste
cada tentativa, com as probabilidades antes e depois, no formato necessário
para essa calibração.

Efeitos visíveis dessa escolha no MVP:

- **Saltos grandes:** com os valores padrão, um acerto leva o domínio de 10%
  para 53%, e três acertos seguidos já marcam o KC como dominado.
- **Erro também sobe a partir do inicial:** `p_learn` é aplicado depois de
  toda resposta (o BKT assume que cada tentativa é uma oportunidade de
  aprender), então um erro leva de 10% para ~31%, e erros seguidos estabilizam
  em ~34%.
- **Parâmetros por KC, não por item:** as questões de um mesmo assunto pesam
  igual; `item.dificuldade` existe no seed mas não entra no BKT.

A analogia com a TRI do ENEM ajuda a explicar: lá, cada questão tem
discriminação, dificuldade e acerto ao acaso estimados a partir das respostas
reais. Aqui os parâmetros equivalentes existem, mas por KC e ainda sem dados
para estimá-los. Dar parâmetros por item ao BKT, aproximando-o da TRI, é a
proposta do KT-IDEM (Pardos & Heffernan, 2011) e fica como trabalho futuro.

## API

| Método | Rota | Descrição |
|---|---|---|
| GET | `/health` | ping no banco + total de KCs |
| GET | `/graph` | nós e arestas do currículo |
| POST | `/sessions` | cria sessão, devolve diagnóstico e trilha |
| GET | `/sessions/{id}` | estado, domínio por KC e tentativas |
| GET | `/sessions/{id}/path` | trilha atual |
| GET | `/sessions/{id}/next-item` | questão do próximo passo (item menos usado do KC) |
| POST | `/sessions/{id}/answers` | registra resposta (`a`–`d` ou `?` = não sei) e replaneja |
| PUT | `/sessions/{id}/target` | troca o nó-objetivo |
| GET | `/app/` | interface web de demonstração |

```bash
SID=$(curl -s -X POST localhost:8000/sessions \
  -H 'content-type: application/json' \
  -d '{"target_id":"funcao_quadratica","aluno":"Ana"}' | jq -r .sessao_id)

curl -s localhost:8000/sessions/$SID/path | jq '.passos[] | {kc_id, motivo}'
```

## Testes

`make test` roda **88 testes** (41 puros + 47 de integração).

| Arquivo | Casos | Tipo |
|---|---:|---|
| `tests/test_graph.py` | 14 | puro |
| `tests/test_bkt.py` | 10 | puro |
| `tests/test_planner.py` | 12 | puro |
| `tests/test_check.py` | 5 | puro |
| `tests/test_repo.py` | 12 | integração |
| `tests/test_engine.py` | 20 | integração |
| `tests/test_api.py` | 15 | integração |

- **Puros** (sem banco): detecção de ciclo, validade da ordem topológica,
  equivalência com a DFS de referência, caminho crítico, valores numéricos do
  BKT, poda/filtro/desempate do planejador, validação do seed.
- **Integração** (exigem `make db-up`): repositório, atomicidade da interação,
  concorrência, ciclo no banco, limites de API e endpoints. São marcados como
  *skip* se o banco estiver indisponível.

Validação executada neste ambiente:

| Verificação | Resultado |
|---|---|
| `pytest` completo | 88 passed |
| `make check` | 25 KCs, 32 arestas, 75 itens, DAG acíclico |
| Seed no Postgres | 25 KCs, 32 arestas, 75 itens (3 por KC) |
| Demo com 24 respostas corretas | alvo `funcao_quadratica` alcançado, 0 pendentes |
| Troca de alvo `logaritmo` → `probabilidade` | trilha recalculada sem perder domínio |
| `GET /health` | `{"db": "ok", "kcs": 25}` |
| Item fora do escopo | 422, nenhuma tentativa gravada |
| Concorrência (2 threads × 10) | 20 tentativas, domínio igual ao sequencial |

## Correções aplicadas na revisão

| ID | Correção |
|---|---|
| D1 | `repo.interagir` grava domínio, tentativa, timestamp e evento em uma transação |
| D2 | `SELECT ... FOR UPDATE` na sessão serializa respostas concorrentes |
| D3 | Planejador ignora KCs sem item e expõe `Plan.sem_item` |
| D4 | Currículo é validado (`detect_cycle`) no carregamento |
| D5 | `/sessions/{id}?limite=50` + `total_tentativas` |
| D6 | Item fora do fechamento do alvo → `ItemForaDoEscopo` (422) |
| D7 | `sessao.atualizada_em` atualizada em toda interação |
| R1 | `python -m trilha.check` + `make check` + `make seed` validado |
| R2 | `psycopg.OperationalError` / `PoolTimeout` → 503 |
| R3 | Código morto removido (`conectar`/`soltar`) |
| R4 | Índice `dominio(kc_id)` |
| R9 | `item.correta` como `text` com `CHECK` de regex |

## Benchmark do planejador

`make bench` gera DAGs sintéticos (arestas sempre para frente, logo acíclicos)
e mede o custo médio por operação em 20 repetições, alvo a 60% da cadeia:

| nós | arestas | ciclo (ms) | fechamento (ms) | plano (ms) | replano (ms) | passos |
|----:|--------:|-----------:|----------------:|-----------:|-------------:|-------:|
| 100 | 360 | 0.065 | 0.009 | 0.217 | 0.151 | 61 |
| 500 | 1.851 | 0.328 | 0.050 | 1.126 | 0.809 | 301 |
| 1.000 | 3.722 | 0.682 | 0.098 | 2.247 | 1.668 | 601 |
| 5.000 | 18.678 | 3.626 | 0.605 | 12.068 | 9.070 | 3.001 |

O replanejamento cabe folgado em um ciclo de requisição, mesmo com um
currículo duas ordens de grandeza maior que o seed.

## Decisões e desvios em relação ao relatório

- **PostgreSQL** é usado como no relatório, com lista de adjacências
  (`kc` + `kc_prereq`) e SQL explícito em vez de ORM.
- **Python** para as regras de negócio e algoritmos de grafo, conforme a
  seção 3.1 do relatório.
- **Sem Alembic**: schema único + `make db-reset`; migrações ficam para o
  TCC II.
- **Sem DKT**: o BKT é o baseline previsto e suficiente para validar o
  replanejamento.
- **Seed com 3 itens por KC**: o diagnóstico usa só o primeiro (fica curto);
  os demais alimentam a trilha, para o aluno não repetir a mesma questão.
- **UI**: página estática única (`web/index.html`) servida pela própria API,
  no lugar de React/Next; o frontend definitivo pode substituí-la sem
  reescrever o motor.

## Próximos passos (TCC II)

1. Ampliar o seed (outras disciplinas e itens com dificuldade graduada).
2. Substituir o threshold fixo por estimativa de maestria com histórico
   (ou DKT) mantendo a interface de `bkt.py`.
3. Avaliar o ganho da heurística de desempate contra ordem topológica pura
   (métrica: passos até o alvo e tempo de conclusão).
4. Frontend definitivo (React/Next) e protocolo A/B com coleta de telemetria.
