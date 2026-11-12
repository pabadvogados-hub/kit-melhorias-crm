# Intimações (DJEN/CNJ): captura, conferência e Calendário

Captura as publicações do DJEN das OABs do escritório, classifica o ato (cível), sugere o prazo em dias úteis e deixa a equipe conferir e criar as providências no Calendário de prazos. Nada vai para o Calendário sem conferência humana.

**Aplicação:** ver [INSTRUCOES_CLAUDE.md](INSTRUCOES_CLAUDE.md).

## O que tem aqui

| Arquivo | Para que serve |
|---|---|
| `backend/app/intimacoes/djen.py` | Cliente da API do DJEN, com retentativa da instabilidade |
| `backend/app/intimacoes/classificador.py` | Classifica o ato pelas palavras do texto (sugestão) |
| `backend/app/intimacoes/prazos_uteis.py` | Contagem em dias úteis (CPC), feriados nacionais, alerta de recesso |
| `backend/app/intimacoes/captura.py` | Captura idempotente, log por rodada, modo `--simular`, CLI para o cron |
| `backend/app/intimacoes/servico.py` | Listar, conferir, descartar, OABs, ponte com o módulo de processos |
| `backend/app/intimacoes/schema.py` | Tabelas próprias: `int_intimacoes`, `int_capturas`, `int_oabs` |
| `backend/app/routers/intimacoes.py` | API `/api/intimacoes` |
| `frontend/src/pages/Intimacoes.jsx` | Tela: lista, perfil, conferência e OABs |
| `teste_intimacoes.py` | Testes com SQLite temporário e DJEN simulada |

## A pegadinha da API: o falso vazio

Para a **mesma consulta**, a API do DJEN responde de três jeitos, todos com HTTP 200:

1. `status: "error"`, com "sistema muito ocupado";
2. `status: "success"`, com `count: 0` e `items: []`: **falso vazio**;
3. `status: "success"`, com os dados certos.

Se o código tratasse (2) como "não há intimações", a equipe perderia publicações sem saber. Por isso:

- (1) e (2) são retentadas com backoff exponencial (2, 4, 8... até 60 s), até 10 tentativas por página;
- "sem intimações" só vale depois de **três respostas vazias sem nenhum dado**;
- se o orçamento acabar sem resposta conclusiva, a rodada grava `incompleta` em `int_capturas` com o log das tentativas. Nunca grava "sem intimações". A próxima rodada refaz a consulta;
- a chave única de cada publicação é o `hash`/`id` da comunicação, então rodar de novo não duplica.

## Limites

- O classificador é heurístico. Quem confere é a equipe, e tudo que ele sugere aparece marcado como sugestão.
- A contagem ignora feriados locais, suspensões de expediente, prazo em dobro e recesso forense (alerta quando o prazo atravessa o recesso). A tela avisa.
- O provedor alternativo pago é só um ponto de extensão (`ProvedorAlternativo`), desligado por padrão e não implementado.
