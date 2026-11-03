/* ruido.js — Sistema, redutor de ruido da ligacao pelo WhatsApp. 08/10/2026, pedido do Admin:
   "vamos fazer o diminuidor de ruido".

   Bloco SEPARADO: nao mexe no whatsapp-ligar.js nem no voip-worklet.js (da Socia). Ele embrulha o
   navigator.mediaDevices.getUserMedia e age SO no pedido de microfone da ligacao (audio mono a 16 kHz, como o
   whatsapp-ligar.js pede). Devolve o microfone ja limpo pelo RNNoise (xiph/rnnoise, via
   @sapphi-red/web-noise-suppressor 0.4.1, licenca MIT, arquivos em /ruido/). Daqui pra frente a ligacao segue
   igual: filtro de graves, ganho, worklet, cancelador de eco do Chrome (o eco e cancelado na captura, antes daqui).
   Medido em 08/10 em duas ligacoes reais da sala comercial (lado da vendedora): ruido nas pausas -28 dB,
   voz -0,1 a -0,2 dB.

   LIGADO PARA TODOS desde 13/10/2026; ?ruido=0 desliga naquele navegador (?ruido=1 religa).
   Se qualquer coisa falhar, devolve o microfone original: a ligacao nunca deixa de sair por causa do redutor.
   Gravacao de audio do chat (pede microfone sem 16 kHz) nao passa por aqui. */
