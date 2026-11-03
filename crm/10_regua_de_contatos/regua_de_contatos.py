"""Regua de contatos: em que contato (1o, 2o, 3o...) o lead esta, quem fez e se respondeu.

Pergunta que originou: "dentro de Lead Quente eu preciso saber se ele ja foi contatado, e
qual foi o 1o, 2o, 3o, 4o contato".

A regua e DERIVADA das mensagens, ninguem digita nada. Um CONTATO (toque) e uma investida
nossa: as mensagens que saem juntas, sem resposta do lead no meio e sem passar de
JANELA_TOQUE_H horas entre elas, contam como UM contato. E como a equipe conta ("mandei
mensagem tres vezes"), nao como o banco conta (17 mensagens).
Conta: mensagem/audio da equipe, fluxo automatico, resposta da IA, ligacao.
Nao conta: nota interna.

O que entrega:
  - GET /conversas/{id}/regua-contatos -> os toques de um lead (quando, quem, canal, respondeu?)
  - GET /regua-contatos?pipeline_id=&etapa= -> a coluna inteira, o mais parado primeiro
  - CAPA DO CARD: em GET /conversas, cada card ganha contatos_total, aguardando_retorno
    ("o lead respondeu e ninguem voltou"), horas_aguardando e sem_resposta_seguidos.
    Na tela: um selo "3 contatos" e um alerta vermelho quando aguardando_retorno.

ONDE ENTRA: routers/atendimento.py. Na listar_conversas, troque o return final pelo trecho
do fim deste arquivo.
"""

JANELA_TOQUE_H = 6
ORIGENS_NOSSAS = ('atendente', 'ia', 'ligacao')


def _quem_falou(m):
    """(rotulo, especie) do autor de um toque."""
    autor = (m.autor or '').strip()
    if m.origem == 'ligacao':
        return ('ligacao', 'ligacao')
    if m.origem == 'ia':
        return (autor or 'IA', 'ia')
    if autor.startswith('fluxo:'):
        return (f'automacao ({autor[6:]})', 'automacao')
    if autor:
        return (autor, 'humano')
    return ('equipe (pelo celular)', 'humano')


def _horas(a, b):
    try:
        return abs((a - b).total_seconds()) / 3600.0
    except Exception:
        return 999.0


def _montar_regua(msgs):
    """msgs em ordem cronologica -> (toques, resumo). Nao toca no banco."""
    toques, atual, respondeu_desde = [], None, False
    for m in msgs:
        if m.origem == 'nota':
            continue
        if m.origem == 'contato':
            if atual and not atual['respondeu']:
                atual['respondeu'] = True
                atual['respondeu_em'] = m.criado_em
                atual['resposta_em_horas'] = round(_horas(m.criado_em, atual['quando']), 1)
            respondeu_desde = True
            continue
        if m.origem not in ORIGENS_NOSSAS:
            continue
        novo = (atual is None or respondeu_desde
                or _horas(m.criado_em, atual['ultima_em']) > JANELA_TOQUE_H)
        if novo:
            rotulo, especie = _quem_falou(m)
            atual = {'numero': len(toques) + 1, 'quando': m.criado_em,
                     'ultima_em': m.criado_em, 'quem': rotulo, 'especie': especie,
                     'canais': [m.tipo], 'mensagens': 1,
                     'respondeu': False, 'respondeu_em': None, 'resposta_em_horas': None,
                     'previa': (getattr(m, 'conteudo', '') or '')[:160]}
            toques.append(atual)
            respondeu_desde = False
        else:
            atual['ultima_em'] = m.criado_em
            atual['mensagens'] += 1
            if m.tipo not in atual['canais']:
                atual['canais'].append(m.tipo)
    agora = datetime.utcnow()
    ult = toques[-1] if toques else None
    resumo = {
        'total_contatos': len(toques),
        'ultimo_numero': ult['numero'] if ult else 0,
        'ultimo_em': ult['quando'].isoformat() + 'Z' if ult else None,
        'ultimo_quem': ult['quem'] if ult else '',
        'ultimo_respondeu': bool(ult['respondeu']) if ult else False,
        'dias_desde_ultimo': round(_horas(agora, ult['quando']) / 24.0, 1) if ult else None,
        'contatos_sem_resposta_no_fim': 0,
        'primeiro_em': toques[0]['quando'].isoformat() + 'Z' if toques else None,
    }
    for t in reversed(toques):
        if t['respondeu']:
            break
        resumo['contatos_sem_resposta_no_fim'] += 1
    saida = [{'numero': t['numero'], 'quando': t['quando'].isoformat() + 'Z',
              'quem': t['quem'], 'especie': t['especie'], 'canais': t['canais'],
              'mensagens': t['mensagens'], 'respondeu': t['respondeu'],
              'respondeu_em': t['respondeu_em'].isoformat() + 'Z' if t['respondeu_em'] else None,
              'resposta_em_horas': t['resposta_em_horas'], 'previa': t['previa']} for t in toques]
    return saida, resumo


