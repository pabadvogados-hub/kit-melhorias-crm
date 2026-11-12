"""Cliente da API publica do DJEN / Comunica (CNJ), com tratamento da instabilidade.

PEGADINHA (validada): para a MESMA consulta, a API alterna entre tres respostas HTTP 200:
  (a) status "error" com "sistema muito ocupado";
  (b) status "success" com count 0 e items [] (FALSO VAZIO);
  (c) status "success" com os dados certos.
Por isso:
- (a) e' retentada com backoff exponencial;
- (b) so' vira "sem intimacoes" depois de VAZIOS_CONFIRMAM respostas vazias SEM NENHUM dado;
- se o orcamento de MAX_TENTATIVAS acabar sem resposta conclusiva, o resultado e'
  "incompleta" (nunca "sem intimacao"), e a rodada seguinte refaz a consulta.

Sem dependencias externas: usa urllib da biblioteca padrao.
"""
import asyncio
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date

DJEN_URL = 'https://comunicaapi.pje.jus.br/api/v1/comunicacao'
ITENS_POR_PAGINA = 100          # maximo aceito pela API
MAX_TENTATIVAS = 10             # por pagina
VAZIOS_CONFIRMAM = 3            # respostas vazias (sem dados) para aceitar "sem intimacao"
BACKOFF_BASE = 2.0              # segundos
BACKOFF_TETO = 60.0
MAX_PAGINAS = 50
TIMEOUT_S = 30


def espera(tentativa: int) -> float:
    """Pausa depois da tentativa n (1, 2, 3...): 2, 4, 8, 16... teto de 60 s."""
    return min(BACKOFF_BASE * (2 ** (tentativa - 1)), BACKOFF_TETO)


def _data(valor) -> date | None:
    if not valor:
        return None
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


def normalizar_item(item: dict, oab: str) -> dict | None:
    """Converte um item da API nas colunas de int_intimacoes. None se nao tem como identificar."""
    if not isinstance(item, dict):
        return None
    numero = str(item.get('numero_processo') or '').strip()
    bruta = str(item.get('hash') or item.get('id') or '').strip()
    if not bruta:
        base = f"{numero}|{item.get('data_disponibilizacao', '')}|{str(item.get('texto') or '')[:300]}"
        bruta = 'h' + hashlib.sha256(base.encode('utf-8')).hexdigest()[:40]
    return {
        'chave_externa': ('djen:' + bruta)[:120],
        'oab': oab,
        'numero_processo': numero[:40],
        'numero_limpo': re.sub(r'\D', '', numero)[:30],
        'tribunal': str(item.get('siglaTribunal') or '')[:20],
        'orgao': str(item.get('nomeOrgao') or '')[:200],
        'tipo_comunicacao': str(item.get('tipoComunicacao') or '')[:80],
        'texto': str(item.get('texto') or ''),
        'link': str(item.get('link') or '')[:600],
        'disponibilizada': _data(item.get('data_disponibilizacao')),
    }


def _interpretar(payload) -> tuple:
    """('dados', count, items) | ('vazio', 0, []) | ('ocupado', motivo)."""
    if not isinstance(payload, dict):
        return ('ocupado', 'resposta sem objeto JSON')
    status = str(payload.get('status') or '').lower()
    if status != 'success':
        msg = payload.get('message') or payload.get('mensagem') or status or 'sem status'
        return ('ocupado', f'status={status or "-"}: {str(msg)[:120]}')
    try:
        count = int(payload.get('count') or 0)
    except (TypeError, ValueError):
        count = 0
    items = payload.get('items') or []
    if items:
        return ('dados', count, items)
    if count == 0:
        return ('vazio', 0, [])
    return ('ocupado', 'count indica itens, mas a lista veio vazia')


@dataclass
class ResultadoBusca:
    status: str                     # ok | vazio_confirmado | incompleta | erro
    itens: list = field(default_factory=list)
    total: int = 0
    tentativas: int = 0
    ocupados: int = 0
    vazios: int = 0
    log: list = field(default_factory=list)


class _Estado:
    def __init__(self):
        self.tentativas = self.ocupados = self.vazios = 0
        self.log = []


