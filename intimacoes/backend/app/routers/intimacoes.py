"""API do modulo de intimacoes: /api/intimacoes

Quem trata (ver, conferir, descartar): administrador e advogado(a), igual ao Calendario.
So administrador: capturar agora, gerenciar OABs, ver o log das capturas.
"""
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import AsyncSessionLocal, Usuario, get_db
from ..deps import usuario_atual
from ..intimacoes import captura, schema, servico
from ..intimacoes.djen import FonteDJEN
from ..intimacoes.servico import ErroIntimacao

router = APIRouter(prefix='/api/intimacoes', tags=['intimacoes'])


def _tratar(u: Usuario):
    if u.papel not in ('admin', 'advogado'):
        raise HTTPException(403, 'Intimações são tratadas por advogados e administradores.')


def _admin(u: Usuario):
    if u.papel != 'admin':
        raise HTTPException(403, 'Ação restrita a administradores.')


def _erro(e: ErroIntimacao):
    raise HTTPException(e.status, e.msg)


class ItemConferir(BaseModel):
    tipo: str = 'prazo'                 # prazo | audiencia | providencia | tarefa | reuniao | outro
    titulo: str
    responsavel: str = ''               # e-mail de um usuario ativo, ou vazio
    data: str                           # AAAA-MM-DD: data fatal (prazo) ou data do ato
    hora: str = ''                      # so para audiencia/reuniao, ex.: 14:30
    fatal: bool = False
    prazo_dias: int | None = None
    pasta: str = ''
    processo: str = ''
    cliente: str = ''
    observacao: str = ''
    sugerido: bool = False              # veio da sugestao do classificador


class ConferirIn(BaseModel):
    itens: list[ItemConferir]


class DescartarIn(BaseModel):
    motivo: str


class OabIn(BaseModel):
    oab: str
    rotulo: str = ''


async def _executar_captura(dias: int, por: str):
    """Roda em segundo plano, com sessao propria (a da requisicao ja foi fechada)."""
    extras = [getattr(settings, 'INT_OABS', '')]
    async with AsyncSessionLocal() as db:
        await schema.garantir_tabelas(db)
        await captura.rodar(db, fonte=FonteDJEN(), dias=dias, extras=extras,
                            origem='manual', por=por)


@router.get('/contagem')
async def contar(user: Usuario = Depends(usuario_atual), db: AsyncSession = Depends(get_db)):
    _tratar(user)
    return await servico.contagem(db)


@router.get('/responsaveis')
async def pessoas(user: Usuario = Depends(usuario_atual), db: AsyncSession = Depends(get_db)):
    _tratar(user)
    return await servico.responsaveis(db)


@router.get('')
async def listar(status: str = Query('nova'), oab: str = '', tribunal: str = '',
                 de: date | None = None, ate: date | None = None, q: str = '',
                 pagina: int = 1, por_pagina: int = 30,
                 user: Usuario = Depends(usuario_atual), db: AsyncSession = Depends(get_db)):
    _tratar(user)
    return await servico.listar(db, status=status, oab=oab or None, tribunal=tribunal or None,
                                de=de, ate=ate, q=q, pagina=pagina, por_pagina=por_pagina)


@router.get('/capturas')
async def capturas(user: Usuario = Depends(usuario_atual), db: AsyncSession = Depends(get_db)):
    _admin(user)
    return await servico.ultimas_capturas(db)


@router.get('/oabs')
async def oabs(user: Usuario = Depends(usuario_atual), db: AsyncSession = Depends(get_db)):
    _admin(user)
    return await servico.listar_oabs(db)


@router.post('/oabs')
async def incluir_oab(req: OabIn, user: Usuario = Depends(usuario_atual),
                      db: AsyncSession = Depends(get_db)):
    _admin(user)
    try:
        return await servico.adicionar_oab(db, req.oab, req.rotulo)
    except ErroIntimacao as e:
        _erro(e)


@router.delete('/oabs')
async def retirar_oab(oab: str = Query(...), user: Usuario = Depends(usuario_atual),
                      db: AsyncSession = Depends(get_db)):
    _admin(user)
    try:
        return await servico.remover_oab(db, oab)
    except ErroIntimacao as e:
        _erro(e)


@router.post('/capturar')
async def capturar_agora(background: BackgroundTasks, dias: int = Query(3, ge=1, le=30),
                         user: Usuario = Depends(usuario_atual)):
    _admin(user)
    background.add_task(_executar_captura, dias, user.email)
    return {'ok': True, 'aviso': 'Captura iniciada. O resultado aparece no log em alguns minutos.'}


@router.get('/{iid}')
async def perfil(iid: int, user: Usuario = Depends(usuario_atual),
                 db: AsyncSession = Depends(get_db)):
    _tratar(user)
    try:
        return await servico.perfil(db, iid)
    except ErroIntimacao as e:
        _erro(e)


@router.post('/{iid}/conferir')
async def conferir(iid: int, req: ConferirIn, user: Usuario = Depends(usuario_atual),
                   db: AsyncSession = Depends(get_db)):
    _tratar(user)
    try:
        resultado = await servico.conferir(db, iid, user, [i.model_dump() for i in req.itens])
    except ErroIntimacao as e:
        _erro(e)
    return resultado


@router.post('/{iid}/descartar')
async def descartar(iid: int, req: DescartarIn, user: Usuario = Depends(usuario_atual),
                    db: AsyncSession = Depends(get_db)):
    _tratar(user)
    try:
        return await servico.descartar(db, iid, user, req.motivo)
    except ErroIntimacao as e:
        _erro(e)
