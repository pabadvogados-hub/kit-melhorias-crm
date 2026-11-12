"""Nucleo do modulo Processos: regras, consultas e ligacao com pz_prazos, pz_pastas
e wa_conversas. Sem FastAPI aqui: o router traduz ErroProcesso em HTTP.

Destino: backend/app/processos_nucleo.py

Pontos que outros modulos usam:
- achar_processo(db, numero)  -> ProcProcesso | None   (intimacoes: ligar intimacao a processo)
- garantir_catalogo(db)       -> semeia as fases na 1a subida (so se a tabela estiver vazia)
- planejar_carga / aplicar_carga -> carga inicial a partir de pz_prazos e pz_pastas
"""
import functools
import json
import re
from datetime import datetime

from sqlalchemy import select, func, or_, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .areas import AREAS_NEGOCIO
from .database import Usuario
from .processos_models import ProcFase, ProcCliente, ProcProcesso, ProcParte, ProcHistorico
from .routers.prazos import Prazo, PastaIndice, pasta_normalizada
from .whatsapp.models import Conversa


# ----------------------------------------------------------------- constantes

# Catalogo inicial, so para o escritorio ajustar na tela (admin). Generico de processo
# civel. O escritorio pode trocar nomes e grupos na tela; nada aqui e regra de negocio.
FASE_PADRAO = 'A classificar'
FASES_PADRAO = [
    ('GERAL', 'A classificar'),
    ('CONTRATAÇÃO', 'Contrato assinado'),
    ('CONTRATAÇÃO', 'Documentação pendente'),
    ('PRÉ-PROCESSUAL / EXTRAJUDICIAL', 'Notificação enviada'),
    ('PRÉ-PROCESSUAL / EXTRAJUDICIAL', 'Negociação'),
    ('CONHECIMENTO', 'Petição inicial protocolada'),
    ('CONHECIMENTO', 'Citação / contestação'),
    ('CONHECIMENTO', 'Audiência'),
    ('CONHECIMENTO', 'Instrução / perícia'),
    ('CONHECIMENTO', 'Sentença'),
    ('RECURSAL', 'Recurso interposto'),
    ('RECURSAL', 'Contrarrazões'),
    ('RECURSAL', 'Julgamento de recurso'),
    ('EXECUÇÃO / CUMPRIMENTO', 'Cumprimento de sentença'),
    ('EXECUÇÃO / CUMPRIMENTO', 'Penhora / bens'),
    ('EXECUÇÃO / CUMPRIMENTO', 'Pagamento / acordo'),
    ('ENCERRADO', 'Acordo homologado'),
    ('ENCERRADO', 'Trânsito em julgado'),
    ('ENCERRADO', 'Arquivado'),
]

PAPEIS_PARTE = ('CLIENTE', 'PARTE CONTRÁRIA', 'ADVOGADO CONTRÁRIO', 'TESTEMUNHA', 'INTERESSADO')
STATUS = ('ativo', 'encerrado')
# Papeis que entram no modulo quando o usuario NAO tem recorte proprio (campo modulos).
# Admin entra sempre (sem recorte). Para liberar outro papel, acrescente aqui.
PAPEIS_ACESSO = ('advogado', 'assistente')
CAMPOS_EDITAVEIS = ('numero', 'cliente_id', 'area', 'pasta', 'comarca', 'vara', 'tribunal',
                    'parte_contraria', 'valor_causa', 'responsavel_email', 'observacao')


class ErroProcesso(Exception):
    """Erro de regra. O router converte em HTTPException(status, msg)."""

    def __init__(self, status: int, msg: str):
        super().__init__(msg)
        self.status = status
        self.msg = msg


# ----------------------------------------------------------------- acesso

def _transacional(fn):
    """Escrita que falhou nao deixa nada pendurado na sessao: desfaz e relanca."""
    @functools.wraps(fn)
    async def wrapper(db: AsyncSession, *args, **kwargs):
        try:
            return await fn(db, *args, **kwargs)
        except BaseException:
            # so desfaz se ha mudanca pendente: rollback expira os objetos da sessao
            if db.new or db.dirty or db.deleted:
                await db.rollback()
            raise
    return wrapper


def areas_do_usuario(user: Usuario) -> list[str]:
    return [a.strip() for a in (user.areas_permitidas or '').split(',') if a.strip()]


def pode_acessar(user: Usuario) -> bool:
    """Quem entra no modulo.

    Recorte por pessoa vence o papel (mesma regra de Usuario.pode_modulo): se o
    usuario tem lista em `modulos`, so entra quem tem 'processos' nela.
    """
    if not user or not user.ativo:
        return False
    if (user.modulos or '').strip():
        return user.pode_modulo('processos')
    if user.papel == 'admin':
        return True
    return user.papel in PAPEIS_ACESSO


def ve_processo(user: Usuario, p: ProcProcesso) -> bool:
    """Admin ve tudo. Sem restricao de area, ve tudo. Com restricao, ve o que e da
    area dele ou o que esta sob a responsabilidade dele."""
    if user.papel == 'admin':
        return True
    if p.responsavel_email and p.responsavel_email == user.email:
        return True
    permitidas = areas_do_usuario(user)
    if not permitidas:
        return True
    return bool(p.area) and p.area in permitidas


def pode_mexer(user: Usuario, p: ProcProcesso) -> bool:
    """Quem so ve o que e seu tambem so mexe no que e seu. Processo sem responsavel
    pode ser mexido por quem ve a area dele."""
    if not ve_processo(user, p):
        return False
    return user.papel == 'admin' or p.responsavel_email in ('', user.email)


