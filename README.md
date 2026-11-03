# Kit de melhorias: Chat, CRM, Ligação e Fluxos

Melhorias que já estão funcionando em produção num sistema irmão (mesma base de código: FastAPI + React, WhatsApp pela Z-API ou D-API, CRM em quadro). O kit foi montado para aplicar no sistema **Braga & Braz** e adaptar às áreas do escritório: Holding Familiar, Direito de Família, Restituição Tributária e Rescisão de Multipropriedade.

Não é um sistema para instalar por cima. Cada pasta é uma melhoria isolada, com o código e as instruções de onde encaixar. Aplique uma de cada vez, teste e só então passe para a próxima.

**Quem vai aplicar:** o Claude Code do lado do escritório. O roteiro está em [INSTRUCOES_CLAUDE.md](INSTRUCOES_CLAUDE.md).

## O que tem aqui

| # | Melhoria | Para que serve | O sistema Braga & Braz já tem? |
|---|---|---|---|
| **Chat** | | | |
| 01 | [Assinatura do remetente](chat/README.md#01) | Cada mensagem chega ao cliente com `*Nome:*` de quem mandou | Não |
| 02 | [Editar mensagem enviada](chat/README.md#02) | Corrigir no WhatsApp do cliente uma mensagem de até 15 minutos | Não |
| 03 | [Pausar o áudio e editar pela tela](chat/README.md#03) | Pausar e continuar a gravação de áudio; botão "editar" no balão | Não |
| 04 | [Vídeo pela câmera](chat/README.md#04) | Gravar vídeo no navegador e mandar ao cliente (converte para MP4) | Não |
| 05 | [Chat mais alto](chat/README.md#05) | Mais mensagens visíveis na tela, só ajustando espaçamentos | Não |
| 06 | [Busca pelo nome dito](chat/README.md#06) | Acha o lead pelo nome que ele falou, não só pelo nome do perfil | Não |
| 07 | [Webhook sem perder mensagem](chat/README.md#07) | Corrige um defeito que **existe hoje** e faz mensagem sumir | **Tem o defeito** |
| 08 | [IA: ritmo humano e limites](chat/README.md#08) | "Digitando...", teto de respostas e saudação do WhatsApp Business | Parcial |
| **CRM** | | | |
| 09 | [Trava do quadro](crm/README.md#09) | Card que a equipe mudou de quadro não volta sozinho | Não |
| 10 | [Régua de contatos](crm/README.md#10) | 1º, 2º, 3º contato, quem fez, se respondeu; alerta "lead esperando" | Não |
| 11 | [Classificação no contato](crm/README.md#11) | Lead que volta meses depois cai onde estava, não na entrada | Não |
| 12 | [Origem do anúncio](crm/README.md#12) | Guarda de qual anúncio do Meta veio cada lead | Não |
| 13 | [Dona do lead](crm/README.md#13) | Cada vendedora com os seus leads; "Meus cards" no CRM | Parcial (filtro `meus`) |
| **Ligação** | | | |
| 14 | [Ligar pelo WhatsApp](ligacao/README.md#14) | Ligar de dentro do sistema, com gravação e transcrição na Ficha | Não (precisa D-API) |
| 15 | [Redutor de ruído](ligacao/README.md#15) | Tira o barulho da sala do microfone de quem liga | Não |
| 16 | [Card anda após ligação](ligacao/README.md#16) | Card sai da entrada sozinho quando a ligação aconteceu | Não |
| **Fluxos** | | | |
| — | [Holding, Família e reaquecimento](fluxos/README.md) | Cadências prontas por área + gatilhos por coluna | Motor sim; textos não |

## Ordem recomendada

1. **07: webhook sem perder mensagem.** É conserto, não novidade: hoje um contato com duas conversas perde toda mensagem nova.
2. **01 e 08:** assinatura e ritmo da IA. Mudam a experiência do lead no primeiro dia.
3. **Fluxos:** depois que o Renato aprovar os textos.
4. **09, 10 e 13:** organização do CRM.
5. **02 a 06, 11 e 12:** chat e CRM, conforme a necessidade.
6. **14 a 16:** ligação. Só depois de conectar um número na D-API.

## O que não veio, e por quê

- **Robôs de venda da área de origem** (qualificação, briefing, vídeo de venda, alarmes de lead quente): os textos e critérios são de outro público e não servem para Holding ou Família. A mecânica de cada um está descrita em [fluxos/README.md](fluxos/README.md#mecanicas-que-podem-ser-replicadas), para recriar com o roteiro do escritório.
- **Telas que só existem no outro sistema** (financeiro, processos, portal do cliente): fora do escopo do Braga & Braz.
- **Credenciais:** nenhuma. Tokens, chaves e senhas ficam no `.env` de cada sistema.

## Avisos

- Os arquivos `.js` das pastas foram feitos para outra tela. No Braga & Braz a tela é React com código-fonte (`frontend/src/pages/Atendimento.jsx`): use o `.js` como referência do comportamento e implemente como componente.
- Os redutores de ruído em `ligacao/15_redutor_de_ruido/ruido/` são do RNNoise (`@sapphi-red/web-noise-suppressor` 0.4.1, licença MIT, ver `LICENSE`).
