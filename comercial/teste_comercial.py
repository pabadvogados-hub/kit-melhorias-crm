"""Teste do painel comercial. Cria um SQLite temporario com o esquema do CRM, insere
conversas FICTICIAS e confere os numeros contra o que foi montado a mao.

Uso (na pasta do kit, com o Python do backend, que ja tem SQLAlchemy[asyncio] com greenlet, aiosqlite e fastapi;
para o teste de rota tambem httpx):

    python -I teste_comercial.py --schema caminho\\schema_do_crm.sql

O esquema sai do proprio banco do CRM, sem dados:

    sqlite3 sistema.db .schema > schema_do_crm.sql

Nao precisa do resto do sistema: o modulo e carregado por caminho, e as dependencias
do app (get_db, usuario_atual, requer_admin) sao substituidas por versoes de teste.
O arquivo de metas do teste e um temporario; o comercial_metas.json do kit so e lido
para conferir que esta valido e que nada nele conta por engano.
"""
import argparse
import asyncio
import json
import os
import sqlite3
import sys
import tempfile
import types
from datetime import datetime, timedelta
from importlib import util
from pathlib import Path

KIT = Path(__file__).resolve().parent
MODULO = KIT / 'backend' / 'comercial.py'
METAS_KIT = KIT / 'backend' / 'comercial_metas.json'

AGORA = datetime(2026, 11, 12, 15, 0, 0)     # quinta-feira, 15h, horario de Brasilia
DIF = timedelta(hours=3)


def utc(br: datetime) -> str:
    """Hora de Brasilia -> texto como o SQLite do CRM guarda (UTC)."""
    return (br + DIF).strftime('%Y-%m-%d %H:%M:%S.%f')


def br(texto: str) -> datetime:
    return datetime.strptime(texto, '%Y-%m-%d %H:%M')


# ---------------------------------------------------------------- stubs do app
def montar_stubs():
    """Substitui app.database, app.deps e o pacote app.routers para carregar comercial.py sozinho."""
    from fastapi import Depends, HTTPException, Request

    app = types.ModuleType('app')
    app.__path__ = []
    routers = types.ModuleType('app.routers')
    routers.__path__ = []
    database = types.ModuleType('app.database')
    deps = types.ModuleType('app.deps')

    async def get_db():                     # substituido por override nos testes de rota
        raise RuntimeError('get_db sem override')
        yield  # pragma: no cover

    def usuario_atual(request: Request):
        """Usuario de teste: cabecalho X-Teste-Email e X-Teste-Papel."""
        email = request.headers.get('X-Teste-Email')
        if not email:
            raise HTTPException(401, 'sem usuario de teste')
        return types.SimpleNamespace(email=email, papel=request.headers.get('X-Teste-Papel', 'usuario'),
                                     areas_permitidas=request.headers.get('X-Teste-Areas', ''))

    def requer_admin(user=Depends(usuario_atual)):
        if user.papel != 'admin':
            raise HTTPException(403, 'Acao restrita a administradores')
        return user

    database.get_db = get_db
    deps.usuario_atual = usuario_atual
    deps.requer_admin = requer_admin
    sys.modules.update({'app': app, 'app.routers': routers, 'app.database': database, 'app.deps': deps})


def carregar_modulo():
    spec = util.spec_from_file_location('app.routers.comercial', MODULO)
    mod = util.module_from_spec(spec)
    sys.modules['app.routers.comercial'] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- banco de teste
PIPELINES = [(1, 'FUNIL GERAL DE ENTRADA'), (2, 'TRIBUTÁRIO CLÍNICAS'), (3, 'FAMÍLIA'),
             (6, 'CLIENTES ESCRITÓRIO'), (11, 'CONTATOS GERAIS')]
ETAPAS = {
    1: ['Pendentes de atendimento', 'Distribuídos para áreas', 'Retomada', 'LEADS DESQUALIFICADOS'],
    2: ['Lead em Atendimento', 'Retomada', 'Análise / Viabilidade', 'Reunião agendada',
        'Ag. documentos/aceite proposta', 'CLIENTE NÃO SEGUIU COM O FECHAMENTO',
        'ELABORAÇÃO CONTRATO/PROCURAÇÃO', 'Assinatura de contrato'],
    3: ['Lead em Atendimento', 'Análise / Viabilidade', 'ELABORAÇÃO CONTRATO/PROCURAÇÃO', 'Assinatura de contrato'],
    6: ['Respondidos'],
    11: ['Respondidos'],
}
ANA, BRUNO = 'ana@exemplo.com', 'bruno@exemplo.com'