def _condicao_visibilidade(user: Usuario):
    """A mesma regra de ve_processo, em SQL (para a lista nao carregar tudo)."""
    if user.papel == 'admin':
        return None
    permitidas = areas_do_usuario(user)
    if not permitidas:
        return None
    return or_(ProcProcesso.responsavel_email == user.email, ProcProcesso.area.in_(permitidas))


# ----------------------------------------------------------------- normalizacao

def so_digitos(s) -> str:
    return re.sub(r'\D', '', str(s or ''))


def mascara_cnj(d: str) -> str:
    if len(d) != 20:
        return d
    return f'{d[:7]}-{d[7:9]}.{d[9:13]}.{d[13]}.{d[14:16]}.{d[16:20]}'


def normaliza_numero(texto) -> tuple[str | None, str | None]:
    """(numero_com_mascara, so_digitos) ou (None, None) quando vazio.
    Numero preenchido precisa ter 20 digitos (CNJ)."""
    t = (texto or '').strip()
    if not t:
        return None, None
    d = so_digitos(t)
    if len(d) != 20:
        raise ErroProcesso(400, 'Número CNJ precisa ter 20 dígitos (NNNNNNN-DD.AAAA.J.TR.OOOO). '
                                'Deixe vazio se ainda não há número.')
    return mascara_cnj(d), d


def normaliza_pasta(texto) -> str:
    t = (texto or '').strip()
    return pasta_normalizada(t) if t else ''


def _area_valida(area) -> str:
    a = (area or '').strip()
    if a and a not in AREAS_NEGOCIO:
        raise ErroProcesso(400, f'Área desconhecida: {a}')
    return a


async def _fase_valida(db: AsyncSession, nome) -> str:
    n = (nome or '').strip()
    existe = (await db.execute(select(ProcFase.id).where(ProcFase.nome == n))).scalar_one_or_none()
    if not existe:
        raise ErroProcesso(400, f'Fase desconhecida: {n or "(vazia)"}')
    return n


async def _responsavel_valido(db: AsyncSession, email) -> str:
    e = (email or '').strip().lower()
    if not e:
        return ''
    ok = (await db.execute(select(Usuario.id).where(Usuario.email == e, Usuario.ativo == True))  # noqa: E712
          ).scalar_one_or_none()
    if not ok:
        raise ErroProcesso(400, f'Responsável não encontrado (usuário ativo): {e}')
    return e


def _historico(db, pid, evento, de='', para='', detalhe='', por=''):
    db.add(ProcHistorico(processo_id=pid, evento=evento, de=str(de or ''), para=str(para or ''),
                         detalhe=str(detalhe or ''), por=por or '', em=datetime.utcnow()))


# ----------------------------------------------------------------- achar

async def achar_processo(db: AsyncSession, numero) -> ProcProcesso | None:
    """Acha o processo pelo CNJ, em qualquer formato (com ou sem pontuacao).

    Usado pelo modulo de intimacoes para ligar a intimacao ao processo. Devolve o
    processo mesmo que esteja encerrado: quem decide o que fazer e o chamador.
    """
    d = so_digitos(numero)
    if not d:
        return None
    return (await db.execute(select(ProcProcesso).where(ProcProcesso.numero_limpo == d))
            ).scalar_one_or_none()


async def info_pasta(db: AsyncSession, pasta) -> dict | None:
    """O que o indice da REDE (pz_pastas) sabe sobre a pasta. None se nao achou."""
    alvo = normaliza_pasta(pasta)
    if not alvo:
        return None
    achado = (await db.execute(select(PastaIndice).where(PastaIndice.pasta == alvo))
              ).scalar_one_or_none()
    if not achado:
        return None
    return {'pasta': alvo, 'cliente': achado.cliente or '',
            'processos': json.loads(achado.processos or '[]')}


async def pasta_do_numero(db: AsyncSession, numero) -> dict | None:
    """O inverso de info_pasta: qual pasta da REDE tem este CNJ."""
    d = so_digitos(numero)
    if len(d) != 20:
        return None
    for pi in (await db.execute(select(PastaIndice))).scalars().all():
        if d in (so_digitos(x) for x in json.loads(pi.processos or '[]')):
            return {'pasta': pi.pasta, 'cliente': pi.cliente or '',
                    'processos': json.loads(pi.processos or '[]')}
    return None


# ----------------------------------------------------------------- catalogo de fases

async def garantir_catalogo(db: AsyncSession) -> int:
    """Semeia as fases padrao SO se a tabela estiver vazia (primeira subida).

    Nao recria fase que o admin apagou depois: seed por 'tabela vazia' e de proposito.
    """
    if (await db.execute(select(func.count(ProcFase.id)))).scalar() or 0:
        return 0
    ordem = 0
    for grupo, nome in FASES_PADRAO:
        ordem += 10
        db.add(ProcFase(grupo=grupo, nome=nome, ordem=ordem))
    await db.commit()
    return len(FASES_PADRAO)


async def listar_fases(db: AsyncSession) -> list[dict]:
    fases = (await db.execute(select(ProcFase).order_by(ProcFase.ordem, ProcFase.id))
             ).scalars().all()
    contagem = dict((await db.execute(
        select(ProcProcesso.fase, func.count(ProcProcesso.id))
        .where(ProcProcesso.status == 'ativo').group_by(ProcProcesso.fase))).all())
    return [{'id': f.id, 'grupo': f.grupo, 'nome': f.nome, 'ordem': f.ordem,
             'ativos': int(contagem.get(f.nome, 0))} for f in fases]


