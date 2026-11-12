"""Regras do modulo de intimacoes: listar, conferir, descartar, OABs e ponte com processos.

Tudo recebe uma AsyncSession (`db`) e usa SQL direto nas tabelas int_* e pz_* (o mesmo
caminho que o OPERACIONAL usa para inserir no Calendario). Erros de regra viram
ErroIntimacao(status, msg); o router converte em HTTPException.

Conferir = criar de 1 a 20 itens em pz_prazos com origem='intimacao' e chave_externa
'int:<id da intimacao>:<n>', e gravar a linha 'criado' em pz_historico de cada um.
"""
import inspect
import json
import re
from datetime import date, datetime, timedelta

from sqlalchemy import text

from . import classificador

TIPOS_CONFERENCIA = ('prazo', 'audiencia', 'providencia', 'tarefa', 'reuniao', 'outro')
TIPOS_COM_APROVACAO = ('prazo', 'audiencia')     # mesma regra de routers/prazos.py
ORIGEM_ITEM = 'intimacao'
MAX_ITENS = 20
STATUS = ('nova', 'conferida', 'descartada')


class ErroIntimacao(Exception):
    def __init__(self, status: int, msg: str):
        super().__init__(msg)
        self.status = status
        self.msg = msg


def _agora() -> datetime:
    """UTC, sem fuso: a VPS roda em UTC e o Calendario ja grava assim."""
    return datetime.utcnow()


def _txt(dt: datetime | None) -> str | None:
    """Formato que o SQLAlchemy grava em DATETIME no SQLite (lido pelos modelos do sistema)."""
    return dt.isoformat(sep=' ', timespec='microseconds') if dt else None


def _linha(row) -> dict:
    d = dict(row._mapping) if hasattr(row, '_mapping') else dict(row)
    try:
        d['alertas'] = json.loads(d.get('alertas') or '[]')
    except ValueError:
        d['alertas'] = []
    return d


def _pasta_normalizada(valor: str) -> str:
    """Usa a mesma normalizacao do Calendario quando o modulo de prazos esta instalado."""
    valor = (valor or '').strip()[:120]
    try:
        from ..routers.prazos import pasta_normalizada
    except ImportError:
        return valor
    return pasta_normalizada(valor)[:120]


_RE_OAB = re.compile(r'^\s*(\d{1,7})\s*/\s*([A-Za-z]{2})\s*$')


def parse_oab(texto: str) -> tuple[str, str]:
    """'123456/SP' -> ('123456', 'SP'). Qualquer outra forma e' recusada."""
    m = _RE_OAB.match(texto or '')
    if not m:
        raise ErroIntimacao(400, 'OAB inválida. Use o formato NUMERO/UF, por exemplo 123456/SP.')
    return m.group(1).lstrip('0') or '0', m.group(2).upper()


# ----------------------------------------------------------------- leitura

async def contagem(db) -> dict:
    rows = (await db.execute(text(
        'SELECT status, COUNT(*) AS n FROM int_intimacoes GROUP BY status'))).all()
    cont = {s: 0 for s in STATUS}
    for status, n in rows:
        cont[status] = n
    cont['total'] = sum(cont[s] for s in STATUS)
    cont['novas'] = cont['nova']
    return cont


async def listar(db, *, status: str = 'nova', oab: str | None = None, tribunal: str | None = None,
                 de: date | None = None, ate: date | None = None, q: str | None = None,
                 pagina: int = 1, por_pagina: int = 30) -> dict:
    """Novas primeiro (as que esperam conferencia), depois a mais recente."""
    where, params = [], {}
    if status in STATUS:
        where.append('status = :status')
        params['status'] = status
    if oab:
        where.append('oab = :oab')
        params['oab'] = oab
    if tribunal:
        where.append('tribunal = :tribunal')
        params['tribunal'] = tribunal.strip().upper()
    if de:
        where.append('disponibilizada_em >= :de')
        params['de'] = de.isoformat()
    if ate:
        where.append('disponibilizada_em <= :ate')
        params['ate'] = ate.isoformat()
    if q and q.strip():
        termo = q.strip()
        digitos = re.sub(r'\D', '', termo)
        cond = ['texto LIKE :q', 'orgao LIKE :q', 'numero_processo LIKE :q']
        params['q'] = f'%{termo}%'
        if digitos:
            cond.append('numero_limpo LIKE :qd')
            params['qd'] = f'%{digitos}%'
        where.append('(' + ' OR '.join(cond) + ')')
    clausula = ('WHERE ' + ' AND '.join(where)) if where else ''
    por_pagina = max(1, min(por_pagina, 100))
    pagina = max(1, pagina)
    total = (await db.execute(text(f'SELECT COUNT(*) FROM int_intimacoes {clausula}'),
                              params)).scalar() or 0
    rows = (await db.execute(text(
        f"""SELECT id, chave_externa, oab, numero_processo, numero_limpo, tribunal, orgao,
                   tipo_comunicacao, disponibilizada_em, publicada_em, inicio_prazo, tipo_ato,
                   rotulo_ato, prazo_dias, prazo_origem, data_fatal, alertas, status,
                   processo_id, conferida_por, conferida_em, descartada_motivo, capturada_em
            FROM int_intimacoes {clausula}
            ORDER BY CASE status WHEN 'nova' THEN 0 ELSE 1 END,
                     disponibilizada_em DESC, id DESC
            LIMIT :lim OFFSET :off"""),
        {**params, 'lim': por_pagina, 'off': (pagina - 1) * por_pagina})).all()
    return {'items': [_linha(r) for r in rows], 'total': total, 'pagina': pagina,
            'por_pagina': por_pagina}


