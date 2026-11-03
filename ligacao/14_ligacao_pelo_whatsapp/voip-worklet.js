// voip-worklet.js — Sistema, ligacao pelo WhatsApp (D-API). 18/09/2026.
// Converte Float32 (navegador) <-> Int16 PCM 16 kHz mono (rede) e amortece jitter.
// Referencia: docs.d-api.cloud/whatsapp/ligacoes/stream
// 07/10/2026: os tamanhos do buffer podem vir de fora (processorOptions {pre, max, alvo}). Sem eles
// valem os mesmos numeros de 18/09. A versao 2 da tela manda 1920 / 6400 / 2560 (120 / 400 / 160 ms).
const FRAME = 320;      // 20 ms @ 16 kHz
const PREBUFFER = 960;  // ~60 ms antes de comecar a tocar
const MAXBUF = 3200;    // se passar de ~200 ms acumulado, descarta o excesso (evita delay crescente)
const ALVO = 1280;      // volta para ~80 ms

class VoipIO extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const po = (options && options.processorOptions) || {};
    this.pre = po.pre > 0 ? po.pre : PREBUFFER;
    this.max = po.max > 0 ? po.max : MAXBUF;
    this.alvo = po.alvo > 0 ? po.alvo : ALVO;
    this.ring = new Float32Array(16000 * 2);
    this.wr = 0; this.rd = 0; this.filled = 0; this.primed = false;
    this.outAccum = new Float32Array(FRAME); this.outLen = 0;
    this.port.onmessage = (e) => {
      if (!e.data || e.data.kind !== "in") return;
      const i16 = new Int16Array(e.data.pcm);
      for (let i = 0; i < i16.length; i++) {
        this.ring[this.wr] = i16[i] / 32768;
        this.wr = (this.wr + 1) % this.ring.length;
        if (this.filled < this.ring.length) this.filled++;
        else this.rd = (this.rd + 1) % this.ring.length; // buffer cheio: descarta o mais antigo
      }
    };
  }
  process(inputs, outputs) {
    const mic = inputs[0] && inputs[0][0];
    if (mic) {
      for (let i = 0; i < mic.length; i++) {
        this.outAccum[this.outLen++] = mic[i];
        if (this.outLen === FRAME) {
          const i16 = new Int16Array(FRAME);
          for (let k = 0; k < FRAME; k++) {
            let v = this.outAccum[k];
            v = v > 1 ? 1 : v < -1 ? -1 : v;
            i16[k] = v * 32767;
          }
          this.port.postMessage({ kind: "out", pcm: i16.buffer }, [i16.buffer]);
          this.outLen = 0;
        }
      }
    }
    const out = outputs[0][0];
    if (this.filled > this.max) {         // atraso acumulado: pula para perto do audio mais novo
      const pular = this.filled - this.alvo;
      this.rd = (this.rd + pular) % this.ring.length;
      this.filled -= pular;
    }
    if (!this.primed && this.filled >= this.pre) this.primed = true;
    for (let i = 0; i < out.length; i++) {
      if (this.primed && this.filled > 0) {
        out[i] = this.ring[this.rd];
        this.rd = (this.rd + 1) % this.ring.length;
        this.filled--;
      } else {
        out[i] = 0;
        if (this.primed && this.filled === 0) this.primed = false;
      }
    }
    return true;
  }
}
registerProcessor("voip-io", VoipIO);
