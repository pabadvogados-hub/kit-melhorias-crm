"""Captura das intimacoes do DJEN para int_intimacoes.

Roda de duas formas:
- cron, sozinho na VPS (sem depender do computador de ninguem):
      cd /opt/<projeto>/backend && python -m app.intimacoes.captura
- botao "Capturar agora" da tela (so administrador), que chama rodar() em segundo plano.

Garantias:
- IDEMPOTENTE: a chave unica e' o id/hash da comunicacao no DJEN. Rodar de novo nao duplica.
  Intimacao ja conferida ou descartada nunca volta a 'nova' (a captura so insere).
- Cada rodada, por OAB, vai para int_capturas com resultado, tentativas e o log da instabilidade.
  "incompleta" quer dizer: a API nao respondeu com dados depois do orcamento de tentativas.
  Nunca vira "sem intimacoes". A proxima rodada refaz a consulta.
- --simular: consulta e classifica, mas nao grava nada (nem int_capturas).

Codigo de saida do CLI: 0 = tudo conclusivo; 2 = alguma OAB ficou incompleta (o cron pode alertar).
"""
import argparse
import asyncio
import json
import sys
from datetime import date, datetime, timedelta

from sqlalchemy import text

from . import classificador, djen, prazos_uteis, schema, servico


def _agora() -> datetime:
    return datetime.utcnow()


def _hoje_brt() -> date:
    return (datetime.utcnow() - timedelta(hours=3)).date()


def _iso(d):
    return d.isoformat() if d else None


def preparar(norm: dict) -> dict:
    """Classificacao e datas do prazo a partir do item normalizado. Puro: sem banco."""
    cl = classificador.classificar(norm['texto'])
    disp = norm['disponibilizada']
    if disp:
        cal = prazos_uteis.calcular(disp, cl['prazo_dias'])
    else:
        cal = {'publicada_em': None, 'inicio_prazo': None, 'data_fatal': None,
               'alertas': ['Data de disponibilizacao ausente na resposta: prazo nao calculado.']}
    return {**norm, 'tipo_ato': cl['tipo_ato'], 'rotulo_ato': cl['rotulo'],
            'prazo_dias': cl['prazo_dias'], 'prazo_origem': cl['prazo_origem'],
            'publicada_em': cal['publicada_em'], 'inicio_prazo': cal['inicio_prazo'],
            'data_fatal': cal['data_fatal'], 'alertas': cl['alertas'] + cal['alertas']}


_INSERT = text(
    """INSERT INTO int_intimacoes (chave_externa, oab, numero_processo, numero_limpo, tribunal,
           orgao, tipo_comunicacao, texto, link, disponibilizada_em, publicada_em, inicio_prazo,
           tipo_ato, rotulo_ato, prazo_dias, prazo_origem, data_fatal, alertas, status,
           processo_id, capturada_em)
       VALUES (:chave_externa, :oab, :numero_processo, :numero_limpo, :tribunal, :orgao,
           :tipo_comunicacao, :texto, :link, :disponibilizada_em, :publicada_em, :inicio_prazo,
           :tipo_ato, :rotulo_ato, :prazo_dias, :prazo_origem, :data_fatal, :alertas, 'nova',
           :processo_id, :capturada_em)
       ON CONFLICT(chave_externa) DO NOTHING""")


async def capturar_oab(db, fonte, numero: str, uf: str, ini: date, fim: date, *,
                       gravar: bool, sleep, origem: str, por: str) -> dict:
    iniciada = _agora()
    oab = f'{numero}/{uf}'
    rb = await fonte.buscar_periodo(numero, uf, ini, fim, sleep=sleep)
    out = {'oab': oab, 'resultado': rb.status, 'recebidas': len(rb.itens), 'novas': 0,
           'ja_existiam': 0, 'tentativas': rb.tentativas, 'ocupados': rb.ocupados,
           'vazios': rb.vazios, 'previa': []}
    if rb.status in ('ok', 'vazio_confirmado'):
        for it in rb.itens:
            norm = djen.normalizar_item(it, oab)
            if not norm:
                continue
            existe = (await db.execute(text(
                'SELECT 1 FROM int_intimacoes WHERE chave_externa = :c'),
                {'c': norm['chave_externa']})).first() is not None
            if existe:
                out['ja_existiam'] += 1
                continue
            prep = preparar(norm)
            if not gravar:
                out['novas'] += 1
                out['previa'].append({'processo': prep['numero_processo'],
                                      'tipo_ato': prep['rotulo_ato'], 'prazo_dias': prep['prazo_dias'],
                                      'data_fatal': _iso(prep['data_fatal'])})
                continue
            processo_id = await servico.processo_id_para(db, prep['numero_processo'])
            res = await db.execute(_INSERT, {
                'chave_externa': prep['chave_externa'], 'oab': oab,
                'numero_processo': prep['numero_processo'], 'numero_limpo': prep['numero_limpo'],
                'tribunal': prep['tribunal'], 'orgao': prep['orgao'],
                'tipo_comunicacao': prep['tipo_comunicacao'], 'texto': prep['texto'],
                'link': prep['link'], 'disponibilizada_em': _iso(prep['disponibilizada']),
                'publicada_em': _iso(prep['publicada_em']), 'inicio_prazo': _iso(prep['inicio_prazo']),
                'tipo_ato': prep['tipo_ato'], 'rotulo_ato': prep['rotulo_ato'],
                'prazo_dias': prep['prazo_dias'], 'prazo_origem': prep['prazo_origem'],
                'data_fatal': _iso(prep['data_fatal']),
                'alertas': json.dumps(prep['alertas'], ensure_ascii=False),
                'processo_id': processo_id, 'capturada_em': servico._txt(_agora())})
            if res.rowcount == 1:
                out['novas'] += 1
            else:
                out['ja_existiam'] += 1
    if gravar:
        await db.execute(text(
            """INSERT INTO int_capturas (iniciada_em, terminada_em, origem, por, oab, janela_ini,
                   janela_fim, resultado, recebidas, novas, ja_existiam, tentativas, ocupados,
                   vazios, detalhe)
               VALUES (:ini, :fim, :origem, :por, :oab, :jini, :jfim, :res, :rec, :nov, :ja,
                   :tent, :oc, :vz, :det)"""),
            {'ini': servico._txt(iniciada), 'fim': servico._txt(_agora()), 'origem': origem,
             'por': por[:200], 'oab': oab, 'jini': ini.isoformat(), 'jfim': fim.isoformat(),
             'res': rb.status, 'rec': out['recebidas'], 'nov': out['novas'],
             'ja': out['ja_existiam'], 'tent': rb.tentativas, 'oc': rb.ocupados,
             'vz': rb.vazios, 'det': json.dumps(rb.log[-80:], ensure_ascii=False)[:4000]})
        await db.commit()
    return out