@_transacional
async def criar_fase(db: AsyncSession, user: Usuario, grupo: str, nome: str, ordem: int | None) -> ProcFase:
    n = (nome or '').strip()
    if not n:
        raise ErroProcesso(400, 'Informe o nome da fase.')
    if (await db.execute(select(ProcFase.id).where(ProcFase.nome == n))).scalar_one_or_none():
        raise ErroProcesso(409, 'Já existe fase com este nome.')
    if ordem is None:
        ordem = ((await db.execute(select(func.max(ProcFase.ordem)))).scalar() or 0) + 10
    f = ProcFase(grupo=(grupo or '').strip(), nome=n, ordem=int(ordem))
    db.add(f)
    await db.commit()
    await db.refresh(f)
    return f


@_transacional
async def atualizar_fase(db: AsyncSession, fid: int, grupo=None, nome=None, ordem=None) -> ProcFase:
    f = await db.get(ProcFase, fid)
    if not f:
        raise ErroProcesso(404, 'Fase não encontrada.')
    if nome is not None and nome.strip() != f.nome:
        novo = nome.strip()
        if not novo:
            raise ErroProcesso(400, 'Nome vazio.')
        if (await db.execute(select(ProcFase.id).where(ProcFase.nome == novo))).scalar_one_or_none():
            raise ErroProcesso(409, 'Já existe fase com este nome.')
        # renomeia nos processos no mesmo passo: o processo guarda o nome
        antigo = f.nome
        for p in (await db.execute(select(ProcProcesso).where(ProcProcesso.fase == antigo))).scalars().all():
            p.fase = novo
        f.nome = novo
    if grupo is not None:
        f.grupo = grupo.strip()
    if ordem is not None:
        f.ordem = int(ordem)
    await db.commit()
    await db.refresh(f)
    return f


@_transacional
async def apagar_fase(db: AsyncSession, fid: int) -> None:
    f = await db.get(ProcFase, fid)
    if not f:
        raise ErroProcesso(404, 'Fase não encontrada.')
    usada = (await db.execute(select(func.count(ProcProcesso.id)).where(ProcProcesso.fase == f.nome))
             ).scalar() or 0
    if usada:
        raise ErroProcesso(409, f'Esta fase tem {usada} processo(s). Mova-os antes de apagar.')
    await db.delete(f)
    await db.commit()


# ----------------------------------------------------------------- serializacao

async def _nomes_clientes(db: AsyncSession, ids) -> dict:
    ids = [i for i in set(ids) if i]
    if not ids:
        return {}
    rows = (await db.execute(select(ProcCliente.id, ProcCliente.nome).where(ProcCliente.id.in_(ids)))).all()
    return {i: n for i, n in rows}


def _serializa(p: ProcProcesso, cliente_nome: str = '') -> dict:
    dias = (datetime.utcnow() - p.fase_desde).days if p.fase_desde else 0
    return {
        'id': p.id, 'numero': p.numero or '', 'cliente_id': p.cliente_id,
        'cliente_nome': cliente_nome or '', 'area': p.area or '', 'fase': p.fase,
        'fase_desde': p.fase_desde.isoformat() + 'Z' if p.fase_desde else None,
        'dias_na_fase': max(dias, 0),
        'responsavel_email': p.responsavel_email or '', 'pasta': p.pasta or '',
        'comarca': p.comarca or '', 'vara': p.vara or '', 'tribunal': p.tribunal or '',
        'parte_contraria': p.parte_contraria or '', 'valor_causa': p.valor_causa or 0.0,
        'status': p.status, 'conversa_id': p.conversa_id,
        'observacao': p.observacao or '',
        'criado_em': p.criado_em.isoformat() + 'Z' if p.criado_em else None,
        'criado_por': p.criado_por or '',
        'atualizado_em': p.atualizado_em.isoformat() + 'Z' if p.atualizado_em else None,
    }


def _serializa_cliente(c: ProcCliente) -> dict:
    return {'id': c.id, 'nome': c.nome, 'cpf_cnpj': c.cpf_cnpj or '', 'telefone': c.telefone or '',
            'email': c.email or '', 'endereco': c.endereco or '', 'cidade': c.cidade or '',
            'uf': c.uf or '', 'conversa_id': c.conversa_id,
            'criado_em': c.criado_em.isoformat() + 'Z' if c.criado_em else None}


def _serializa_historico(h: ProcHistorico) -> dict:
    return {'id': h.id, 'evento': h.evento, 'de': h.de, 'para': h.para, 'detalhe': h.detalhe,
            'por': h.por, 'em': h.em.isoformat() + 'Z' if h.em else None}


# ----------------------------------------------------------------- consultas

