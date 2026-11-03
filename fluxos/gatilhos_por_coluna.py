"""Gatilhos: qual fluxo liga quando o card entra numa coluna, de acordo com a AREA do card.

A area ja e escolhida ao aceitar a conversa (fica em Conversa.tag). Este trecho troca o
gatilho unico de hoje ("Fechado" -> 'contratacao') por um gatilho por coluna e por area.

ONDE ENTRA: routers/atendimento.py, na rota mover_etapa, no lugar de

    entrou_no_contrato = (req.etapa == ETAPA_CONTRATO and conv.etapa != ETAPA_CONTRATO)
    ...
    if entrou_no_contrato:
        fluxo_disparado = await _iniciar_fluxo(db, conv, FLUXO_CONTRATACAO)

Area sem fluxo proprio (ex.: Restituicao Tributaria) cai no fluxo generico que ja existe.
Ao entrar num fluxo novo, os fluxos anteriores do card sao desligados: o lead nunca recebe
duas cadencias ao mesmo tempo.
"""

# coluna -> {area: fluxo}. '*' = qualquer area sem regra propria.
GATILHOS = {
    'Proposta': {
        'Holding Familiar': 'holding_pos_consulta',
        'Direito de Família': 'familia_pos_consulta',
    },
    'Fechado': {
        'Holding Familiar': 'holding_documentos',
        'Direito de Família': 'familia_documentos',
        '*': 'contratacao',
    },
    'Perdido': {            # crie a coluna "Perdido" no quadro para usar este
        '*': 'reaquecimento_anual',
    },
}


def fluxo_do_gatilho(etapa, area):
    regra = GATILHOS.get(etapa) or {}
    return regra.get((area or '').strip()) or regra.get('*')


async def _desligar_fluxos(db, conv):
    for fl in (await db.execute(select(Fluxo).where(
            Fluxo.conversa_id == conv.id, Fluxo.ativo == True))).scalars().all():
        fl.ativo = False
        fl.concluido_em = datetime.utcnow()


# ------------------------- dentro de mover_etapa -------------------------
#
#     entrou_em_coluna_nova = (req.etapa != conv.etapa)
#     ... (move o card como hoje) ...
#     fluxo_disparado = False
#     if entrou_em_coluna_nova:
#         tipo = fluxo_do_gatilho(req.etapa, conv.tag)
#         if tipo and tipo in FLUXOS:
#             await _desligar_fluxos(db, conv)
#             # ATENCAO: _iniciar_fluxo manda o passo 1 NA HORA quando enviar_ja=True, sem olhar
#             # apos_horas. So pode ser True quando o passo 1 e imediato (apos_horas 0, como nos
#             # *_documentos). Nos outros, o cron manda no tempo certo.
#             imediato = FLUXOS[tipo]['passos'][0]['apos_horas'] == 0
#             fluxo_disparado = await _iniciar_fluxo(db, conv, tipo, enviar_ja=imediato)
#     await db.commit()
#
# Confira tambem que o cron do /fluxos/processar roda pelo menos de hora em hora no horario
# comercial: os passos de 4 horas dependem disso. Uma vez por dia atrasa a cadencia.
#
# Os fluxos *_retomar ficam de fora dos gatilhos de proposito: a equipe liga na mao,
# pelo seletor de fluxos que ja existe no card (POST /conversas/{id}/fluxo).
