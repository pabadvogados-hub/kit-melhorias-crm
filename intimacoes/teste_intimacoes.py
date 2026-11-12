"""Testes do modulo de intimacoes. Sem rede e sem o sistema do cliente.

Rodar (use o Python que tem SQLAlchemy>=2 e aiosqlite):
    python -I teste_intimacoes.py

Cobre: classificacao, contagem em dias uteis (feriados, recesso), instabilidade da API
(ocupado, falso vazio, desistencia, paginacao), captura idempotente com log, modo simular,
conferencia gerando pz_prazos + pz_historico (com aprovacao), descartar e validacoes.

O esquema de pz_prazos / pz_historico / usuarios abaixo e' um ESPELHO MINIMO das colunas
que o modulo usa (conferir com schema_banco_renato.sql antes de aplicar no sistema real).
"""
import asyncio
import os
import shutil
import sys
import tempfile
import traceback
from datetime import date
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'backend'))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.intimacoes import captura, classificador, djen, prazos_uteis, schema, servico  # noqa: E402
from app.intimacoes.servico import ErroIntimacao  # noqa: E402

ESQUEMA = [
    """CREATE TABLE usuarios (
        id INTEGER PRIMARY KEY, email VARCHAR(200) NOT NULL UNIQUE, nome VARCHAR(200) NOT NULL,
        senha_hash VARCHAR(300) NOT NULL DEFAULT '', papel VARCHAR(50) NOT NULL,
        ativo BOOLEAN NOT NULL, criado_em DATETIME NOT NULL)""",
    """CREATE TABLE pz_prazos (
        id INTEGER PRIMARY KEY, origem VARCHAR(20) NOT NULL, chave_externa VARCHAR(120) NOT NULL,
        titulo VARCHAR(300) NOT NULL, tipo VARCHAR(20) NOT NULL, data DATE NOT NULL,
        fatal BOOLEAN NOT NULL, processo VARCHAR(60) NOT NULL, pasta VARCHAR(120) NOT NULL,
        cliente VARCHAR(200) NOT NULL, responsavel VARCHAR(200) NOT NULL,
        observacao TEXT NOT NULL, concluido BOOLEAN NOT NULL, concluido_em DATETIME,
        concluido_por VARCHAR(200) NOT NULL, sumiu BOOLEAN NOT NULL,
        criado_em DATETIME NOT NULL, atualizado_em DATETIME NOT NULL,
        prazo_dias INTEGER, hora VARCHAR(5) DEFAULT '', travas VARCHAR(120) DEFAULT '',
        oculto BOOLEAN DEFAULT 0, aprovacao VARCHAR(12) DEFAULT 'aprovado',
        aprovacao_nota VARCHAR(400) DEFAULT '', decidido_por VARCHAR(200) DEFAULT '',
        decidido_em DATETIME, criado_por VARCHAR(200) DEFAULT '', fatal_em DATE,
        elaboracao_em DATE, resultado VARCHAR(20) DEFAULT '')""",
    """CREATE TABLE pz_historico (
        id INTEGER PRIMARY KEY, prazo_id INTEGER NOT NULL, pasta VARCHAR(120) NOT NULL,
        processo VARCHAR(60) NOT NULL, cliente VARCHAR(200) NOT NULL,
        titulo VARCHAR(300) NOT NULL, evento VARCHAR(20) NOT NULL,
        detalhe VARCHAR(400) NOT NULL DEFAULT '', por VARCHAR(200) NOT NULL DEFAULT '',
        em DATETIME NOT NULL)""",
]

ADMIN = SimpleNamespace(email='admin@exemplo.invalid', papel='admin')
ADVOGADA = SimpleNamespace(email='advogada@exemplo.invalid', papel='advogado')

OCUPADO = ('ok', {'status': 'error', 'message': 'sistema muito ocupado'})
VAZIO = ('ok', {'status': 'success', 'count': 0, 'items': []})


