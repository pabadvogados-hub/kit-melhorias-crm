"""Painel comercial ao vivo: leads, contratos e mesa de cada pessoa, lidos do proprio CRM.

Destino: backend/app/routers/comercial.py (ver INSTRUCOES_CLAUDE.md).

PARA QUE SERVE
--------------
Responde, a qualquer hora e sem planilha: quantos leads chegaram, quantos foram
respondidos, quantos contratos foram assinados, o que esta parado e com quem.
Tudo e lido do banco do CRM no momento em que a tela abre. Nada e gravado para
depois, e nada e estimado: o que o CRM nao sabe medir sai listado em AVISOS.

DE ONDE SAI CADA NUMERO
-----------------------
- LEAD: conversa cuja PRIMEIRA fala do contato (wa_mensagens.origem = 'contato')
  caiu no periodo. E a mesma regra da Analise de leads (relatorios._medir), para
  os dois paineis baterem. Fica de fora: grupo; conversa importada (o historico
  de antes do sistema nao tem a primeira fala de verdade); e quadro fora do funil
  (clientes do escritorio e contatos gerais, ver quadros_fora_do_funil).
- RESPONDIDO: o lead recebeu resposta da IA ou da equipe depois da primeira fala.
  RESPONDIDO PELA EQUIPE: a mesma coisa, so com mensagens de origem 'atendente'.
- FECHADO: contrato com assinatura confirmada. Conta pela data da assinatura,
  com a MESMA nota que a Analise de leads usa (esteira ou "confirmado na pasta").
  Decisao de quem administra o escritorio: contrato so conta depois de assinado.
  Opcional: fechado_conta_etapa = true soma tambem quem esta em ELABORACAO DE
  CONTRATO / ASSINATURA DE CONTRATO (ou tipo de contato 'cliente') sem assinatura,
  pela data em que entrou nessa coluna. Padrao: desligado.
- FECHADO DE LEADS DO PERIODO: dos leads que chegaram no periodo, quantos ja
  assinaram ate hoje. E a conversao de verdade (coorte). Nao se divide fechados
  do mes por leads do mes: sao populacoes diferentes.
- EM FECHAMENTO (agora): sem assinatura, numa coluna de elaboracao/assinatura de
  contrato. Foto do momento, nao depende do periodo.
- PERDIDO: card que entrou (etapa_desde no periodo) numa coluna de perda
  (desqualificado, nao seguiu, perdido). Mais as conversas apagadas pela limpeza
  automatica, quando a tabela wa_leads_apagados_log existir.
- PARADO: card aberto, dentro do funil, numa coluna que nao e de perda nem de
  encerramento, sem mudar de coluna ha N dias (etapa_desde; se vazio, a data do
  primeiro contato). N vem de parado_dias_padrao ou do parametro dias_parado.
- TEMPO ATE A 1A RESPOSTA: mediana, em minutos, dos leads do periodo que tiveram
  resposta. Duas medidas: IA ou equipe, e so equipe.
- CUSTO: gasto gravado em rl_anuncios (o mesmo bloco que a Analise de leads usa),
  somando as linhas diarias da janela. Sem bloco que cubra o periodo, nao aparece.
- RECEITA ESTIMADA: fechados x ticket configurado por quadro. O campo valor do CRM
  fica zerado, entao sem ticket configurado a receita nao aparece.
- COMISSAO: valor fixo por fechamento, so se comissao_fixa_por_fechamento.ativa
  for true. Padrao desligado.
- LIGACOES: o CRM nao guarda ligacao de forma estruturada. So conta se
  marca_ligacao estiver preenchida e a equipe escrever essa marca no comeco de
  uma nota ao ligar. Sem marca, a secao fica como "nao medido".

PERIODOS
--------
hoje, semana (segunda a agora), mes (dia 1 a agora), mes_anterior (mes inteiro
passado) e 15dias (14 dias para tras mais hoje). Horario de Brasilia (UTC-3, sem
horario de verao desde 2019). O banco guarda UTC: a conversao acontece na carga.

ESCOPO
------
- Administrador ve tudo (painel completo, mesa de todos, funil e perdas).
- Quem nao e administrador ve so a propria mesa (minha-mesa). Se o usuario tiver
  areas_permitidas, so as conversas dessas areas (campo tag) entram nos numeros,
  igual ao que o Chat/CRM ja mostra para essa pessoa.

PERFORMANCE
-----------
A carga le o CRM inteiro uma vez por consulta (conversas, primeiras falas,
primeiras respostas, notas de assinatura) e calcula tudo em memoria. Para algo
da ordem de milhares de conversas isso e rapido. Se um dia ficar lento, o
ponto a trocar e _carregar, nao as contas.

O QUE ESTE PAINEL NAO SABE
--------------------------
- Valor de venda: o campo valor do CRM nao e preenchido. Receita so como estimativa.
- Ligacoes: sem registro estruturado (ver LIGACOES acima).
- Historico de colunas: parado e perdido usam a coluna ATUAL e a data em que o card
  entrou nela. Card que foi para perda e voltou nao aparece como perdido.
- Motivo da perda: o motivo e o nome da coluna onde o card parou.
- Quem atribuiu o lead: so a dona atual (atendente_email) e conhecida.
"""
import json
import re
import statistics
import unicodedata
from datetime import date, datetime, time, timedelta
from collections import Counter
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..deps import requer_admin, usuario_atual

