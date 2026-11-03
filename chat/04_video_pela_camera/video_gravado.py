"""Video gravado pela camera no Chat ao Vivo (26/10/2026, pedido do Admin para a Vendedora1).

O navegador grava em WebM, que o WhatsApp nao toca. Aqui o video vira MP4 (H.264 + AAC, lado maior ate 1280 = 720p, com
faststart) e sai pelo MESMO envio de video do chat (zapi.enviar_video, que a Socia ligou em 23/10), com a
legenda assinada. Fica no chat como mensagem tipo 'video', igual ao video anexado pelo "+".
Rota separada: nao mexe no /midia, no /audio nem no resto do atendimento.py.
"""
import asyncio
import os
import subprocess
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..deps import usuario_atual
from ..whatsapp import zapi
from ..whatsapp.models import Conversa, Mensagem, NumeroWhatsapp

router = APIRouter(prefix="/api/atendimento", tags=["video-gravado"])

MEDIA_DIR = "/opt/sistema/media"
TETO_WHATSAPP = 16 * 1024 * 1024        # o WhatsApp toca video ate uns 16 MB
TETO_ENTRADA = 120 * 1024 * 1024        # gravacao bruta aceita (o nginx limita antes, se for menor)
MAX_SEGUNDOS = 180
FFMPEG = "/usr/bin/ffmpeg" if os.path.exists("/usr/bin/ffmpeg") else "ffmpeg"
ESCALA = "scale='if(gt(iw,ih),min({l},iw),-2)':'if(gt(iw,ih),-2,min({l},ih))'"


def _converter(entrada, saida, lado, crf):
    cmd = [FFMPEG, "-y", "-i", entrada, "-t", str(MAX_SEGUNDOS), "-vf", ESCALA.format(l=lado),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-profile:v", "main", "-pix_fmt", "yuv420p",
           "-r", "30", "-c:a", "aac", "-b:a", "96k", "-ac", "1", "-movflags", "+faststart", saida]
    r = subprocess.run(cmd, capture_output=True, timeout=300)
    return r.returncode == 0 and os.path.exists(saida) and os.path.getsize(saida) > 0


@router.post("/conversas/{conversa_id}/video-gravado")
async def enviar_video_gravado(conversa_id: int, arquivo: UploadFile = File(...), caption: str = Form(""),
                               user=Depends(usuario_atual), db: AsyncSession = Depends(get_db)):
    conv = (await db.execute(select(Conversa).where(Conversa.id == conversa_id))).scalar_one_or_none()
    if not conv:
        raise HTTPException(404, "Conversa nao encontrada")
    numero = (await db.execute(select(NumeroWhatsapp).where(NumeroWhatsapp.id == conv.numero_id))).scalar_one_or_none()
    raw = await arquivo.read()
    if not raw:
        raise HTTPException(400, "O video chegou vazio. Grave de novo.")
    if len(raw) > TETO_ENTRADA:
        raise HTTPException(413, "Gravacao grande demais. Grave um video mais curto.")
    os.makedirs(MEDIA_DIR, exist_ok=True)
    base = "vid_" + uuid.uuid4().hex[:12]
    tmp, mp4 = f"{MEDIA_DIR}/{base}.in", f"{MEDIA_DIR}/{base}.mp4"
    with open(tmp, "wb") as fp:
        fp.write(raw)
    try:
        ok = await asyncio.to_thread(_converter, tmp, mp4, 1280, 28)   # lado maior ate 1280 (720p)
        if ok and os.path.getsize(mp4) > TETO_WHATSAPP:          # passou de 16 MB: tenta menor antes de desistir
            ok = await asyncio.to_thread(_converter, tmp, mp4, 854, 32)
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass
    if not ok:
        raise HTTPException(500, "Nao consegui converter o video. Grave de novo.")
    tam = os.path.getsize(mp4)
    if tam > TETO_WHATSAPP:
        os.remove(mp4)
        raise HTTPException(413, "O video ficou com %.1f MB e o WhatsApp toca ate 16 MB. Grave um video mais curto."
                            % (tam / 1048576.0))
    url = f"https://seu-dominio.com.br/media/{base}.mp4"
    enviado, info = await asyncio.to_thread(zapi.enviar_video, numero, conv.contato_telefone, url,
                                            caption, zapi.nome_assinatura(user))
    if not enviado:
        raise HTTPException(502, f"O WhatsApp nao aceitou o video: {info}")
    db.add(Mensagem(conversa_id=conversa_id, origem="atendente", autor=user.email,
                    tipo="video", conteudo=caption, midia_url=url, remote_id=(info or "")))
    conv.ia_ativa = False
    conv.ultima_mensagem = (caption or "[video]")[:300]
    conv.atualizado_em = datetime.utcnow()
    await db.commit()
    return {"ok": True, "url": url, "mb": round(tam / 1048576.0, 1)}