async def listar(db: AsyncSession, user: Usuario, area='', fase='', responsavel='',
                 status='ativo', q='', limite=500) -> list[dict]:
    stmt = select(ProcProcesso)
    cond = _condicao_visibilidade(user)
    if cond is not None:
        stmt = stmt.where(cond)
    if status in STATUS:
        stmt = stmt.where(ProcProcesso.status == status)
    if area:
        stmt = stmt.where(ProcProcesso.area == area)
    if fase:
        stmt = stmt.where(ProcProcesso.fase == fase)
    if responsavel:
        stmt = stmt.where(ProcProcesso.responsavel_email == responsavel.strip().lower())
    termo = (q or '').strip()
    if termo:
        like = f'%{termo}%'
        conds = [ProcProcesso.numero.like(like), ProcProcesso.pasta.like(like),
                 ProcProcesso.parte_contraria.like(like),
                 ProcProcesso.cliente_id.in_(select(ProcCliente.id).where(ProcCliente.nome.like(like)))]
        d = so_digitos(termo)
        if d:
            conds.append(ProcProcesso.numero_limpo.like(f'%{d}%'))
        stmt = stmt.where(or_(*conds))
    stmt = stmt.order_by(ProcProcesso.atualizado_em.desc(), ProcProcesso.id.desc()).limit(min(limite, 1000))
    rows = (await db.execute(stmt)).scalars().all()
    nomes = await _nomes_clientes(db, [p.cliente_id for p in rows])
    return [_serializa(p, nomes.get(p.cliente_id, '')) for p in rows]


async def resumo(db: AsyncSession, user: Usuario) -> dict:
    """Contagem por fase e por area, so dos processos que o usuario ve."""
    rows = await listar(db, user, status='ativo', limite=1000)
    por_fase, por_area = {}, {}
    for r in rows:
        por_fase[r['fase']] = por_fase.get(r['fase'], 0) + 1
        por_area[r['area'] or '(sem área)'] = por_area.get(r['area'] or '(sem área)', 0) + 1
    encerrados = len(await listar(db, user, status='encerrado', limite=1000))
    return {'ativos': len(rows), 'encerrados': encerrados,
            'por_fase': por_fase, 'por_area': por_area}


async def _carregar(db: AsyncSession, user: Usuario, pid: int) -> ProcProcesso:
    p = await db.get(ProcProcesso, pid)
    if not p or not ve_processo(user, p):
        raise ErroProcesso(404, 'Processo não encontrado.')
    return p


async def ficha(db: AsyncSession, user: Usuario, pid: int) -> dict:
    p = await _carregar(db, user, pid)
    cliente = await db.get(ProcCliente, p.cliente_id) if p.cliente_id else None
    partes = (await db.execute(select(ProcParte).where(ProcParte.processo_id == p.id)
                               .order_by(ProcParte.id))).scalars().all()
    hist = (await db.execute(select(ProcHistorico).where(ProcHistorico.processo_id == p.id)
                             .order_by(ProcHistorico.em.desc(), ProcHistorico.id.desc()).limit(200))
            ).scalars().all()
    conversa = None
    if p.conversa_id:
        c = await db.get(Conversa, p.conversa_id)
        if c:
            conversa = {'id': c.id, 'nome': c.contato_nome or '', 'telefone': c.contato_telefone or '',
                        'area': c.tag or '', 'tipo_contato': c.tipo_contato or 'lead'}
    return {
        'processo': _serializa(p, cliente.nome if cliente else ''),
        'cliente': _serializa_cliente(cliente) if cliente else None,
        'partes': [{'id': x.id, 'nome': x.nome, 'papel': x.papel, 'documento': x.documento or ''}
                   for x in partes],
        'historico': [_serializa_historico(h) for h in hist],
        'pasta_indice': await info_pasta(db, p.pasta) if p.pasta else None,
        'conversa': conversa,
        'pode_mexer': pode_mexer(user, p),
    }


async def historico(db: AsyncSession, user: Usuario, pid: int) -> list[dict]:
    await _carregar(db, user, pid)
    hist = (await db.execute(select(ProcHistorico).where(ProcHistorico.processo_id == pid)
                             .order_by(ProcHistorico.em.desc(), ProcHistorico.id.desc()))).scalars().all()
    return [_serializa_historico(h) for h in hist]


async def prazos_do_processo(db: AsyncSession, user: Usuario, pid: int) -> list[dict]:
    """Prazos de pz_prazos ligados a este processo, por CNJ (digitos) ou por pasta.

    So leitura. Quem nao e admin ve so os prazos sem responsavel ou de si mesmo,
    a mesma regra da agenda (routers/prazos.listar).
    """
    p = await _carregar(db, user, pid)
    if not p.numero_limpo and not p.pasta:
        return []
    conds = []
    if p.pasta:
        conds.append(Prazo.pasta == p.pasta)
    if p.numero_limpo:
        conds.append(Prazo.processo != '')
    stmt = select(Prazo).where(Prazo.oculto == False, or_(*conds))  # noqa: E712
    if user.papel != 'admin':
        stmt = stmt.where(Prazo.responsavel.in_(['', user.email]))
    out = []
    for pr in (await db.execute(stmt.order_by(Prazo.data))).scalars().all():
        bate_numero = bool(p.numero_limpo) and so_digitos(pr.processo) == p.numero_limpo
        bate_pasta = bool(p.pasta) and (pr.pasta or '') == p.pasta
        if not (bate_numero or bate_pasta):
            continue
        out.append({'id': pr.id, 'titulo': pr.titulo, 'tipo': pr.tipo,
                    'data': pr.data.isoformat() if pr.data else None,
                    'hora': pr.hora or '', 'fatal': bool(pr.fatal), 'concluido': bool(pr.concluido),
                    'responsavel': pr.responsavel or '', 'processo': pr.processo or '',
                    'pasta': pr.pasta or ''})
    return out


# ----------------------------------------------------------------- clientes

async def _cliente_por_nome(db: AsyncSession, nome: str) -> ProcCliente | None:
    return (await db.execute(select(ProcCliente).where(
        func.lower(ProcCliente.nome) == nome.strip().lower()).order_by(ProcCliente.id))
    ).scalars().first()