def item(numero: str, texto: str, chave: str, disp: str = '2026-11-09') -> dict:
    return {'id': chave, 'hash': chave, 'numero_processo': numero, 'siglaTribunal': 'TJSP',
            'nomeOrgao': '1a Vara Civel', 'tipoComunicacao': 'Intimacao', 'texto': texto,
            'link': 'https://exemplo.invalid/' + chave, 'data_disponibilizacao': disp}


def dados(*itens, count=None):
    return ('ok', {'status': 'success', 'count': len(itens) if count is None else count,
                   'items': list(itens)})


def roteiro(respostas):
    fila = list(respostas)
    chamadas = []

    def get(params):
        chamadas.append(dict(params))
        if not fila:
            raise AssertionError('roteiro esgotado: o codigo pediu mais respostas do que o previsto')
        return fila.pop(0)
    return get, chamadas


def sono():
    registro = []

    async def dorme(s):
        registro.append(s)
    return dorme, registro


async def novo_banco():
    pasta = tempfile.mkdtemp(prefix='teste_intimacoes_')
    engine = create_async_engine('sqlite+aiosqlite:///' + pasta.replace('\\', '/') + '/t.db')
    Sessao = async_sessionmaker(engine, expire_on_commit=False)
    async with Sessao() as db:
        for stmt in ESQUEMA:
            await db.execute(text(stmt))
        for email, papel, ativo in (('admin@exemplo.invalid', 'admin', 1),
                                    ('advogada@exemplo.invalid', 'advogado', 1),
                                    ('inativa@exemplo.invalid', 'advogado', 0)):
            await db.execute(text("INSERT INTO usuarios (email, nome, papel, ativo, criado_em) "
                                  "VALUES (:e, :n, :p, :a, '2026-01-01 00:00:00')"),
                             {'e': email, 'n': email.split('@')[0], 'p': papel, 'a': ativo})
        await db.commit()
        await schema.garantir_tabelas(db)
    return engine, Sessao, pasta


async def contar(db, tabela: str, where: str = '1=1', params=None) -> int:
    return (await db.execute(text(f'SELECT COUNT(*) FROM {tabela} WHERE {where}'),
                             params or {})).scalar()


# ============================================================== testes puros

def t_classificador():
    c = classificador.classificar('Fica o réu intimado para apresentar contestação no prazo de 15 dias.')
    assert c['tipo_ato'] == 'contestacao' and c['prazo_dias'] == 15 and c['prazo_origem'] == 'texto', c
    c = classificador.classificar('Intime-se a parte autora para apresentar réplica.')
    assert c['tipo_ato'] == 'replica' and c['prazo_dias'] == 15 and c['prazo_origem'] == 'lei', c
    c = classificador.classificar('Fica intimada para embargos de declaração no prazo de cinco dias.')
    assert c['tipo_ato'] == 'embargos_declaracao' and c['prazo_dias'] == 5, c
    c = classificador.classificar('Apresente contrarrazões ao recurso de apelação.')
    assert c['tipo_ato'] == 'contrarrazoes', c            # contrarrazoes antes de apelacao
    c = classificador.classificar('Recebo o recurso de apelação. Intime-se.')
    assert c['tipo_ato'] == 'apelacao' and c['prazo_dias'] == 15, c
    assert any('confira' in a.lower() for a in c['alertas']), c['alertas']
    c = classificador.classificar('Designo audiência de conciliação para 10/12/2026.')
    assert c['tipo_ato'] == 'audiencia' and c['prazo_dias'] is None and c['tipo_item'] == 'audiencia', c
    c = classificador.classificar('Manifeste-se a parte autora sobre os documentos.')
    assert c['tipo_ato'] == 'manifestacao' and c['prazo_dias'] is None and c['tipo_item'] == 'tarefa', c
    c = classificador.classificar('Ciência às partes.')
    assert c['tipo_ato'] == 'ciencia' and c['prazo_dias'] is None, c
    c = classificador.classificar('Juntada de documentos.')
    assert c['tipo_ato'] == 'providencia', c
    c = classificador.classificar('Prazo de 10 dias corridos para o autor.')
    assert any('corridos' in a for a in c['alertas']), c['alertas']
    c = classificador.classificar('Intime-se a Fazenda Pública para contestar no prazo de 30 dias.')
    assert c['prazo_dias'] == 30 and c['prazo_origem'] == 'texto', c
    assert any('em dobro' in a for a in c['alertas']), c['alertas']
    c = classificador.classificar('Prazo de 5 dias para contestação.')
    assert c['tipo_ato'] == 'contestacao' and c['prazo_dias'] == 5, c
    assert any('regra usual' in a for a in c['alertas']), c['alertas']


