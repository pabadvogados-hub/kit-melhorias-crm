"""Webhook: contato com conversa duplicada nao perde mais mensagem.

O DEFEITO (existe no webhook de origem do seu sistema):

    conv = (await db.execute(select(Conversa).where(
        Conversa.numero_id == numero_id,
        Conversa.contato_telefone.like(f'%{ult8}')))).scalar_one_or_none()

Quando o contato manda a primeira mensagem, o WhatsApp pode disparar dois webhooks quase
juntos e nascem DUAS conversas para o mesmo numero. A partir dai scalar_one_or_none()
estoura MultipleResultsFound em TODA mensagem nova dele: o webhook responde erro e a
mensagem se perde, sem aviso. No sistema de origem isso derrubou mensagens de 9 contatos.

A CORRECAO: pegar a conversa mais recente em vez de exigir uma so. Troque as buscas
de conversa do webhook (por @lid, pelos ultimos 8 digitos e por telefone exato) por:

    .order_by(Conversa.atualizado_em.desc(), Conversa.id).limit(1))).scalars().first()

E use _conversa_por_numero (abaixo) em todo lugar que cria ou cadastra conversa
(cadastro manual de cliente, importacao), para nao nascer duplicata por outro caminho.

DEPOIS DE APLICAR: procure as duplicatas que ja existem e junte na mao (ou deixe: com a
correcao, as mensagens novas caem na mais recente e nada se perde).

    SELECT substr(contato_telefone, -8) AS fim, count(*) FROM wa_conversas
    WHERE contato_telefone NOT LIKE '%@%' GROUP BY numero_id, fim HAVING count(*) > 1;
"""


def _norm_tel(raw):
    """So digitos, com DDI 55 (10/11 digitos -> +55)."""
    d = ''.join(ch for ch in str(raw or '') if ch.isdigit())
    if len(d) in (10, 11):
        d = '55' + d
    return d


async def _conversa_por_numero(db, numero_id, telefone_raw):
    """Conversa existente desse numero, casando pelos ULTIMOS 8 digitos (com/sem 55, com/sem o 9).
    Se ja houver duplicata, devolve a mais recente em vez de estourar."""
    d = _norm_tel(telefone_raw)
    if len(d) < 8:
        return None
    ult8 = d[-8:]
    return (await db.execute(select(Conversa).where(
        Conversa.numero_id == numero_id,
        Conversa.contato_telefone.like(f'%{ult8}'))
        .order_by(Conversa.atualizado_em.desc(), Conversa.id).limit(1))).scalars().first()


# Trecho do webhook ja corrigido (substitui o bloco "acha/cria conversa"):
#
#     eh_lid = '@' in dados['telefone']
#     dig = ''.join(ch for ch in dados['telefone'] if ch.isdigit())
#     if eh_lid:
#         tel_store = dados['telefone']
#         conv = (await db.execute(select(Conversa).where(
#             Conversa.numero_id == numero_id,
#             Conversa.contato_telefone == dados['telefone'])
#             .order_by(Conversa.atualizado_em.desc(), Conversa.id).limit(1))).scalars().first()
#     elif len(dig) >= 8:
#         tel_store = dig if dig.startswith('55') else ('55' + dig if len(dig) >= 10 else dig)
#         conv = await _conversa_por_numero(db, numero_id, dig)
#     else:
#         tel_store = dados['telefone']
#         conv = (await db.execute(select(Conversa).where(
#             Conversa.numero_id == numero_id,
#             Conversa.contato_telefone == dados['telefone'])
#             .order_by(Conversa.atualizado_em.desc(), Conversa.id).limit(1))).scalars().first()
