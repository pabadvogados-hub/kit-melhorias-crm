"""Router do modulo Processos: /api/processos.

Destino: backend/app/routers/processos.py

Regras de acesso ficam em processos_nucleo (pode_acessar, ve_processo, pode_mexer).
Este arquivo so traduz: dependencia de login, erro de regra -> HTTP e a rota.

Ordem importa: as rotas de uma palavra (/fases, /resumo, /clientes...) ficam ANTES
de /{pid:int}, e o id e tipado para nao engolir essas palavras.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import Usuario, get_db
from ..deps import usuario_atual
from .. import processos_nucleo as nuc
from ..processos_nucleo import ErroProcesso
from ..whatsapp.models import Conversa
from .atendimento import _pode_ver_conversa, _quadro_clientes_id

router = APIRouter(prefix='/api/processos', tags=['processos'])


# ----------------------------------------------------------------- dependencias

async def usuario_processos(user: Usuario = Depends(usuario_atual)) -> Usuario:
    if not nuc.pode_acessar(user):
        raise HTTPException(403, 'Sem acesso ao módulo Processos.')
    return user


async def admin_processos(user: Usuario = Depends(usuario_processos)) -> Usuario:
    if user.papel != 'admin':
        raise HTTPException(403, 'Ação restrita ao administrador.')
    return user


async def _roda(coro):
    """Executa uma chamada do nucleo e troca ErroProcesso por HTTP."""
    try:
        return await coro
    except ErroProcesso as e:
        raise HTTPException(e.status, e.msg)


async def _conversa_visivel(db: AsyncSession, user: Usuario, conversa_id: int) -> Conversa:
    conv = await db.get(Conversa, conversa_id)
    if not conv:
        raise HTTPException(404, 'Conversa não encontrada.')
    # a mesma regra do CRM: quem nao ve a conversa la, nao cria processo a partir dela
    if not _pode_ver_conversa(conv, user, await _quadro_clientes_id(db)):
        raise HTTPException(403, 'Esta conversa não é de uma área sua.')
    return conv


# ----------------------------------------------------------------- modelos de entrada

class ProcessoIn(BaseModel):
    numero: str = ''
    cliente_id: int | None = None
    cliente_nome: str = ''
    area: str = ''
    fase: str = ''
    pasta: str = ''
    comarca: str = ''
    vara: str = ''
    tribunal: str = ''
    parte_contraria: str = ''
    valor_causa: float = 0.0
    # None = quem cria; '' = sem responsavel
    responsavel_email: str | None = None
    observacao: str = ''


class ProcessoPatch(BaseModel):
    numero: str | None = None
    cliente_id: int | None = None
    cliente_nome: str | None = None
    area: str | None = None
    pasta: str | None = None
    comarca: str | None = None
    vara: str | None = None
    tribunal: str | None = None
    parte_contraria: str | None = None
    valor_causa: float | None = None
    responsavel_email: str | None = None
    observacao: str | None = None


class MoverIn(BaseModel):
    fase: str


class EncerrarIn(BaseModel):
    motivo: str = ''


class ParteIn(BaseModel):
    nome: str
    papel: str
    documento: str = ''


class FaseIn(BaseModel):
    grupo: str = ''
    nome: str = ''
    ordem: int | None = None


class ClienteIn(BaseModel):
    nome: str = ''
    cpf_cnpj: str = ''
    telefone: str = ''
    email: str = ''
    endereco: str = ''
    cidade: str = ''
    uf: str = ''


class ClientePatch(BaseModel):
    nome: str | None = None
    cpf_cnpj: str | None = None
    telefone: str | None = None
    email: str | None = None
    endereco: str | None = None
    cidade: str | None = None
    uf: str | None = None


# ----------------------------------------------------------------- rotas de uma palavra

@router.get('/fases')
async def fases(user: Usuario = Depends(usuario_processos), db: AsyncSession = Depends(get_db)):
    return {'items': await nuc.listar_fases(db)}


@router.post('/fases')
async def criar_fase(req: FaseIn, user: Usuario = Depends(admin_processos), db: AsyncSession = Depends(get_db)):
    f = await _roda(nuc.criar_fase(db, user, req.grupo, req.nome, req.ordem))
    return {'id': f.id, 'nome': f.nome, 'grupo': f.grupo, 'ordem': f.ordem}


@router.patch('/fases/{fid}')
async def editar_fase(fid: int, req: FaseIn, user: Usuario = Depends(admin_processos),
                      db: AsyncSession = Depends(get_db)):
    dados = req.model_dump(exclude_unset=True)
    f = await _roda(nuc.atualizar_fase(db, fid, grupo=dados.get('grupo'), nome=dados.get('nome'),
                                       ordem=dados.get('ordem')))
    return {'id': f.id, 'nome': f.nome, 'grupo': f.grupo, 'ordem': f.ordem}


@router.delete('/fases/{fid}')
async def apagar_fase(fid: int, user: Usuario = Depends(admin_processos), db: AsyncSession = Depends(get_db)):
    await _roda(nuc.apagar_fase(db, fid))
    return {'ok': True}


@router.get('')
async def listar(area: str = '', fase: str = '', responsavel: str = '', status: str = 'ativo',
                 q: str = '', limite: int = Query(500, ge=1, le=1000),
                 user: Usuario = Depends(usuario_processos), db: AsyncSession = Depends(get_db)):
    items = await nuc.listar(db, user, area=area, fase=fase, responsavel=responsavel,
                             status=status, q=q, limite=limite)
    return {'items': items, 'total': len(items)}


@router.get('/resumo')
async def resumo(user: Usuario = Depends(usuario_processos), db: AsyncSession = Depends(get_db)):
    return await nuc.resumo(db, user)


@router.get('/responsaveis')
async def responsaveis(user: Usuario = Depends(usuario_processos), db: AsyncSession = Depends(get_db)):
    """Quem pode ser responsavel por um processo: usuarios ativos (nome e e-mail)."""
    rows = (await db.execute(select(Usuario.email, Usuario.nome).where(Usuario.ativo == True)  # noqa: E712
                             .order_by(Usuario.nome))).all()
    return {'items': [{'email': e, 'nome': n} for e, n in rows]}


@router.get('/pasta')
async def pasta(pasta: str = Query(...), user: Usuario = Depends(usuario_processos),
                db: AsyncSession = Depends(get_db)):
    """Pasta da REDE -> cliente e processo(s), para preencher o formulario."""
    info = await nuc.info_pasta(db, pasta)
    return info or {'pasta': '', 'cliente': '', 'processos': []}


@router.get('/por-numero')
async def por_numero(numero: str = Query(...), user: Usuario = Depends(usuario_processos),
                     db: AsyncSession = Depends(get_db)):
    """CNJ -> pasta da REDE (o inverso de /pasta)."""
    info = await nuc.pasta_do_numero(db, numero)
    return info or {'pasta': '', 'cliente': '', 'processos': []}


@router.post('')
async def criar(req: ProcessoIn, user: Usuario = Depends(usuario_processos), db: AsyncSession = Depends(get_db)):
    dados = req.model_dump()
    if dados['responsavel_email'] is None:
        dados['responsavel_email'] = user.email
    p = await _roda(nuc.criar(db, user, dados))
    return await _roda(nuc.ficha(db, user, p.id))


@router.get('/clientes')
async def clientes(q: str = '', user: Usuario = Depends(usuario_processos), db: AsyncSession = Depends(get_db)):
    return {'items': await nuc.listar_clientes(db, user, q=q)}


@router.post('/clientes')
async def criar_cliente(req: ClienteIn, user: Usuario = Depends(usuario_processos),
                        db: AsyncSession = Depends(get_db)):
    c = await _roda(nuc.criar_cliente(db, user, req.model_dump()))
    return {'id': c.id, 'nome': c.nome}


@router.get('/clientes/{cid}')
async def cliente(cid: int, user: Usuario = Depends(usuario_processos), db: AsyncSession = Depends(get_db)):
    return await _roda(nuc.ficha_cliente(db, user, cid))


@router.patch('/clientes/{cid}')
async def editar_cliente(cid: int, req: ClientePatch, user: Usuario = Depends(usuario_processos),
                         db: AsyncSession = Depends(get_db)):
    await _roda(nuc.atualizar_cliente(db, user, cid, req.model_dump(exclude_unset=True)))
    return await _roda(nuc.ficha_cliente(db, user, cid))


@router.get('/conversa/{conversa_id}/elegivel')
async def elegivel(conversa_id: int, user: Usuario = Depends(usuario_processos),
                   db: AsyncSession = Depends(get_db)):
    """Antes do formulario: o card do CRM pode virar processo? Traz a sugestao preenchida."""
    conv = await _conversa_visivel(db, user, conversa_id)
    return await nuc.previa_conversa(db, user, conv)


@router.post('/conversa/{conversa_id}')
async def criar_de_conversa(conversa_id: int, req: ProcessoIn, user: Usuario = Depends(usuario_processos),
                            db: AsyncSession = Depends(get_db)):
    conv = await _conversa_visivel(db, user, conversa_id)
    p = await _roda(nuc.criar_de_conversa(db, user, conv, req.model_dump()))
    return await _roda(nuc.ficha(db, user, p.id))


# ----------------------------------------------------------------- por id (depois das rotas de uma palavra)

@router.get('/{pid:int}')
async def ficha(pid: int, user: Usuario = Depends(usuario_processos), db: AsyncSession = Depends(get_db)):
    return await _roda(nuc.ficha(db, user, pid))


@router.patch('/{pid:int}')
async def editar(pid: int, req: ProcessoPatch, user: Usuario = Depends(usuario_processos),
                 db: AsyncSession = Depends(get_db)):
    await _roda(nuc.atualizar(db, user, pid, req.model_dump(exclude_unset=True)))
    return await _roda(nuc.ficha(db, user, pid))


@router.post('/{pid:int}/mover')
async def mover(pid: int, req: MoverIn, user: Usuario = Depends(usuario_processos),
                db: AsyncSession = Depends(get_db)):
    await _roda(nuc.mover_fase(db, user, pid, req.fase))
    return await _roda(nuc.ficha(db, user, pid))


@router.post('/{pid:int}/encerrar')
async def encerrar(pid: int, req: EncerrarIn, user: Usuario = Depends(usuario_processos),
                   db: AsyncSession = Depends(get_db)):
    await _roda(nuc.encerrar(db, user, pid, req.motivo))
    return await _roda(nuc.ficha(db, user, pid))


@router.post('/{pid:int}/reabrir')
async def reabrir(pid: int, user: Usuario = Depends(usuario_processos), db: AsyncSession = Depends(get_db)):
    await _roda(nuc.reabrir(db, user, pid))
    return await _roda(nuc.ficha(db, user, pid))


@router.post('/{pid:int}/partes')
async def incluir_parte(pid: int, req: ParteIn, user: Usuario = Depends(usuario_processos),
                        db: AsyncSession = Depends(get_db)):
    await _roda(nuc.adicionar_parte(db, user, pid, req.model_dump()))
    return await _roda(nuc.ficha(db, user, pid))


@router.delete('/{pid:int}/partes/{parte_id}')
async def excluir_parte(pid: int, parte_id: int, user: Usuario = Depends(usuario_processos),
                        db: AsyncSession = Depends(get_db)):
    await _roda(nuc.remover_parte(db, user, pid, parte_id))
    return await _roda(nuc.ficha(db, user, pid))


@router.get('/{pid:int}/historico')
async def historico(pid: int, user: Usuario = Depends(usuario_processos), db: AsyncSession = Depends(get_db)):
    return {'items': await _roda(nuc.historico(db, user, pid))}


@router.get('/{pid:int}/prazos')
async def prazos(pid: int, user: Usuario = Depends(usuario_processos), db: AsyncSession = Depends(get_db)):
    """So leitura: os prazos continuam sendo editados no Calendario."""
    return {'items': await _roda(nuc.prazos_do_processo(db, user, pid))}
