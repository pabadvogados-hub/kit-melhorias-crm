/* crm-meus.js — Sistema, "Meus cards" no CRM. 23/10/2026, pedido do Admin: cada vendedora
   trabalha pelo CRM e ve so os leads dela (a dona e o atendente_email, o mesmo campo do filtro "meus" do Chat).

   Bloco SEPARADO: nao mexe no bundle nem nos blocos da Socia. So acrescenta meus=true na busca dos cards
   do quadro (/api/atendimento/conversas?...pipeline_id=...), que o servidor ja entende.
   Liga sozinho para Vendedora1 e Vendedora2; para os outros comeca em "Todos". Botao no topo do CRM troca.
   ?crmmeus=0 desliga o bloco neste navegador. */
(function () {
  "use strict";
  try {
    var m = location.search.match(/[?&]crmmeus=([01])/);
    if (m) localStorage.setItem("kit_crmmeus_bloco", m[1]);
    if (localStorage.getItem("kit_crmmeus_bloco") === "0") return;
  } catch (e) {}

  var VENDEDORAS = ["vendedora1@seuescritorio.com.br", "vendedora2@seuescritorio.com.br"];
  var CHAVE = "kit_crm_meus";
  var email = "";
  function token() { try { return localStorage.getItem("bragabraz_token") || ""; } catch (e) { return ""; } }
  function ligado() {
    try {
      var v = localStorage.getItem(CHAVE);
      if (v === "1" || v === "0") return v === "1";
    } catch (e) {}
    return VENDEDORAS.indexOf(email) >= 0;          // vendedora comeca vendo so os dela
  }

  // 23/10 (Admin: "nao ta aparecendo aqui"): Admin e Socia escolhem de quem ver o quadro
  // (Todos / Vendedora1 / Vendedora2). Filtra a lista que o quadro ja recebeu, pela dona do card.
  var ADMINS = ["admin@seuescritorio.com.br", "socia@seuescritorio.com.br"];
  var CHAVE_VER = "kit_crm_ver";
  function ver() { try { var v = localStorage.getItem(CHAVE_VER) || ""; return VENDEDORAS.indexOf(v) >= 0 ? v : ""; } catch (e) { return ""; } }
  function ehQuadroDeLeads(u) {
    return u && location.pathname.indexOf("/crm") === 0 && /\/api\/atendimento\/conversas\?/.test(u) &&
      /[?&]pipeline_id=(10|24)(&|$)/.test(u) && !/[?&]meus=/.test(u);
  }

  var fetchOriginal = window.fetch;
  // 26/10/2026: sem recarregar a pagina. Antes, na 1a visita da vendedora, o bloco dava location.reload() para
  // ligar o "Meus cards"; o reload abortava o /api/auth/me do sistema, que entendia como sessao invalida, apagava
  // o login e mandava para /login (e o logout apagava a preferencia: ciclo). Agora a busca do quadro ESPERA
  // saber quem e a pessoa e ja sai com o filtro certo.
  var mePromessa = fetchOriginal.call(window, "/api/auth/me", { headers: { Authorization: "Bearer " + token() } })
    .then(function (r) { return r.ok ? r.json() : {}; })
    .then(function (me) { email = String((me && me.email) || "").toLowerCase(); return email; })
    .catch(function () { return ""; })
    .then(function (e) { meResolvido = true; return e; });
  var meResolvido = false;
  window.fetch = function (url, opt) {
    var self = this, args = arguments;
    try {
      var u0 = typeof url === "string" ? url : "";
      if (!meResolvido && ehQuadroDeLeads(u0)) {      // ainda nao sei quem e: espera o /me e decide
        return mePromessa.then(function () { return window.fetch.apply(self, args); });
      }
    } catch (e) {}
    try {
      var u = typeof url === "string" ? url : "";
      var dela = ver();
      if (ehQuadroDeLeads(u) && dela) {              // so o seletor de Admin/Socia grava kit_crm_ver
        return fetchOriginal.call(this, url, opt).then(function (r) {
          if (!r.ok) return r;
          return r.clone().json().then(function (lista) {
            if (!Array.isArray(lista)) return r;
            var so = lista.filter(function (c) { return String(c.atendente_email || "").toLowerCase() === dela; });
            return new Response(JSON.stringify(so), { status: r.status, statusText: r.statusText, headers: r.headers });
          }).catch(function () { return r; });
        });
      }
      if (ehQuadroDeLeads(u) && ligado()) {
        // so nos quadros de leads (Leads 10 e Area 2 24); Contratacao, Producao etc. continuam com todos
        url = u + "&meus=true";
      }
    } catch (e) {}
    return fetchOriginal.call(this, url, opt);
  };

  function seletor(novo) {
    var caixa = document.createElement("span");
    caixa.setAttribute("data-kit-crm-meus", "1");
    caixa.style.cssText = "margin-left:10px;display:inline-flex;gap:4px;align-items:center;border:1px solid var(--border);" +
      "border-radius:10px;padding:3px;vertical-align:middle";
    var atual = ver();
    [["", "Todos"], ["vendedora1@seuescritorio.com.br", "Vendedora1"], ["vendedora2@seuescritorio.com.br", "Vendedora2"]].forEach(function (o) {
      var b = document.createElement("button");
      var on = atual === o[0];
      b.textContent = o[1];
      b.title = o[0] ? "Ver o CRM da " + o[1] + " (Leads e Area 2)" : "Ver todos os leads";
      b.setAttribute("aria-pressed", on ? "true" : "false");
      b.style.cssText = "cursor:pointer;font-size:13px;font-weight:700;border-radius:7px;padding:6px 12px;font-family:inherit;border:1px solid " +
        (on ? "var(--kit-verde)" : "transparent") + ";background:" + (on ? "var(--kit-verde-bg)" : "transparent") +
        ";color:" + (on ? "var(--kit-verde)" : "inherit") + ";";
      b.addEventListener("click", function () {
        try { localStorage.setItem(CHAVE_VER, o[0]); } catch (e) {}
        location.reload();
      });
      caixa.appendChild(b);
    });
    novo.insertAdjacentElement("afterend", caixa);
  }

  function botao() {
    if (!email || location.pathname.indexOf("/crm") !== 0 || document.querySelector("[data-kit-crm-meus]")) return;
    var novo = Array.prototype.find.call(document.querySelectorAll("button"), function (b) {
      return /Novo cliente/.test(b.textContent);
    });
    if (!novo) return;
    if (ADMINS.indexOf(email) >= 0) { seletor(novo); return; }
    var b = document.createElement("button");
    b.setAttribute("data-kit-crm-meus", "1");
    var on = ligado();
    b.textContent = on ? "Meus cards" : "Todos os cards";
    b.title = on ? "Leads e Area 2: mostrando só os leads em que você é a responsável. Clique para ver todos."
                 : "Leads e Area 2: mostrando todos os leads. Clique para ver só os seus.";
    b.style.cssText = "margin-left:10px;cursor:pointer;font-size:13px;font-weight:700;border-radius:9px;" +
      "padding:8px 14px;font-family:inherit;border:1px solid " + (on ? "var(--kit-verde)" : "var(--border)") +
      ";background:" + (on ? "var(--kit-verde-bg)" : "transparent") + ";color:" + (on ? "var(--kit-verde)" : "inherit") + ";";
    b.addEventListener("click", function () {
      try { localStorage.setItem(CHAVE, ligado() ? "0" : "1"); } catch (e) {}
      location.reload();
    });
    novo.insertAdjacentElement("afterend", b);
  }

  mePromessa.then(function () { botao(); });
  function vigiar() {
    new MutationObserver(function () { botao(); }).observe(document.body || document.documentElement,
      { childList: true, subtree: true });
    botao();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", vigiar);
  else vigiar();
})();