async def _resumo_contatos_em_lote(db, convs):
    """Resumo da regua para varios cards de uma vez (alimenta a CAPA do card no quadro)."""
    if not convs:
        return {}
    ids = [c.id for c in convs]
    linhas = (await db.execute(
        select(Mensagem.conversa_id, Mensagem.origem, Mensagem.criado_em, Mensagem.tipo, Mensagem.autor)
        .where(Mensagem.conversa_id.in_(ids), Mensagem.origem != 'nota')
        .order_by(Mensagem.conversa_id, Mensagem.criado_em, Mensagem.id))).all()
    por_conv = {}
    for l in linhas:
        por_conv.setdefault(l.conversa_id, []).append(l)
    agora = datetime.utcnow()
    saida = {}
    for c in convs:
        msgs = por_conv.get(c.id, [])
        _, r = _montar_regua(msgs)
        ultima = msgs[-1] if msgs else None
        esperando = bool(ultima is not None and ultima.origem == 'contato')   # a bola esta com a gente
        saida[c.id] = {
            'contatos_total': r['total_contatos'],
            'aguardando_retorno': esperando,
            'horas_aguardando': round(_horas(agora, ultima.criado_em), 1) if esperando else None,
            'sem_resposta_seguidos': r['contatos_sem_resposta_no_fim'],
        }
    return saida


@router.get('/conversas/{conversa_id}/regua-contatos')
async def regua_contatos(conversa_id: int, user: Usuario = Depends(usuario_atual),
                         db: AsyncSession = Depends(get_db)):
    conv = (await db.execute(select(Conversa).where(Conversa.id == conversa_id))).scalar_one_or_none()
    if not conv:
        raise HTTPException(404, 'Conversa nao encontrada')
    msgs = (await db.execute(select(Mensagem).where(Mensagem.conversa_id == conversa_id)
                             .order_by(Mensagem.criado_em, Mensagem.id))).scalars().all()
    toques, resumo = _montar_regua(msgs)
    return {'conversa_id': conversa_id, 'contato_nome': conv.contato_nome,
            'etapa': conv.etapa, 'pipeline_id': conv.pipeline_id,
            'resumo': resumo, 'toques': toques}


@router.get('/regua-contatos')
async def regua_da_coluna(pipeline_id: int, etapa: Optional[str] = None,
                          limite: int = 200, user: Usuario = Depends(usuario_atual),
                          db: AsyncSession = Depends(get_db)):
    """A coluna inteira, o mais parado primeiro: e a fila que a equipe precisa atacar."""
    q = select(Conversa).where(Conversa.pipeline_id == pipeline_id, Conversa.status == 'aberto')
    if etapa:
        q = q.where(Conversa.etapa == etapa)
    convs = (await db.execute(q.limit(max(1, min(limite, 500))))).scalars().all()
    if not convs:
        return {'items': [], 'total': 0}
    ids = [c.id for c in convs]
    msgs = (await db.execute(select(Mensagem).where(Mensagem.conversa_id.in_(ids))
                             .order_by(Mensagem.criado_em, Mensagem.id))).scalars().all()
    por_conv = {}
    for m in msgs:
        por_conv.setdefault(m.conversa_id, []).append(m)
    itens = []
    for c in convs:
        _, resumo = _montar_regua(por_conv.get(c.id, []))
        itens.append({'conversa_id': c.id, 'contato_nome': c.contato_nome,
                      'contato_telefone': c.contato_telefone, 'etapa': c.etapa,
                      'tag': c.tag or '', 'origem': c.origem or '',
                      'atendente_email': c.atendente_email or '', **resumo})
    itens.sort(key=lambda i: (-(i['contatos_sem_resposta_no_fim'] or 0), -(i['dias_desde_ultimo'] or 0)))
    return {'items': itens, 'total': len(itens)}


# ------------- fim de listar_conversas (capa do card) -------------
#
#     rows = (await db.execute(q)).scalars().all()
#     try:   # a capa e informacao a mais, nunca motivo para a tela quebrar
#         extras = await _resumo_contatos_em_lote(db, rows)
#     except Exception as e:
#         print(f'[capa] resumo de contatos falhou: {e}', flush=True)
#         extras = {}
#     return [{**c.to_dict(), **extras.get(c.id, {})} for c in rows]