async def responsaveis(db) -> list[dict]:
    rows = (await db.execute(text(
        'SELECT email, nome, papel FROM usuarios WHERE ativo = 1 ORDER BY nome'))).all()
    return [{'email': e, 'nome': n, 'papel': p} for e, n, p in rows]


async def _carregar(db, iid: int) -> dict:
    row = (await db.execute(text('SELECT * FROM int_intimacoes WHERE id = :i'),
                            {'i': iid})).first()
    if not row:
        raise ErroIntimacao(404, 'Intimação não encontrada.')
    return _linha(row)


async def perfil(db, iid: int) -> dict:
    d = await _carregar(db, iid)
    prazos = (await db.execute(text(
        """SELECT id, titulo, tipo, data, hora, responsavel, aprovacao, concluido, prazo_dias
           FROM pz_prazos WHERE origem = :o AND chave_externa LIKE :p ORDER BY data"""),
        {'o': ORIGEM_ITEM, 'p': f'int:{iid}:%'})).all()
    d['prazos'] = [dict(r._mapping) for r in prazos]
    d['sugestoes'] = []
    if d['status'] == 'nova':
        d['sugestoes'] = [classificador.sugestao_item(
            d['tipo_ato'], d['rotulo_ato'], d['prazo_dias'], d['numero_processo'], d['data_fatal'])]
    return d


async def ultimas_capturas(db, n: int = 20) -> list[dict]:
    rows = (await db.execute(text(
        'SELECT * FROM int_capturas ORDER BY iniciada_em DESC, id DESC LIMIT :n'),
        {'n': max(1, min(n, 100))})).all()
    return [dict(r._mapping) for r in rows]


# ----------------------------------------------------------------- OABs

async def listar_oabs(db) -> list[dict]:
    rows = (await db.execute(text(
        'SELECT oab, rotulo, ativo, criado_em FROM int_oabs ORDER BY oab'))).all()
    return [dict(r._mapping) for r in rows]


async def adicionar_oab(db, texto: str, rotulo: str = '') -> dict:
    numero, uf = parse_oab(texto)
    chave = f'{numero}/{uf}'
    await db.execute(text(
        """INSERT INTO int_oabs (oab, rotulo, ativo, criado_em) VALUES (:o, :r, 1, :e)
           ON CONFLICT(oab) DO UPDATE SET ativo = 1, rotulo = excluded.rotulo"""),
        {'o': chave, 'r': (rotulo or '').strip()[:120], 'e': _txt(_agora())})
    await db.commit()
    return {'oab': chave, 'rotulo': (rotulo or '').strip()[:120], 'ativo': True}


async def remover_oab(db, texto: str) -> dict:
    numero, uf = parse_oab(texto)
    await db.execute(text('DELETE FROM int_oabs WHERE oab = :o'), {'o': f'{numero}/{uf}'})
    await db.commit()
    return {'ok': True}


async def oabs_ativas(db, extras=()) -> list[tuple[str, str]]:
    """OABs a consultar: as ativas na tabela + as de INT_OABS (.env) + extras, sem repetir."""
    vistas, saida = set(), []
    fontes = []
    rows = (await db.execute(text('SELECT oab FROM int_oabs WHERE ativo = 1'))).all()
    fontes += [r[0] for r in rows]
    fontes += list(extras or ())
    for bruto in fontes:
        for pedaco in re.split(r'[;,\n]', bruto or ''):
            if not pedaco.strip():
                continue
            try:
                par = parse_oab(pedaco)
            except ErroIntimacao:
                continue
            if par not in vistas:
                vistas.add(par)
                saida.append(par)
    return saida