def t_feriados():
    assert prazos_uteis.pascoa(2024) == date(2024, 3, 31)
    assert prazos_uteis.pascoa(2025) == date(2025, 4, 20)
    assert prazos_uteis.pascoa(2026) == date(2026, 4, 5)
    assert not prazos_uteis.e_dia_util(date(2026, 4, 3))      # Sexta-feira Santa
    assert not prazos_uteis.e_dia_util(date(2026, 11, 20))    # Consciencia Negra
    assert prazos_uteis.e_dia_util(date(2026, 2, 16))         # Carnaval: ponto facultativo, conta
    assert not prazos_uteis.e_dia_util(date(2026, 11, 14))    # sabado


def t_prazo_dias_uteis():
    r = prazos_uteis.calcular(date(2026, 11, 9), 15)          # segunda
    assert r['publicada_em'] == date(2026, 11, 10), r
    assert r['inicio_prazo'] == date(2026, 11, 11), r
    assert r['data_fatal'] == date(2026, 12, 3), r            # 15o dia util, pulando 20/11
    r = prazos_uteis.calcular(date(2026, 11, 9), 5)
    assert r['data_fatal'] == date(2026, 11, 18), r
    r = prazos_uteis.calcular(date(2026, 11, 13), 5)          # sexta
    assert r['publicada_em'] == date(2026, 11, 16) and r['inicio_prazo'] == date(2026, 11, 17), r
    assert r['data_fatal'] == date(2026, 11, 25), r           # pula 20/11 e o fim de semana
    assert prazos_uteis.calcular(date(2026, 11, 9), None)['data_fatal'] is None
    r = prazos_uteis.calcular(date(2026, 12, 15), 15)         # atravessa o recesso
    assert r['alertas'] and 'recesso' in r['alertas'][0], r


def t_djen_normalizar():
    n = djen.normalizar_item(item('1000001-02.2026.8.26.0100', 'texto', 'abc123'), '1/SP')
    assert n['chave_externa'] == 'djen:abc123', n
    assert n['numero_limpo'] == '10000010220268260100', n
    assert n['disponibilizada'] == date(2026, 11, 9), n
    sem_id = {'numero_processo': '1000001-02.2026.8.26.0100', 'texto': 'x',
              'data_disponibilizacao': '2026-11-09'}
    a = djen.normalizar_item(sem_id, '1/SP')['chave_externa']
    b = djen.normalizar_item(sem_id, '1/SP')['chave_externa']
    assert a == b and a.startswith('djen:h'), (a, b)        # chave estavel quando a API nao traz id
    assert djen.espera(1) == 2.0 and djen.espera(3) == 8.0 and djen.espera(10) == 60.0