def _documento_valido(doc) -> str:
    d = so_digitos(doc)
    if not d:
        return ''
    if len(d) not in (11, 14):
        raise ErroProcesso(400, 'CPF precisa ter 11 dígitos e CNPJ, 14. Deixe vazio se não souber.')
    return (doc or '').strip()


async def listar_clientes(db: AsyncSession, user: Usuario, q='', limite=300) -> list[dict]:
    stmt = select(ProcCliente)
    termo = (q or '').strip()
    if termo:
        like = f'%{termo}%'
        conds = [ProcCliente.nome.like(like), ProcCliente.telefone.like(like),
                 ProcCliente.email.like(like)]
        d = so_digitos(termo)
        if d:
            conds.append(ProcCliente.cpf_cnpj.like(f'%{d}%'))
        stmt = stmt.where(or_(*conds))
    rows = (await db.execute(stmt.order_by(ProcCliente.nome).limit(min(limite, 1000)))).scalars().all()
    return [_serializa_cliente(c) for c in rows]


@_transacional
async def criar_cliente(db: AsyncSession, user: Usuario, dados: dict) -> ProcCliente:
    nome = (dados.get('nome') or '').strip()
    if not nome:
        raise ErroProcesso(400, 'Informe o nome do cliente.')
    c = ProcCliente(nome=nome[:200], cpf_cnpj=_documento_valido(dados.get('cpf_cnpj')),
                    telefone=(dados.get('telefone') or '').strip()[:30],
                    email=(dados.get('email') or '').strip().lower()[:200],
                    endereco=(dados.get('endereco') or '').strip()[:300],
                    cidade=(dados.get('cidade') or '').strip()[:120],
                    uf=(dados.get('uf') or '').strip().upper()[:2],
                    conversa_id=dados.get('conversa_id') or None,
                    criado_em=datetime.utcnow(), criado_por=user.email)
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


@_transacional
async def atualizar_cliente(db: AsyncSession, user: Usuario, cid: int, dados: dict) -> ProcCliente:
    c = await db.get(ProcCliente, cid)
    if not c:
        raise ErroProcesso(404, 'Cliente não encontrado.')
    if 'nome' in dados:
        if not (dados['nome'] or '').strip():
            raise ErroProcesso(400, 'Nome não pode ficar vazio.')
        c.nome = dados['nome'].strip()[:200]
    if 'cpf_cnpj' in dados:
        c.cpf_cnpj = _documento_valido(dados['cpf_cnpj'])
    for campo, tam in (('telefone', 30), ('endereco', 300), ('cidade', 120)):
        if campo in dados:
            setattr(c, campo, (dados[campo] or '').strip()[:tam])
    if 'email' in dados:
        c.email = (dados['email'] or '').strip().lower()[:200]
    if 'uf' in dados:
        c.uf = (dados['uf'] or '').strip().upper()[:2]
    await db.commit()
    await db.refresh(c)
    return c


async def ficha_cliente(db: AsyncSession, user: Usuario, cid: int) -> dict:
    c = await db.get(ProcCliente, cid)
    if not c:
        raise ErroProcesso(404, 'Cliente não encontrado.')
    procs = (await db.execute(select(ProcProcesso).where(ProcProcesso.cliente_id == cid)
                              .order_by(ProcProcesso.status, ProcProcesso.id.desc()))).scalars().all()
    visiveis = [_serializa(p, c.nome) for p in procs if ve_processo(user, p)]
    return {'cliente': _serializa_cliente(c), 'processos': visiveis}


async def _cliente_da_conversa(db: AsyncSession, conv: Conversa) -> ProcCliente:
    """Um cliente por conversa: reaproveita o que ja existe, senao cria com os dados do CRM."""
    existente = (await db.execute(select(ProcCliente).where(ProcCliente.conversa_id == conv.id)
                                  .order_by(ProcCliente.id))).scalars().first()
    if existente:
        return existente
    c = ProcCliente(nome=(conv.contato_nome or conv.contato_telefone or 'Cliente sem nome')[:200],
                    telefone=(conv.contato_telefone or '')[:30], email=(conv.email or '')[:200],
                    conversa_id=conv.id, criado_em=datetime.utcnow(), criado_por='crm')
    return c


async def _resolver_cliente_id(db: AsyncSession, user: Usuario, dados: dict) -> int | None:
    if dados.get('cliente_id'):
        c = await db.get(ProcCliente, int(dados['cliente_id']))
        if not c:
            raise ErroProcesso(400, 'Cliente não encontrado.')
        return c.id
    nome = (dados.get('cliente_nome') or '').strip()
    if not nome:
        return None
    c = await _cliente_por_nome(db, nome)
    if c is None:
        c = ProcCliente(nome=nome[:200], criado_em=datetime.utcnow(), criado_por=user.email)
        db.add(c)
        await db.flush()
    return c.id


# ----------------------------------------------------------------- escrita

async def _numero_livre(db: AsyncSession, digitos: str, ignorar_id: int | None = None):
    if not digitos:
        return
    q = select(ProcProcesso.id).where(ProcProcesso.numero_limpo == digitos)
    if ignorar_id:
        q = q.where(ProcProcesso.id != ignorar_id)
    existente = (await db.execute(q)).scalar_one_or_none()
    if existente:
        raise ErroProcesso(409, f'Já existe processo com este número (id {existente}).')