async def rodar(db, *, fonte=None, dias: int = 3, extras=(), gravar: bool = True,
                origem: str = 'cron', por: str = 'cron', sleep=asyncio.sleep,
                hoje: date | None = None) -> dict:
    """Consulta todas as OABs ativas na janela (hoje - dias ... hoje)."""
    fonte = fonte or djen.FonteDJEN()
    hoje = hoje or _hoje_brt()
    ini = hoje - timedelta(days=max(1, min(int(dias), 30)))
    oabs = await servico.oabs_ativas(db, extras)
    out = {'janela': [ini.isoformat(), hoje.isoformat()], 'simulada': not gravar,
           'oabs': [], 'aviso': '', 'incompletas': 0}
    if not oabs:
        out['aviso'] = ('Nenhuma OAB cadastrada. Cadastre na tela de Intimações (ou em INT_OABS '
                        'no .env). Nada foi consultado.')
        return out
    for numero, uf in oabs:
        r = await capturar_oab(db, fonte, numero, uf, ini, hoje, gravar=gravar, sleep=sleep,
                               origem=origem, por=por)
        out['oabs'].append(r)
        if r['resultado'] in ('incompleta', 'erro'):
            out['incompletas'] += 1
    return out


# ----------------------------------------------------------------- CLI (cron)

def _args():
    ap = argparse.ArgumentParser(description='Captura intimacoes do DJEN (CNJ).')
    ap.add_argument('--dias', type=int, default=3, help='janela ate hoje, em dias (padrao 3)')
    ap.add_argument('--oab', action='append', default=[], help='OAB extra NUMERO/UF (repetivel)')
    ap.add_argument('--simular', action='store_true',
                    help='consulta e classifica, sem gravar nada')
    return ap.parse_args()


def _imprimir(out: dict) -> None:
    print(f"janela {out['janela'][0]} a {out['janela'][1]}"
          + (' (SIMULACAO, nada gravado)' if out['simulada'] else ''))
    if out['aviso']:
        print(out['aviso'])
    for o in out['oabs']:
        print(f"  {o['oab']}: {o['resultado']} | recebidas {o['recebidas']} | novas {o['novas']} "
              f"| ja existiam {o['ja_existiam']} | tentativas {o['tentativas']} "
              f"(ocupado {o['ocupados']}, vazio {o['vazios']})")
        for p in o['previa']:
            print(f"      previa: {p['processo']} | {p['tipo_ato']} | prazo {p['prazo_dias']} | "
                  f"fatal sugerida {p['data_fatal']}")
    if out['incompletas']:
        print(f"ATENCAO: {out['incompletas']} OAB(s) nao concluiram. A proxima rodada refaz a consulta.")


async def _main(a) -> int:
    from ..config import settings          # configuracao do sistema (.env)
    from ..database import AsyncSessionLocal

    extras = [getattr(settings, 'INT_OABS', '')] + list(a.oab)
    fonte = (djen.ProvedorAlternativo() if getattr(settings, 'INT_PROVEDOR_ALTERNATIVO', False)
             else djen.FonteDJEN())
    origem = 'manual' if sys.stdin and sys.stdin.isatty() else 'cron'
    async with AsyncSessionLocal() as db:
        await schema.garantir_tabelas(db)
        out = await rodar(db, fonte=fonte, dias=a.dias, extras=extras, gravar=not a.simular,
                          origem=origem, por=origem)
    _imprimir(out)
    return 2 if out['incompletas'] else 0


if __name__ == '__main__':
    sys.exit(asyncio.run(_main(_args())))