router = APIRouter(prefix='/api/comercial', tags=['comercial'])

# Metas e premissas. Arquivo na raiz do backend (ao lado de app/), lido a cada consulta:
# editou, a tela ja mostra. Ver comercial_metas.json e INSTRUCOES_CLAUDE.md.
METAS_ARQ = Path(__file__).resolve().parents[2] / 'comercial_metas.json'

DIFERENCA_BRASILIA = timedelta(hours=3)   # UTC-3, sem horario de verao desde 2019

PERIODOS = [('hoje', 'Hoje'), ('semana', 'Esta semana'), ('mes', 'Este mês'),
            ('mes_anterior', 'Mês anterior'), ('15dias', 'Últimos 15 dias')]
PERIODOS_VALIDOS = {chave for chave, _ in PERIODOS}

METRICAS = {'leads', 'respondidos', 'sem_resposta', 'fechados', 'fechados_de_leads',
            'em_fechamento', 'perdidos', 'parados', 'etapa'}

# AJUSTAR se algum quadro tiver os nomes de coluna renomeados.
RE_EM_FECHAMENTO = re.compile(r'elabora[cç][aã]o\s+(de\s+)?contrato|assinatura\s+de\s+contrato', re.I)
RE_PERDA = re.compile(r'desqualificad|n[aã]o\s+seguiu|perdid', re.I)
RE_ENCERRADA = re.compile(r'encerrad|finalizad|conclu[ií]d', re.I)

# Notas que confirmam a assinatura. Os mesmos textos que a Analise de leads usa.
# AJUSTAR se a esteira gravar outro texto.
NOTA_ASSINATURA_A = 'Esteira de contratação: contrato assinado em%'
NOTA_ASSINATURA_B = 'Contrato assinado — confirmado na pasta%'

DEFAULTS = {
    'quadros_fora_do_funil': ['CLIENTES ESCRITÓRIO', 'CLIENTES DO ESCRITÓRIO', 'CONTATOS GERAIS'],
    'parado_dias_padrao': 7,
    'fechado_conta_etapa': False,
    'feriados': [],
    'metas_mensais': {},
    'ticket_medio_por_area': {},
    'comissao_fixa_por_fechamento': {'ativa': False, 'valor': None, 'por_pessoa': {}},
    'marca_ligacao': '',
}


# ----------------------------------------------------------------- utilidades
def _sem_acento(texto) -> str:
    return unicodedata.normalize('NFKD', str(texto or '')).encode('ascii', 'ignore').decode().lower().strip()


def _config() -> dict:
    """Le comercial_metas.json. Chave que comeca com '_' e comentario e nao entra na conta."""
    try:
        bruto = json.loads(METAS_ARQ.read_text(encoding='utf-8'))
    except FileNotFoundError:
        bruto = {}
    except json.JSONDecodeError as e:
        raise HTTPException(500, f'comercial_metas.json com erro de sintaxe (linha {e.lineno}): {e.msg}')
    return {**DEFAULTS, **{k: v for k, v in bruto.items() if not str(k).startswith('_')}}


def _agora(agora=None) -> datetime:
    """Instante da consulta em Brasilia, sem fuso. O parametro existe para o teste."""
    return agora or (datetime.utcnow() - DIFERENCA_BRASILIA)


def _para_brasilia(valor):
    """Valor do banco (UTC, texto ou datetime) -> datetime de Brasilia, sem fuso."""
    if valor is None or valor == '':
        return None
    if isinstance(valor, str):
        valor = datetime.fromisoformat(valor.replace('T', ' ').rstrip('Z'))
    return valor.replace(tzinfo=None) - DIFERENCA_BRASILIA


def _para_utc(valor: datetime) -> datetime:
    return valor + DIFERENCA_BRASILIA


def _iso_utc(valor):
    """Brasilia -> ISO em UTC com 'Z', o mesmo formato que o resto do CRM devolve."""
    return (valor + DIFERENCA_BRASILIA).isoformat() + 'Z' if valor else None