def semear(caminho_db: str, schema_sql: str):
    con = sqlite3.connect(caminho_db)
    con.executescript(schema_sql)
    con.executemany('INSERT INTO wa_pipelines (id, nome, ordem, dono_email, so_admin, so_incluidos, chave_padrao, criado_em) '
                    'VALUES (?, ?, ?, "", 0, "", "", "2026-08-01 00:00:00")',
                    [(pid, nome, pid) for pid, nome in PIPELINES])
    ordem = 0
    for pid, nomes in ETAPAS.items():
        for n in nomes:
            ordem += 1
            con.execute('INSERT INTO wa_stages (id, pipeline_id, nome, cor, ordem, descricao) VALUES (?, ?, ?, "#000", ?, "")',
                        (ordem, pid, n, nomes.index(n)))
    con.execute('INSERT INTO wa_numeros (id, nome, telefone, zapi_instance, zapi_token, zapi_client_token, atende_ia, agente, ativo, criado_em) '
                'VALUES (1, "Central fictícia", "5500000000000", "", "", "", 1, "bragabraz", 1, "2026-08-01 00:00:00")')

    msgs = []   # (conv, origem, autor, criado_em_BR, conteudo)

    def conv(cid, pid, nome, etapa, dona='', tag='', status='aberto', tipo='lead', etapa_desde=None, grupo=0,
             contato=None, respostas=(), notas=()):
        con.execute('INSERT INTO wa_conversas (id, numero_id, pipeline_id, contato_telefone, contato_nome, foto_url, tag, '
                    'origem, responsavel, email, handle, valor, notas, status, etapa, atendente_email, ia_ativa, aceita, '
                    'recusada, nao_lidas, ultima_mensagem, criado_em, atualizado_em, tipo_contato, eh_grupo, etapa_desde, '
                    'fechado_em) VALUES (?, 1, ?, "5500000000000", ?, "", ?, "", "", "", "", 0, "", ?, ?, ?, 1, 0, 0, 0, "", '
                    '?, ?, ?, ?, ?, NULL)',
                    (cid, pid, nome, tag, status, etapa, dona, utc(contato or AGORA), utc(contato or AGORA),
                     tipo, grupo, utc(etapa_desde) if etapa_desde else None))
        if contato:
            msgs.append((cid, 'contato', 'contato', contato, 'primeira fala'))
        for origem, autor, quando, texto in respostas:
            msgs.append((cid, origem, autor, quando, texto))
        for quando, texto, autor in notas:
            msgs.append((cid, 'nota', autor, quando, texto))

    # c1: lead de hoje, a IA respondeu em 2 minutos, sem dona, coluna de entrada
    conv(1, 1, 'Lead Hoje', 'Pendentes de atendimento', contato=br('2026-11-12 09:00'),
         respostas=[('ia', 'ia', br('2026-11-12 09:02'), 'resposta da IA')])
    # c2: lead de 05/11, equipe da Ana respondeu em 30 min; parada na analise ha 11 dias
    conv(2, 2, 'Lead Holding', 'Análise / Viabilidade', dona=ANA, tag='Holding Familiar',
         contato=br('2026-11-05 10:00'), etapa_desde=br('2026-11-01 09:00'),
         respostas=[('atendente', ANA, br('2026-11-05 10:30'), 'oi, sou da equipe')])
    # c3: contrato em elaboracao, sem assinatura; entrou na coluna em 10/11; contato de outubro
    conv(3, 2, 'Contrato em elaboração', 'ELABORAÇÃO CONTRATO/PROCURAÇÃO', dona=ANA, tag='Restituição Tributária',
         contato=br('2026-10-20 10:00'), etapa_desde=br('2026-11-10 10:00'))
    # c4: contrato assinado em 11/11 (nota de confirmacao), ainda na coluna de assinatura desde 04/11
    conv(4, 2, 'Assinou', 'Assinatura de contrato', dona=BRUNO, tipo='cliente', contato=br('2026-10-28 10:00'),
         etapa_desde=br('2026-11-04 10:00'),
         respostas=[('atendente', BRUNO, br('2026-10-28 10:20'), 'resposta da Bruno')],
         notas=[(br('2026-11-11 16:00'), 'Contrato assinado — confirmado na pasta PASTA-FICTICIA', 'equipe@exemplo.com')])
    # c5: lead de 08/11, ninguem respondeu
    conv(5, 3, 'Lead Família', 'Lead em Atendimento', contato=br('2026-11-08 14:00'))
    # c6: lead de 03/11 que foi para desqualificado em 11/11, sem resposta
    conv(6, 1, 'Desqualificado', 'LEADS DESQUALIFICADOS', contato=br('2026-11-03 11:00'),
         etapa_desde=br('2026-11-11 08:00'))
    # c7: historico importado: nao e lead
    conv(7, 1, 'Importada', 'Pendentes de atendimento', contato=br('2026-11-02 09:00'),
         notas=[(br('2026-11-02 09:00'), '(importacao) historico anterior ao sistema', '(importacao)')])
    # c8: grupo: nao e lead
    conv(8, 1, 'Grupo da equipe', 'Pendentes de atendimento', contato=br('2026-11-10 09:00'), grupo=1)
    # c9: cliente do escritorio fora do funil: nao e lead nem contrato em fechamento
    conv(9, 6, 'Cliente antigo', 'Respondidos', tipo='cliente', contato=br('2026-10-01 09:00'))
    # c10: lead de outubro, parado na analise ha 23 dias (aparece na mesa do Bruno, fora do mes)
    conv(10, 3, 'Lead antigo', 'Análise / Viabilidade', dona=BRUNO, contato=br('2026-10-15 09:00'),
         etapa_desde=br('2026-10-20 09:00'))

    # apagado pela limpeza automatica, em 04/11
    con.execute('CREATE TABLE IF NOT EXISTS wa_leads_apagados_log (id INTEGER PRIMARY KEY, entrou_em DATETIME, '
                'falas TEXT, respondeu BOOLEAN, virou_cliente BOOLEAN, apagado_em DATETIME)')
    con.execute('INSERT INTO wa_leads_apagados_log (entrou_em, falas, respondeu, virou_cliente, apagado_em) '
                'VALUES (?, "[]", 0, 0, ?)', (utc(br('2026-11-04 10:00')), utc(br('2026-11-07 10:00'))))

    # gasto com anuncio: bloco de novembro (linhas diarias)
    linhas = [{'date': '2026-11-05', 'campaign': 'Campanha A', 'spend': '100.50', 'impressions': 1000, 'clicks': 10},
              {'date': '2026-11-10', 'campaign': 'Campanha B', 'spend': '49.50', 'impressions': 500, 'clicks': 5},
              {'date': '2026-10-20', 'campaign': 'Campanha A', 'spend': '999', 'impressions': 1, 'clicks': 1}]
    con.execute('INSERT INTO rl_anuncios (de, ate, criado_em, criado_por, dados) VALUES ("2026-11-01", "2026-11-30", '
                '"2026-11-12 10:00:00", "teste", ?)', (json.dumps({'linhas': linhas}),))

    for cid, origem, autor, quando, texto in msgs:
        con.execute('INSERT INTO wa_mensagens (conversa_id, origem, autor, tipo, conteudo, midia_url, remote_id, criado_em) '
                    'VALUES (?, ?, ?, "texto", ?, "", "", ?)', (cid, origem, autor, texto, utc(quando)))
    # ligacao: nota de ligacao da Ana em 06/11 (so conta se marca_ligacao estiver configurada)
    con.execute('INSERT INTO wa_mensagens (conversa_id, origem, autor, tipo, conteudo, midia_url, remote_id, criado_em) '
                'VALUES (2, "nota", ?, "texto", "LIGAÇÃO: atendeu, falou 5 min", "", "", ?)',
                (ANA, utc(br('2026-11-06 11:00'))))
    con.commit()
    con.close()