# ----------------------------------------------------------------- ponte com processos

async def processo_id_para(db, numero: str) -> int | None:
    """Liga a intimacao ao processo, SE o modulo de processos estiver instalado.

    Contrato: processos_nucleo.achar_processo(db, numero) casa pelos digitos do CNJ e
    devolve o processo (objeto ou dict) ou None. Sem o modulo, devolve None e a
    intimacao segue funcionando so com o numero.
    """
    if not numero:
        return None
    try:
        from ..processos_nucleo import achar_processo
    except ImportError:
        return None
    try:
        achado = achar_processo(db, numero)
        if inspect.isawaitable(achado):
            achado = await achado
    except Exception:
        return None
    if achado is None:
        return None
    pid = achado.get('id') if isinstance(achado, dict) else getattr(achado, 'id', None)
    return int(pid) if pid else None


# ----------------------------------------------------------------- conferir / descartar

_RE_HORA = re.compile(r'^\s*(\d{1,2})\s*[:h]?\s*(\d{2})?\s*$')


def _validar_item(i: int, it: dict, emails: set) -> dict:
    """Valida uma providencia da conferencia. Erro aponta o item pelo numero (1-based)."""
    tipo = (it.get('tipo') or 'prazo').strip()
    if tipo not in TIPOS_CONFERENCIA:
        raise ErroIntimacao(400, f'Item {i}: tipo inválido ({tipo}).')
    titulo = (it.get('titulo') or '').strip()
    if not titulo:
        raise ErroIntimacao(400, f'Item {i}: informe o título.')
    try:
        data = date.fromisoformat(str(it.get('data') or ''))
    except ValueError:
        raise ErroIntimacao(400, f'Item {i}: informe a data (AAAA-MM-DD).')
    hora = ''
    if (it.get('hora') or '').strip():
        m = _RE_HORA.match(it['hora'])
        if not m or int(m.group(1)) > 23 or int(m.group(2) or 0) > 59:
            raise ErroIntimacao(400, f'Item {i}: hora inválida. Use 14:30.')
        hora = f'{int(m.group(1)):02d}:{int(m.group(2) or 0):02d}'
    responsavel = (it.get('responsavel') or '').strip().lower()
    if responsavel and responsavel not in emails:
        raise ErroIntimacao(400, f'Item {i}: responsável não é usuário ativo.')
    dias = it.get('prazo_dias')
    if dias in ('', 0):
        dias = None
    if dias is not None:
        try:
            dias = int(dias)
        except (TypeError, ValueError):
            raise ErroIntimacao(400, f'Item {i}: prazo em dias inválido.')
        if not 1 <= dias <= 120:
            raise ErroIntimacao(400, f'Item {i}: prazo em dias deve ficar entre 1 e 120.')
    return {'tipo': tipo, 'titulo': titulo[:300], 'data': data, 'hora': hora,
            'fatal': tipo == 'prazo' or bool(it.get('fatal')), 'responsavel': responsavel,
            'prazo_dias': dias, 'pasta': _pasta_normalizada(it.get('pasta') or ''),
            'processo': (it.get('processo') or '').strip()[:60],
            'cliente': (it.get('cliente') or '').strip()[:200],
            'observacao': (it.get('observacao') or '').strip()[:1500],
            'sugerido': bool(it.get('sugerido'))}