def _num(valor) -> float:
    try:
        return float(str(valor).replace(',', '.')) if valor not in (None, '') else 0.0
    except (TypeError, ValueError):
        return 0.0


def _mediana(valores):
    valores = [v for v in valores if v is not None and v >= 0]
    return round(statistics.median(valores), 1) if valores else None


def _periodo_valido(periodo: str) -> str:
    if periodo not in PERIODOS_VALIDOS:
        raise HTTPException(400, f"periodo invalido. Use: {', '.join(sorted(PERIODOS_VALIDOS))}")
    return periodo


def janela(periodo: str, agora: datetime):
    """(inicio, fim) em Brasilia. Fim exclusivo. Veja o cabecalho para o significado de cada um."""
    hoje = agora.date()

    def dia(d: date) -> datetime:
        return datetime.combine(d, time.min)

    if periodo == 'hoje':
        return dia(hoje), agora
    if periodo == 'semana':
        return dia(hoje - timedelta(days=hoje.weekday())), agora
    if periodo == 'mes':
        return dia(hoje.replace(day=1)), agora
    if periodo == 'mes_anterior':
        primeiro_atual = hoje.replace(day=1)
        return dia((primeiro_atual - timedelta(days=1)).replace(day=1)), dia(primeiro_atual)
    if periodo == '15dias':
        return dia(hoje - timedelta(days=14)), agora
    raise HTTPException(400, f'periodo invalido: {periodo}')


def _mes_de(ini: datetime, fim: datetime) -> str:
    """Mes de referencia da meta: o mes em que o periodo termina."""
    return (fim - timedelta(seconds=1)).strftime('%Y-%m')


def _limites_do_mes(mes_ref: str):
    ano, mes = (int(p) for p in mes_ref.split('-'))
    ini = datetime(ano, mes, 1)
    fim = datetime(ano + (mes == 12), mes % 12 + 1, 1)
    return ini, fim


def _dias_uteis(ini: date, fim: date, feriados: set) -> int:
    """Dias uteis entre ini e fim, os dois inclusive. Sabado e domingo nao contam."""
    total, d = 0, ini
    while d <= fim:
        if d.weekday() < 5 and d.isoformat() not in feriados:
            total += 1
        d += timedelta(days=1)
    return total


def _areas_de(user) -> set | None:
    """Areas que a pessoa ve. Administrador e quem nao tem recorte: None (ve tudo)."""
    if getattr(user, 'papel', '') == 'admin':
        return None
    crus = [a for a in (getattr(user, 'areas_permitidas', '') or '').split(',') if a.strip()]
    return {_sem_acento(a) for a in crus} or None


def _no_escopo(r: dict, pessoa, areas) -> bool:
    if pessoa and r['dona'] != pessoa:
        return False
    if areas is not None and _sem_acento(r['tag']) not in areas:
        return False
    return True


