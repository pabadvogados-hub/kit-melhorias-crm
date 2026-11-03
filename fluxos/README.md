# Fluxos de cadência por área

O sistema Braga & Braz já tem o motor de fluxos: tabela `wa_fluxos`, `POST /fluxos/processar` no cron, parada automática quando o lead responde e trava de 20 envios por rodada. Hoje só existem dois fluxos, `retomar_contato` (genérico) e `contratacao` (pede documentos quando o card entra em "Fechado"). Aqui estão os fluxos por área.

**Os textos são rascunho e precisam da aprovação do Renato antes de ligar.**

## Arquivos

- [fluxos_holding_familia.py](fluxos_holding_familia.py): os fluxos, no mesmo formato do `FLUXOS` que já existe.
- [gatilhos_por_coluna.py](gatilhos_por_coluna.py): qual fluxo liga quando o card entra numa coluna, de acordo com a área do card.

## Os fluxos

| Fluxo | Quando liga | Toques | Duração |
|---|---|---|---|
| `holding_retomar` | Na mão, quando o lead para de responder | 3 | 6 dias |
| `holding_pos_consulta` | Card entra em **Proposta** | 5 | 15 dias |
| `holding_documentos` | Card entra em **Fechado** | 4 | 10 dias |
| `familia_retomar` | Na mão | 3 | 7 dias |
| `familia_pos_consulta` | Card entra em **Proposta** | 4 | 12 dias |
| `familia_documentos` | Card entra em **Fechado** | 4 | 10 dias |
| `reaquecimento_anual` | Card entra em **Perdido** (criar a coluna) | 3 | 4, 8 e 12 meses |

Restituição Tributária e Multipropriedade continuam no `contratacao` genérico ao entrar em "Fechado". Para ganharem fluxo próprio, copie o modelo de holding e troque os textos e a lista de documentos. Os documentos de cada área estão no `whatsapp/bragabraz.py`.

## Por que assim

- **Holding:** a decisão costuma envolver mais de uma pessoa da família. O 3º toque oferece uma conversa com todos os envolvidos, e a lista de documentos é a do padrão de atendimento do escritório.
- **Família:** a pessoa está num momento difícil (separação, guarda, pensão). Por isso são menos toques e o tom é acolhedor: oferece ligação em vez de mensagem e garante sigilo. **A lista de documentos é genérica e precisa ser conferida pela equipe jurídica**, porque muda com o tipo de caso.
- **Reaquecimento anual:** no sistema de origem, o reaquecimento a cada dois meses foi trocado por 3 toques no ano. Lead perdido não quer mensagem todo mês.
- **Todos:** os textos não prometem resultado, não falam de preço e não usam emoji (Provimento 205/2021 da OAB e padrão do escritório).

## Cuidados ao ligar

1. **`_iniciar_fluxo` manda o passo 1 na hora.** Use `enviar_ja=True` só quando o passo 1 tem `apos_horas: 0`. O detalhe está em `gatilhos_por_coluna.py`.
2. **Cron em horário comercial e de hora em hora**, por exemplo `0 9-19 * * 1-6`. Uma vez por dia atrasa os passos de 4 horas, e rodar de madrugada manda mensagem de madrugada.
3. **Teste com `dry_run: true`** no `/fluxos/processar` antes de deixar enviar.
4. **Ao entrar num fluxo novo, os anteriores do card são desligados.** O lead nunca recebe duas cadências ao mesmo tempo.

<a id="mecanicas-que-podem-ser-replicadas"></a>
## Mecânicas que podem ser replicadas

Estas rotinas existem no sistema de origem, mas os textos e critérios são de outro público, por isso o código não veio. Se o escritório quiser alguma, recrie com o roteiro dele.

- **Régua de fechamento de 12 contatos:** depois da reunião, 12 toques em cerca de 30 dias, cada um com um ângulo (dor, prova, autoridade da advogada, urgência do prazo, despedida). No sistema de origem, a maior parte dos fechamentos aconteceu entre o 8º e o 12º contato.
- **Leads quentes parados:** uma rotina diária lê, com IA, as respostas dos leads parados na entrada. Quem demonstrou interesse vira "Lead Quente" e a vendedora recebe o aviso "ligar hoje".
- **Alarme de lead totalmente qualificado:** quando a IA termina a qualificação, a vendedora da vez recebe na hora o "ligar agora", com o resumo do caso.
- **Fila diária de ligação:** a lista do dia, priorizada (quem respondeu e ninguém voltou vem primeiro), com o roteiro de abertura da ligação.
- **Perda declarada:** sem resposta depois do último toque da régua, o card vai sozinho para "Perdido" e entra no reaquecimento anual.
- **Briefing de fechamento:** quando a IA encaminha o lead, ela deixa uma nota interna com o resumo para quem vai ligar (nome, como chamar, o caso, o que ele quer). A busca do item 06 usa a linha "Nome/como chamar" dessa nota.