# ---------------------------------------------------------------- execucao
def metas_temporario(conteudo: dict) -> Path:
    arq = Path(tempfile.mkdtemp()) / 'comercial_metas.json'
    arq.write_text(json.dumps(conteudo, ensure_ascii=False), encoding='utf-8')
    return arq


async def _com_sessao(url, fn):
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    engine = create_async_engine(url)
    try:
        async with AsyncSession(engine) as s:
            return await fn(s)
    finally:
        await engine.dispose()


def rodar(url, fn):
    return asyncio.run(_com_sessao(url, fn))


FALHAS = []


def conferir(nome, obtido, esperado):
    ok = obtido == esperado
    marca = 'ok  ' if ok else 'FALHA'
    print(f'  [{marca}] {nome}: obtido={obtido!r} esperado={esperado!r}')
    if not ok:
        FALHAS.append(nome)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--schema', required=True, help='arquivo .sql com o esquema do CRM (sqlite3 .schema)')
    args = ap.parse_args()
    schema = Path(args.schema).read_text(encoding='utf-8')

    # o arquivo de metas do kit precisa ser JSON valido e nao pode trazer numero inventado
    padrao = json.loads(METAS_KIT.read_text(encoding='utf-8'))
    print('Arquivo de metas do kit:', METAS_KIT.name)
    conferir('metas do kit: sem meta preenchida', {k: v for k, v in padrao['metas_mensais'].items()
                                                  if not k.startswith('_')}, {})
    conferir('metas do kit: sem ticket preenchido', [k for k in padrao['ticket_medio_por_area'] if not k.startswith('_')], [])
    conferir('metas do kit: comissao desligada', padrao['comissao_fixa_por_fechamento']['ativa'], False)

    montar_stubs()
    mod = carregar_modulo()
    tmp = Path(tempfile.mkdtemp())
    caminho = tmp / 'crm_teste.db'
    semear(str(caminho), schema)
    url = f'sqlite+aiosqlite:///{caminho.as_posix()}'

    mod.METAS_ARQ = metas_temporario({})   # sem metas: nada de meta, ticket ou comissao
    print('\nVisao do time, periodo "mes" (1 a 12/11/2026):')
    p = rodar(url, lambda s: mod.montar_painel(s, periodo='mes', agora=AGORA))
    r = p['resumo']
    conferir('leads', r['leads'], 4)                       # c1, c2, c5, c6
    conferir('respondidos', r['respondidos'], 2)           # c1 (IA) e c2 (equipe)
    conferir('respondidos pela equipe', r['respondidos_equipe'], 1)
    conferir('sem resposta', r['sem_resposta'], 2)         # c5 e c6
    conferir('taxa de resposta', r['taxa_resposta'], 50.0)
    conferir('tempo 1a resposta (min)', r['tempo_1a_resposta_min'], 16.0)   # mediana de 2 e 30
    conferir('tempo 1a resposta equipe (min)', r['tempo_1a_resposta_equipe_min'], 30.0)
    conferir('fechados (assinados no mes)', r['fechados'], 1)                # c4, nota de 11/11
    conferir('fechados de leads do periodo', r['fechados_de_leads_do_periodo'], 0)
    conferir('em fechamento agora', r['em_fechamento'], 1)                   # c3; c9 esta fora do funil
    conferir('perdidos (coluna + apagados)', r['perdidos'], 2)              # c6 + 1 apagado em 04/11
    conferir('parados (7 dias)', r['parados'], 4)                            # c2, c4, c7 (importada, parada), c10
    conferir('receita estimada sem ticket', r['receita_estimada'], None)
    conferir('fechados sem ticket', r['fechados_sem_ticket'], 1)
    conferir('gasto com anuncio do periodo', r['gasto_anuncios'], 150.0)    # 100,50 + 49,50; outubro fora
    conferir('custo por lead', r['custo_por_lead'], 37.5)
    conferir('custo por fechamento', r['custo_por_fechamento'], 150.0)
    conferir('ligacoes sem marca', p['ligacoes']['medido'], False)
    conferir('comissao desligada', p['comissao'], None)

    mesa = {m['pessoa']: m for m in p['mesa']}
    conferir('mesa: ordem (quem fechou primeiro)', [m['pessoa'] for m in p['mesa']], [BRUNO, ANA])
    conferir('mesa Ana: leads', mesa[ANA]['leads'], 1)
    conferir('mesa Ana: respostas da equipe no mes', mesa[ANA]['respostas_equipe'], 1)
    conferir('mesa Ana: em fechamento', mesa[ANA]['em_fechamento'], 1)
    conferir('mesa Ana: parados', mesa[ANA]['parados'], 1)
    conferir('mesa Bruno: fechados', mesa[BRUNO]['fechados'], 1)
    conferir('mesa Bruno: parados', mesa[BRUNO]['parados'], 2)              # c4 e c10 (c10 e de outubro, mas esta parada)

    funil = {f['quadro']: f for f in p['funil']}
    etapas_q1 = {e['nome']: e['quantidade'] for e in funil['FUNIL GERAL DE ENTRADA']['etapas']}
    conferir('funil: entrada, abertas (grupo fora)', funil['FUNIL GERAL DE ENTRADA']['abertas'], 3)   # c1, c6, c7
    conferir('funil: entradas no periodo', funil['FUNIL GERAL DE ENTRADA']['entradas_no_periodo'], 2)  # c1, c6
    conferir('funil: pendentes', etapas_q1['Pendentes de atendimento'], 2)
    conferir('funil: desqualificados', etapas_q1['LEADS DESQUALIFICADOS'], 1)
    conferir('funil: clientes do escritorio nao aparecem', 'CLIENTES ESCRITÓRIO' in funil, False)

    conferir('perdas por motivo', [x['motivo'] for x in p['perdas']['por_motivo']], ['LEADS DESQUALIFICADOS'])
    conferir('limpeza automatica no periodo', p['perdas']['apagados_pela_limpeza'], 1)
    conferir('parados por etapa: total', p['parados']['total'], 4)        # c2, c4, c7 (importada, parada), c10
    conferir('parados: mais antigo (dias)', p['parados']['mais_antigos'][0]['dias_na_etapa'], 23)

    print('\nPeriodo "hoje" e "15dias":')
    h = rodar(url, lambda s: mod.montar_painel(s, periodo='hoje', agora=AGORA))['resumo']
    conferir('hoje: leads', h['leads'], 1)
    conferir('hoje: respondidos', h['respondidos'], 1)
    conferir('hoje: fechados', h['fechados'], 0)
    q = rodar(url, lambda s: mod.montar_painel(s, periodo='15dias', agora=AGORA))['resumo']
    conferir('15 dias: leads', q['leads'], 4)                     # c1, c2, c5, c6 (c4 de 28/10 ficou de fora)
    conferir('15 dias: fechados', q['fechados'], 1)
    conferir('15 dias: perdidos', q['perdidos'], 2)

    print('\nPeriodo "semana" (desde segunda 09/11) e "mes_anterior":')
    s = rodar(url, lambda s_: mod.montar_painel(s_, periodo='semana', agora=AGORA))['resumo']
    conferir('semana: leads', s['leads'], 1)                      # so c1
    conferir('semana: fechados', s['fechados'], 1)                # assinatura de 11/11 (quarta)
    a = rodar(url, lambda s_: mod.montar_painel(s_, periodo='mes_anterior', agora=AGORA))
    conferir('outubro: leads', a['resumo']['leads'], 3)           # c3, c4, c10
    conferir('outubro: respondidos', a['resumo']['respondidos'], 1)   # c4 (Bruno, 28/10)
    conferir('outubro: fechados de leads (ate hoje)', a['resumo']['fechados_de_leads_do_periodo'], 1)  # c4 assinou em 11/11
    conferir('outubro: taxa de fechamento de leads', a['resumo']['taxa_fechamento_de_leads'], 33.3)
    conferir('outubro: sem bloco de anuncio cobrindo', a['resumo']['gasto_anuncios'], None)

    print('\nDrill-down (mesmos recortes dos numeros):')
    lista = rodar(url, lambda s: mod.listar_conversas(s, metrica='fechados', periodo='mes', agora=AGORA))
    conferir('fechados: lista', [c['id'] for c in lista['conversas']], [4])
    lista = rodar(url, lambda s: mod.listar_conversas(s, metrica='parados', periodo='mes', agora=AGORA))
    conferir('parados: lista', sorted(c['id'] for c in lista['conversas']), [2, 4, 7, 10])
    lista = rodar(url, lambda s: mod.listar_conversas(s, metrica='etapa', periodo='mes', agora=AGORA,
                                                      quadro='TRIBUTÁRIO CLÍNICAS', etapa='Análise / Viabilidade'))
    conferir('coluna do funil: so as abertas dela', [c['id'] for c in lista['conversas']], [2])
    lista = rodar(url, lambda s: mod.listar_conversas(s, metrica='fechados_de_leads', periodo='mes_anterior', agora=AGORA))
    conferir('fechados de leads de outubro: lista', [c['id'] for c in lista['conversas']], [4])

    print('\nEscopo pessoal (minha mesa da Ana, sem areas):')
    m = rodar(url, lambda s: mod.montar_painel(s, periodo='mes', agora=AGORA, pessoa=ANA, completo=False))
    conferir('minha mesa: sem visao do funil', 'funil' in m, False)
    conferir('minha mesa: sem a mesa dos outros', 'mesa' in m, False)
    conferir('minha mesa: leads', m['resumo']['leads'], 1)
    conferir('minha mesa: em fechamento', m['resumo']['em_fechamento'], 1)
    conferir('minha mesa: sem custo de anuncio', m['resumo']['gasto_anuncios'], None)

    print('\nEscopo com areas (Ana so ve Holding Familiar):')
    m = rodar(url, lambda s: mod.montar_painel(s, periodo='mes', agora=AGORA, pessoa=ANA,
                                               areas={'holding familiar'}, completo=False))
    conferir('areas: leads', m['resumo']['leads'], 1)
    conferir('areas: em fechamento (Restituicao fica de fora)', m['resumo']['em_fechamento'], 0)
    lista = rodar(url, lambda s: mod.listar_conversas(s, metrica='parados', periodo='mes', agora=AGORA,
                                                      pessoa=ANA, areas={'holding familiar'}))
    conferir('areas: drill so da area', [c['id'] for c in lista['conversas']], [2])

    print('\nMetas, ticket, comissao e ligacao configurados (arquivo temporario):')
    mod.METAS_ARQ = metas_temporario({
        'metas_mensais': {'2026-11': {'fechados': 10, 'por_pessoa_fechados': {BRUNO: 1}}},
        'ticket_medio_por_area': {'TRIBUTÁRIO CLÍNICAS': 5000},
        'comissao_fixa_por_fechamento': {'ativa': True, 'valor': 50, 'por_pessoa': {BRUNO: 100}},
        'marca_ligacao': 'LIGAÇÃO',
    })
    c = rodar(url, lambda s: mod.montar_painel(s, periodo='mes', agora=AGORA))
    conferir('receita estimada com ticket', c['resumo']['receita_estimada'], 5000.0)
    conferir('fechados sem ticket: zero', c['resumo']['fechados_sem_ticket'], 0)
    conferir('meta do time (fechados)', c['meta']['ritmo']['meta'], 10)
    conferir('ritmo disponivel no mes em curso', c['meta']['ritmo']['disponivel'], True)
    conferir('projecao existe', c['meta']['ritmo']['projecao'] is not None, True)
    conferir('comissao total (Bruno, 1 fechamento a R$ 100)', c['comissao']['total_estimado'], 100.0)
    conferir('ligacao medida', c['ligacoes']['total'], 1)
    mesa = {x['pessoa']: x for x in c['mesa']}
    conferir('ligacao da Ana', mesa[ANA]['ligacoes'], 1)
    meta_pessoa = rodar(url, lambda s: mod.montar_painel(s, periodo='mes', agora=AGORA, pessoa=BRUNO, completo=False))
    conferir('minha mesa do Bruno: meta pessoal', meta_pessoa['meta']['ritmo']['meta'], 1)

    print('\nFechado conta etapa (fechado_conta_etapa = true):')
    mod.METAS_ARQ = metas_temporario({'fechado_conta_etapa': True})
    e = rodar(url, lambda s: mod.montar_painel(s, periodo='mes', agora=AGORA))
    conferir('fechados com a etapa: c4 + c3', e['resumo']['fechados'], 2)
    e_ant = rodar(url, lambda s: mod.montar_painel(s, periodo='mes_anterior', agora=AGORA))
    conferir('outubro: c3 entrou na etapa so em 10/11', e_ant['resumo']['fechados'], 0)

    print('\nRotas (FastAPI, com get_db de teste):')
    rotas()

    print('\nMetas invalidas (JSON quebrado) devolvem erro claro:')
    ruim = Path(tempfile.mkdtemp()) / 'ruim.json'
    ruim.write_text('{ "metas_mensais": ', encoding='utf-8')
    mod.METAS_ARQ = ruim
    try:
        mod._config()
        conferir('JSON quebrado gera HTTP 500', 'nao gerou erro', 'HTTP 500')
    except Exception as err:      # HTTPException
        conferir('JSON quebrado gera HTTP 500', getattr(err, 'status_code', None), 500)

    print()
    if FALHAS:
        print(f'{len(FALHAS)} FALHA(S): ' + ', '.join(FALHAS))
        sys.exit(1)
    print('TODOS OS TESTES PASSARAM')


