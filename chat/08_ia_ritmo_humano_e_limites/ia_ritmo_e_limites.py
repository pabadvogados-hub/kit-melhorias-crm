"""Agente de IA no WhatsApp: ritmo humano, teto de respostas e saudacao automatica.

Tres ajustes no _responder_ia / webhook, todos independentes. Aplique um de cada vez.

1) RITMO HUMANO
   A IA respondia no mesmo segundo, e ninguem digita assim: o lead percebe que e maquina e
   esfria. Antes de mandar, marca como lida, acende o "digitando..." e espera o tempo que
   alguem levaria para escrever aquilo (le ~1,5 s e digita ~22 letras por segundo, com
   variacao). Resposta de 3 linhas cai entre ~7 e ~13 s.
   Na Z-API o "digitando" pode ir no proprio envio: o send-text aceita um atraso de
   digitacao (delayTyping, em segundos). CONFERIR NA DOC (developer.z-api.io) antes de usar.

2) TETO DE RESPOSTAS DA IA
   Se a IA ja mandou LIMITE_RESPOSTAS_IA respostas na conversa e o caso nao foi encaminhado,
   ela para sozinha, deixa nota interna e a equipe assume. Evita a IA girando em loop com
   trote, spam ou caso confuso.

3) SAUDACAO DO WHATSAPP BUSINESS NAO DESLIGA A IA
   O WhatsApp Business do celular manda sozinho a mensagem de boas-vindas no primeiro
   contato. Ela volta pelo webhook como mensagem "nossa" (fromMe) e o sistema entendia que
   alguem da equipe respondeu pelo celular: desligava a IA. No sistema de origem isso deixou
   128 leads novos sem resposta em dois dias. Agora essa mensagem entra como fluxo e a IA
   segue atendendo.
"""
import random

LIMITE_RESPOSTAS_IA = 12
MARK_LIMITE = '[LIMITE IA]'
MARK_BRIEFING = '[BRIEFING DE FECHAMENTO]'   # AJUSTAR: o marcador da nota que sua IA deixa ao encaminhar

# AJUSTAR: comeco EXATO da mensagem de saudacao configurada no WhatsApp Business do numero
SAUDACAO_WHATSAPP_BUSINESS = 'Bem-vindo ao escritorio'


def _tempo_de_digitacao(texto: str) -> float:
    segundos = 1.5 + len(texto or "") / 22.0
    segundos *= random.uniform(0.85, 1.15)      # sem cadencia de metronomo
    return max(2.5, min(segundos, 13.0))


# --- 1) dentro de _responder_ia, logo depois de gerar `resposta` e antes do enviar_texto ---
#
#     espera = _tempo_de_digitacao(resposta)
#     try:   # enfeite: se falhar, nunca segura a resposta
#         await asyncio.to_thread(zapi.marcar_lido, numero, conv.contato_telefone)
#         await asyncio.to_thread(zapi.digitando, numero, conv.contato_telefone, int(espera * 1000))
#     except Exception:
#         pass
#     await asyncio.sleep(espera)
#
# Sem marcar_lido/digitando no seu zapi.py, deixe so o asyncio.sleep(espera): ja resolve o principal.


# --- 2) dentro de _responder_ia, antes de chamar a IA (depois do filtro "humano ja falou") ---
#
#     if not forcar:
#         n_ia = sum(1 for m in msgs if m.origem == 'ia')
#         encaminhado = any(m.origem == 'nota' and (m.conteudo or '').startswith(MARK_BRIEFING) for m in msgs)
#         if n_ia >= LIMITE_RESPOSTAS_IA and not encaminhado:
#             conv.ia_ativa = False
#             db.add(Mensagem(conversa_id=conversa_id, origem='nota', autor='sistema', tipo='texto',
#                             conteudo=f'{MARK_LIMITE} A IA chegou a {n_ia} respostas sem encaminhar o caso. '
#                                      'IA pausada: assumir manualmente.'))
#             await db.commit()
#             return


# --- 3) no webhook, bloco da mensagem que SAIU (direcao 'out'), no lugar do "conv.ia_ativa = False" ---
#
#     saudacao = (dados['conteudo'] or '').lstrip().startswith(SAUDACAO_WHATSAPP_BUSINESS)
#     db.add(Mensagem(conversa_id=conv.id, origem='atendente', tipo=dados['tipo'],
#                     **({'autor': 'fluxo:saudacao-whatsapp'} if saudacao else {}),
#                     conteudo=dados['conteudo'], midia_url=dados['midia_url'],
#                     remote_id=dados['remote_id']))
#     if saudacao:
#         await db.commit()
#         return {'ok': True, 'out': True, 'saudacao': True}
#     conv.ia_ativa = False   # gente respondeu pelo celular -> IA sai de cena
#     await db.commit()
#     return {'ok': True, 'out': True}
#
# Funciona porque o filtro "humano ja falou" do _responder_ia ignora mensagens com autor 'fluxo:...'.
