"""Busca de contatos que acha o lead pelo nome que ele DISSE na conversa.

Problema real: o card fica com o nome do perfil do WhatsApp ("Araujo 😎", ou so o
numero) e o lead se apresenta com outro nome. A equipe procura "Francisco" e nao acha.

Como resolve: depois dos acertos por nome do card e por numero, procura tambem
  1. na nota de briefing que a IA gera ao encaminhar o lead (linha "Nome/como chamar:");
  2. nas mensagens CURTAS do proprio lead (ate 60 letras), que e onde ele diz o nome.
So para termo com 4+ letras e sem numero. Se der erro, a busca sai como sempre saiu.

ONDE ENTRA: substitui (ou cria) a rota GET /api/atendimento/contatos em
routers/atendimento.py. Na tela, a caixa de busca do Chat chama esta rota.

AJUSTAR: MARCA_NOME_BRIEFING precisa casar com a linha que o seu briefing escreve. Se a
sua IA nao gera briefing, o item 1 so nao acha nada (o item 2 continua valendo).
Se o sistema filtra conversas por area (areas_permitidas), aplique o mesmo filtro no fim.
"""
import re

MARCA_NOME_BRIEFING = 'Nome/como chamar'


@router.get('/contatos')
async def buscar_contatos(q: str = '', limit: int = 60,
                          user: Usuario = Depends(usuario_atual), db: AsyncSession = Depends(get_db)):
    """Busca em TODAS as conversas por nome OU numero, nada fica escondido."""
    termo = (q or '').strip()
    query = select(Conversa)
    if termo:
        dig = re.sub(r'\D', '', termo)
        conds = [Conversa.contato_nome.ilike(f'%{termo}%')]
        if len(dig) >= 3:
            conds.append(Conversa.contato_telefone.like(f'%{dig}%'))
        query = query.where(or_(*conds))
    lim = max(1, min(limit, 200))
    rows = list((await db.execute(query.order_by(desc(Conversa.atualizado_em)).limit(lim))).scalars().all())

    if termo and len(termo) >= 4 and not re.search(r'\d', termo) and len(rows) < lim:
        try:
            briefs = (await db.execute(select(Mensagem.conversa_id, Mensagem.conteudo).where(
                Mensagem.origem == 'nota', Mensagem.conteudo.like(f'%{MARCA_NOME_BRIEFING}%'),
                Mensagem.conteudo.ilike(f'%{termo}%')).limit(500))).all()
            t_min = termo.lower()
            padrao = re.escape(MARCA_NOME_BRIEFING) + r':([^\n]*)'
            por_briefing = {cid for cid, txt in briefs
                            if any(t_min in re.split(r'\s+-\s+', linha)[0].lower()
                                   for linha in re.findall(padrao, txt or ''))}
            curtas = select(Mensagem.conversa_id).where(
                Mensagem.origem == 'contato', func.length(Mensagem.conteudo) <= 60,
                Mensagem.conteudo.ilike(f'%{termo}%'))
            q2 = select(Conversa).where(or_(Conversa.id.in_(curtas), Conversa.id.in_(por_briefing)))
            ja = [r.id for r in rows]
            if ja:
                q2 = q2.where(~Conversa.id.in_(ja))
            rows += (await db.execute(q2.order_by(desc(Conversa.atualizado_em)).limit(lim - len(rows)))).scalars().all()
        except Exception as e:
            print(f'[busca] nome dito na conversa falhou: {type(e).__name__}: {e}', flush=True)

    itens = [r.to_dict() for r in rows]
    return {'items': itens, 'total': len(itens)}