async def _inserir(db: AsyncSession, user: Usuario, dados: dict) -> ProcProcesso:
    """Monta e adiciona o processo na sessao, sem commit (quem chama decide).

    Todas as validacoes rodam ANTES de qualquer db.add, para um erro nao deixar
    cliente ou processo pela metade na sessao."""
    numero, digitos = normaliza_numero(dados.get('numero'))
    pasta = normaliza_pasta(dados.get('pasta'))
    # pasta preenche processo: se nao veio numero e a pasta tem UM processo no indice
    if not digitos and pasta:
        info = await info_pasta(db, pasta)
        if info and len(info['processos']) == 1:
            numero, digitos = normaliza_numero(info['processos'][0])
    await _numero_livre(db, digitos)
    agora = datetime.utcnow()
    fase = await _fase_valida(db, dados.get('fase') or FASE_PADRAO)
    area = _area_valida(dados.get('area'))
    responsavel = await _responsavel_valido(db, dados.get('responsavel_email'))
    cliente_id = await _resolver_cliente_id(db, user, dados)   # unico ponto que pode adicionar
    p = ProcProcesso(
        numero=numero, numero_limpo=digitos,
        cliente_id=cliente_id,
        area=area, fase=fase, fase_desde=agora,
        responsavel_email=responsavel,
        pasta=pasta, comarca=(dados.get('comarca') or '').strip()[:120],
        vara=(dados.get('vara') or '').strip()[:120], tribunal=(dados.get('tribunal') or '').strip()[:60],
        parte_contraria=(dados.get('parte_contraria') or '').strip()[:200],
        valor_causa=float(dados.get('valor_causa') or 0.0), status='ativo',
        criado_em=agora, criado_por=dados.get('criado_por') or user.email, atualizado_em=agora,
        conversa_id=dados.get('conversa_id') or None,
        observacao=(dados.get('observacao') or '').strip(),
    )
    db.add(p)
    await db.flush()
    _historico(db, p.id, 'criado', '', fase, numero or 'sem número', dados.get('criado_por') or user.email)
    return p


async def _commit_seguro(db: AsyncSession):
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ErroProcesso(409, 'Conflito: número de processo ou cadastro já existe.')


@_transacional
async def criar(db: AsyncSession, user: Usuario, dados: dict) -> ProcProcesso:
    p = await _inserir(db, user, dados)
    await _commit_seguro(db)
    await db.refresh(p)
    return p


@_transacional
async def atualizar(db: AsyncSession, user: Usuario, pid: int, dados: dict) -> ProcProcesso:
    p = await _carregar(db, user, pid)
    if not pode_mexer(user, p):
        raise ErroProcesso(403, 'Este processo está com outro responsável.')
    alterados = []
    if 'numero' in dados:
        numero, digitos = normaliza_numero(dados['numero'])
        if digitos != p.numero_limpo:
            await _numero_livre(db, digitos, ignorar_id=p.id)
            alterados.append(('numero', p.numero or '', numero or ''))
            p.numero, p.numero_limpo = numero, digitos
    if 'cliente_id' in dados or 'cliente_nome' in dados:
        novo = await _resolver_cliente_id(db, user, dados)
        if novo != p.cliente_id:
            alterados.append(('cliente', p.cliente_id or '', novo or ''))
            p.cliente_id = novo
    if 'area' in dados:
        nova = _area_valida(dados['area'])
        if nova != p.area:
            alterados.append(('area', p.area, nova))
            p.area = nova
    if 'pasta' in dados:
        nova = normaliza_pasta(dados['pasta'])
        if nova != p.pasta:
            alterados.append(('pasta', p.pasta, nova))
            p.pasta = nova
    if 'responsavel_email' in dados:
        novo = await _responsavel_valido(db, dados['responsavel_email'])
        if novo != p.responsavel_email:
            alterados.append(('responsável', p.responsavel_email, novo))
            p.responsavel_email = novo
    for campo, rotulo, tam in (('comarca', 'comarca', 120), ('vara', 'vara', 120),
                               ('tribunal', 'tribunal', 60), ('parte_contraria', 'parte contrária', 200),
                               ('observacao', 'observação', 5000)):
        if campo in dados:
            novo = (dados[campo] or '').strip()[:tam]
            if novo != (getattr(p, campo) or ''):
                alterados.append((rotulo, getattr(p, campo) or '', novo))
                setattr(p, campo, novo)
    if 'valor_causa' in dados:
        novo = float(dados['valor_causa'] or 0.0)
        if novo != (p.valor_causa or 0.0):
            alterados.append(('valor da causa', str(p.valor_causa or 0.0), str(novo)))
            p.valor_causa = novo
    if alterados:
        p.atualizado_em = datetime.utcnow()
        _historico(db, p.id, 'editado', '', '', 'campos: ' + ', '.join(r for r, _de, _para in alterados),
                   user.email)
    await _commit_seguro(db)
    await db.refresh(p)
    return p


@_transacional
async def mover_fase(db: AsyncSession, user: Usuario, pid: int, nova: str) -> ProcProcesso:
    p = await _carregar(db, user, pid)
    if not pode_mexer(user, p):
        raise ErroProcesso(403, 'Este processo está com outro responsável.')
    nova = await _fase_valida(db, nova)
    if nova == p.fase:
        return p
    de = p.fase
    p.fase = nova
    p.fase_desde = datetime.utcnow()
    p.atualizado_em = p.fase_desde
    _historico(db, p.id, 'fase', de, nova, '', user.email)
    await db.commit()
    await db.refresh(p)
    return p