async def t_djen_instabilidade():
    # 1) ocupado, falso vazio, depois dados
    get, _ = roteiro([OCUPADO, VAZIO, dados(item('1', 'a', 'h1'), item('2', 'b', 'h2'))])
    r = await djen.FonteDJEN(get=get).buscar_periodo('1', 'SP', date(2026, 11, 6), date(2026, 11, 9),
                                                    sleep=sono()[0])
    assert r.status == 'ok' and len(r.itens) == 2 and r.tentativas == 3, r
    assert r.ocupados == 1 and r.vazios == 1, r

    # 2) so falsos vazios: tres respostas vazias confirmam "sem intimacao"
    get, _ = roteiro([VAZIO, VAZIO, VAZIO])
    r = await djen.FonteDJEN(get=get).buscar_periodo('1', 'SP', date(2026, 11, 6), date(2026, 11, 9),
                                                    sleep=sono()[0])
    assert r.status == 'vazio_confirmado' and r.itens == [] and r.tentativas == 3, r

    # 3) vazios intercalados com ocupado: ainda confirma com tres vazios
    get, _ = roteiro([VAZIO, OCUPADO, VAZIO, OCUPADO, VAZIO])
    r = await djen.FonteDJEN(get=get).buscar_periodo('1', 'SP', date(2026, 11, 6), date(2026, 11, 9),
                                                    sleep=sono()[0])
    assert r.status == 'vazio_confirmado' and r.tentativas == 5, r

    # 4) so ocupado: desiste depois de 10 e NAO conclui "sem intimacao"
    get, _ = roteiro([OCUPADO] * djen.MAX_TENTATIVAS)
    pausas, reg = sono()
    r = await djen.FonteDJEN(get=get).buscar_periodo('1', 'SP', date(2026, 11, 6), date(2026, 11, 9),
                                                    sleep=pausas)
    assert r.status == 'incompleta' and r.tentativas == 10 and r.ocupados == 10, r
    assert any('desistiu' in linha for linha in r.log), r.log
    assert reg == [2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0, 60.0, 60.0], reg

    # 5) paginacao: 3 no total, 2 na pagina 1 e 1 na pagina 2
    get, chamadas = roteiro([dados(item('1', 'a', 'h1'), item('2', 'b', 'h2'), count=3),
                             dados(item('3', 'c', 'h3'), count=3)])
    r = await djen.FonteDJEN(get=get).buscar_periodo('1', 'SP', date(2026, 11, 6), date(2026, 11, 9),
                                                    sleep=sono()[0])
    assert r.status == 'ok' and len(r.itens) == 3, r
    assert [c['pagina'] for c in chamadas] == [1, 2], chamadas

    # 6) erro que nao e' de instabilidade nao e' retentado
    get, _ = roteiro([('erro', 'HTTP 400')])
    r = await djen.FonteDJEN(get=get).buscar_periodo('1', 'SP', date(2026, 11, 6), date(2026, 11, 9),
                                                    sleep=sono()[0])
    assert r.status == 'erro' and r.tentativas == 1, r


async def t_oabs_e_parse():
    assert servico.parse_oab(' 123456 / sp ') == ('123456', 'SP')
    try:
        servico.parse_oab('SP123456')
    except ErroIntimacao as e:
        assert e.status == 400
    else:
        raise AssertionError('OAB invalida foi aceita')
    engine, Sessao, pasta = await novo_banco()
    try:
        async with Sessao() as db:
            await servico.adicionar_oab(db, '123456/sp', 'Teste')
            ativas = await servico.oabs_ativas(db, ['123456/SP, 999/RJ', 'lixo', ''])
            assert ativas == [('123456', 'SP'), ('999', 'RJ')], ativas
    finally:
        await engine.dispose()
        shutil.rmtree(pasta, ignore_errors=True)


# ============================================================== testes com banco

NOTAS = {
    'h1': 'Fica o réu intimado para apresentar contestação no prazo de 15 dias.',
    'h2': 'Designo audiência de conciliação para 10/12/2026, às 14h.',
    'h3': 'Manifeste-se a parte autora sobre a juntada.',
}


def _tres_itens():
    return [item('1000001-02.2026.8.26.0100', NOTAS['h1'], 'h1'),
            item('1000002-02.2026.8.26.0100', NOTAS['h2'], 'h2'),
            item('1000003-02.2026.8.26.0100', NOTAS['h3'], 'h3')]


