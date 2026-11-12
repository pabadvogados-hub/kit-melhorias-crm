# Agentes por pessoa

Desenho e roteiro para dar a cada pessoa da equipe um agente de IA próprio dentro do sistema: ela conversa com o agente, o agente consulta o escritório e age com a permissão dela, e o administrador lê e orienta.

## Os dois arquivos

- `ENGENHARIA_REVERSA.md`: documento de arquitetura. Modelo de dados, fluxo de uma mensagem, ferramentas, travas, voz, "Meu dia", cérebro e pontos de risco. Serve para entender e para revisar.
- `PROMPT_DE_ARRANQUE.md`: prompt pronto para colar no Claude Code, dentro do repositório. Faz o trabalho em cinco fases, com teste e parada ao fim de cada uma.

## Ordem de uso

1. Ler o `ENGENHARIA_REVERSA.md`, pelo menos as seções 1, 4, 8 e 14.
2. Copiar a pasta `agentes/` para dentro do repositório (sugestão: `docs/agentes/`).
3. Preencher a tabela de agentes da seção 3 do `PROMPT_DE_ARRANQUE.md`.
4. Colocar as chaves no `backend/.env` (lista na seção 5 do prompt).
5. Abrir o Claude Code na raiz do repositório e colar o bloco do prompt.
6. Aprovar cada fase depois de ver os testes. Deploy é feito pelo processo do escritório, não pelo agente.
