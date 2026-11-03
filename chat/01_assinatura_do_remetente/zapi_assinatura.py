"""Assinatura do remetente na primeira linha de cada mensagem.

Toda mensagem de texto sai com o nome de quem mandou, em negrito do WhatsApp:

    *Nome da Pessoa:*
    texto da mensagem

Pessoa da equipe assina com o nome do cadastro. Robo e fluxo automatico assinam com o
nome do assistente (ASSINATURA_AUTOMACAO). O cliente sabe com quem esta falando e a
equipe nao precisa se apresentar em toda mensagem.

ONDE ENTRA: substitua o enviar_texto do seu whatsapp/zapi.py por este (mesma assinatura
de chamada, com o parametro remetente a mais) e acrescente nome_assinatura/assinar.
O texto GRAVADO no banco continua sem a assinatura: so o que vai para o cliente leva.
"""
import re
import requests

BASE = "https://api.z-api.io"

# AJUSTAR: nome com que robo e fluxo assinam (ex.: o nome da persona da IA)
ASSINATURA_AUTOMACAO = "Assistente"


def nome_assinatura(user):
    """Nome que assina a mensagem de um usuario logado. Conta de robo (nome com "(IA)" ou
    "(automacao)") assina como a automacao."""
    nome = str(getattr(user, "nome", "") or getattr(user, "email", "") or "").strip()
    if not nome or re.search(r"\((ia|automa[cç][aã]o)\)", nome, re.I):
        return ASSINATURA_AUTOMACAO
    return nome


def assinar(mensagem, remetente=None):
    """Poe "*Nome:*" na primeira linha. Nao duplica se ja estiver assinada.
    remetente=None -> assinatura da automacao; remetente="" -> sem assinatura."""
    nome = ASSINATURA_AUTOMACAO if remetente is None else str(remetente).strip()
    texto = str(mensagem or "")
    if not nome or not texto.strip():
        return texto
    cabecalho = f"*{nome}:*"
    if texto.lstrip().startswith((cabecalho, f"*{nome}*")):
        return texto
    return f"{cabecalho}\n{texto}"


def enviar_texto(numero, telefone, mensagem, remetente=None):
    """Envia texto. Retorna (ok, info): info = messageId no sucesso, erro no fracasso."""
    mensagem = assinar(mensagem, remetente)
    url = f"{BASE}/instances/{numero.zapi_instance}/token/{numero.zapi_token}/send-text"
    headers = {"Content-Type": "application/json"}
    if numero.zapi_client_token:
        headers["Client-Token"] = numero.zapi_client_token
    try:
        r = requests.post(url, json={"phone": telefone, "message": mensagem}, headers=headers, timeout=30)
        if r.status_code in (200, 201):
            try:
                j = r.json()
                return True, (j.get("messageId") or j.get("id") or "")
            except Exception:
                return True, ""
        return False, (r.text[:300] if r is not None else "")
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# COMO CHAMAR (routers/atendimento.py)
#
# Resposta da equipe (rota /conversas/{id}/responder):
#     ok, detalhe = await asyncio.to_thread(zapi.enviar_texto, numero, conv.contato_telefone,
#                                           req.texto, zapi.nome_assinatura(user))
#     db.add(Mensagem(..., conteudo=req.texto, ...))     # grava SEM a assinatura
#
# Resposta da IA (_responder_ia):
#     ok, msg_id = await asyncio.to_thread(zapi.enviar_texto, numero, conv.contato_telefone,
#                                          resposta, "Jaqueline")     # nome da persona
#
# Fluxos automaticos: chamar sem remetente (assina como ASSINATURA_AUTOMACAO).
# Legenda de imagem/video: assinar(caption, remetente) antes de mandar, se tiver texto.
# ---------------------------------------------------------------------------