# ----------------------------------------------------------------- carga
async def _carregar(db: AsyncSession, cfg: dict, agora: datetime) -> dict:
    """Le o CRM uma vez. Devolve uma lista de registros (uma por conversa), com as
    datas ja em Brasilia, e as listas auxiliares que as contas precisam."""
    quadros = (await db.execute(text('SELECT id, nome FROM wa_pipelines ORDER BY ordem, id'))).all()
    fora = {_sem_acento(n) for n in cfg['quadros_fora_do_funil']}
    nome_quadro = {pid: nome for pid, nome in quadros}
    no_funil = {pid for pid, nome in quadros if _sem_acento(nome) not in fora}

    etapas = {}
    for pid, nome, ordem in (await db.execute(text(
            'SELECT pipeline_id, nome, ordem FROM wa_stages ORDER BY pipeline_id, ordem'))).all():
        etapas.setdefault(pid, []).append(nome)

    # Primeira fala, primeira resposta (IA ou equipe) e primeira resposta humana, por conversa.
    linhas = (await db.execute(text("""
        SELECT c.id, fc.t,
          (SELECT MIN(m.criado_em) FROM wa_mensagens m
             WHERE m.conversa_id = c.id AND m.origem IN ('atendente', 'ia') AND m.criado_em > fc.t),
          (SELECT MIN(m.criado_em) FROM wa_mensagens m
             WHERE m.conversa_id = c.id AND m.origem = 'atendente' AND m.criado_em > fc.t)
        FROM wa_conversas c
        LEFT JOIN (SELECT conversa_id, MIN(criado_em) AS t FROM wa_mensagens
                   WHERE origem = 'contato' GROUP BY conversa_id) fc ON fc.conversa_id = c.id
    """))).all()
    temporal = {cid: (pc, ia_eq, humana) for cid, pc, ia_eq, humana in linhas}

    assinados = {cid: t for cid, t in (await db.execute(text(
        "SELECT conversa_id, MIN(criado_em) FROM wa_mensagens WHERE origem = 'nota' "
        "AND (conteudo LIKE :a OR conteudo LIKE :b) GROUP BY conversa_id"),
        {'a': NOTA_ASSINATURA_A, 'b': NOTA_ASSINATURA_B})).all()}

    importadas = {cid for (cid,) in (await db.execute(text(
        "SELECT DISTINCT conversa_id FROM wa_mensagens WHERE origem = 'nota' AND autor = '(importacao)'"))).all()}

    convs = (await db.execute(text(
        "SELECT id, pipeline_id, contato_nome, tag, etapa, etapa_desde, status, tipo_contato, "
        "atendente_email, eh_grupo FROM wa_conversas"))).mappings().all()

    registros = []
    for c in convs:
        cid = c['id']
        pc, ia_eq, humana = temporal.get(cid, (None, None, None))
        r = {
            'id': cid,
            'pid': c['pipeline_id'],
            'nome': (c['contato_nome'] or '(sem nome)').strip()[:80],
            'quadro': nome_quadro.get(c['pipeline_id'], '(sem quadro)'),
            'tag': c['tag'] or '',
            'funil': c['pipeline_id'] in no_funil,
            'etapa': c['etapa'] or '',
            'etapa_desde': _para_brasilia(c['etapa_desde']),
            'aberta': (c['status'] or 'aberto') != 'fechado',
            'dona': (c['atendente_email'] or '').strip().lower(),
            'tipo': c['tipo_contato'] or 'lead',
            'grupo': bool(c['eh_grupo']),
            'importada': cid in importadas,
            'primeiro_contato': _para_brasilia(pc),
            'primeira_resposta': _para_brasilia(ia_eq),
            'primeira_humana': _para_brasilia(humana),
            'assinado_em': _para_brasilia(assinados.get(cid)),
        }
        r['lead'] = bool(r['funil'] and not r['grupo'] and not r['importada'] and r['primeiro_contato'])
        r['em_fechamento'] = bool(not r['assinado_em'] and not r['grupo'] and (
            RE_EM_FECHAMENTO.search(r['etapa']) or (r['tipo'] == 'cliente' and r['funil'])))
        r['perda'] = bool(r['funil'] and RE_PERDA.search(r['etapa']))
        r['encerrada'] = bool(RE_ENCERRADA.search(r['etapa']))
        registros.append(r)

    desde = _para_utc(janela('mes_anterior', agora)[0])   # menor janela usada: so o que cabe nela
    respostas_equipe = [(a.strip().lower(), _para_brasilia(t)) for a, t in (await db.execute(text(
        "SELECT autor, criado_em FROM wa_mensagens WHERE origem = 'atendente' AND criado_em >= :d"),
        {'d': desde.isoformat(' ')})).all()]

    ligacoes = []
    if cfg['marca_ligacao']:
        ligacoes = [(a.strip().lower(), _para_brasilia(t)) for a, t in (await db.execute(text(
            "SELECT autor, criado_em FROM wa_mensagens WHERE origem = 'nota' "
            "AND conteudo LIKE :m AND criado_em >= :d"),
            {'m': cfg['marca_ligacao'] + '%', 'd': desde.isoformat(' ')})).all()]

    apagados = []
    existe = (await db.execute(text(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'wa_leads_apagados_log'"))).first()
    if existe:
        apagados = [(_para_brasilia(t), bool(cli)) for t, cli in (await db.execute(text(
            "SELECT entrou_em, virou_cliente FROM wa_leads_apagados_log WHERE entrou_em >= :d"),
            {'d': desde.isoformat(' ')})).all()]

    return {'registros': registros, 'quadros': [(pid, nome) for pid, nome in quadros if pid in no_funil],
            'etapas': etapas, 'respostas_equipe': respostas_equipe, 'ligacoes': ligacoes,
            'apagados': apagados}


async def _gasto(db: AsyncSession, ini: datetime, fim: datetime):
    """Gasto com anuncio no periodo, do bloco gravado em rl_anuncios que cubra a janela."""
    de, ate = ini.date(), (fim - timedelta(seconds=1)).date()
    bloco = (await db.execute(text(
        "SELECT de, ate, dados, criado_em FROM rl_anuncios WHERE de <= :de AND ate >= :ate "
        "ORDER BY criado_em DESC LIMIT 1"), {'de': de.isoformat(), 'ate': ate.isoformat()})).first()
    if not bloco:
        return None
    dados = json.loads(bloco.dados or '{}')
    total, dias = 0.0, set()
    for linha in dados.get('linhas', []):
        dia = str(linha.get('date') or '')[:10]
        if de.isoformat() <= dia <= ate.isoformat():
            total += _num(linha.get('spend'))
            dias.add(dia)
    if not dias:
        return None
    return {'gasto': round(total, 2), 'cobre_de': str(bloco.de), 'cobre_ate': str(bloco.ate),
            'dias_com_dado': len(dias), 'gravado_em': str(bloco.criado_em) + 'Z'}


# ----------------------------------------------------------------- recortes
def _fechados(regs, ini, fim, cfg):
    saida = [r for r in regs if r['assinado_em'] and ini <= r['assinado_em'] < fim]
    if cfg['fechado_conta_etapa']:
        saida += [r for r in regs if r['em_fechamento'] and r['etapa_desde']
                  and ini <= r['etapa_desde'] < fim]
    return saida


def _dias_parado(r, agora, dias):
    if not r['funil'] or not r['aberta'] or r['perda'] or r['encerrada'] or r['grupo']:
        return None
    referencia = r['etapa_desde'] or r['primeiro_contato']
    if not referencia:
        return None
    parados = (agora - referencia).days
    return parados if parados >= dias else None


def _recortes(regs, ini, fim, agora, cfg, dias) -> dict:
    """Todas as listas que os numeros usam. A tela e o drill-down saem daqui: mesmo numero, mesma lista."""
    leads = [r for r in regs if r['lead'] and ini <= r['primeiro_contato'] < fim]
    perdidos = [r for r in regs if r['perda'] and r['etapa_desde'] and ini <= r['etapa_desde'] < fim]
    return {
        'leads': leads,
        'respondidos': [r for r in leads if r['primeira_resposta']],
        'sem_resposta': [r for r in leads if not r['primeira_resposta']],
        'fechados': _fechados(regs, ini, fim, cfg),
        'fechados_de_leads': [r for r in leads if r['assinado_em']],
        'em_fechamento': [r for r in regs if r['em_fechamento']],
        'perdidos': perdidos,
        'parados': [r for r in regs if _dias_parado(r, agora, dias) is not None],
    }


def _ticket(cfg, quadro):
    tabela = {_sem_acento(k): v for k, v in (cfg.get('ticket_medio_por_area') or {}).items()
              if not str(k).startswith('_')}
    valor = tabela.get(_sem_acento(quadro))
    return _num(valor) if valor else None


def _linha(r: dict) -> dict:
    return {'id': r['id'], 'nome': r['nome'], 'quadro': r['quadro'], 'etapa': r['etapa'],
            'dona': r['dona'] or None, 'tipo': r['tipo'],
            'primeiro_contato': _iso_utc(r['primeiro_contato']),
            'primeira_resposta': _iso_utc(r['primeira_resposta']),
            'etapa_desde': _iso_utc(r['etapa_desde']),
            'assinado_em': _iso_utc(r['assinado_em'])}


def _meta_mes(cfg, mes_ref):
    bloco = (cfg.get('metas_mensais') or {}).get(mes_ref) or {}
    return bloco.get('fechados'), bloco.get('por_pessoa_fechados') or {}


def _ritmo(meta, realizado, agora, mes_ref, feriados):
    """Projecao e ritmo do mes. So faz sentido para o mes em curso."""
    ini, fim = _limites_do_mes(mes_ref)
    ini_d, fim_d = ini.date(), (fim - timedelta(days=1)).date()
    total = _dias_uteis(ini_d, fim_d, feriados)
    base = {'mes': mes_ref, 'meta': meta, 'realizado': realizado, 'dias_uteis_total': total}
    if mes_ref != agora.strftime('%Y-%m'):
        return {**base, 'disponivel': False}
    hoje = agora.date()
    decorridos = _dias_uteis(ini_d, min(hoje, fim_d), feriados)
    restantes = _dias_uteis(hoje + timedelta(days=1), fim_d, feriados) if hoje < fim_d else 0
    projecao = round(realizado / decorridos * total, 1) if decorridos else None
    if meta is None:
        necessario = None
    elif meta - realizado <= 0:
        necessario = 0
    elif restantes:
        necessario = round((meta - realizado) / restantes, 2)
    else:
        necessario = None
    return {**base, 'disponivel': True, 'dias_uteis_decorridos': decorridos,
            'dias_uteis_restantes': restantes, 'ritmo_atual_por_dia':
            round(realizado / decorridos, 2) if decorridos else None,
            'projecao': projecao, 'necessario_por_dia': necessario,
            'no_ritmo': (projecao >= meta) if (projecao is not None and meta) else None}


def _avisos(cfg) -> list:
    avisos = [
        'Valor de venda: o CRM nao registra. Receita so aparece como estimativa, com o ticket configurado.',
        'Lead e resposta usam a primeira fala do contato. Conversa importada (historico de antes do sistema) fica de fora.',
        'Quadros fora do funil (clientes do escritorio e contatos gerais) nao entram em nenhum numero de lead.',
        'Parado e perdido usam a coluna atual e a data em que o card entrou nela. Movimentos anteriores nao aparecem.',
    ]
    if cfg['fechado_conta_etapa']:
        avisos.append('Fechado inclui quem esta em elaboracao ou assinatura de contrato sem assinatura confirmada (fechado_conta_etapa).')
    else:
        avisos.append('Fechado = contrato com assinatura confirmada. Quem esta na etapa de contrato sem assinatura aparece em Em fechamento.')
    if not cfg['marca_ligacao']:
        avisos.append('Ligacoes nao medidas: o CRM nao guarda ligacao de forma estruturada. Configure marca_ligacao para contar.')
    return avisos


# ----------------------------------------------------------------- montagem
async def montar_painel(db: AsyncSession, *, periodo='mes', agora=None, pessoa=None, areas=None,
                        dias_parado=None, completo=True) -> dict:
    """Monta o painel. completo=False devolve so a parte pessoal (minha-mesa)."""
    cfg = _config()
    agora = _agora(agora)
    dias = dias_parado or cfg['parado_dias_padrao']
    ini, fim = janela(periodo, agora)
    base = await _carregar(db, cfg, agora)
    regs = [r for r in base['registros'] if _no_escopo(r, pessoa, areas)]
    R = _recortes(regs, ini, fim, agora, cfg, dias)

    # --- resumo do periodo
    leads, resp, humana = R['leads'], R['respondidos'], [r for r in R['leads'] if r['primeira_humana']]
    fech = R['fechados']
    receita, sem_ticket = 0.0, 0
    for r in fech:
        t = _ticket(cfg, r['quadro'])
        if t is None:
            sem_ticket += 1
        else:
            receita += t
    visao_time = not (pessoa or areas)   # limpeza automatica e custo de anuncio so existem na visao do time
    apagados_periodo = sum(1 for t, _ in base['apagados'] if t and ini <= t < fim) if visao_time else 0
    gasto = await _gasto(db, ini, fim) if visao_time else None

    resumo = {
        'leads': len(leads),
        'respondidos': len(resp),
        'taxa_resposta': round(100 * len(resp) / len(leads), 1) if leads else None,
        'respondidos_equipe': len(humana),
        'sem_resposta': len(R['sem_resposta']),
        'tempo_1a_resposta_min': _mediana([(r['primeira_resposta'] - r['primeiro_contato']).total_seconds() / 60 for r in resp]),
        'tempo_1a_resposta_equipe_min': _mediana([(r['primeira_humana'] - r['primeiro_contato']).total_seconds() / 60 for r in humana]),
        'fechados': len(fech),
        'fechados_de_leads_do_periodo': len(R['fechados_de_leads']),
        'taxa_fechamento_de_leads': round(100 * len(R['fechados_de_leads']) / len(leads), 1) if leads else None,
        'em_fechamento': len(R['em_fechamento']),
        'perdidos': len(R['perdidos']) + apagados_periodo,
        'parados': len(R['parados']),
        'receita_estimada': round(receita, 2) if (fech and sem_ticket < len(fech)) else None,
        'fechados_sem_ticket': sem_ticket,
        'gasto_anuncios': gasto['gasto'] if gasto else None,
        'custo_por_lead': round(gasto['gasto'] / len(leads), 2) if (gasto and leads) else None,
        'custo_por_fechamento': round(gasto['gasto'] / len(fech), 2) if (gasto and fech) else None,
    }

    # --- meta do mes de referencia e ritmo
    mes_ref = _mes_de(ini, fim)
    m_ini, m_fim = _limites_do_mes(mes_ref)
    meta_time, meta_por_pessoa = _meta_mes(cfg, mes_ref)
    fech_mes_time = _fechados(base['registros'], m_ini, m_fim, cfg)
    feriados = set(cfg['feriados'] or [])
    if pessoa:
        meta_atual = meta_por_pessoa.get(pessoa, None)
        realizado_mes = len([r for r in fech_mes_time if r['dona'] == pessoa])
    else:
        meta_atual = meta_time
        realizado_mes = len(fech_mes_time)
    meta = {'ritmo': _ritmo(meta_atual, realizado_mes, agora, mes_ref, feriados),
            'escopo': 'pessoa' if pessoa else 'time'}

    # --- parados por etapa
    parados_lista = sorted(((r, _dias_parado(r, agora, dias)) for r in R['parados']),
                           key=lambda x: -x[1])
    por_etapa_parado = Counter((r['quadro'], r['etapa']) for r, _ in parados_lista)
    paradas = {
        'dias': dias,
        'total': len(parados_lista),
        'por_etapa': [{'quadro': q, 'etapa': e, 'quantidade': n,
                       'dias_maximo': max(d for r, d in parados_lista if r['quadro'] == q and r['etapa'] == e)}
                      for (q, e), n in por_etapa_parado.most_common()],
        'mais_antigos': [{**_linha(r), 'dias_na_etapa': d} for r, d in parados_lista[:15]],
    }

    # --- perdas por motivo (o motivo e o nome da coluna)
    motivos = Counter(r['etapa'] for r in R['perdidos'])
    perdas = {
        'total': resumo['perdidos'],
        'por_motivo': [{'motivo': m, 'quantidade': n} for m, n in motivos.most_common()],
        'apagados_pela_limpeza': apagados_periodo if visao_time else None,
    }

    # --- ligacoes (so com marca_ligacao configurada)
    marca = bool(cfg['marca_ligacao'])
    ligacoes_pessoa = Counter(a for a, t in base['ligacoes'] if t and ini <= t < fim and (not pessoa or a == pessoa))
    ligacoes = {'medido': marca, 'total': sum(ligacoes_pessoa.values()) if marca else None}

    # --- comissao (so se ativa; valor fixo por fechamento)
    com = cfg['comissao_fixa_por_fechamento'] or {}
    comissao = None
    if com.get('ativa'):
        por_dona = Counter(r['dona'] for r in fech if r['dona'])
        comissao = {'ativa': True, 'valor_padrao': com.get('valor'),
                    'total_estimado': round(sum(
                        n * _num((com.get('por_pessoa') or {}).get(d, com.get('valor'))) for d, n in por_dona.items()), 2),
                    'por_pessoa': [{'pessoa': d, 'fechados': n,
                                    'valor_por_fechamento': _num((com.get('por_pessoa') or {}).get(d, com.get('valor'))),
                                    'estimado': round(n * _num((com.get('por_pessoa') or {}).get(d, com.get('valor'))), 2)}
                                   for d, n in por_dona.most_common()]}

    saida = {
        'gerado_em': _iso_utc(agora),
        'periodo': {'chave': periodo, 'rotulo': dict(PERIODOS)[periodo],
                    'de': ini.date().isoformat(), 'ate': (fim - timedelta(seconds=1)).date().isoformat()},
        'periodos': [{'chave': c, 'rotulo': n} for c, n in PERIODOS],
        'pessoa': pessoa,
        'resumo': resumo,
        'meta': meta,
        'parados': paradas,
        'perdas': perdas,
        'ligacoes': ligacoes,
        'comissao': comissao,
        'avisos': _avisos(cfg),
    }

    if completo:
        # --- mesa por pessoa (administrador)
        donos = {r['dona'] for r in base['registros'] if r['dona'] and r['funil']}
        donos |= {a for a, t in base['respostas_equipe'] if t and ini <= t < fim}
        mesa = []
        for d in donos:
            mine = [r for r in base['registros'] if r['dona'] == d]
            leads_d = [r for r in R['leads'] if r['dona'] == d]
            fech_d = [r for r in fech if r['dona'] == d]
            meta_d = meta_por_pessoa.get(d)
            mesa.append({
                'pessoa': d,
                'leads': len(leads_d),
                'respondidos': len([r for r in leads_d if r['primeira_resposta']]),
                'respostas_equipe': sum(1 for a, t in base['respostas_equipe'] if a == d and t and ini <= t < fim),
                'fechados': len(fech_d),
                'meta_fechados': meta_d,
                'realizado_mes': len([r for r in fech_mes_time if r['dona'] == d]),
                'em_fechamento': len([r for r in R['em_fechamento'] if r['dona'] == d]),
                'perdidos': len([r for r in R['perdidos'] if r['dona'] == d]),
                'parados': len([r for r, _ in parados_lista if r['dona'] == d]),
                'tempo_1a_resposta_equipe_min': _mediana([(r['primeira_humana'] - r['primeiro_contato']).total_seconds() / 60
                                                          for r in leads_d if r['primeira_humana']]),
                'ligacoes': ligacoes_pessoa.get(d, 0) if marca else None,
                'comissao_estimada': next((c['estimado'] for c in (comissao or {}).get('por_pessoa', []) if c['pessoa'] == d), None),
                'abertas': len([r for r in mine if r['aberta'] and r['funil']]),
            })
        mesa.sort(key=lambda x: (-x['fechados'], -x['leads'], x['pessoa']))
        saida['mesa'] = mesa

        # --- funil por etapa (quadros do funil, colunas em ordem)
        funil = []
        for pid, nome in base['quadros']:
            abertas = [r for r in regs if r['pid'] == pid and r['aberta'] and not r['grupo']]
            ordem = base['etapas'].get(pid, [])
            contagem = Counter(r['etapa'] for r in abertas)
            paradas_q = Counter(r['etapa'] for r, _ in parados_lista if r['pid'] == pid)
            etapas_saida = [{'nome': e, 'quantidade': contagem.get(e, 0), 'parados': paradas_q.get(e, 0)}
                            for e in ordem]
            extras = sorted(e for e in contagem if e not in ordem)
            for e in extras:
                etapas_saida.append({'nome': e or '(sem etapa)', 'quantidade': contagem[e], 'parados': paradas_q.get(e, 0)})
            funil.append({'pid': pid, 'quadro': nome, 'abertas': len(abertas),
                          'entradas_no_periodo': len([r for r in R['leads'] if r['pid'] == pid]),
                          'etapas': etapas_saida})
        saida['funil'] = funil

    return saida


async def listar_conversas(db: AsyncSession, *, metrica: str, periodo='mes', agora=None, pessoa=None,
                           areas=None, quadro=None, etapa=None, dias_parado=None) -> dict:
    """Lista de conversas por tras de um numero. Usa os mesmos recortes de montar_painel."""
    if metrica not in METRICAS:
        raise HTTPException(400, f"metrica invalida. Use: {', '.join(sorted(METRICAS))}")
    cfg = _config()
    agora = _agora(agora)
    dias = dias_parado or cfg['parado_dias_padrao']
    ini, fim = janela(periodo, agora)
    base = await _carregar(db, cfg, agora)
    regs = [r for r in base['registros'] if _no_escopo(r, pessoa, areas)]
    if metrica == 'etapa':
        # coluna do funil: so as abertas daquele quadro e daquela coluna ('(sem etapa)' = coluna vazia)
        nome_etapa = '' if etapa == '(sem etapa)' else (etapa or '')
        alvo = [r for r in regs if r['funil'] and r['aberta'] and not r['grupo']
                and r['quadro'] == quadro and r['etapa'] == nome_etapa]
    else:
        alvo = _recortes(regs, ini, fim, agora, cfg, dias)[metrica]
    alvo = sorted(alvo, key=lambda r: (r['primeiro_contato'] or r['etapa_desde'] or datetime.min), reverse=True)
    return {'metrica': metrica, 'periodo': periodo, 'total': len(alvo),
            'conversas': [_linha(r) for r in alvo[:500]],
            'limitado_a': 500 if len(alvo) > 500 else None}


# ----------------------------------------------------------------- rotas
@router.get('/painel')
async def painel(periodo: str = Query('mes', description='hoje | semana | mes | mes_anterior | 15dias'),
                 dias_parado: int | None = Query(None, ge=1, le=365),
                 _admin=Depends(requer_admin),
                 db: AsyncSession = Depends(get_db)):
    """Painel completo. So administrador. Monta a partir do banco na hora."""
    return await montar_painel(db, periodo=_periodo_valido(periodo), dias_parado=dias_parado, completo=True)


@router.get('/minha-mesa')
async def minha_mesa(periodo: str = Query('mes', description='hoje | semana | mes | mes_anterior | 15dias'),
                     dias_parado: int | None = Query(None, ge=1, le=365),
                     pessoa: str | None = Query(None, description='so administrador: ver a mesa de outra pessoa'),
                     user=Depends(usuario_atual),
                     db: AsyncSession = Depends(get_db)):
    """A mesa de quem esta logado. Quem nao e administrador so ve a propria."""
    alvo = (user.email or '').strip().lower()
    if getattr(user, 'papel', '') == 'admin' and pessoa:
        alvo = pessoa.strip().lower()
    return await montar_painel(db, periodo=_periodo_valido(periodo), pessoa=alvo,
                               areas=_areas_de(user) if alvo == (user.email or '').strip().lower() else None,
                               dias_parado=dias_parado, completo=False)


@router.get('/conversas')
async def conversas(metrica: str = Query(..., description=' | '.join(sorted(METRICAS))),
                    periodo: str = Query('mes'),
                    pessoa: str | None = Query(None),
                    quadro: str | None = Query(None),
                    etapa: str | None = Query(None),
                    dias_parado: int | None = Query(None, ge=1, le=365),
                    user=Depends(usuario_atual),
                    db: AsyncSession = Depends(get_db)):
    """Drill-down: a lista de conversas por tras de um numero da tela.
    Quem nao e administrador ve so as proprias conversas (e das areas que pode ver)."""
    if getattr(user, 'papel', '') == 'admin':
        alvo, areas = (pessoa or '').strip().lower() or None, None
    else:
        alvo, areas = (user.email or '').strip().lower(), _areas_de(user)
    return await listar_conversas(db, metrica=metrica, periodo=_periodo_valido(periodo), pessoa=alvo,
                                  areas=areas, quadro=quadro, etapa=etapa, dias_parado=dias_parado)