def rotas():
    """Chama as rotas de verdade (FastAPI TestClient), com permissao de administrador e de vendedora."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    mod = sys.modules['app.routers.comercial']
    tmp = Path(tempfile.mkdtemp())
    caminho = tmp / 'rotas.db'
    schema = os.environ['COMERCIAL_TESTE_SCHEMA_TEXTO']
    semear(str(caminho), schema)
    url = f'sqlite+aiosqlite:///{caminho.as_posix()}'
    mod.METAS_ARQ = metas_temporario({})

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    async def db_override():
        engine = create_async_engine(url)
        try:
            async with AsyncSession(engine) as s:
                yield s
        finally:
            await engine.dispose()

    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[sys.modules['app.database'].get_db] = db_override
    cli = TestClient(app)
    adm = {'X-Teste-Email': 'admin@exemplo.com', 'X-Teste-Papel': 'admin'}
    vend = {'X-Teste-Email': ANA, 'X-Teste-Papel': 'usuario', 'X-Teste-Areas': 'Holding Familiar'}

    r = cli.get('/api/comercial/painel?periodo=mes', headers=adm)
    conferir('painel admin: 200', r.status_code, 200)
    conferir('painel admin: tem mesa e funil', sorted(k for k in ('mesa', 'funil') if k in r.json()), ['funil', 'mesa'])
    r = cli.get('/api/comercial/painel?periodo=mes', headers=vend)
    conferir('painel para vendedora: 403', r.status_code, 403)
    r = cli.get('/api/comercial/minha-mesa?periodo=mes', headers=vend)
    conferir('minha mesa vendedora: 200', r.status_code, 200)
    conferir('minha mesa vendedora: so ela', r.json()['pessoa'], ANA)
    conferir('minha mesa vendedora: sem funil', 'funil' in r.json(), False)
    r = cli.get(f'/api/comercial/minha-mesa?periodo=mes&pessoa={BRUNO}', headers=vend)
    conferir('vendedora nao ve a mesa de outra', r.json()['pessoa'], ANA)
    r = cli.get(f'/api/comercial/conversas?metrica=parados&periodo=mes', headers=vend)
    conferir('drill vendedora: so a propria e da area', [c['id'] for c in r.json()['conversas']], [2])
    r = cli.get('/api/comercial/conversas?metrica=nada&periodo=mes', headers=adm)
    conferir('metrica invalida: 400', r.status_code, 400)
    r = cli.get('/api/comercial/painel?periodo=ano', headers=adm)
    conferir('periodo invalido: 400', r.status_code, 400)
    r = cli.get('/api/comercial/painel?periodo=mes', headers={})
    conferir('sem usuario: 401', r.status_code, 401)


if __name__ == '__main__':
    # o texto do esquema e lido antes, para as rotas reaproveitarem
    _ap = argparse.ArgumentParser()
    _ap.add_argument('--schema', required=True)
    _a, _ = _ap.parse_known_args()
    os.environ['COMERCIAL_TESTE_SCHEMA_TEXTO'] = Path(_a.schema).read_text(encoding='utf-8')
    main()