async def t_captura_idempotente_e_log():
    engine, Sessao, pasta = await novo_banco()
    try:
        async with Sessao() as db:
            await servico.adicionar_oab(db, '100001/SP', 'Teste')
            get, _ = roteiro([dados(*_tres_itens())])
            fonte = djen.FonteDJEN(get=get)
            r1 = await captura.rodar(db, fonte=fonte, dias=3, sleep=sono()[0], hoje=date(2026, 11, 9))
            assert r1['oabs'][0]['novas'] == 3 and r1['oabs'][0]['ja_existiam'] == 0, r1
            assert await contar(db, 'int_intimacoes') == 3

            # segunda rodada, mesma resposta: nada duplicado
            get, _ = roteiro([dados(*_tres_itens())])
            r2 = await captura.rodar(db, fonte=djen.FonteDJEN(get=get), dias=3,
                                     sleep=sono()[0], hoje=date(2026, 11, 9))
            assert r2['oabs'][0]['novas'] == 0 and r2['oabs'][0]['ja_existiam'] == 3, r2
            assert await contar(db, 'int_intimacoes') == 3
            assert await contar(db, 'int_capturas') == 2

            linha = (await db.execute(text(
                "SELECT * FROM int_intimacoes WHERE chave_externa = 'djen:h1'"))).mappings().first()
            assert linha['tipo_ato'] == 'contestacao' and linha['prazo_dias'] == 15, dict(linha)
            assert linha['disponibilizada_em'] == '2026-11-09', dict(linha)
            assert linha['data_fatal'] == '2026-12-03', dict(linha)
            assert linha['status'] == 'nova' and linha['oab'] == '100001/SP', dict(linha)

            log = (await db.execute(text(
                "SELECT resultado, recebidas, novas, tentativas, detalhe FROM int_capturas "
                "ORDER BY id"))).mappings().all()
            assert [l['resultado'] for l in log] == ['ok', 'ok'], [dict(l) for l in log]
            assert log[0]['novas'] == 3 and log[0]['tentativas'] == 1
            assert 'dados' in log[0]['detalhe']
    finally:
        await engine.dispose()
        shutil.rmtree(pasta, ignore_errors=True)


async def t_captura_incompleta_nao_vira_vazio():
    engine, Sessao, pasta = await novo_banco()
    try:
        async with Sessao() as db:
            await servico.adicionar_oab(db, '100001/SP')
            get, _ = roteiro([OCUPADO] * djen.MAX_TENTATIVAS)
            r = await captura.rodar(db, fonte=djen.FonteDJEN(get=get), dias=3,
                                    sleep=sono()[0], hoje=date(2026, 11, 9))
            assert r['incompletas'] == 1 and r['oabs'][0]['resultado'] == 'incompleta', r
            assert await contar(db, 'int_intimacoes') == 0
            res = (await db.execute(text('SELECT resultado FROM int_capturas'))).scalars().all()
            assert res == ['incompleta'], res
    finally:
        await engine.dispose()
        shutil.rmtree(pasta, ignore_errors=True)


async def t_simular_nao_grava():
    engine, Sessao, pasta = await novo_banco()
    try:
        async with Sessao() as db:
            await servico.adicionar_oab(db, '100001/SP')
            get, _ = roteiro([dados(*_tres_itens())])
            r = await captura.rodar(db, fonte=djen.FonteDJEN(get=get), dias=3, gravar=False,
                                    sleep=sono()[0], hoje=date(2026, 11, 9))
            o = r['oabs'][0]
            assert r['simulada'] and o['novas'] == 3 and len(o['previa']) == 3, r
            assert await contar(db, 'int_intimacoes') == 0
            assert await contar(db, 'int_capturas') == 0
    finally:
        await engine.dispose()
        shutil.rmtree(pasta, ignore_errors=True)


async def _capturar(db, n_itens=3):
    await servico.adicionar_oab(db, '100001/SP')
    get, _ = roteiro([dados(*_tres_itens()[:n_itens])])
    await captura.rodar(db, fonte=djen.FonteDJEN(get=get), dias=3, sleep=sono()[0],
                        hoje=date(2026, 11, 9))


