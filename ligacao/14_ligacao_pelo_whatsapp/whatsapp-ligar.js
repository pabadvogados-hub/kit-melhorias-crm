/* LIGAR PELO WHATSAPP — Sistema (D-API). 18/09/2026.
   Bloco SEPARADO: nao altera o bundle nem o softphone. Poe um botao "WhatsApp" ao lado do
   botao "Ligar" da conversa. A ligacao sai pelo WhatsApp do escritorio; o audio vai do
   microfone direto para o stream da D-API. Gravacao + transcricao voltam como nota na conversa.
   Remover = tirar a tag <script id="kit-wa-ligar"> do index.html.
   07/10/2026: versao 2 atras de interruptor (?voz=2): reconexao quando a conexao cai, filtro de
   graves em 200 Hz, ganho menor, buffer de audio maior e nota com "tocou / nao tocou" + inicio do
   id da chamada. SEM o interruptor tudo se comporta como a versao de 24/09. */
(function () {
  "use strict";
  if (window.__kitWaLigar) return;
  window.__kitWaLigar = true;

  var SEL_LIGAR = 'button[title="Ligar para o lead pelo sistema (softphone)"]';
  var ICONE = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 21l1.65-3.8a9 9 0 1 1 3.4 2.9L3 21"/><path d="M9 10a.5.5 0 0 0 1 0V9a.5.5 0 0 0-1 0v1a5 5 0 0 0 5 5h1a.5.5 0 0 0 0-1h-1a.5.5 0 0 0 0 1"/></svg>';
  var chamada = null;   // estado da ligacao atual

  // 07/10/2026: interruptor da versao 2. Liga abrindo seu-dominio.com.br/?voz=2 (fica guardado neste
  // navegador); desliga com ?voz=1. Enquanto a Socia nao mandar virar, o padrao e a versao 1.
  var V2 = (function () {
    try {
      var m = /[?&]voz=([12])(?:&|$)/.exec(location.search);
      if (m) localStorage.setItem("kit_voz_v2", m[1] === "2" ? "1" : "0");
      return localStorage.getItem("kit_voz_v2") === "1";
    } catch (e) { return false; }
  })();

  function token() { try { return localStorage.getItem("bragabraz_token") || ""; } catch (e) { return ""; } }
  var saindo = false;   // vira true so no beforeunload
  function api(caminho, corpo) {
    return fetch(caminho, {
      method: "POST",
      // keepalive SO na saida da pagina. O Chrome limita as requisicoes
      // keepalive a 64 KB simultaneos por pagina; com ele ligado no /wa/estado,
      // que roda de 2 em 2 segundos, a cota estoura e todo fetch passa a falhar
      // com "Failed to fetch" (visto em producao em 24/09/2026 as 16h).
      keepalive: saindo,
      headers: { "Content-Type": "application/json", "Authorization": "Bearer " + token() },
      body: JSON.stringify(corpo || {})
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) throw new Error(j.detail || ("erro " + r.status));
        return j;
      });
    });
  }

  // ---------- botao ao lado do "Ligar" ----------
  function colocarBotoes() {
    var btns = document.querySelectorAll(SEL_LIGAR);
    for (var i = 0; i < btns.length; i++) {
      var b = btns[i];
      if (b.nextElementSibling && b.nextElementSibling.classList.contains("kit-wa-ligar-btn")) continue;
      var w = document.createElement("button");
      w.type = "button";
      w.className = "btn btn-sm kit-wa-ligar-btn";
      w.title = "Ligar pelo WhatsApp do escritório (a ligação é gravada e transcrita na conversa)";
      w.innerHTML = ICONE + "<span>Ligar</span>";
      w.addEventListener("click", (function (orig) { return function (ev) { ev.preventDefault(); pegarDadosELigar(orig); }; })(b));
      b.parentNode.insertBefore(w, b.nextSibling);
    }
  }
  // Os dados do contato (numero, nome, id da conversa) sao os mesmos que o botao "Ligar"
  // manda para o softphone: disparamos o clique dele e capturamos o evento antes do softphone.
  function pegarDadosELigar(botaoOriginal) {
    if (chamada) { painelMsg("Já existe uma ligação em andamento."); return; }
    // O "Ligar" chama window.dispatchEvent(kit:ligar). Trocamos o dispatchEvent so durante
    // este clique: o evento e ENGOLIDO aqui e o softphone (DirectCall) nunca fica sabendo.
    var capturado = null;
    var original = window.dispatchEvent;
    window.dispatchEvent = function (ev) {
      if (ev && ev.type === "kit:ligar") { capturado = ev.detail || {}; return true; }
      return original.call(window, ev);
    };
    try { botaoOriginal.click(); } finally { window.dispatchEvent = original; }
    if (!capturado || !capturado.numero) { alert("Não achei o telefone desta conversa."); return; }
    ligar(capturado.numero, capturado.nome || "", capturado.conversaId || null);
  }

  // ---------- painel ----------
  var painel, elNome, elStatus, elTempo, btnMudo, btnDesligar;
  function montarPainel() {
    if (painel) return;
    painel = document.createElement("div");
    painel.id = "kit-wa-painel";
    painel.setAttribute("role", "status");
    painel.innerHTML =
      '<div class="pwa-top">' + ICONE + '<b>Ligação WhatsApp</b>' + (V2 ? '<small class="pwa-v2">v2</small>' : '') + '</div>' +
      '<div class="pwa-nome"></div><div class="pwa-status"></div><div class="pwa-tempo">00:00</div>' +
      '<div class="pwa-acoes"><button type="button" class="pwa-mudo">Mudo</button>' +
      '<button type="button" class="pwa-desligar">Desligar</button></div>';
    document.body.appendChild(painel);
    elNome = painel.querySelector(".pwa-nome"); elStatus = painel.querySelector(".pwa-status");
    elTempo = painel.querySelector(".pwa-tempo");
    btnMudo = painel.querySelector(".pwa-mudo"); btnDesligar = painel.querySelector(".pwa-desligar");
    btnMudo.addEventListener("click", function () {
      if (!chamada || !chamada.mic) return;
      chamada.mudo = !chamada.mudo;
      chamada.mic.getAudioTracks().forEach(function (t) { t.enabled = !chamada.mudo; });
      btnMudo.textContent = chamada.mudo ? "Voltar o som" : "Mudo";
      btnMudo.classList.toggle("on", chamada.mudo);
    });
    btnDesligar.addEventListener("click", function () { desligar("desligou"); });
  }
  function painelMsg(t) { montarPainel(); painel.style.display = "block"; elStatus.textContent = t; }
  function fecharPainelDepois() {
    setTimeout(function () { if (!chamada && painel) painel.style.display = "none"; }, 4000);
  }

  // ---------- ligacao ----------
  function ligar(numero, nome, conversaId) {
    montarPainel();
    painel.style.display = "block";
    elNome.textContent = (nome || "") + "  +" + String(numero).replace(/\D/g, "");
    elStatus.textContent = "Preparando microfone…";
    elTempo.textContent = "00:00";
    btnMudo.textContent = "Mudo"; btnMudo.classList.remove("on");
    chamada = { conversaId: conversaId, inicio: 0, gravacao: null, motivo: "", mudo: false, fim: false,
      podeFalar: false, tocou: false, estados: [] };
    var c = chamada;
    navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true, sampleRate: 16000 } })
      .then(function (mic) {
        c.mic = mic;
        if (c.fim) { limpar(c); return; }
        elStatus.textContent = "Iniciando ligação…";
        return api("/api/voz/wa/ligar", { telefone: numero, conversa_id: conversaId }).then(function (d) {
          if (c.fim) { limpar(c); return; }
          c.callId = d.callId; c.linha = d.linha || null;
          if (d.linha_nome && elNome) elNome.title = "Saindo pela linha " + d.linha_nome;
          return abrirAudio(c, d.wsUrl);
        });
      })
      .catch(function (e) {
        var msg = String(e && e.message || e);
        if (/Permission|NotAllowed/i.test(msg)) msg = "Libere o microfone para o seu-dominio.com.br e tente de novo.";
        elStatus.textContent = "Não foi possível ligar: " + msg;
        c.motivo = "erro"; c.fim = true; limpar(c); chamada = null; fecharPainelDepois();
      });
  }

  function abrirAudio(c, wsUrl) {
    var ctx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000, latencyHint: "interactive" });
    c.ctx = ctx;
    // 07/10 (v2): pede ao worklet um buffer maior (120 ms antes de tocar, teto 400 ms, alvo 160 ms):
    // som menos picotado quando a rede oscila, ao custo de ~60 ms a mais de atraso.
    var urlWorklet = V2 ? "/voip-worklet.js?v=20261007" : "/voip-worklet.js?v=202609181530";
    return ctx.audioWorklet.addModule(urlWorklet).then(function () {
      var node = new AudioWorkletNode(ctx, "voip-io", { numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1],
        processorOptions: V2 ? { pre: 1920, max: 6400, alvo: 2560 } : {} });
      c.node = node;
      // MICROFONE: corta grave (ruido de mesa/ar) -> compressor (nivela voz baixa/alta) -> ganho
      // 07/10 (v2): o ruido medido nas gravacoes da sala comercial fica abaixo de 300 Hz (ar-condicionado,
      // ventilador, zumbido). A v2 corta em 200 Hz em dois estagios e amplifica menos (1,4x em vez de 2,2x).
      var hp = ctx.createBiquadFilter(); hp.type = "highpass"; hp.frequency.value = V2 ? 200 : 100;
      var comp = ctx.createDynamicsCompressor();
      comp.threshold.value = -28; comp.knee.value = 10; comp.ratio.value = 4;
      comp.attack.value = 0.003; comp.release.value = 0.2;
      var ganho = ctx.createGain(); ganho.gain.value = V2 ? 1.4 : 2.2;
      var limite = ctx.createDynamicsCompressor();          // limitador: nao deixa estourar
      limite.threshold.value = -3; limite.knee.value = 0; limite.ratio.value = 20;
      limite.attack.value = 0.001; limite.release.value = 0.1;
      ctx.createMediaStreamSource(c.mic).connect(hp);
      var saidaFiltro = hp;
      if (V2) { var hp2 = ctx.createBiquadFilter(); hp2.type = "highpass"; hp2.frequency.value = 200; hp.connect(hp2); saidaFiltro = hp2; }
      saidaFiltro.connect(comp); comp.connect(ganho);
      ganho.connect(limite); limite.connect(node);
      // ALTO-FALANTE: toca a voz do cliente via WebRTC local, para o cancelador de eco do
      // Chrome enxergar esse audio e nao devolver a voz do cliente para ele (eco).
      tocarComCancelamentoDeEco(c, ctx, node);
      node.port.onmessage = function (ev) {
        if (ev.data && ev.data.kind === "out" && c.podeFalar && c.ws && c.ws.readyState === 1) c.ws.send(ev.data.pcm);
      };
      // 07/10 (v2): com resume=1 na URL a D-API NAO desliga quando o socket cai; ela segura a chamada
      // por ate 20 s esperando reconectar com a MESMA URL (docs.d-api.cloud/whatsapp/ligacoes/stream).
      // Para desligar de proposito nesse modo: close(1000) ou {type:"hangup"}, que ja fazemos.
      c.wsUrl = V2 ? wsUrl + (wsUrl.indexOf("?") >= 0 ? "&" : "?") + "resume=1" : wsUrl;
      conectar(c);
      c.tIni = Date.now(); relogio(c);
      vigiarChamada(c);
    });
  }

  // 07/10: guarda os eventos vistos e se o celular do cliente chegou a tocar (vai para a nota no fim)
  function marcarEstado(c, tipo) {
    if (!tipo) return;
    if (c.estados.indexOf(tipo) < 0) c.estados.push(tipo);
    if (tipo === "ringing" || tipo === "accepted" || tipo === "connected" || tipo === "active") c.tocou = true;
  }

  function conectar(c) {
    var ws = new WebSocket(c.wsUrl);
    ws.binaryType = "arraybuffer";
    c.ws = ws;
    var node = c.node;
    ws.onmessage = function (e) {
      if (typeof e.data !== "string") { node.port.postMessage({ kind: "in", pcm: e.data }, [e.data]); return; }
      var m; try { m = JSON.parse(e.data); } catch (x) { return; }
      marcarEstado(c, m.type);
      switch (m.type) {
        // depois de uma reconexao a D-API reenvia calling/ringing/accepted: o que ja passou e ignorado
        case "calling": if (!c.inicio) { elStatus.textContent = "Chamando…"; tomLiga(c); } break;
        case "ringing": if (!c.inicio) { elStatus.textContent = "Tocando no celular do cliente…"; tomLiga(c); } break;
        case "accepted": case "connected":
          if (!c.podeFalar) { tomDesliga(c); c.podeFalar = true; c.inicio = Date.now(); elStatus.textContent = "Em ligação"; relogio(c); }
          break;
        case "recording": c.gravacao = { files: m.files || {}, url: m.url || "" }; break;
        case "ended": c.motivo = m.reason || ""; encerrar(c); break;
        case "error": c.motivo = "erro"; elStatus.textContent = "Erro: " + (m.msg || m.code || ""); encerrar(c); break;
      }
    };
    ws.onclose = function (ev) {
      if (c.ws !== ws) return;                                  // socket antigo, ja substituido
      if (!V2 || c.fim || c.encerrando) { encerrar(c); return; }
      if (ev && ev.code === 1000) { encerrar(c); return; }      // fechamento limpo: a chamada acabou mesmo
      reconectar(c);                                            // queda: tenta voltar na mesma chamada
    };
    ws.onerror = function () { /* onclose trata */ };
    ws.onopen = function () {
      if (c.fim) return;
      if (c.quedaEm) {                                          // voltou depois de uma queda
        c.quedaEm = 0;
        elStatus.textContent = c.inicio ? "Em ligação (reconectada)" : "Chamando…";
        return;
      }
      if (!c.inicio) { tomLiga(c); if (!elStatus.textContent || /Iniciando/.test(elStatus.textContent)) elStatus.textContent = "Chamando…"; }
    };
  }

  // 07/10 (v2): a conexao caiu no meio da ligacao. Tenta voltar por ate 20 s, que e o que a D-API segura.
  function reconectar(c) {
    if (c.fim) return;
    if (!c.quedaEm) { c.quedaEm = Date.now(); c.tentativas = 0; }
    if (Date.now() - c.quedaEm > 20000) { c.motivo = c.motivo || "queda"; encerrar(c); return; }
    c.tentativas++;
    elStatus.textContent = "Conexão caiu, reconectando… (" + c.tentativas + ")";
    setTimeout(function () { if (!c.fim && c.quedaEm) conectar(c); }, c.tentativas === 1 ? 300 : 1500);
  }

  // ---------- desligar sozinho (igual ao WhatsApp) ----------
  // A D-API nem sempre avisa pelo WebSocket quando o cliente recusa ou nao atende: o painel
  // ficava "chamando" para sempre. Consultamos o estado da chamada no servidor e ha um limite de toque.
  var LIMITE_TOQUE = 45000;   // ms sem atender -> desliga (o WhatsApp faz parecido)
  var ESTADOS_FIM = { idle: 1, ended: 1, ending: 1, terminated: 1, "": 0 };
  function vigiarChamada(c) {
    if (c.fim || chamada !== c) return;
    var tocando = !c.inicio;
    if (tocando && Date.now() - c.tIni > LIMITE_TOQUE) { autoEncerrar(c, "timeout"); return; }
    api("/api/voz/wa/estado", { callId: c.callId, linha: c.linha }).then(function (st) {
      if (c.fim || chamada !== c) return;
      var e = String(st && st.state || "");
      if (e === "ringing" || e === "active") c.tocou = true;   // 07/10: a consulta tambem conta como "tocou"
      if (e && !ESTADOS_FIM[e]) c.estadoVisto = true;
      var acabou = ESTADOS_FIM[e] === 1 && c.estadoVisto;   // so encerra se ja viu a chamada ativa antes
      if (acabou) {
        if (!c.inicio) autoEncerrar(c, Date.now() - c.tIni < 25000 ? "rejected" : "timeout");
        else autoEncerrar(c, "cliente_desligou");
        return;
      }
      setTimeout(function () { vigiarChamada(c); }, c.inicio ? 4000 : 2000);
    }).catch(function () { setTimeout(function () { vigiarChamada(c); }, 3000); });
  }
  function autoEncerrar(c, motivo) {
    if (c.fim) return;
    c.encerrando = true;        // 07/10: daqui em diante um fechamento do socket nao e queda
    c.motivo = motivo;
    api("/api/voz/wa/desligar", { callId: c.callId, linha: c.linha, motivo: motivo === "timeout" ? "no_answer" : motivo }).catch(function () {});
    try { if (c.ws && c.ws.readyState === 1) c.ws.send(JSON.stringify({ type: "hangup" })); } catch (e) {}
    if (c.inicio) { setTimeout(function () { encerrar(c); }, 1500); }   // da tempo do evento da gravacao
    else encerrar(c);
  }

  // ---------- som de chamada (tuuu... tuuu...) enquanto o celular do cliente toca ----------
  function tomLiga(c) {
    if (c.tom || !c.ctx) return;
    try {
      var o = c.ctx.createOscillator(), g = c.ctx.createGain();
      o.type = "sine"; o.frequency.value = 425; g.gain.value = 0;
      o.connect(g); g.connect(c.ctx.destination); o.start();
      var t = c.ctx.currentTime + 0.05;
      for (var i = 0; i < 14; i++) {            // cobre ate ~70 s de toque
        g.gain.setValueAtTime(0, t + i * 5); g.gain.linearRampToValueAtTime(0.12, t + i * 5 + 0.03);
        g.gain.setValueAtTime(0.12, t + i * 5 + 1.0); g.gain.linearRampToValueAtTime(0, t + i * 5 + 1.03);
      }
      c.tom = { o: o, g: g };
    } catch (e) {}
  }
  function tomDesliga(c) {
    if (!c.tom) return;
    try { c.tom.g.gain.cancelScheduledValues(0); c.tom.g.gain.value = 0; c.tom.o.stop(); c.tom.o.disconnect(); c.tom.g.disconnect(); } catch (e) {}
    c.tom = null;
  }
  function tocarComCancelamentoDeEco(c, ctx, node) {
    var direto = function () {
      if (c.direto) return;
      c.direto = true;
      if (c.audioEl) { c.audioEl.srcObject = null; }
      try { node.connect(ctx.destination); } catch (e) {}
    };
    if (!window.RTCPeerConnection || !ctx.createMediaStreamDestination) { direto(); return; }
    try {
      var dest = ctx.createMediaStreamDestination();
      node.connect(dest);
      var pc1 = new RTCPeerConnection(), pc2 = new RTCPeerConnection();
      c.pcs = [pc1, pc2];
      pc1.onicecandidate = function (e) { if (e.candidate) pc2.addIceCandidate(e.candidate).catch(function () {}); };
      pc2.onicecandidate = function (e) { if (e.candidate) pc1.addIceCandidate(e.candidate).catch(function () {}); };
      var el = document.createElement("audio"); el.autoplay = true; el.style.display = "none";
      document.body.appendChild(el); c.audioEl = el;
      pc2.ontrack = function (e) { if (c.direto) return; el.srcObject = e.streams[0] || new MediaStream([e.track]); el.play().catch(function () {}); };
      dest.stream.getTracks().forEach(function (t) { pc1.addTrack(t, dest.stream); });
      pc1.createOffer().then(function (o) { return pc1.setLocalDescription(o); })
        .then(function () { return pc2.setRemoteDescription(pc1.localDescription); })
        .then(function () { return pc2.createAnswer(); })
        .then(function (a) { return pc2.setLocalDescription(a); })
        .then(function () { return pc1.setRemoteDescription(pc2.localDescription); })
        .catch(function () { direto(); });
      // se em 3 s o audio local nao conectou, toca direto (sem perder o som)
      setTimeout(function () { if (pc2.iceConnectionState !== "connected" && pc2.iceConnectionState !== "completed") direto(); }, 3000);
    } catch (e) { direto(); }
  }

  // cronometro: conta o tempo de TOQUE desde que a chamada sai e zera quando o cliente atende (tempo de conversa)
  function relogio(c) {
    if (c.relogioOn) return; c.relogioOn = true;
    (function tic() {
      if (chamada !== c || c.fim) return;
      var base = c.inicio || c.tIni; if (!base) { setTimeout(tic, 250); return; }
      var s = Math.floor((Date.now() - base) / 1000);
      elTempo.style.opacity = c.inicio ? "1" : ".6";
      elTempo.textContent = String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
      setTimeout(tic, 500);
    })();
  }

  function desligar(motivo) {
    var c = chamada; if (!c) return;
    c.encerrando = true;        // 07/10: fechamento de proposito, nao e queda
    c.motivo = c.motivo || motivo;
    if (c.callId) api("/api/voz/wa/desligar", { callId: c.callId, linha: c.linha, motivo: "hangup" }).catch(function () {});
    if (c.ws && c.ws.readyState === 1) {
      try { c.ws.send(JSON.stringify({ type: "hangup" })); } catch (e) {}
      // espera um pouco pelo evento "recording" antes de fechar
      setTimeout(function () { try { c.ws.close(1000); } catch (e) {} encerrar(c); }, 2500);
      elStatus.textContent = "Encerrando…";
    } else { encerrar(c); }
  }

  var MOTIVOS = { hangup: "desligada", rejected: "o cliente recusou", timeout: "o cliente não atendeu (a D-API encerra a chamada após 30 s de toque)",
    no_answer: "o cliente não atendeu (a D-API encerra a chamada após 30 s de toque)", cliente_desligou: "o cliente desligou", desligou: "você desligou",
    accepted_elsewhere: "atendida em outro aparelho", terminate: "tempo máximo atingido", ws_closed: "conexão fechada",
    queda: "a conexão caiu e não voltou em 20 s" };
  // 07/10 (v2): o servidor guarda so os 40 primeiros caracteres do motivo (voz.py, motivo[:40]); era por isso
  // que a nota saia cortada em "(limite da". Na v2 cabem: motivo curto, se o celular tocou (pelo que a D-API
  // avisou) e o inicio do id da chamada, para cruzar com GET /calls/{id} na D-API quando precisar investigar.
  var MOTIVOS_NOTA = { hangup: "desligada", rejected: "o cliente recusou", timeout: "30 s sem resposta", no_answer: "30 s sem resposta",
    cliente_desligou: "o cliente desligou", desligou: "você desligou", accepted_elsewhere: "atendida em outro aparelho",
    terminate: "tempo máximo atingido", ws_closed: "conexão fechada", queda: "conexão caiu" };
  function motivoNota(c) {
    if (!V2) return MOTIVOS[c.motivo] || c.motivo || "";
    var t = MOTIVOS_NOTA[c.motivo] || c.motivo || "";
    if (!c.inicio) t += c.tocou ? ", tocou" : ", não tocou";
    var id = String(c.callId || "").replace(/-/g, "").slice(0, 8);
    if (id && (t + "; " + id).length <= 40) t += "; " + id;
    return t.slice(0, 40);
  }
  function encerrar(c) {
    if (c.encerrada) return;
    c.encerrada = true; c.fim = true; c.encerrando = true;
    var segundos = c.inicio ? Math.round((Date.now() - c.inicio) / 1000) : 0;
    limpar(c);
    if (chamada === c) chamada = null;
    var auto = c.motivo === "timeout" || c.motivo === "rejected" || c.motivo === "no_answer";
    elStatus.textContent = (auto ? "Encerrada automaticamente" : "Ligação encerrada") +
      (MOTIVOS[c.motivo] ? ": " + MOTIVOS[c.motivo] : "") +
      (segundos ? ". A gravação e a transcrição vão aparecer na conversa." : ".");
    if (c.callId) {
      api("/api/voz/wa/fim", { callId: c.callId, linha: c.linha, conversa_id: c.conversaId, segundos: segundos,
        motivo: motivoNota(c), gravacao: c.gravacao || {} }).catch(function () {});
    }
    fecharPainelDepois();
  }
  function limpar(c) {
    tomDesliga(c);
    try { if (c.ws && c.ws.readyState <= 1) c.ws.close(1000); } catch (e) {}
    try { if (c.mic) c.mic.getTracks().forEach(function (t) { t.stop(); }); } catch (e) {}
    try { if (c.ctx) c.ctx.close(); } catch (e) {}
    try { (c.pcs || []).forEach(function (p) { p.close(); }); } catch (e) {}
    try { if (c.audioEl) { c.audioEl.srcObject = null; c.audioEl.remove(); } } catch (e) {}
  }
  window.addEventListener("beforeunload", function () {
    if (!chamada) return;
    var c = chamada;
    saindo = true;              // daqui pra frente o fetch precisa sobreviver ao unload
    desligar("pagina fechada");
    encerrar(c);   // agora, nao daqui a 2,5 s: a pagina nao vai estar viva la.
                   // encerrar() comeca com "if (c.encerrada) return", entao o
                   // setTimeout de desligar() nao manda /wa/fim duas vezes.
  });

  // ---------- estilo (usa as cores do tema, nada global) ----------
  var css = document.createElement("style");
  css.id = "kit-wa-ligar-css";
  css.textContent =
    // 18/09: o "Ligar" antigo (softphone/DirectCall) fica ESCONDIDO a pedido do Admin; continua
    // no DOM porque o botao do WhatsApp le o numero da conversa atraves dele. Voltar = apagar a 1a regra.
    SEL_LIGAR + "{display:none !important}" +
    // 21/09: DirectCall aposentada — some tambem o selo "Telefone pronto" do softphone antigo
    'div[style*="bottom: 16px"][style*="right: 16px"][style*="z-index: 60"]{display:none !important}' +
    "button.kit-wa-ligar-btn.btn{display:inline-flex !important;align-items:center;gap:6px;white-space:nowrap;font-weight:700 !important;" +
    "background:#34d399 !important;color:#08130d !important;border:none !important;opacity:1 !important}" +
    "button.kit-wa-ligar-btn.btn:hover{background:#4ade80 !important}" +
    "#kit-wa-painel{position:fixed;right:16px;bottom:72px;z-index:10000;width:260px;display:none;" +
    "background:var(--surface-solid,var(--surface,#10213b));color:var(--text,#eaeff6);border:1px solid var(--success,#34d399);" +
    "border-radius:12px;padding:14px;box-shadow:0 12px 36px rgba(0,0,0,.45);font-size:13px}" +
    "#kit-wa-painel .pwa-top{display:flex;align-items:center;gap:8px;color:var(--success,#34d399);margin-bottom:8px}" +
    "#kit-wa-painel .pwa-top small.pwa-v2{margin-left:auto;font-size:10px;opacity:.75;border:1px solid currentColor;border-radius:6px;padding:0 5px}" +
    "#kit-wa-painel .pwa-nome{font-weight:700;word-break:break-word}" +
    "#kit-wa-painel .pwa-status{color:var(--muted,#97a3b6);margin-top:4px;min-height:18px}" +
    "#kit-wa-painel .pwa-tempo{font-size:22px;font-weight:700;font-variant-numeric:tabular-nums;margin:8px 0}" +
    "#kit-wa-painel .pwa-acoes{display:flex;gap:8px}" +
    "#kit-wa-painel .pwa-acoes button{flex:1;min-height:36px;border-radius:8px;border:1px solid var(--border,rgba(255,255,255,.2));" +
    "background:transparent;color:inherit;font-weight:700;cursor:pointer}" +
    "#kit-wa-painel .pwa-mudo.on{background:rgba(234,179,84,.18);border-color:#eab354}" +
    "#kit-wa-painel .pwa-desligar{background:#dc2626 !important;border-color:#dc2626 !important;color:#fff !important}";
  (document.head || document.documentElement).appendChild(css);

  function vigiar() {
    colocarBotoes();
    new MutationObserver(function () { colocarBotoes(); }).observe(document.body, { childList: true, subtree: true });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", vigiar); else vigiar();
})();
