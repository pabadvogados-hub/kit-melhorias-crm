# Ligação pelo WhatsApp

**Pré-requisito:** um número do escritório conectado na **D-API** (d-api.cloud). A Z-API não faz ligação de voz pelo navegador. O número pode continuar na Z-API para mensagens e ter uma sessão na D-API só para ligar, ou migrar inteiro.

<a id="14"></a>
## 14. Ligar pelo WhatsApp de dentro do sistema

Arquivos:
- [voz.py](14_ligacao_pelo_whatsapp/voz.py) (backend)
- [dapi.py](14_ligacao_pelo_whatsapp/dapi.py) (cliente D-API)
- [whatsapp-ligar.js](14_ligacao_pelo_whatsapp/whatsapp-ligar.js) e [voip-worklet.js](14_ligacao_pelo_whatsapp/voip-worklet.js) (referência da tela)

### Como funciona

1. A pessoa clica em "Ligar pelo WhatsApp" na conversa, e a tela chama `POST /api/voz/wa/ligar` com o id da conversa.
2. O backend pede a chamada à D-API e devolve só o `callId` e o `wsUrl`. A chave da D-API nunca vai ao navegador.
3. O navegador abre o microfone em 16 kHz e troca áudio PCM direto com o `wsUrl`. O `voip-worklet.js` faz a captura e a reprodução. **O servidor não fica no caminho do áudio**, então a ligação não pesa na VPS.
4. A tela mostra o tempo e os botões de mudo e desligar, e consulta `POST /api/voz/wa/estado`.
5. Ao desligar, `POST /api/voz/wa/fim` faz o fechamento:
   - baixa as duas gravações, `-sender.wav` (escritório) e `-recipient.wav` (cliente);
   - transcreve cada lado separado e junta numa conversa com tempo: `[01:12] Cliente: ...`;
   - grava a transcrição como nota no chat ("TRANSCRIÇÃO DA LIGAÇÃO") e no campo **Notas da Ficha**, com o link da gravação.

### Outros comportamentos

- **Várias linhas:** com mais de um número na D-API, o sistema escolhe uma linha livre e avisa quem está usando cada uma.
- **Linha presa:** quando a D-API diz que a linha está ocupada por uma ligação que já caiu, o sistema destrava sozinho em vez de recusar a ligação.

### Transcrição

O `voz.py` usa as mesmas variáveis `STT_*` que o sistema Braga & Braz já tem (Groq Whisper), então não precisa de chave nova. Trechos de silêncio em que o transcritor "inventa" frases são descartados.

### Configurar o número na D-API (sem coluna nova)

| Campo em `wa_numeros` | Valor |
|---|---|
| `zapi_instance` | `dapi:<id da sessão>` |
| `zapi_token` | API Key da D-API |

O `dapi.py` reconhece o prefixo `dapi:`. Para mensagens passarem pela D-API também, o `zapi.py` precisa desviar para o `dapi` quando `dapi.eh_dapi(numero)`.

### Aplicar

1. Copie `dapi.py` para `whatsapp/` e `voz.py` para `routers/`, e registre `voz.router` no `main.py`.
2. Instale `ffmpeg` na VPS.
3. **Tela (React):** botão "Ligar pelo WhatsApp" no cabeçalho da conversa e um painel flutuante com tempo, mudo e desligar.
   - O áudio segue o `whatsapp-ligar.js`: WebSocket binário, PCM 16-bit a 16 kHz, e o `voip-worklet.js` em `public/`.
   - Os pedaços do `.js` que procuram botões da tela de origem (`SEL_LIGAR`, captura do evento) não se aplicam ao React.
4. **Teste ligando para o celular de alguém da equipe em outra sala.** Na mesma sala o cancelador de eco corta a voz e o teste engana.

### Lições do uso real

- **Microfone longe da boca pega a sala inteira.** Com duas pessoas ligando lado a lado, a voz de uma entra na ligação da outra quase no mesmo volume. Nenhum filtro separa isso: a solução é headset com microfone de haste.
- **Cortes no áudio do cliente** quase sempre vêm da rede celular dele. **Cortes do lado do escritório** vêm da internet ou do PC de quem liga: teste a velocidade de upload e prefira cabo.

<a id="15"></a>
## 15. Redutor de ruído

Arquivos:
- [ruido.js](15_redutor_de_ruido/ruido.js)
- [ruido/](15_redutor_de_ruido/ruido/): RNNoise, licença MIT

Passa o microfone da ligação pelo RNNoise antes de mandar. Nas gravações reais, o ruído nas pausas caiu 28 dB e a voz ficou igual.

- Age só no pedido de microfone da ligação (`sampleRate: 16000`). A gravação de áudio do chat não passa por ele.
- Se algo falhar, ou demorar mais de 4 segundos, devolve o microfone original.
- `?ruido=0` na URL desliga naquele navegador.

**Não ligue o "nivelador" (compressor) que aparece desativado no arquivo.** Em sala com várias pessoas ele sobe a voz das colegas até o volume de quem liga. O RNNoise tira barulho de fundo, mas não tira voz de colega.

**No React:** coloque a pasta `ruido/` em `public/` e aplique a mesma cadeia no `getUserMedia` da ligação: `AudioContext` a 48 kHz → `AudioWorkletNode` do RNNoise → `MediaStreamDestination`.

<a id="16"></a>
## 16. Card anda depois da ligação

Arquivo: [card_apos_ligacao.py](16_card_anda_apos_ligacao/card_apos_ligacao.py)

Se a ligação aconteceu (há transcrição ou gravação na conversa) e o card continua na coluna de entrada, ele vai sozinho para a próxima coluna, 30 minutos depois. Esse tempo é para alguém mover na mão, se preferir.

- Só mexe em card que ainda está na entrada e nunca o faz voltar.
- Registra o movimento em `wa_board_hist` (item 09) e deixa uma nota na conversa.

**Rodar:** `python card_apos_ligacao.py` mostra o que faria; `--aplicar` move. No cron, a cada 10 minutos.

**Depende do item 09**, porque grava em `wa_board_hist`. **Ajustar** `DB`, `BOARD`, `DE` e `PARA`.