class FonteDJEN:
    """Provedor padrao. `get` injetavel (usado pelos testes): recebe os parametros e devolve
    ('ok', json) | ('ocupado', motivo) | ('erro', motivo)."""
    nome = 'djen'

    def __init__(self, url: str = DJEN_URL, get=None, timeout: int = TIMEOUT_S):
        self.url = url
        self.timeout = timeout
        self._get = get or self._http_get

    def _http_get(self, params: dict) -> tuple:
        qs = urllib.parse.urlencode(params)
        req = urllib.request.Request(f'{self.url}?{qs}', headers={
            'User-Agent': 'intimacoes-kit/1.0', 'Accept': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                corpo = resp.read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                return ('ocupado', f'HTTP {e.code}')
            return ('erro', f'HTTP {e.code}')
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            return ('ocupado', f'rede: {type(e).__name__}')
        try:
            return ('ok', json.loads(corpo))
        except ValueError:
            return ('ocupado', 'resposta nao-JSON')

    async def _pagina(self, base: dict, pagina: int, st: _Estado, sleep):
        vazios = 0
        for t in range(1, MAX_TENTATIVAS + 1):
            st.tentativas += 1
            params = {**base, 'pagina': pagina, 'itensPorPagina': ITENS_POR_PAGINA}
            kind, payload = await asyncio.to_thread(self._get, params)
            if kind == 'erro':
                st.log.append(f'p{pagina} t{t}: erro sem retentativa ({payload})')
                return ('erro', payload)
            r = _interpretar(payload) if kind == 'ok' else ('ocupado', payload)
            if r[0] == 'dados':
                st.log.append(f'p{pagina} t{t}: dados ({r[1]} no total, {len(r[2])} nesta pagina)')
                return ('dados', r)
            if r[0] == 'vazio':
                vazios += 1
                st.vazios += 1
                st.log.append(f'p{pagina} t{t}: vazio ({vazios} de {VAZIOS_CONFIRMAM})')
                if pagina == 1 and vazios >= VAZIOS_CONFIRMAM:
                    return ('vazio', None)
            else:
                st.ocupados += 1
                st.log.append(f'p{pagina} t{t}: sem resposta util ({r[1]})')
            if t < MAX_TENTATIVAS:
                await sleep(espera(t))
        return ('desistiu', None)

    async def buscar_periodo(self, numero: str, uf: str, ini: date, fim: date, *,
                             sleep=asyncio.sleep) -> ResultadoBusca:
        st = _Estado()
        base = {'numeroOab': numero, 'ufOab': uf,
                'dataDisponibilizacaoInicio': ini.isoformat(),
                'dataDisponibilizacaoFim': fim.isoformat()}
        itens: dict = {}
        total = 0
        recebidos = 0
        pagina = 1
        status = 'ok'
        while True:
            kind, val = await self._pagina(base, pagina, st, sleep)
            if kind == 'vazio':
                status = 'vazio_confirmado'
                break
            if kind == 'desistiu':
                status = 'incompleta'
                st.log.append(f'p{pagina}: desistiu apos {MAX_TENTATIVAS} tentativas')
                break
            if kind == 'erro':
                status = 'erro'
                break
            _, count, lista = val
            total = count
            recebidos += len(lista)
            for it in lista:
                norm = normalizar_item(it, f'{numero}/{uf}')
                if norm:
                    itens.setdefault(norm['chave_externa'], it)
            if recebidos >= total:
                break
            pagina += 1
            if pagina > MAX_PAGINAS:
                status = 'incompleta'
                st.log.append('limite de paginas atingido')
                break
        return ResultadoBusca(status=status, itens=list(itens.values()), total=total,
                              tentativas=st.tentativas, ocupados=st.ocupados,
                              vazios=st.vazios, log=st.log)


class ProvedorAlternativo:
    """PONTO DE EXTENSAO, sem implementacao. Desligado por padrao (INT_PROVEDOR_ALTERNATIVO=false).
    Se um dia houver outra fonte paga, implemente buscar_periodo com o mesmo retorno
    de FonteDJEN.buscar_periodo (ResultadoBusca)."""
    nome = 'alternativo'

    async def buscar_periodo(self, *args, **kwargs):
        raise NotImplementedError('Provedor alternativo nao implementado neste kit.')