(function () {
  "use strict";
  var CHAVE = "kit_ruido", BASE = "/ruido/", VERSAO = "041";
  var NOME_WORKLET = "@sapphi-red/web-noise-suppressor/rnnoise";
  try {
    var m = location.search.match(/[?&]ruido=([01])/);
    if (m) localStorage.setItem(CHAVE, m[1]);
  } catch (e) {}
  // 13/10/2026 (Admin: "melhore a ligacao"): ligado para todos; ?ruido=0 desliga naquele navegador.
  function ligado() { try { return localStorage.getItem(CHAVE) !== "0"; } catch (e) { return true; } }
  // Nivelador de voz (13/10): sobe a fala de quem esta longe do microfone ou fala baixo e segura o pico abaixo
  // de -8 dBFS, porque a ligacao ainda multiplica o sinal por ate 2,2 depois daqui (whatsapp-ligar.js).
  // 14/10/2026: DESLIGADO por padrao. Numa sala com varias vendedoras ele subia tambem as vozes do fundo e o
  // cliente reclamou "muita gente falando, nao consigo entender". Fica o RNNoise. Liga so com kit_nivelador=1.
  function nivelar() { try { return localStorage.getItem("kit_nivelador") === "1"; } catch (e) { return false; } }
  var NIVEL = { limiar: -34, joelho: 10, razao: 4, ataque: 0.004, solta: 0.25, ganho: 0.6, teto: -9 };
  // medido 13/10 (gravacao real, cadeia da ligacao imitada): estouro 1,14% -> 0,01%; voz longe +2,2 dB;
  // ruido nas pausas -55 -> -65 dB. Nivela ANTES do RNNoise para ele limpar o que o nivelador levantou.

  var md = navigator.mediaDevices;
  var AC = window.AudioContext || window.webkitAudioContext;
  if (!md || !md.getUserMedia || !AC || !window.AudioWorkletNode || !window.WebAssembly) return;
  var original = md.getUserMedia.bind(md);

  var wasmPromessa = null;
  function temSimd() {
    try {
      return WebAssembly.validate(new Uint8Array([0, 97, 115, 109, 1, 0, 0, 0, 1, 5, 1, 96, 0, 1, 123, 3, 2, 1, 0,
        10, 10, 1, 8, 0, 65, 0, 253, 15, 253, 98, 11]));
    } catch (e) { return false; }
  }
  function wasm() {
    if (!wasmPromessa) {
      wasmPromessa = fetch(BASE + (temSimd() ? "rnnoise_simd.wasm" : "rnnoise.wasm") + "?v=" + VERSAO)
        .then(function (r) { if (!r.ok) throw new Error("wasm " + r.status); return r.arrayBuffer(); })
        .catch(function (e) { wasmPromessa = null; throw e; });
    }
    return wasmPromessa;
  }

  function ehDaLigacao(c) {
    var a = c && c.audio;
    if (!a || typeof a !== "object" || c.video) return false;
    var sr = a.sampleRate;
    return sr === 16000 || (sr && (sr.ideal === 16000 || sr.exact === 16000));
  }

  function comPrazo(p, ms) {
    return Promise.race([p, new Promise(function (_, nao) { setTimeout(function () { nao(new Error("demorou")); }, ms); })]);
  }

  function limpar(bruto) {
    var ctx;
    try { ctx = new AC({ sampleRate: 48000, latencyHint: "interactive" }); } catch (e) { return bruto; }
    var etapa = Promise.all([wasm(), ctx.audioWorklet.addModule(BASE + "rnnoiseWorklet.js?v=" + VERSAO)])
      .then(function (r) {
        var src = ctx.createMediaStreamSource(bruto);
        var rn = new AudioWorkletNode(ctx, NOME_WORKLET, {
          processorOptions: { maxChannels: 1, wasmBinary: r[0] },
          channelCount: 1, channelCountMode: "explicit", outputChannelCount: [1]
        });
        var dest = ctx.createMediaStreamDestination();
        dest.channelCount = 1;
        if (nivelar()) {
          var comp = ctx.createDynamicsCompressor();
          comp.threshold.value = NIVEL.limiar; comp.knee.value = NIVEL.joelho; comp.ratio.value = NIVEL.razao;
          comp.attack.value = NIVEL.ataque; comp.release.value = NIVEL.solta;
          var ganho = ctx.createGain(); ganho.gain.value = NIVEL.ganho;
          var teto = ctx.createDynamicsCompressor();          // limitador: nada passa de NIVEL.teto
          teto.threshold.value = NIVEL.teto; teto.knee.value = 0; teto.ratio.value = 20;
          teto.attack.value = 0.001; teto.release.value = 0.08;
          src.connect(comp); comp.connect(ganho); ganho.connect(rn); rn.connect(teto); teto.connect(dest);   // nivela, depois limpa
        } else {
          src.connect(rn); rn.connect(dest);
        }
        return (ctx.state === "running" ? Promise.resolve() : ctx.resume()).then(function () {
          if (ctx.state !== "running") throw new Error("audio do navegador parado (" + ctx.state + ")");
          var faixa = dest.stream.getAudioTracks()[0];
          var fechado = false;
          var pararFaixa = faixa.stop.bind(faixa);
          function fechar() {
            if (fechado) return;
            fechado = true;
            ativo = false;
            try { rn.port.postMessage("destroy"); } catch (e) {}
            try { bruto.getTracks().forEach(function (t) { t.stop(); }); } catch (e) {}
            try { ctx.close(); } catch (e) {}
          }
          // a ligacao desliga o microfone com stop(): fecha tambem o microfone de verdade (senao a luz fica acesa)
          faixa.stop = function () { pararFaixa(); fechar(); };
          bruto.getAudioTracks().forEach(function (t) {
            t.addEventListener("ended", function () { pararFaixa(); fechar(); });   // microfone desconectado
          });
          ativo = true;
          marcarPainel();
          try { console.info("[ruido] redutor de ruido ligado (RNNoise)"); } catch (e) {}
          return dest.stream;
        });
      });
    return comPrazo(etapa, 4000).catch(function (e) {
      try { console.warn("[ruido] redutor nao entrou, a ligacao segue sem ele:", e && e.message || e); } catch (x) {}
      try { ctx.close(); } catch (x) {}
      return bruto;
    });
  }

  md.getUserMedia = function (c) {
    if (!ligado() || !ehDaLigacao(c)) return original(c);
    return original(c).then(limpar);
  };

  // Etiqueta discreta no painel da ligacao, ao lado da "v2", so enquanto o redutor esta de fato limpando.
  var ativo = false;
  function marcarPainel() {
    var n = 0;
    var t = setInterval(function () {
      n++;
      var topo = document.querySelector("#kit-wa-painel .pwa-top");
      if (topo && ativo && !topo.querySelector("[data-kit-ruido]")) {
        var s = document.createElement("small");
        s.setAttribute("data-kit-ruido", "1");
        s.title = "Redutor de ruído ligado neste navegador (para desligar: seu-dominio.com.br/?ruido=0)";
        s.textContent = "sem ruído";
        var temV2 = !!topo.querySelector(".pwa-v2");
        s.style.cssText = "font-size:10px;opacity:.75;border:1px solid currentColor;border-radius:6px;padding:0 5px;" +
          "margin-left:" + (temV2 ? "6px" : "auto");
        topo.appendChild(s);
      }
      if ((topo && topo.querySelector("[data-kit-ruido]")) || n > 40 || !ativo) clearInterval(t);
    }, 250);
  }

  if (ligado()) { try { wasm().catch(function () {}); } catch (e) {} }   // ja deixa o wasm baixado
})();
