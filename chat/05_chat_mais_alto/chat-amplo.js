/* chat-amplo.js — Sistema, conversa mais alta no Chat ao Vivo. 08/10/2026, pedido do Admin:
   "quero que fique maior a visualizacao das conversas, estao muito curto".

   Bloco SEPARADO: nao mexe no bundle, no tema da Socia nem no visual novo. So aperta os espacamentos que
   comem altura acima e abaixo das mensagens (cabecalho da conversa, faixa das etiquetas, caixa de escrever e o
   respiro da pagina). Nada muda de lugar, de cor ou de fonte. Medido em 1366x768: a area das mensagens tinha
   333 px de altura.

   Regra do escritorio: mudanca de tela so vira padrao depois da Socia aprovar. Ate la vale so para quem
   ligar no proprio navegador: seu-dominio.com.br/chat?chatamplo=1 liga, ?chatamplo=0 desliga (fica guardado).
   PADRAO PARA TODOS desde 08/10/2026 (Admin: "pode replicar, sem mexer nos fluxos"); ?chatamplo=0 volta ao anterior. */
(function () {
  "use strict";
  var CHAVE = "kit_chat_amplo", ATTR = "data-kit-chat-amplo";
  try {
    var m = location.search.match(/[?&]chatamplo=([01])/);
    if (m) localStorage.setItem(CHAVE, m[1]);
  } catch (e) {}
  function ligado() { try { return localStorage.getItem(CHAVE) !== "0"; } catch (e) { return true; } }

  // Os blocos do chat nao tem classe: o alvo e o estilo inline que o bundle escreve. Se o bundle mudar e o
  // seletor deixar de casar, simplesmente nada acontece (a tela fica como antes).
  var H = "html[" + ATTR + "][" + ATTR + "]";
  var PAINEL_TOPO = H + ' .panel > div[style*="padding: 14px 20px"][style*="border-bottom"]';
  var ETIQUETAS = H + ' .panel > div[style*="padding: 8px 20px"][style*="font-size: 12px"]';
  var MENSAGENS = H + ' .panel > div[style*="--chat-bg"]';
  var CAIXA = H + ' .panel > div[style*="padding: 14px"][style*="border-top"]';
  var CSS = [
    H + " .content{padding-top:8px!important;padding-bottom:8px!important}",
    H + ' .content > div > div[style*="margin-bottom: 14px"][style*="flex-wrap: wrap"]{margin-bottom:8px!important}',
    PAINEL_TOPO + "{padding:6px 14px!important;gap:6px 8px!important}",
    ETIQUETAS + "{padding:3px 14px!important}",
    MENSAGENS + "{padding:12px 16px!important;gap:6px!important}",
    CAIXA + "{padding:8px 12px!important}",
    CAIXA + ' > div[style*="margin-bottom: 8px"]{margin-bottom:4px!important}',
    CAIXA + ' > div[style*="margin-bottom: 8px"] .btn{padding-top:3px!important;padding-bottom:3px!important;' +
      "min-height:28px!important;height:auto!important}"
  ].join("\n");

  function estilo() {
    if (document.getElementById("kit-chat-amplo-css")) return;
    var s = document.createElement("style");
    s.id = "kit-chat-amplo-css";
    s.textContent = CSS;
    (document.head || document.documentElement).appendChild(s);
  }

  function aplicar() {
    var h = document.documentElement;
    if (!h) { document.addEventListener("DOMContentLoaded", aplicar); return; }
    var ok = ligado() && /^\/chat(\/|$)/.test(location.pathname);
    if (ok) { estilo(); if (!h.hasAttribute(ATTR)) h.setAttribute(ATTR, ""); }
    else if (h.hasAttribute(ATTR)) h.removeAttribute(ATTR);
  }

  // o sistema troca de tela sem recarregar: confere a rota quando ela muda
  ["pushState", "replaceState"].forEach(function (k) {
    var orig = history[k];
    if (typeof orig !== "function") return;
    history[k] = function () { var r = orig.apply(this, arguments); setTimeout(aplicar, 0); return r; };
  });
  window.addEventListener("popstate", aplicar);
  aplicar();
})();