@_transacional
async def _mudar_status(db: AsyncSession, user: Usuario, pid: int, novo: str, motivo: str = ''):
    p = await _carregar(db, user, pid)
    if not pode_mexer(user, p):
        raise ErroProcesso(403, 'Este processo está com outro responsável.')
    if p.status == novo:
        raise ErroProcesso(409, 'O processo já está ' + ('encerrado.' if novo == 'encerrado' else 'ativo.'))
    anterior = p.status
    p.status = novo
    p.atualizado_em = datetime.utcnow()
    _historico(db, p.id, 'encerrado' if novo == 'encerrado' else 'reaberto',
               anterior, novo, (motivo or '').strip(), user.email)
    await db.commit()
    await db.refresh(p)
    return p


async def encerrar(db: AsyncSession, user: Usuario, pid: int, motivo: str = ''):
    return await _mudar_status(db, user, pid, 'encerrado', motivo)


async def reabrir(db: AsyncSession, user: Usuario, pid: int):
    return await _mudar_status(db, user, pid, 'ativo')


@_transacional
async def adicionar_parte(db: AsyncSession, user: Usuario, pid: int, dados: dict) -> ProcParte:
    p = await _carregar(db, user, pid)
    if not pode_mexer(user, p):
        raise ErroProcesso(403, 'Este processo está com outro responsável.')
    nome = (dados.get('nome') or '').strip()
    papel = (dados.get('papel') or '').strip().upper()
    if not nome:
        raise ErroProcesso(400, 'Informe o nome da parte.')
    if papel not in PAPEIS_PARTE:
        raise ErroProcesso(400, f'Papel inválido. Use: {", ".join(PAPEIS_PARTE)}')
    parte = ProcParte(processo_id=p.id, nome=nome[:200], papel=papel,
                      documento=_documento_valido(dados.get('documento')))
    db.add(parte)
    await db.flush()
    _historico(db, p.id, 'parte+', '', f'{papel}: {nome}', '', user.email)
    p.atualizado_em = datetime.utcnow()
    await db.commit()
    await db.refresh(parte)
    return parte


@_transacional
async def remover_parte(db: AsyncSession, user: Usuario, pid: int, parte_id: int) -> None:
    p = await _carregar(db, user, pid)
    if not pode_mexer(user, p):
        raise ErroProcesso(403, 'Este processo está com outro responsável.')
    parte = await db.get(ProcParte, parte_id)
    if not parte or parte.processo_id != p.id:
        raise ErroProcesso(404, 'Parte não encontrada.')
    _historico(db, p.id, 'parte-', f'{parte.papel}: {parte.nome}', '', '', user.email)
    await db.execute(delete(ProcParte).where(ProcParte.id == parte_id))
    p.atualizado_em = datetime.utcnow()
    await db.commit()


# ----------------------------------------------------------------- CRM

def elegibilidade_conversa(conv: Conversa) -> tuple[bool, str]:
    """Um card so vira processo quando o contato ja e cliente (contrato fechado).

    tipo_contato='cliente' e a marca que o CRM ja usa (botao "Fechei com o cliente"
    e a passagem para o quadro de clientes)."""
    if (conv.tipo_contato or '') != 'cliente':
        return False, 'Só vira processo quem já é cliente (contrato fechado). Este contato ainda é lead.'
    return True, ''


async def previa_conversa(db: AsyncSession, user: Usuario, conv: Conversa) -> dict:
    ok, motivo = elegibilidade_conversa(conv)
    existente = (await db.execute(select(ProcProcesso.id).where(
        ProcProcesso.conversa_id == conv.id, ProcProcesso.status == 'ativo').order_by(ProcProcesso.id))
    ).scalars().first()
    if existente and not motivo:
        motivo = f'Este cliente já tem processo ativo (id {existente}).'
        ok = False
    return {
        'elegivel': ok, 'motivo': motivo, 'processo_existente': existente,
        'sugestao': {
            'cliente_nome': conv.contato_nome or '', 'telefone': conv.contato_telefone or '',
            'email': conv.email or '',
            'area': conv.tag if conv.tag in AREAS_NEGOCIO else '',
            'responsavel_email': conv.atendente_email or user.email,
            'fechado_em': conv.fechado_em.isoformat() + 'Z' if conv.fechado_em else None,
        },
    }


@_transacional
async def criar_de_conversa(db: AsyncSession, user: Usuario, conv: Conversa, dados: dict) -> ProcProcesso:
    previa = await previa_conversa(db, user, conv)
    if not previa['elegivel']:
        raise ErroProcesso(409, previa['motivo'])
    cliente = await _cliente_da_conversa(db, conv)
    if cliente.id is None:
        db.add(cliente)
        await db.flush()
    sug = previa['sugestao']
    dados = dict(dados)
    dados['cliente_id'] = cliente.id
    dados['conversa_id'] = conv.id
    dados['area'] = dados.get('area') or sug['area']
    dados['responsavel_email'] = dados.get('responsavel_email') or sug['responsavel_email']
    p = await _inserir(db, user, dados)
    # o CRM ganha o processo e a pasta na ficha, mas so onde estiver vazio
    if p.numero and not (conv.processo or '').strip():
        conv.processo = p.numero
    if p.pasta and not (conv.pasta or '').strip():
        conv.pasta = p.pasta
    await _commit_seguro(db)
    await db.refresh(p)
    return p


# ----------------------------------------------------------------- carga inicial

