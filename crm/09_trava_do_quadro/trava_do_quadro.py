"""Trava do quadro: card que a equipe mudou de quadro fica la. Automacao nao tira.

O problema: robos e fluxos movem cards sozinhos. Quando alguem da equipe leva um lead para
outro quadro (ex.: de Leads para Clientes), a automacao seguinte trazia de volta, e o card
"sumia" de onde a pessoa deixou.

Regras (nesta ordem):
  R1  Automacao NUNCA traz card de outro quadro de volta para o quadro de leads.
  R2  Card com o quadro fixado por gente so muda de quadro por gente. Excecao: o AVANCO
      normal da esteira (ESTEIRA_QUADROS, na ordem), ex.: Leads -> Contratacao -> Producao.
Trocar de COLUNA dentro do mesmo quadro continua livre para a automacao.
Toda tentativa, aceita ou recusada, fica em wa_board_hist: responde "quem tirou meu card daqui".

Tambem: mover para coluna que NAO existe e recusado (card mandado para coluna apagada some
do quadro).

INSTALAR:
  1. models.py: os 3 campos em Conversa + a tabela MoveBoard (abaixo). Banco existente:
       ALTER TABLE wa_conversas ADD COLUMN board_fixado INTEGER DEFAULT 0;
       ALTER TABLE wa_conversas ADD COLUMN board_fixado_por VARCHAR(200) DEFAULT '';
       ALTER TABLE wa_conversas ADD COLUMN board_fixado_em VARCHAR(40) DEFAULT '';
     (wa_board_hist nasce sozinha no create_all.) Inclua os 3 campos no to_dict().
  2. routers/atendimento.py: as funcoes abaixo. Daqui pra frente, TODA movimentacao feita
     por automacao (IA, fluxo, cron) passa por _mover_automatico, nunca por atribuicao direta.
  3. Na rota mover_etapa (arrastar card na tela), o trecho do fim deste arquivo.
"""

# ----------------------------- models.py -----------------------------
#
# class Conversa(Base):
#     ...
#     board_fixado: Mapped[int] = mapped_column(Integer, default=0)
#     board_fixado_por: Mapped[str] = mapped_column(String(200), default='')
#     board_fixado_em: Mapped[str] = mapped_column(String(40), default='')
#
# class MoveBoard(Base):
#     """Trilha de TODA troca de quadro/coluna, inclusive as que a trava recusou."""
#     __tablename__ = 'wa_board_hist'
#     id: Mapped[int] = mapped_column(Integer, primary_key=True)
#     conversa_id: Mapped[int] = mapped_column(Integer, index=True)
#     de_pipeline: Mapped[int] = mapped_column(Integer, default=0)
#     de_etapa: Mapped[str] = mapped_column(String(60), default='')
#     para_pipeline: Mapped[int] = mapped_column(Integer, default=0)
#     para_etapa: Mapped[str] = mapped_column(String(60), default='')
#     quem: Mapped[str] = mapped_column(String(200), default='')
#     origem: Mapped[str] = mapped_column(String(80), default='')
#     bloqueado: Mapped[int] = mapped_column(Integer, default=0)
#     criado_em: Mapped[str] = mapped_column(String(40), default='')
#
#     def to_dict(self):
#         return {'id': self.id, 'conversa_id': self.conversa_id,
#                 'de_pipeline': self.de_pipeline, 'de_etapa': self.de_etapa,
#                 'para_pipeline': self.para_pipeline, 'para_etapa': self.para_etapa,
#                 'quem': self.quem, 'origem': self.origem, 'bloqueado': bool(self.bloqueado),
#                 'criado_em': self.criado_em}

# ----------------------- routers/atendimento.py -----------------------

PIPE_LEADS = 'Braga & Braz - Leads'                         # AJUSTAR: nome do quadro de leads
ESTEIRA_QUADROS = ['Braga & Braz - Leads']                  # AJUSTAR: quadros da esteira, na ordem


async def _id_pipeline(db, nome):
    return (await db.execute(select(Pipeline.id).where(Pipeline.nome == nome))).scalar_one_or_none()


def _registrar_move(db, conv, para_pid, para_etapa, quem, origem, bloqueado=False):
    """Anota a troca (ou a tentativa recusada) na trilha. Nao commita."""
    db.add(MoveBoard(conversa_id=conv.id, de_pipeline=conv.pipeline_id or 0,
                     de_etapa=conv.etapa or '', para_pipeline=para_pid or 0,
                     para_etapa=para_etapa or '', quem=quem, origem=origem,
                     bloqueado=1 if bloqueado else 0,
                     criado_em=datetime.utcnow().isoformat(sep=' ')))


