# Chat ao Vivo e agente de IA

<a id="01"></a>
## 01. Assinatura do remetente

Arquivo: [01_assinatura_do_remetente/zapi_assinatura.py](01_assinatura_do_remetente/zapi_assinatura.py)

Cada mensagem de texto chega ao cliente com o nome de quem mandou na primeira linha:

```
*Ana Souza:*
Bom dia! Recebi seus documentos.
```

- Pessoa da equipe assina com o nome do cadastro.
- A IA assina com o nome da persona ("Jaqueline").
- Fluxo automático assina com `ASSINATURA_AUTOMACAO`.

O banco guarda o texto sem a assinatura, então o chat do sistema continua igual.

**Aplicar:** troque o `enviar_texto` do `whatsapp/zapi.py` e acrescente `nome_assinatura` e `assinar`. Depois passe o remetente nas chamadas de `/responder`, da IA e da legenda de mídia; o fim do arquivo mostra como.

<a id="02"></a>
## 02. Editar mensagem enviada

Arquivo: [02_editar_mensagem/editar_mensagem.py](02_editar_mensagem/editar_mensagem.py)

Edita no WhatsApp do cliente uma mensagem de texto da equipe com até 15 minutos.

- Só quem mandou a mensagem, ou um admin, pode editar.
- Toda edição fica registrada em `wa_mensagens_edicoes`.
- O aviso de edição que volta pelo webhook é apagado sozinho, para não aparecer um balão duplicado.

**Rotas:**
- `POST /api/atendimento/mensagens/{id}/editar` com `{"texto": "..."}`.
- `GET /api/atendimento/conversas/{id}/editadas` devolve os ids editados, para a tela marcar "editada".

**Provedor:** no sistema de origem a edição sai pela D-API (`dapi.editar_texto`). Pela Z-API, implemente `zapi.editar_texto` seguindo a documentação atual. Esse caminho não foi testado.

<a id="03"></a>
## 03. Pausar o áudio e editar pela tela

Arquivo de referência: [03_editar_e_pausar_na_tela/chat-extras.js](03_editar_e_pausar_na_tela/chat-extras.js)

- **Pausar e continuar a gravação de áudio:** durante a gravação aparece um botão que chama `MediaRecorder.pause()` e `resume()`. O áudio final sai inteiro, sem os trechos pausados.
- **Editar:** nas mensagens de texto da própria pessoa com menos de 15 minutos aparece "editar". Ele abre uma caixa com o texto e chama a rota do item 02. As mensagens editadas ganham o selo "editada".

**No React:** no componente que grava o áudio em `Atendimento.jsx`, guarde a instância do `MediaRecorder` em um `useRef` e alterne `pause()`/`resume()` num botão. O "editar" é um item no menu do balão.

<a id="04"></a>
## 04. Vídeo pela câmera

Arquivos:
- [04_video_pela_camera/video_gravado.py](04_video_pela_camera/video_gravado.py) (backend)
- [04_video_pela_camera/video-gravado.js](04_video_pela_camera/video-gravado.js) (referência da tela)

Botão de câmera ao lado do microfone. O fluxo é:

1. A pessoa grava até 3 minutos no navegador.
2. O navegador grava em WebM, e o backend converte para MP4 (H.264, até 720p) porque o WhatsApp não toca WebM.
3. O vídeo é enviado como vídeo nativo e fica no chat como mensagem do tipo `video`.

**Precisa de:**
- `ffmpeg` na VPS.
- `zapi.enviar_video`, já incluso no item 01. Pela Z-API ele usa o endpoint `send-video`.
- Registrar o router no `main.py`.
- Ajustar `MEDIA_DIR` e o domínio público da pasta `media`.

No sistema de origem ele começou liberado só para dois usuários de teste (lista `TESTE` no `.js`).

<a id="05"></a>
## 05. Chat mais alto

Arquivo de referência: [05_chat_mais_alto/chat-amplo.js](05_chat_mais_alto/chat-amplo.js)

Só CSS na tela do chat: diminui os espaçamentos do cabeçalho, das etiquetas e da caixa de escrever, e as mensagens ganham uns 80 px de altura. Não muda cores, fontes nem a posição de nada.

**No React:** aplique os mesmos valores no CSS do `Atendimento.jsx`. Antes, mostre ao escritório como fica, porque é mudança visual.

<a id="06"></a>
## 06. Busca pelo nome dito

Arquivo: [06_busca_pelo_nome_dito/busca_contatos.py](06_busca_pelo_nome_dito/busca_contatos.py)

O card fica com o nome do perfil do WhatsApp ("Araujo", um emoji, só o número), e a pessoa se apresenta com outro nome na conversa. A busca agora procura também nas mensagens curtas do lead (onde ele diz o nome) e na nota de briefing da IA.

**Rota:** `GET /api/atendimento/contatos?q=`.

<a id="07"></a>
## 07. Webhook sem perder mensagem (conserto)

Arquivo: [07_webhook_sem_perder_mensagem/webhook_conversa_duplicada.py](07_webhook_sem_perder_mensagem/webhook_conversa_duplicada.py)

**O defeito existe hoje no sistema Braga & Braz.** No primeiro contato podem nascer duas conversas para o mesmo número. A partir daí, a busca por telefone do webhook (`scalar_one_or_none()`) estoura em toda mensagem nova desse contato, e a mensagem se perde sem aviso. A correção pega a conversa mais recente.

<a id="08"></a>
## 08. IA: ritmo humano, teto de respostas e saudação

Arquivo: [08_ia_ritmo_humano_e_limites/ia_ritmo_e_limites.py](08_ia_ritmo_humano_e_limites/ia_ritmo_e_limites.py)

Três ajustes independentes:

1. **Ritmo humano:** a IA espera o tempo de alguém lendo e digitando, entre 7 e 13 segundos numa resposta curta, antes de mandar. Resposta instantânea entrega que é robô.
2. **Teto de respostas:** com 12 respostas sem encaminhar o caso, a IA para e deixa uma nota para a equipe assumir. Isso evita loop com trote e spam.
3. **Saudação do WhatsApp Business:** a mensagem automática de boas-vindas do celular voltava pelo webhook como se alguém da equipe tivesse respondido, e a IA era desligada em quase todo lead novo. Agora ela entra como fluxo e a IA segue atendendo.

O sistema Braga & Braz já faz a IA parar quando alguém da equipe responde. O ajuste 3 depende disso.