async def conferir(db, iid: int, usuario, itens: list[dict]) -> dict:
    """Grava 1..N prazos/compromissos a partir da intimacao. Tudo ou nada (uma transacao)."""
    if not itens:
        raise ErroIntimacao(400, 'Inclua pelo menos uma providência.')
    if len(itens) > MAX_ITENS:
        raise ErroIntimacao(400, f'No máximo {MAX_ITENS} providências por intimação.')
    row = await _carregar(db, iid)
    if row['status'] != 'nova':
        raise ErroIntimacao(409, f"Esta intimação já foi {row['status']}.")
    emails = {u['email'].lower() for u in await responsaveis(db)}
    limpos = [_validar_item(n, it, emails) for n, it in enumerate(itens, start=1)]

    agora = _agora()
    e_admin = usuario.papel == 'admin'
    criados = []
    for n, it in enumerate(limpos, start=1):
        pendente = (not e_admin) and it['tipo'] in TIPOS_COM_APROVACAO
        eh_prazo = it['tipo'] == 'prazo'
        chave = f'int:{iid}:{n}'
        obs = f"Intimação #{iid} ({row['tribunal']} - {row['orgao']})".strip()
        if it['observacao']:
            obs += '. ' + it['observacao']
        params = {
            'origem': ORIGEM_ITEM, 'chave': chave, 'titulo': it['titulo'], 'tipo': it['tipo'],
            'data': it['data'].isoformat(), 'hora': it['hora'], 'fatal': 1 if it['fatal'] else 0,
            'processo': row['numero_processo'] or it['processo'],
            'pasta': it['pasta'], 'cliente': it['cliente'], 'responsavel': it['responsavel'],
            'obs': obs[:2000], 'dias': it['prazo_dias'],
            'fatal_em': it['data'].isoformat() if eh_prazo else None,
            'aprov': 'pendente' if pendente else 'aprovado',
            'dec_por': usuario.email if e_admin else '',
            'dec_em': _txt(agora) if e_admin else None,
            'criado_por': usuario.email, 'agora': _txt(agora),
        }
        res = await db.execute(text(
            """INSERT INTO pz_prazos (origem, chave_externa, titulo, tipo, data, hora, fatal,
                   processo, pasta, cliente, responsavel, observacao, concluido, concluido_em,
                   concluido_por, sumiu, oculto, prazo_dias, fatal_em, travas, aprovacao,
                   aprovacao_nota, decidido_por, decidido_em, criado_por, criado_em,
                   atualizado_em, resultado)
               VALUES (:origem, :chave, :titulo, :tipo, :data, :hora, :fatal, :processo, :pasta,
                   :cliente, :responsavel, :obs, 0, NULL, '', 0, 0, :dias, :fatal_em, '',
                   :aprov, '', :dec_por, :dec_em, :criado_por, :agora, :agora, '')"""),
            params)
        prazo_id = res.lastrowid
        detalhe = (f"da intimação #{iid} ({row['rotulo_ato'] or row['tipo_ato']}, "
                   f"disponibilizada em {row['disponibilizada_em']})")
        detalhe += ' · aguarda aprovação' if pendente else ''
        await db.execute(text(
            """INSERT INTO pz_historico (prazo_id, pasta, processo, cliente, titulo, evento,
                   detalhe, por, em)
               VALUES (:pid, :pasta, :processo, :cliente, :titulo, 'criado', :detalhe, :por, :em)"""),
            {'pid': prazo_id, 'pasta': it['pasta'], 'processo': params['processo'],
             'cliente': it['cliente'], 'titulo': it['titulo'], 'detalhe': detalhe[:400],
             'por': usuario.email, 'em': _txt(agora)})
        criados.append({'id': prazo_id, 'tipo': it['tipo'], 'data': params['data'],
                        'aprovacao': params['aprov'], 'responsavel': it['responsavel']})

    upd = await db.execute(text(
        """UPDATE int_intimacoes SET status = 'conferida', conferida_por = :u,
                  conferida_em = :e, processo_id = COALESCE(processo_id, :pid)
           WHERE id = :i AND status = 'nova'"""),
        {'u': usuario.email, 'e': _txt(agora), 'i': iid, 'pid': row['processo_id']})
    if upd.rowcount != 1:
        await db.rollback()
        raise ErroIntimacao(409, 'Esta intimação foi tratada por outra pessoa agora. Atualize a tela.')
    await db.commit()
    return {'ok': True, 'prazos': criados}


async def descartar(db, iid: int, usuario, motivo: str) -> dict:
    motivo = (motivo or '').strip()
    if len(motivo) < 3:
        raise ErroIntimacao(400, 'Informe o motivo para descartar (pelo menos 3 letras).')
    await _carregar(db, iid)
    agora = _agora()
    upd = await db.execute(text(
        """UPDATE int_intimacoes SET status = 'descartada', conferida_por = :u,
                  conferida_em = :e, descartada_motivo = :m
           WHERE id = :i AND status = 'nova'"""),
        {'u': usuario.email, 'e': _txt(agora), 'm': motivo[:400], 'i': iid})
    if upd.rowcount != 1:
        await db.rollback()
        raise ErroIntimacao(409, 'Esta intimação já foi tratada.')
    await db.commit()
    return {'ok': True}