async def _automacao_pode_mover(db, conv, para_pid):
    """Regras R1 e R2. True = a automacao pode levar o card para la."""
    if not para_pid or para_pid == conv.pipeline_id:
        return True                      # trocar de coluna no mesmo quadro e livre
    leads_id = await _id_pipeline(db, PIPE_LEADS)
    if leads_id and para_pid == leads_id:
        return False                     # R1
    if not getattr(conv, 'board_fixado', 0):
        return True
    ids = [i for i in [await _id_pipeline(db, n) for n in ESTEIRA_QUADROS] if i]
    if (conv.pipeline_id in ids and para_pid in ids
            and ids.index(para_pid) > ids.index(conv.pipeline_id)):
        return True                      # R2: avanco da esteira passa
    return False


async def _coluna_existe(db, pid, etapa):
    cols = (await db.execute(select(Stage.nome).where(Stage.pipeline_id == pid))).scalars().all()
    return (not cols) or (etapa in cols)


async def _mover_automatico(db, conv, para_pid, para_etapa, quem, origem, nota=None):
    """UNICO caminho pelo qual a automacao move um card. Devolve True se moveu. Nao commita."""
    if conv.pipeline_id == para_pid and conv.etapa == para_etapa:
        return False                     # ja esta la
    if not await _coluna_existe(db, para_pid, para_etapa):
        _registrar_move(db, conv, para_pid, para_etapa, quem, origem, bloqueado=True)
        return False
    if not await _automacao_pode_mover(db, conv, para_pid):
        _registrar_move(db, conv, para_pid, para_etapa, quem, origem, bloqueado=True)
        return False
    _registrar_move(db, conv, para_pid, para_etapa, quem, origem)
    conv.pipeline_id = para_pid
    conv.etapa = para_etapa
    conv.atualizado_em = datetime.utcnow()
    if nota:
        db.add(Mensagem(conversa_id=conv.id, origem='nota', autor='sistema', tipo='texto', conteudo=nota))
    return True


@router.get('/conversas/{conversa_id}/board-historico')
async def board_historico(conversa_id: int, user: Usuario = Depends(usuario_atual),
                          db: AsyncSession = Depends(get_db)):
    """Quem moveu este card, quando e por que, inclusive as tentativas recusadas."""
    nomes = {p.id: p.nome for p in (await db.execute(select(Pipeline))).scalars().all()}
    rows = (await db.execute(select(MoveBoard).where(MoveBoard.conversa_id == conversa_id)
                             .order_by(desc(MoveBoard.id)).limit(100))).scalars().all()
    itens = []
    for r in rows:
        d = r.to_dict()
        d['de_board'] = nomes.get(r.de_pipeline, str(r.de_pipeline))
        d['para_board'] = nomes.get(r.para_pipeline, str(r.para_pipeline))
        itens.append(d)
    return {'items': itens}


class BoardTravaReq(BaseModel):
    fixado: bool


@router.post('/conversas/{conversa_id}/board-trava')
async def board_trava(conversa_id: int, req: BoardTravaReq,
                      user: Usuario = Depends(usuario_atual), db: AsyncSession = Depends(get_db)):
    """Liga/desliga a trava na mao. Destravar devolve o card para as automacoes."""
    conv = (await db.execute(select(Conversa).where(Conversa.id == conversa_id))).scalar_one_or_none()
    if not conv:
        raise HTTPException(404, 'Conversa nao encontrada')
    conv.board_fixado = 1 if req.fixado else 0
    conv.board_fixado_por = user.email if req.fixado else ''
    conv.board_fixado_em = datetime.utcnow().isoformat(sep=' ') if req.fixado else ''
    _registrar_move(db, conv, conv.pipeline_id, conv.etapa, user.email,
                    'ui:trava-on' if req.fixado else 'ui:trava-off')
    await db.commit()
    return {'ok': True, 'board_fixado': bool(conv.board_fixado)}


# ------------- dentro de mover_etapa (card arrastado por gente na tela) -------------
#
#     trocou_board = (pid != conv.pipeline_id)
#     _registrar_move(db, conv, pid, req.etapa, user.email, 'ui')
#     conv.pipeline_id = pid
#     conv.etapa = req.etapa
#     if trocou_board:                       # gente trocou de quadro -> arma a trava
#         conv.board_fixado = 1
#         conv.board_fixado_por = user.email
#         conv.board_fixado_em = datetime.utcnow().isoformat(sep=' ')
#
# Opcional: restringir troca de QUADRO a admin (trocar de coluna fica livre para todos):
#     if trocou_board and user.papel != 'admin':
#         _registrar_move(db, conv, pid, req.etapa, user.email, 'ui', bloqueado=True)
#         await db.commit()
#         raise HTTPException(403, 'Voce pode mover o card entre as colunas deste quadro.')