async def planejar_carga(db: AsyncSession, incluir_sem_processo: bool = False) -> dict:
    """Le pz_prazos e pz_pastas (so leitura) e diz o que a carga criaria. Nao grava.

    Um processo por CNJ distinto. Prazo sem CNJ vira processo pela pasta. Pasta sem
    CNJ so entra com incluir_sem_processo (sao centenas de pastas sem numero).
    """
    alvo = {}   # chave -> {numero, digitos, pasta, cliente, responsaveis:set, fontes:set}

    def _entra(chave, numero, digitos, pasta, cliente, responsavel, fonte):
        it = alvo.setdefault(chave, {'numero': numero, 'digitos': digitos, 'pasta': '', 'cliente': '',
                                     'responsaveis': set(), 'fontes': set()})
        it['numero'] = it['numero'] or numero
        it['digitos'] = it['digitos'] or digitos
        it['pasta'] = it['pasta'] or pasta
        it['cliente'] = it['cliente'] or cliente
        if responsavel:
            it['responsaveis'].add(responsavel.strip().lower())
        it['fontes'].add(fonte)

    for pi in (await db.execute(select(PastaIndice))).scalars().all():
        cnjs = [so_digitos(x) for x in json.loads(pi.processos or '[]')]
        cnjs = [d for d in cnjs if len(d) == 20]
        if not cnjs and incluir_sem_processo:
            _entra(('pasta', pi.pasta), None, None, pi.pasta, (pi.cliente or '').strip(), '', 'rede')
        for d in cnjs:
            _entra(d, mascara_cnj(d), d, pi.pasta, (pi.cliente or '').strip(), '', 'rede')

    for pr in (await db.execute(select(Prazo).where(Prazo.oculto == False))  # noqa: E712
               ).scalars().all():
        d = so_digitos(pr.processo)
        pasta = normaliza_pasta(pr.pasta)
        if len(d) == 20:
            _entra(d, mascara_cnj(d), d, pasta, (pr.cliente or '').strip(), pr.responsavel, 'prazos')
        elif pasta:
            _entra(('pasta', pasta), None, None, pasta, (pr.cliente or '').strip(), pr.responsavel, 'prazos')

    # pasta sem CNJ some quando algum processo com CNJ ja usa a mesma pasta
    com_cnj_nas_pastas = {it['pasta'] for k, it in alvo.items() if not isinstance(k, tuple) and it['pasta']}
    for k in [k for k in alvo if isinstance(k, tuple) and alvo[k]['pasta'] in com_cnj_nas_pastas]:
        del alvo[k]

    existentes_cnj = set((await db.execute(select(ProcProcesso.numero_limpo).where(
        ProcProcesso.numero_limpo.isnot(None)))).scalars().all())
    existentes_pasta = set((await db.execute(select(ProcProcesso.pasta).where(
        ProcProcesso.numero_limpo.is_(None), ProcProcesso.pasta != ''))).scalars().all())
    usuarios = set((await db.execute(select(Usuario.email).where(Usuario.ativo == True))  # noqa: E712
                    ).scalars().all())

    novos, ja_existem = [], 0
    for k, it in alvo.items():
        if (not isinstance(k, tuple) and k in existentes_cnj) or \
           (isinstance(k, tuple) and it['pasta'] in existentes_pasta):
            ja_existem += 1
            continue
        resp = list(it['responsaveis'])
        novos.append({
            'numero': it['numero'], 'digitos': it['digitos'], 'pasta': it['pasta'],
            'cliente': it['cliente'],
            # so vira responsavel quando ha UM responsavel nos prazos e ele e usuario ativo
            'responsavel_email': resp[0] if len(resp) == 1 and resp[0] in usuarios else '',
            'fontes': sorted(it['fontes']),
        })
    novos.sort(key=lambda x: (x['pasta'] or '', x['numero'] or ''))
    nomes_clientes = set((await db.execute(select(ProcCliente.nome))).scalars().all())
    nomes_novos = {x['cliente'] for x in novos if x['cliente']}
    return {'novos': novos, 'ja_existem': ja_existem,
            'com_numero': sum(1 for x in novos if x['numero']),
            'sem_numero': sum(1 for x in novos if not x['numero']),
            'clientes_novos': len(nomes_novos - nomes_clientes)}


@_transacional
async def aplicar_carga(db: AsyncSession, plano: dict, por: str = 'carga-inicial') -> dict:
    """Grava o plano de planejar_carga. Nunca apaga nada. Pode rodar de novo sem duplicar."""
    criados_proc, criados_cli = 0, 0
    for item in plano['novos']:
        cliente_id = None
        if item['cliente']:
            c = await _cliente_por_nome(db, item['cliente'])
            if c is None:
                c = ProcCliente(nome=item['cliente'][:200], criado_em=datetime.utcnow(), criado_por=por)
                db.add(c)
                await db.flush()
                criados_cli += 1
            cliente_id = c.id
        agora = datetime.utcnow()
        p = ProcProcesso(numero=item['numero'], numero_limpo=item['digitos'], cliente_id=cliente_id,
                         area='', fase=FASE_PADRAO, fase_desde=agora,
                         responsavel_email=item['responsavel_email'], pasta=item['pasta'], status='ativo',
                         criado_em=agora, criado_por=por, atualizado_em=agora)
        db.add(p)
        await db.flush()
        _historico(db, p.id, 'criado', '', FASE_PADRAO,
                   'carga inicial a partir de ' + ' e '.join(item['fontes']), por)
        criados_proc += 1
    await _commit_seguro(db)
    return {'processos_criados': criados_proc, 'clientes_criados': criados_cli}
