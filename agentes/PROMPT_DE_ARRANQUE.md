# Prompt de arranque: agentes por pessoa no Braga & Braz

## Como usar (para o Renato)

1. Copie a pasta `agentes/` inteira para dentro do repositório `SISTEMA_BRAGA_BRAZ` (sugestão: `docs/agentes/`). O prompt pede para o Claude ler o `ENGENHARIA_REVERSA.md`.
2. Abra o Claude Code na **raiz do repositório** (a pasta que contém `backend/` e `frontend/`).
3. Cole o bloco abaixo inteiro, como mensagem única.
4. Preencha a tabela de agentes (seção 3 do prompt) antes de mandar, ou responda quando o Claude perguntar.
5. Coloque as chaves só no `backend/.env` (seção 5 do prompt). Nunca cole chave no chat.

O Claude vai parar ao fim de cada fase e mostrar o resultado. Você decide se segue.

---

```text
Você vai construir, neste repositório (Braga & Braz, sistema de atendimento e CRM em FastAPI + SQLAlchemy async + SQLite, com React/Vite), um sistema de AGENTES POR PESSOA: cada usuário da equipe conversa com o próprio agente de IA, que consulta o sistema e age com a permissão da pessoa. O administrador lê as conversas e deixa orientações.

Antes de qualquer código, leia com atenção:

1. `docs/agentes/ENGENHARIA_REVERSA.md` (ou onde a pasta `agentes/` estiver). É o desenho completo, extraído de outro sistema que já roda. Use como referência de DESENHO, não copie código nem nomes de lá. Este projeto é isolado: nenhum dado, nome, chave, domínio ou marca de outro escritório entra aqui, nem como exemplo, nem em comentário.
2. `CLAUDE.md` deste repositório (regras de ouro do escritório). Elas valem para o agente também.
3. `backend/app/database.py`, `backend/app/deps.py`, `backend/app/security.py`, `backend/app/main.py`, `backend/app/config.py`, `backend/app/routers/atendimento.py` (funções `_filtro_visibilidade`, `_pode_ver_conversa`, `usuario_do_atendimento` e a rota `/conversas/{id}/responder`), `backend/app/whatsapp/models.py`, `backend/app/routers/prazos.py` (modelo `Prazo` e rotas), `backend/app/routers/pecas.py` (rotas `/pedidos`), `frontend/src/App.jsx`, `frontend/src/modules.js`, `frontend/src/components/Layout.jsx`, `frontend/src/api.js`.

## Regras que não podem ser quebradas

- **Atendimento atual não quebra.** Não altere o webhook, o agente de primeiro atendimento (`backend/app/whatsapp/bragabraz.py`), os fluxos automáticos, o envio de WhatsApp nem o significado dos campos de `wa_conversas`. Este trabalho só acrescenta.
- **Backup antes de qualquer mudança de banco.** Copie `sistema_bragabraz.db` (o nome real está em `config.py`) para `sistema_bragabraz.db.bak_AAAAMMDD_HHMM` antes da primeira migração e antes de cada fase.
- **Testes nunca usam o banco de produção.** Para testar, aponte `DATABASE_URL` para uma cópia do banco.
- **Nenhuma mensagem real de WhatsApp em teste.** Para testar envio, substitua a função de envio por um stub que só registra o que sairia (ou use uma conversa de teste com número da equipe, só se eu autorizar). Nunca chame o envio contra um lead ou cliente real.
- **Nada sai para cliente ou lead sem confirmação explícita.** Toda ação que chega a alguém de fora vira prévia; quem confirma é um humano (regra detalhada na Fase 2).
- **O agente nunca protocola nada e nunca produz peça de processo que não seja do escritório.** Se a pessoa pedir isso, a resposta é a recusa padrão do escritório, sem gerar nada.
- **Nunca inventar fundamentação jurídica.** Dúvida de direito: consulte o cérebro (Fase 3) ou diga que é orientação geral.
- **Nada público.** O repositório é privado. Não crie remoto público, não suba `.env`, não suba dados de cliente, não ponha CPF ou telefone real em código, teste ou exemplo.
- **Não mexa em** `OPERACIONAL/`, `INTEGRACOES/`, scripts de contrato e boleto, nem na pasta da Rede/OneDrive. Não rode deploy: eu faço o deploy depois, pelo processo do escritório.
- **Uma fase por vez.** Ao fim de cada fase: compile (`python -m py_compile` nos arquivos novos e alterados), rode os testes da fase, mostre o resultado e PARE. Só siga para a próxima quando eu disser.

## 1. Primeiro, investigação e plano curto (sem editar nada)

Investigue o código e responda, em no máximo 40 linhas:

- Como `Usuario.papel` e as flags (`pecas_liberado`, `contratacao_liberado`, `modulos`, `areas_permitidas`) são usadas hoje. Quais métodos (`pode_pecas`, `pode_contratacao`, `pode_modulo`) cada rota chama.
- Como a rota de prazo (`POST /api/prazos`) trata o campo de aprovação quando quem cria é da equipe (não admin). Esse fluxo é o que o agente deve seguir.
- Como o campo `responsavel` de prazo e de conversa é gravado (nome? e-mail?). Isso decide como o agente acha "os meus".
- Quais colunas de `wa_stages` disparam automação ao entrar (contrato, boas-vindas, envio ao cliente). Liste-as. São as colunas de prévia obrigatória.
- Onde o token JWT é validado e como criar um token para um usuário no servidor (`criar_token`).
- O que já existe de Anthropic, Groq (STT) e ElevenLabs no `config.py` e no `.env.example`.

Depois proponha o plano: arquivos novos, arquivos alterados, tabelas novas, rotas novas. Liste o que você não sabe e me pergunte, em lista curta. Não comece a Fase 1 antes da minha resposta.

## 2. Desenho que deve ser seguido (resumo do ENGENHARIA_REVERSA.md)

- Um agente por pessoa. Identidade: nome, gênero (a/o), cor, símbolo, papel, foco, voz. Sem linha na tabela, o agente é "Assistente" com o papel do usuário.
- Só a pessoa conversa com o próprio agente (o `user.id` vem do token). O admin lê a conversa de qualquer pessoa em modo somente leitura e grava orientações, que entram no prompt de todas as respostas seguintes daquela pessoa.
- O agente chama o próprio sistema com um token JWT criado no servidor para a pessoa da conversa, de vida curta, nunca enviado ao modelo nem ao navegador. Assim vale a mesma permissão da tela. Na dúvida sobre visibilidade, reutilize `_pode_ver_conversa` e `_filtro_visibilidade`; não reescreva a regra.
- Ações internas (criar prazo, anotar, atribuir) executam e gravam o antes e o depois em `ag_acoes`.
- Ações externas (mensagem ao lead, mover card para coluna que dispara automação, qualquer DELETE) só executam pela confirmação (Fase 2).
- Laço de ferramentas com limite de rodadas; na última rodada, sem ferramentas, o agente diz o que fez e o que falhou.
- Resposta gravada com fontes e ações. Pergunta da pessoa gravada ANTES de chamar o modelo.

## 3. Tabela de agentes (preencher; o Claude cria as linhas com esta tabela)

| Pessoa | Papel no sistema | Nome do agente | Artigo (a/o) | Cor | Símbolo | Voz (id da ElevenLabs, Fase 4) | Foco (uma frase) |
|---|---|---|---|---|---|---|---|
| Renato | admin | a definir | | | | a definir | |
| Maria Gabriela | admin | a definir | | | | a definir | |
| Giselle | advogado | a definir | | | | a definir | |
| Erick | assistente | a definir | | | | a definir | |
| Lucas | sdr | a definir | | | | a definir | |

Enquanto a tabela estiver com "a definir", crie os agentes com nome genérico "Assistente" e deixe claro na tela que o admin ainda não batizou. Não invente nomes nem vozes. O foco padrão, se vazio, pode ser: advogado = "prazos, processos e peças da sua área"; assistente = "apoio em prazos e documentos"; sdr = "qualificação e agendamento de leads"; admin = "gestão do escritório e supervisão da equipe". Marque como sugestão no código.

## 4. Fases

### Fase 1: núcleo, conversa por texto, orientações e leitura

Entregas:

1. Modelos novos (prefixo `ag_`, padrão do repositório): `ag_agentes`, `ag_mensagens`, `ag_orientacoes`, `ag_acoes`. Crie com a mesma base declarativa de `database.py` e com o `init_db()` existente. Só tabelas novas: não altere tabelas existentes nesta fase.
2. Semeadura: para cada usuário ativo sem linha em `ag_agentes`, crie uma linha com "Assistente" (ou o nome da tabela da seção 3 se eu já tiver preenchido).
3. Módulo novo (sugestão: `backend/app/agentes/`) com: identidade (`agente_de`, `apresentacao`), montagem do prompt do sistema (persona, pessoa, data e hora em português, foco, regras de atuação, bloco de postura, orientações ativas), laço de ferramentas (até 6 rodadas, última rodada sem ferramentas, resultado cortado em 40 mil caracteres, erro vira `{"erro": ...}`, nunca quebra o turno).
4. Ferramentas da Fase 1, todas só leitura, sempre com a identidade da pessoa da conversa:
   - `minhas_tarefas` (prazos da pessoa: atrasados, hoje, amanhã, semana), com o campo de responsável descoberto no passo 1.
   - `minha_agenda` (compromissos da pessoa nos próximos 7 dias).
   - `meus_leads` (conversas com `atendente_email` = a pessoa, últimos 3 dias, máximo 40).
   - `buscar_lead` (pelo nome ou telefone, respeitando a visibilidade).
   - `ler_chat` (mensagens de uma conversa, máximo 80, 4 mil caracteres por mensagem; respeitando `_pode_ver_conversa`; sem marcar nada como lido).
   - `buscar_conhecimento` e `ler_documento`: devolvem "o cérebro do escritório ainda não foi carregado" até a Fase 3.
5. Endpoints em `/api/agentes`:
   - `GET /meu` (agente da pessoa; admin pode passar `usuario_id`);
   - `GET /equipe` (só admin);
   - `GET /conversa` (últimas 80 mensagens da conversa atual; admin pode passar `usuario_id`; admin recebe também as orientações);
   - `POST /conversa` com `{texto}` (até 6 mil caracteres);
   - `POST /conversa/nova`;
   - `POST /{uid}/orientacoes` e `DELETE /orientacoes/{id}` (desativa, não apaga; só admin);
   - `PUT /{uid}` para batizar (nome, gênero, cor, símbolo, foco; só admin).
6. Motor: use o SDK `anthropic` já listado no `requirements.txt`, com `ANTHROPIC_API_KEY` do `config.py`. Modelo: use o mesmo identificador que o `whatsapp/bragabraz.py` usa para respostas de qualidade (confira no arquivo). Sem modo de raciocínio. Não adicione motor pela assinatura nem Gemini nesta fase.
7. Frontend: página nova `/agentes` (sugestão de nome), com:
   - cabeçalho com o nome e o artigo do agente;
   - aba "Conversar" (texto; Enter envia, Shift+Enter quebra linha; botão "Nova conversa");
   - para admin: seletor de pessoa (conversa em modo somente leitura para as outras), área de orientações (listar, adicionar, desativar) e formulário para batizar;
   - mensagens de erro da API mostradas na tela com botão de tentar de novo.
   Registre a página em `modules.js` (acesso: `todos`) e no `Layout.jsx`, e a rota em `App.jsx`. Use o padrão de `api.js`. Não use emoji na interface.
8. Config: nada novo obrigatório nesta fase. Documente em `backend/.env.example` apenas os nomes das variáveis, sem valor.

Testes da Fase 1 (obrigatórios, com banco de cópia):
- Pessoa A não lê a conversa da pessoa B (403). Admin lê a de B. Pessoa comum não cria orientação (403).
- Orientação ativa aparece no prompt montado; desativada, não aparece.
- Ferramenta de leitura nunca retorna lead ou conversa que `_pode_ver_conversa` negaria para a pessoa.
- Nenhuma chamada a envio de WhatsApp durante os testes (confirme com um stub que conta chamadas: deve ser zero).
- `py_compile` em tudo que criou; `npm run build` no frontend sem erro.

PARE e mostre: lista de arquivos, resultado dos testes e um exemplo de conversa de teste.

### Fase 2: ações internas e ações que saem para fora

Entregas:

1. Ações internas (executam, gravam em `ag_acoes` com resumo, antes e depois, e devolvem uma frase de confirmação):
   - criar prazo ou compromisso (`POST /api/prazos`). Se quem pede não é admin, o prazo segue o mesmo fluxo de aprovação que a tela já usa para a equipe (descoberto no passo 1). Não crie um atalho que pule a aprovação;
   - concluir prazo (só o que é da pessoa; o administrador pode mais);
   - remarcar prazo: só mexe em data interna. Mudar o prazo fatal exige pedido explícito e data nova dita pela pessoa;
   - anotar no card (`POST /api/atendimento/conversas/{id}/nota`);
   - editar dados do card (`PATCH /.../dados`);
   - pegar o lead para si (`POST /.../atribuir`).
2. Ações externas. Não executam na hora:
   - `responder_lead` (chama o mesmo caminho de `POST /conversas/{id}/responder`);
   - `mover_lead` para coluna que dispara automação (`POST /conversas/{id}/etapa`). A lista de colunas que disparam automação vem do passo 1: mover para coluna segura passa direto, as outras têm prévia;
   - qualquer DELETE, ou chamada genérica à API que envie mensagem.
3. Prévia e confirmação. Tabela `ag_pendentes` (campos: id, usuário, ferramenta, argumentos em JSON, texto exato da prévia, id da última mensagem da pessoa, criado em, status: aguardando, feita, falhou, cancelada, expirada, substituída). Regras:
   - a prévia expira em 1 hora;
   - só executa se a pessoa que confirma é a mesma que pediu;
   - a confirmação é um BOTÃO na tela ("Confirmar envio" / "Cancelar"), com o texto exato à vista. Endpoints: `POST /api/agentes/acoes/{codigo}/confirmar` e `POST /api/agentes/acoes/{codigo}/cancelar`;
   - sugestão de salvaguarda: "sim" digitado no chat não executa nada. Se quiser, aceite só como atalho ligado por configuração e desligado por padrão;
   - se a pessoa muda o texto depois da prévia, a prévia antiga vira "substituída" e a nova precisa de confirmação.
4. Regra do escritório (decisão do Renato, a confirmar): "ato que chega ao cliente só sai depois do 'pode' do Renato". Implemente uma configuração `AG_CLIENTE_EXIGE_ADMIN` com padrão LIGADO: quando quem pede não é admin, a confirmação vira pendência de administrador, que aprova no mesmo painel. Não desligue por conta própria. Me pergunte antes de mudar o padrão.
5. Registro: todo confirmar, cancelar e expirar entra em `ag_acoes`. Use também a trilha de auditoria que o sistema já tem (`registrar` em `whatsapp/models.py`).
6. Idempotência (obrigatório, a origem não tinha no caminho da API): cada chamada de ferramenta que age recebe uma chave (id da mensagem da pessoa + nome da ferramenta + hash dos argumentos), gravada em `ag_acoes` ANTES de executar. Se o laço for refeito (motor caiu, reserva entrou), o despacho consulta a chave e devolve o resultado anterior, sem executar de novo.

Testes da Fase 2:
- Ação interna cria o registro em `ag_acoes` com antes e depois.
- Ação externa sem confirmação não altera nada e não chama o envio (stub contando zero).
- Confirmação por quem não pediu: recusada.
- Prévia expirada: recusada.
- Texto mudado após a prévia: a antiga fica "substituída" e não executa.
- Usuário não admin com ação para cliente: vira pendência de administrador, não executa.
- Idempotência: rodar o mesmo turno duas vezes (simulando queda do motor no meio) não duplica nenhuma ação.
- Teste das regras de visibilidade do Fase 1 continua passando.

PARE e mostre os testes.

### Fase 3: cérebro (conhecimento do escritório)

Entregas:

1. Montagem (script em `backend/tools/cerebro/montar.py` ou pasta equivalente, roda no seu computador):
   - allowlist: lista de fontes em arquivo de configuração revisável (caminho, área, padrão de arquivo). A lista é SUA. Pare e peça a lista de fontes antes de montar. Sugestão de áreas: teses, regras, peças (modelos), operacional, comercial, marketing, mapas. Não inclua contratos, procurações, documentos de cliente, financeiro, comissões nem nada com credencial;
   - remoção de frontmatter; descarte de linha com padrão sensível (remuneração, senha, token, chave, segredo, configuração); máscara de CPF; PDF lido como texto;
   - documento com menos de 80 caracteres sai;
   - saída: JSON `{gerado_em, documentos: [{caminho, titulo, area, texto}]}`.
   - marcadores `[CONFERIR]` ou "a confirmar" dos documentos de origem são preservados no texto. O agente repete esse aviso quando citar a tese.
2. Índice (script `indexar.py`, ou na inicialização do backend):
   - banco SQLite separado (caminho em `config.py`, ex.: `CEREBRO_DB`), reconstruído do zero em arquivo temporário e trocado com `os.replace` (troca atômica);
   - tabela FTS5 `trechos` (título, seção, área, caminho, texto), tokenizer `unicode61 remove_diacritics 2`; tabela `documentos` com o texto completo; tabela `meta`;
   - pedaços de até 2500 caracteres, cortados nos títulos `#`, `##`, `###`; pedaço com menos de 40 caracteres sai.
