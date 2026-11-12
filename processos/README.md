# Processos: clientes e processos no Braga & Braz

Módulo novo, que acrescenta cadastro de **clientes** e **processos** ao sistema. Liga-se ao Calendário (`pz_prazos`), ao índice das pastas da REDE (`pz_pastas`) e aos cards do CRM (`wa_conversas`).

Quem aplica é o Claude Code do escritório. O roteiro passo a passo está em [INSTRUCOES_CLAUDE.md](INSTRUCOES_CLAUDE.md).

## O que tem aqui

| Pasta | Conteúdo |
|---|---|
| `backend/app/` | Modelos (`processos_models.py`), núcleo com as regras (`processos_nucleo.py`) e o router `routers/processos.py` |
| `backend/` | Teste local (`teste_processos.py`) e carga inicial opcional (`carregar_processos_inicial.py`) |
| `frontend/src/pages/` | Quadro por fase, lista com CSV, ficha lateral, clientes e utilitários |

## Tabelas novas

`proc_fases`, `proc_clientes`, `proc_processos`, `proc_partes`, `proc_historico`. Criadas pelo `init_db` na subida. Nenhuma tabela existente é alterada.

## Rotas

Prefixo `/api/processos`. Principais: `GET /` (lista com filtros), `POST /` (criar), `GET /{id}` (ficha), `POST /{id}/mover`, `POST /{id}/encerrar`, `POST /{id}/reabrir`, `GET /{id}/prazos`, `GET /{id}/historico`, `GET /resumo`, `GET /fases`, `GET /clientes`, `GET /pasta`, `GET /por-numero`, `GET /conversa/{id}/elegivel` e `POST /conversa/{id}`.

## Teste

Na pasta `backend/`, com o Python do sistema:

```
python -I teste_processos.py
```

Roda contra um SQLite temporário e não toca no banco do sistema. Deve terminar com `18 de 18 testes passaram.`

## Requisitos

Nenhum pacote novo. Usa as mesmas dependências do backend (FastAPI, SQLAlchemy assíncrono, Pydantic).