async def t_conferencia_e_calendario():
    engine, Sessao, pasta = await novo_banco()
    try:
        async with Sessao() as db:
            await _capturar(db)
            ids = {r['chave_externa']: r['id'] for r in (await servico.listar(
                db, status='todas'))['items']}
            i1, i2, i3 = ids['djen:h1'], ids['djen:h2'], ids['djen:h3']

            perfil = await servico.perfil(db, i1)
            assert perfil['sugestoes'] and perfil['sugestoes'][0]['sugerido'] is True, perfil
            assert perfil['sugestoes'][0]['tipo'] == 'prazo', perfil['sugestoes']

            # advogada conferindo: prazo + audiencia, responsavel dela
            itens = [
                {'tipo': 'prazo', 'titulo': 'Contestação - 1000001', 'responsavel': 'Advogada@exemplo.invalid',
                 'data': '2026-12-03', 'prazo_dias': 15, 'pasta': '383', 'processo': '',
                 'cliente': 'Cliente Teste', 'observacao': 'conferir a procuracao', 'sugerido': True},
                {'tipo': 'audiencia', 'titulo': 'Audiencia de conciliacao', 'responsavel': '',
                 'data': '2026-12-10', 'hora': '14h30', 'sugerido': False},
            ]
            res = await servico.conferir(db, i1, ADVOGADA, itens)
            assert len(res['prazos']) == 2, res
            pz = (await db.execute(text(
                "SELECT * FROM pz_prazos WHERE chave_externa LIKE 'int:%' ORDER BY id"))).mappings().all()
            assert len(pz) == 2, [dict(p) for p in pz]
            p1, p2 = dict(pz[0]), dict(pz[1])
            assert p1['origem'] == 'intimacao' and p1['chave_externa'] == f'int:{i1}:1', p1
            assert p1['data'] == '2026-12-03' and p1['fatal_em'] == '2026-12-03' and p1['fatal'] == 1, p1
            assert p1['prazo_dias'] == 15 and p1['responsavel'] == 'advogada@exemplo.invalid', p1
            assert p1['aprovacao'] == 'pendente' and p1['criado_por'] == ADVOGADA.email, p1
            assert p1['observacao'].startswith(f'Intimação #{i1}'), p1
            assert p2['tipo'] == 'audiencia' and p2['hora'] == '14:30' and p2['aprovacao'] == 'pendente', p2
            assert p2['fatal_em'] is None and p2['prazo_dias'] is None, p2

            hist = (await db.execute(text(
                "SELECT prazo_id, evento, detalhe, por FROM pz_historico ORDER BY id"))).mappings().all()
            assert len(hist) == 2 and all(h['evento'] == 'criado' for h in hist), [dict(h) for h in hist]
            assert 'aguarda aprovação' in hist[0]['detalhe'] and hist[0]['por'] == ADVOGADA.email

            st = (await db.execute(text(
                "SELECT status, conferida_por FROM int_intimacoes WHERE id = :i"), {'i': i1})).first()
            assert st[0] == 'conferida' and st[1] == ADVOGADA.email, st

            # nao conferir duas vezes
            try:
                await servico.conferir(db, i1, ADVOGADA, itens)
            except ErroIntimacao as e:
                assert e.status == 409, e.status
            else:
                raise AssertionError('conferiu duas vezes')

            # administrador: ja nasce aprovado
            await servico.conferir(db, i2, ADMIN, [{'tipo': 'audiencia', 'titulo': 'Audiencia',
                                                    'data': '2026-12-10', 'hora': '09:00'}])
            ad = (await db.execute(text(
                "SELECT aprovacao, decidido_por FROM pz_prazos WHERE chave_externa = :c"),
                {'c': f'int:{i2}:1'})).first()
            assert ad[0] == 'aprovado' and ad[1] == ADMIN.email, ad

            # validacoes: nada e' gravado quando uma das providencias esta errada
            antes = await contar(db, 'pz_prazos')
            casos = [
                ([], 'Inclua pelo menos'),
                ([{'titulo': 'x', 'data': '2026-12-03', 'responsavel': 'fulano@x.invalid'}], 'não é usuário'),
                ([{'titulo': 'x', 'data': '2026-12-03', 'hora': '25:00'}], 'hora'),
                ([{'titulo': 'x', 'data': '03/12/2026'}], 'data'),
                ([{'titulo': 'x', 'data': '2026-12-03', 'prazo_dias': 200}], 'entre 1 e 120'),
                ([{'titulo': '', 'data': '2026-12-03'}], 'título'),
                ([{'titulo': 'ok', 'data': '2026-12-03'},
                  {'titulo': 'ruim', 'data': '2026-12-03', 'tipo': 'inventado'}], 'Item 2'),
            ]
            for lista, trecho in casos:
                try:
                    await servico.conferir(db, i3, ADVOGADA, lista)
                except ErroIntimacao as e:
                    assert trecho.lower() in e.msg.lower(), (trecho, e.msg)
                else:
                    raise AssertionError(f'validacao nao barrou: {trecho}')
            assert await contar(db, 'pz_prazos') == antes
            assert (await db.execute(text(
                "SELECT status FROM int_intimacoes WHERE id = :i"), {'i': i3})).scalar() == 'nova'

            # descartar: motivo obrigatorio, depois nao conferir mais
            try:
                await servico.descartar(db, i3, ADVOGADA, 'x')
            except ErroIntimacao as e:
                assert e.status == 400
            else:
                raise AssertionError('descartou sem motivo')
            await servico.descartar(db, i3, ADVOGADA, 'Publicacao de outro escritorio')
            try:
                await servico.conferir(db, i3, ADVOGADA, itens[:1])
            except ErroIntimacao as e:
                assert e.status == 409
            else:
                raise AssertionError('conferiu intimacao descartada')

            # listagem: novas primeiro; contagem bate
            lista = await servico.listar(db, status='todas')
            assert lista['total'] == 3 and len(lista['items']) == 3, lista
            assert await servico.listar(db, status='conferida') and \
                (await servico.listar(db, status='conferida'))['total'] == 2
            cont = await servico.contagem(db)
            assert cont['novas'] == 0 and cont['conferida'] == 2 and cont['descartada'] == 1, cont
            perfil = await servico.perfil(db, i1)
            assert len(perfil['prazos']) == 2, perfil['prazos']
    finally:
        await engine.dispose()
        shutil.rmtree(pasta, ignore_errors=True)


