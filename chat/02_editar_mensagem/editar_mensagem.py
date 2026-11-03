"""Editar no WhatsApp do cliente uma mensagem de texto que a equipe mandou.

Regras (ficam no sistema, porque o provedor responde "ok" ate para id que nao existe):
  - so mensagem de TEXTO mandada pela EQUIPE (origem 'atendente', com remote_id);
  - so quem mandou, ou administrador;
  - so ate 15 minutos depois do envio (o WhatsApp ignora edicao mais velha);
  - toda edicao fica registrada em wa_mensagens_edicoes (antes, depois, quem, quando).

Efeito colateral tratado: o aviso da edicao volta pelo webhook com OUTRO id e viraria um
balao novo no chat. _absorver_eco_edicao apaga esse eco por 2 minutos.

ONDE ENTRA: cole no routers/atendimento.py (imports ja existem la: asyncio, datetime,
select, or_, BackgroundTasks, HTTPException, Depends, BaseModel, Usuario, Conversa,
Mensagem, NumeroWhatsapp, AsyncSessionLocal, get_db, usuario_atual).

PROVEDOR: no sistema de origem a edicao sai pela D-API (dapi.editar_texto, incluso em
ligacao/14_ligacao_pelo_whatsapp/dapi.py). Para Z-API, implemente zapi.editar_texto
conforme a documentacao atual (developer.z-api.io). CONFERIR NA DOC antes de ligar:
nao testamos edicao pela Z-API.
"""
from datetime import datetime, timedelta

EDITAR_JANELA_MIN = 15


class EditarMsgReq(BaseModel):
    texto: str


def _criado_utc(v):
    if isinstance(v, datetime):
        return v
    return datetime.fromisoformat(str(v).replace('T', ' ').replace('Z', '')[:26])


async def _historico_edicao(db, m, conv_id, antes, depois, por):
    from sqlalchemy import text as _sql
    await db.execute(_sql("CREATE TABLE IF NOT EXISTS wa_mensagens_edicoes (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                          "mensagem_id INTEGER, conversa_id INTEGER, texto_antes TEXT, texto_depois TEXT, por TEXT, em TEXT)"))
    await db.execute(_sql("INSERT INTO wa_mensagens_edicoes (mensagem_id, conversa_id, texto_antes, texto_depois, por, em) "
                          "VALUES (:m, :c, :a, :d, :p, :e)"),
                     {'m': m, 'c': conv_id, 'a': antes, 'd': depois, 'p': por, 'e': datetime.utcnow().isoformat()})


async def _absorver_eco_edicao(conversa_id: int, mensagem_id: int, texto: str, desde: datetime):
    """Por 2 min, apaga o eco da edicao: mesma conversa, depois da mensagem editada, atendente
    sem autor (o webhook grava assim) e exatamente o texto novo. Nao mexe no webhook."""
    for _ in range(12):
        await asyncio.sleep(10)
        try:
            async with AsyncSessionLocal() as db:
                ecos = (await db.execute(select(Mensagem).where(
                    Mensagem.conversa_id == conversa_id, Mensagem.id > mensagem_id, Mensagem.origem == 'atendente',
                    or_(Mensagem.autor.is_(None), Mensagem.autor == ''), Mensagem.conteudo == texto,
                    Mensagem.criado_em >= desde - timedelta(seconds=5)))).scalars().all()
                if ecos:
                    for e in ecos:
                        await db.delete(e)
                    await db.commit()
                    return
        except Exception as e:
            print(f'[editar] absorver eco falhou: {type(e).__name__}: {e}', flush=True)
            return


@router.post('/mensagens/{mensagem_id}/editar')
async def editar_mensagem(mensagem_id: int, req: EditarMsgReq, bg: BackgroundTasks,
                          user: Usuario = Depends(usuario_atual), db: AsyncSession = Depends(get_db)):
    texto = (req.texto or '').strip()
    if not texto:
        raise HTTPException(400, 'Escreva o texto novo')
    m = (await db.execute(select(Mensagem).where(Mensagem.id == mensagem_id))).scalar_one_or_none()
    if not m:
        raise HTTPException(404, 'Mensagem nao encontrada')
    if m.origem != 'atendente' or m.tipo != 'texto' or not m.remote_id:
        raise HTTPException(400, 'So da para editar mensagem de texto enviada pela equipe')
    if (m.autor or '').lower() != (user.email or '').lower() and user.papel != 'admin':
        raise HTTPException(403, 'So quem mandou a mensagem pode editar')
    if (datetime.utcnow() - _criado_utc(m.criado_em)).total_seconds() > EDITAR_JANELA_MIN * 60:
        raise HTTPException(400, 'O WhatsApp so deixa editar ate 15 minutos depois do envio')
    if texto == (m.conteudo or '').strip():
        return {'ok': True, 'igual': True}
    conv = (await db.execute(select(Conversa).where(Conversa.id == m.conversa_id))).scalar_one_or_none()
    if not conv:
        raise HTTPException(404, 'Conversa nao encontrada')
    numero = (await db.execute(select(NumeroWhatsapp).where(NumeroWhatsapp.id == conv.numero_id))).scalar_one_or_none()
    # o texto editado volta ao cliente com a assinatura de quem mandou (ver chat/01)
    autor_u = (await db.execute(select(Usuario).where(Usuario.email == (m.autor or '')))).scalar_one_or_none()
    texto_envio = zapi.assinar(texto, zapi.nome_assinatura(autor_u or user))
    ok, detalhe = await asyncio.to_thread(zapi.editar_texto, numero, conv.contato_telefone, m.remote_id, texto_envio)
    if not ok:
        raise HTTPException(502, f'O WhatsApp recusou a edicao: {detalhe}')
    antes = m.conteudo or ''
    m.conteudo = texto
    if (conv.ultima_mensagem or '') == antes[:300]:
        conv.ultima_mensagem = texto[:300]
    await _historico_edicao(db, m.id, conv.id, antes, texto, user.email)
    await db.commit()
    bg.add_task(_absorver_eco_edicao, conv.id, m.id, texto_envio, datetime.utcnow())
    return {'ok': True, 'mensagem': m.to_dict()}


@router.get('/conversas/{conversa_id}/editadas')
async def mensagens_editadas(conversa_id: int, user: Usuario = Depends(usuario_atual),
                             db: AsyncSession = Depends(get_db)):
    """Ids das mensagens editadas dessa conversa (a tela marca 'editada')."""
    from sqlalchemy import text as _sql
    try:
        rows = (await db.execute(_sql("SELECT DISTINCT mensagem_id FROM wa_mensagens_edicoes WHERE conversa_id = :c"),
                                 {'c': conversa_id})).all()
    except Exception:
        rows = []
    return {'ids': [r[0] for r in rows]}