3. Ferramentas `buscar_conhecimento` (até 6 resultados, até 1600 caracteres cada, ranking `bm25` com peso 3 no título, 2 na seção, 1 no texto) e `ler_documento` (até 15 mil caracteres). Conexão somente leitura ao índice.
4. Tela de fontes (só admin, sugestão): lista de fontes com botão ligar/desligar, gravada em `ag_cerebro_fontes`. Sem isso, a mudança é por arquivo.

Testes da Fase 3:
- Linha sensível some do texto indexado; CPF aparece mascarado; documento curto fica de fora.
- Busca por palavra com e sem acento acha o mesmo trecho.
- Reconstrução do índice não deixa o backend lendo arquivo pela metade (simule uma falha no meio e confira que o índice antigo continua válido).
- Nenhum documento de cliente entrou (confira a lista de caminhos).

PARE e mostre a lista de fontes que entrou, sem o conteúdo.

### Fase 4: voz e "Meu dia"

Entregas:

1. Escuta: transcrição pelo Groq já configurado (`STT_API_KEY`, `STT_BASE_URL`). Use `whisper-large-v3` para o agente (variável nova `AG_STT_MODEL`), idioma `pt`, `temperature=0`, e um prompt com vocabulário do escritório (nomes da equipe, termos de prazo, audiência, prazo fatal, petição). Limite de 12 MB por áudio.
2. Fala: ElevenLabs (variável nova `ELEVENLABS_API_KEY`), modelo `eleven_flash_v2_5`, saída `mp3_44100_64`, idioma `pt`, estabilidade 0,5, similaridade 0,8, velocidade 1,05. Voz por agente (campo da tabela da seção 3). Sem chave ou em erro: a tela mostra "voz indisponível agora" e o texto segue no chat. Reserva Gemini de voz é opcional, só com `GEMINI_API_KEY` e aprovação.
3. Preparo do texto para falar: troca `[#123]` por "tarefa 123", tira markdown, corta em frase até 450 caracteres e acrescenta "O resto está escrito aqui no chat."
4. Prompt de voz: no máximo 3 frases curtas, sem lista, sem markdown, sem colchetes; não ler número de processo, dizer o nome do cliente.
5. Endpoints: `POST /api/agentes/voz` (multipart: transcreve, conversa, responde falando) e `POST /api/agentes/ouvir/{mensagem_id}` (lê uma resposta escrita; só a própria pessoa; admin ouve qualquer uma).
6. Interface de voz: captura com `MediaRecorder` e echo/ruído ligados; fim de fala por 1,5 s de silêncio depois de ter falado; desiste após 15 s sem fala; máximo 45 s; uma pergunta por clique (não fica ouvindo entre respostas); botão "Pular" e "Encerrar voz"; mensagem clara quando o microfone é negado.
7. "Meu dia" (painel no topo da tela de Prazos ou na página do agente, a decidir com o Renato): `GET /api/agentes/meu-dia` com:
   - dados do dia: atrasados, hoje, amanhã, semana, sem prazo, caixa "Conferir" (sugestão: prazo com status de "sumiu" no espelho, ou compromisso passado sem marca de cumprido), compromissos;
   - texto escrito pelo modelo a partir SÓ desses dados, até 9 linhas, começando por "Bom dia, <nome>. Aqui é <agente>.", sem emoji, sem título, sem travessão, citando prazos como [#id];
   - cache por pessoa e por dia (`ag_dia`); `refazer=true` regenera; em erro do modelo, mostra os dados e "O assistente não respondeu agora".
   - Admin pode ver o dia de outra pessoa; os outros recebem 403.

Testes da Fase 4:
- `para_falar` corta em frase e nunca passa do limite; remove markdown; troca `[#id]`.
- Com chave de voz ausente, a resposta do chat continua e a voz vem como indisponível.
- "Meu dia" não inventa item: confira que cada prazo citado no texto existe nos dados.
- Pessoa comum não vê o dia de outra (403).

PARE e mostre.

### Fase 5 (opcional, só com aprovação explícita minha)

Não implemente nada desta fase sem eu autorizar por escrito, depois de ler a seção 14 do ENGENHARIA_REVERSA.md.

- Motor pela assinatura do Claude (token da conta de assinatura): antes, eu preciso verificar os termos de uso da Anthropic para este caso. A recomendação do documento é usar chave de API. Se autorizado, fica desligado por padrão e com caminho de volta para a API.
- Operador técnico (agente de código no servidor): NÃO recomendado. Não implemente. Se eu insistir depois de ler a seção 14, faça no máximo a versão só de leitura e me mostre o desenho antes de codar.

## 5. Chaves e configuração

Chaves que você precisa, e em que fase:

| Chave | Para quê | Fase | Já existe? |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Motor do agente (API) | 1 | Sim, em `config.py` |
| `STT_API_KEY` (Groq) | Ouvir áudio | 4 | Sim, em `config.py` |
| `ELEVENLABS_API_KEY` | Falar a resposta | 4 | Não, criar |
| `GEMINI_API_KEY` | Reserva de voz (opcional) | 4 | Opcional |
| `CLAUDE_CODE_OAUTH_TOKEN` | Motor pela assinatura | 5 | Não recomendado sem aprovação |

Regras das chaves:
- Vão só em `backend/.env` (que já está fora do git). Nunca em código, teste, commit, mensagem ou log.
- Em `backend/.env.example` entram apenas os nomes, com valor vazio.
- Nenhum valor de chave aparece nas respostas que você me der.

Variáveis novas (nomes sugeridos, todas com padrão seguro): `AG_STT_MODEL`, `AG_CLIENTE_EXIGE_ADMIN` (padrão ligado), `CEREBRO_DB` (caminho do índice).

## 6. Entrega final

Ao terminar a última fase que eu autorizar, me entregue:

1. Lista de arquivos criados e alterados, com o caminho.
2. Lista de tabelas novas e confirmação de que nenhuma tabela existente mudou de estrutura (exceto colunas acrescentadas por migração leve, se for o caso, com o motivo).
3. Resultado de cada teste da fase, com contagem.
4. Confirmação de que o agente de atendimento e o webhook não foram tocados (diff restrito).
5. O que ficou de fora e por quê.
6. O comando de deploy que eu devo rodar pelo processo do escritório. Você não faz deploy.

Responda em português, direto, sem emoji. Se algo do código real não bater com este prompt, pare e me pergunte. Não invente.
```

---

## Checklist rápido (para o Renato, antes de colar)

- [ ] Pasta `agentes/` copiada para dentro do repositório
- [ ] Backup do banco feito (ou deixado para o próprio Claude, como pede o prompt)
- [ ] Tabela da seção 3 preenchida (ou pronta para responder às perguntas do Claude)
- [ ] Decisão sobre "ato que chega ao cliente só com o seu pode" (o padrão do prompt é ligado)
- [ ] `ELEVENLABS_API_KEY` só se for chegar à Fase 4
- [ ] Confirmar a lista de fontes do cérebro antes da Fase 3 (o Claude não escolhe sozinho)