async def t_listagem_novas_primeiro():
    engine, Sessao, pasta = await novo_banco()
    try:
        async with Sessao() as db:
            await _capturar(db)
            i2 = (await db.execute(text(
                "SELECT id FROM int_intimacoes WHERE chave_externa = 'djen:h2'"))).scalar()
            await servico.descartar(db, i2, ADMIN, 'Teste de ordenacao')
            r = await servico.listar(db, status='todas')
            status = [i['status'] for i in r['items']]
            assert status[:2] == ['nova', 'nova'] and status[2] == 'descartada', status
            so_novas = await servico.listar(db, status='nova', q='1000003')
            assert [i['numero_processo'] for i in so_novas['items']] == ['1000003-02.2026.8.26.0100'], so_novas
    finally:
        await engine.dispose()
        shutil.rmtree(pasta, ignore_errors=True)


TESTES = [
    t_classificador, t_feriados, t_prazo_dias_uteis, t_djen_normalizar,
    t_djen_instabilidade, t_oabs_e_parse, t_captura_idempotente_e_log,
    t_captura_incompleta_nao_vira_vazio, t_simular_nao_grava,
    t_conferencia_e_calendario, t_listagem_novas_primeiro,
]


def main() -> int:
    falhas = 0
    for fn in TESTES:
        try:
            if asyncio.iscoroutinefunction(fn):
                asyncio.run(fn())
            else:
                fn()
            print(f'PASSOU  {fn.__name__}')
        except Exception:
            falhas += 1
            print(f'FALHOU  {fn.__name__}')
            traceback.print_exc()
    print(f'\n{len(TESTES) - falhas} de {len(TESTES)} testes passaram.')
    return 1 if falhas else 0


if __name__ == '__main__':
    sys.exit(main())
