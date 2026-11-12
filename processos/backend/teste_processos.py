"""Teste local do modulo Processos.

Roda contra um SQLite TEMPORARIO (nunca o banco do sistema), com o init_db, os modelos,
o nucleo e o router reais. Nao sobe o servidor, nao chama WhatsApp, nao usa rede.

Uso, na pasta backend/ (de preferencia com o venv do sistema):

    python -I teste_processos.py

Sai com codigo 0 quando tudo passa.
"""
import asyncio
import json
import os
import shutil
import sys
import tempfile
import traceback
from datetime import date, datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
TMP = tempfile.mkdtemp(prefix='teste_processos_')
os.environ['DATABASE_URL'] = 'sqlite+aiosqlite:///' + (Path(TMP) / 'teste.db').as_posix()
os.environ['JWT_SECRET'] = 'teste-local-nao-usar'
os.environ['REDE_DIR'] = ''
sys.path.insert(0, str(BACKEND))   # com python -I o diretorio do script nao entra no path sozinho

import httpx  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from sqlalchemy import select, func  # noqa: E402

from app.database import Base, AsyncSessionLocal, init_db, Usuario, engine  # noqa: E402
from app.security import criar_token  # noqa: E402
from app.whatsapp.models import Conversa  # noqa: E402
from app.routers.prazos import Prazo, PastaIndice  # noqa: E402
from app import processos_models as pm  # noqa: E402
from app import processos_nucleo as nuc  # noqa: E402
from app.processos_nucleo import ErroProcesso  # noqa: E402
from app.routers import processos as rota  # noqa: E402

CNJ1 = '0001234-56.2025.8.26.0100'   # 00012345620258260100
CNJ2 = '0007777-11.2024.8.26.0001'   # 00077771120248260001 (pasta 383/K74, sem processo unico)
CNJ3 = '0008888-22.2023.5.02.0003'   # 00088882220235020003 (pasta 383/K74)
CNJ4 = '0004444-44.2024.8.26.0002'   # 00044444420248260002 (pasta 512, unico)
CNJ5 = '0005555-55.2024.8.26.0003'   # 00055555520248260003 (criado no teste de editar)
CNJ6 = '0006666-66.2024.8.26.0004'   # 00066666620248260004 (criado pela rota HTTP)
AREA_A = 'Holding Familiar'
AREA_B = 'Direito de Família'

USUARIOS = [
    # email, papel, areas, modulos, ativo
    ('admin@teste.local', 'admin', '', '', True),
    ('adv@teste.local', 'advogado', AREA_A, '', True),
    ('adv2@teste.local', 'advogado', '', '', True),
    ('advb@teste.local', 'advogado', AREA_B, '', True),
    ('assist@teste.local', 'assistente', '', '', True),
    ('sdr@teste.local', 'sdr', '', '', True),
    ('recorte@teste.local', 'advogado', '', 'prazos', True),
    ('inativo@teste.local', 'advogado', '', '', False),
    ('outro@teste.local', 'advogado', '', '', True),
]

ESTADO = {}
RESULTADOS = []


async def _carrega_usuarios(db):
    rows = (await db.execute(select(Usuario))).scalars().all()
    return {u.email: u for u in rows}


async def espera_erro(coro, status, db=None):
    try:
        await coro
    except ErroProcesso as e:
        if e.status != status:
            raise AssertionError(f'esperava HTTP {status}, veio {e.status}: {e.msg}')
        return e
    raise AssertionError(f'esperava erro {status}, nao veio erro')


# ----------------------------------------------------------------- preparo

async def preparar():
    await init_db()
    await init_db()   # idempotente: segunda subida nao quebra
    async with AsyncSessionLocal() as db:
        assert 'proc_processos' in Base.metadata.tables
        for email, papel, areas, modulos, ativo in USUARIOS:
            db.add(Usuario(email=email, nome=email.split('@')[0], senha_hash='x', papel=papel,
                           ativo=ativo, areas_permitidas=areas, modulos=modulos,
                           criado_em=datetime.utcnow()))
        db.add(Conversa(numero_id=1, contato_telefone='5511999990000', contato_nome='Cliente Teste',
                        tag=AREA_A, tipo_contato='cliente', atendente_email='adv@teste.local',
                        email='cliente@exemplo.com', etapa='Assinatura de contrato',
                        fechado_em=datetime(2026, 11, 1), criado_em=datetime.utcnow(),
                        atualizado_em=datetime.utcnow()))
        db.add(Conversa(numero_id=1, contato_telefone='5511888880000', contato_nome='Lead Teste',
                        tag=AREA_B, tipo_contato='lead', atendente_email='', email='',
                        etapa='Lead em Atendimento', criado_em=datetime.utcnow(),
                        atualizado_em=datetime.utcnow()))
        db.add(PastaIndice(pasta='250', cliente='FULANO DE TAL', processos=json.dumps([CNJ1]),
                           caminho='250. FULANO DE TAL', atualizado_em=datetime.utcnow()))
        db.add(PastaIndice(pasta='383/K74', cliente='BELTRANO', processos=json.dumps([CNJ2, CNJ3]),
                           caminho='383/K74', atualizado_em=datetime.utcnow()))
        db.add(PastaIndice(pasta='512', cliente='CICLANO', processos=json.dumps([CNJ4]),
                           caminho='512. CICLANO', atualizado_em=datetime.utcnow()))
        db.add(PastaIndice(pasta='777', cliente='SEM CNJ', processos='[]', caminho='777. SEM CNJ',
                           atualizado_em=datetime.utcnow()))
        agora = datetime.utcnow()
        db.add(Prazo(origem='manual', chave_externa='t1', titulo='Contestação (PF 10/12)', tipo='prazo',
                     data=date(2026, 12, 10), fatal=True, processo='0001234-56.2025.8.26.0100',
                     pasta='250', cliente='FULANO', responsavel='adv@teste.local', observacao='',
                     concluido=False, sumiu=False, criado_em=agora, atualizado_em=agora))
        db.add(Prazo(origem='manual', chave_externa='t2', titulo='Audiência', tipo='audiencia',
                     data=date(2026, 12, 15), fatal=False, processo='00012345620258260100',
                     pasta='', cliente='FULANO', responsavel='outro@teste.local', observacao='',
                     concluido=False, sumiu=False, criado_em=agora, atualizado_em=agora))
        db.add(Prazo(origem='manual', chave_externa='t3', titulo='Juntar documento', tipo='tarefa',
                     data=date(2026, 12, 20), fatal=False, processo='', pasta='250', cliente='FULANO',
                     responsavel='', observacao='', concluido=False, sumiu=False,
                     criado_em=agora, atualizado_em=agora))
        await db.commit()
    async with AsyncSessionLocal() as db:
        n = await nuc.garantir_catalogo(db)
        assert n > 0, 'catalogo deveria ser semeado na 1a vez'
        assert await nuc.garantir_catalogo(db) == 0, 'catalogo nao pode ser semeado de novo'


# ----------------------------------------------------------------- testes

async def t_normalizacao():
    mask, dig = nuc.normaliza_numero(CNJ1.replace('-', '').replace('.', ''))
    assert mask == CNJ1 and dig == '00012345620258260100', (mask, dig)
    assert nuc.normaliza_numero('') == (None, None)
    await espera_erro(_sync_raise(lambda: nuc.normaliza_numero('123')), 400)
    assert nuc.normaliza_pasta('P. 250') == '250'
    assert nuc.normaliza_pasta('P.383 K74') == '383/K74'


async def _sync_raise(fn):
    fn()


async def t_acesso():
    async with AsyncSessionLocal() as db:
        u = await _carrega_usuarios(db)
        assert nuc.pode_acessar(u['admin@teste.local'])
        assert nuc.pode_acessar(u['adv@teste.local'])
        assert nuc.pode_acessar(u['assist@teste.local'])
        assert not nuc.pode_acessar(u['sdr@teste.local']), 'sdr nao entra por padrao'
        assert not nuc.pode_acessar(u['recorte@teste.local']), 'recorte sem processos nao entra'
        assert not nuc.pode_acessar(u['inativo@teste.local'])


async def t_criar_e_achar():
    async with AsyncSessionLocal() as db:
        u = await _carrega_usuarios(db)
        p = await nuc.criar(db, u['admin@teste.local'], {
            'numero': CNJ1, 'cliente_nome': 'Cliente Teste', 'area': AREA_A,
            'fase': 'Petição inicial protocolada', 'responsavel_email': 'adv@teste.local',
            'pasta': 'P. 250', 'valor_causa': 1000.0})
        ESTADO['p1'] = p.id
        assert p.numero == CNJ1 and p.numero_limpo == '00012345620258260100'
        assert p.pasta == '250', p.pasta
        assert p.cliente_id is not None
        assert p.status == 'ativo' and p.fase == 'Petição inicial protocolada'
        cliente = await db.get(pm.ProcCliente, p.cliente_id)
        assert cliente.nome == 'Cliente Teste'
        # achar por formatos diferentes
        for formato in (CNJ1, '00012345620258260100', '0001234.56.2025.8.26.0100'):
            achado = await nuc.achar_processo(db, formato)
            assert achado is not None and achado.id == p.id, formato
        assert await nuc.achar_processo(db, '9999999-99.2099.9.99.9999') is None
        assert await nuc.achar_processo(db, '') is None
        hist = (await db.execute(select(pm.ProcHistorico).where(pm.ProcHistorico.processo_id == p.id))
                ).scalars().all()
        assert [h.evento for h in hist] == ['criado']


async def t_duplicado():
    async with AsyncSessionLocal() as db:
        u = await _carrega_usuarios(db)
        await espera_erro(nuc.criar(db, u['admin@teste.local'], {'numero': CNJ1}), 409)


async def t_pasta_preenche_processo():
    async with AsyncSessionLocal() as db:
        u = await _carrega_usuarios(db)
        # pasta com UM processo no indice: o numero aparece sozinho
        p = await nuc.criar(db, u['admin@teste.local'], {'pasta': '512', 'cliente_nome': 'CICLANO'})
        assert p.numero == nuc.mascara_cnj(nuc.so_digitos(CNJ4)), p.numero
        # pasta com DOIS processos: nao chuta
        q = await nuc.criar(db, u['admin@teste.local'], {'pasta': '383/K74', 'cliente_nome': 'BELTRANO'})
        assert q.numero is None and q.pasta == '383/K74'
        info = await nuc.info_pasta(db, 'P.383 K74')
        assert info and info['cliente'] == 'BELTRANO' and len(info['processos']) == 2
        inverso = await nuc.pasta_do_numero(db, CNJ2)
        assert inverso and inverso['pasta'] == '383/K74'
        ESTADO['p_sem_numero'] = q.id


async def t_mover_fase():
    async with AsyncSessionLocal() as db:
        u = await _carrega_usuarios(db)
        p = await db.get(pm.ProcProcesso, ESTADO['p1'])
        antes = p.fase_desde
        await espera_erro(nuc.mover_fase(db, u['admin@teste.local'], p.id, 'Fase inventada'), 400)
        await nuc.mover_fase(db, u['admin@teste.local'], p.id, 'Sentença')
        p = await db.get(pm.ProcProcesso, p.id)
        assert p.fase == 'Sentença' and p.fase_desde >= antes
        await nuc.mover_fase(db, u['admin@teste.local'], p.id, 'Sentença')   # mesma fase: nada a registrar
        hist = (await db.execute(select(pm.ProcHistorico).where(
            pm.ProcHistorico.processo_id == p.id, pm.ProcHistorico.evento == 'fase'))).scalars().all()
        assert len(hist) == 1 and hist[0].de == 'Petição inicial protocolada' and hist[0].para == 'Sentença'


async def t_permissoes():
    async with AsyncSessionLocal() as db:
        u = await _carrega_usuarios(db)
        p = await db.get(pm.ProcProcesso, ESTADO['p1'])
        # adv2 nao tem area nem e responsavel: ve (sem restricao) mas nao mexe
        assert nuc.ve_processo(u['adv2@teste.local'], p) and not nuc.pode_mexer(u['adv2@teste.local'], p)
        await espera_erro(nuc.mover_fase(db, u['adv2@teste.local'], p.id, 'Sentença'), 403)
        # advb tem outra area: nao ve e portanto nao existe para ele
        assert not nuc.ve_processo(u['advb@teste.local'], p)
        await espera_erro(nuc.ficha(db, u['advb@teste.local'], p.id), 404)
        # o responsavel mexe
        assert nuc.pode_mexer(u['adv@teste.local'], p)
        await nuc.mover_fase(db, u['adv@teste.local'], p.id, 'Recurso interposto')
        await nuc.mover_fase(db, u['admin@teste.local'], p.id, 'Sentença')


async def t_encerrar_reabrir():
    async with AsyncSessionLocal() as db:
        u = await _carrega_usuarios(db)
        adm = u['admin@teste.local']
        await nuc.encerrar(db, adm, ESTADO['p1'], 'acordo homologado')
        p = await db.get(pm.ProcProcesso, ESTADO['p1'])
        assert p.status == 'encerrado'
        await espera_erro(nuc.encerrar(db, adm, p.id), 409)
        ativos = await nuc.listar(db, adm, status='ativo', q=CNJ1)
        assert all(x['id'] != p.id for x in ativos)
        enc = await nuc.listar(db, adm, status='encerrado', q=CNJ1)
        assert any(x['id'] == p.id for x in enc)
        await nuc.reabrir(db, adm, p.id)
        p = await db.get(pm.ProcProcesso, p.id)
        assert p.status == 'ativo'
        eventos = [h.evento for h in (await db.execute(select(pm.ProcHistorico).where(
            pm.ProcHistorico.processo_id == p.id).order_by(pm.ProcHistorico.id))).scalars().all()]
        assert eventos[-2:] == ['encerrado', 'reaberto'], eventos


async def t_partes():
    async with AsyncSessionLocal() as db:
        u = await _carrega_usuarios(db)
        adm = u['admin@teste.local']
        pid = ESTADO['p1']
        await espera_erro(nuc.adicionar_parte(db, adm, pid, {'nome': 'X', 'papel': 'QUALQUER'}), 400)
        await espera_erro(nuc.adicionar_parte(db, adm, pid, {'nome': 'X', 'papel': 'CLIENTE',
                                                            'documento': '123'}), 400)
        parte = await nuc.adicionar_parte(db, adm, pid, {'nome': 'Empresa Ré Ltda',
                                                        'papel': 'parte contrária',
                                                        'documento': '12.345.678/0001-90'})
        assert parte.papel == 'PARTE CONTRÁRIA'
        await nuc.remover_parte(db, adm, pid, parte.id)
        await espera_erro(nuc.remover_parte(db, adm, pid, parte.id), 404)
        f = await nuc.ficha(db, adm, pid)
        assert f['partes'] == []
        eventos = [h['evento'] for h in f['historico']]
        assert 'parte+' in eventos and 'parte-' in eventos


async def t_editar():
    async with AsyncSessionLocal() as db:
        u = await _carrega_usuarios(db)
        adm = u['admin@teste.local']
        pid = ESTADO['p1']
        await nuc.atualizar(db, adm, pid, {'comarca': 'São Bernardo do Campo', 'pasta': 'P. 250'})
        f = await nuc.ficha(db, adm, pid)
        assert f['processo']['comarca'] == 'São Bernardo do Campo'
        assert any(h['evento'] == 'editado' for h in f['historico'])
        # numero ja usado por outro processo
        outro = await nuc.criar(db, adm, {'numero': CNJ5})
        await espera_erro(nuc.atualizar(db, adm, pid, {'numero': CNJ5}), 409)
        # responsavel precisa ser usuario ativo
        await espera_erro(nuc.atualizar(db, adm, pid, {'responsavel_email': 'ninguem@x.com'}), 400)
        # quem nao e responsavel nem admin nao edita
        await espera_erro(nuc.atualizar(db, u['adv2@teste.local'], pid, {'comarca': 'X'}), 403)
        ESTADO['p_outro'] = outro.id


async def t_listar_filtros():
    async with AsyncSessionLocal() as db:
        u = await _carrega_usuarios(db)
        adm, adv = u['admin@teste.local'], u['adv@teste.local']
        todos_admin = await nuc.listar(db, adm)
        assert len(todos_admin) >= 3, f'so {len(todos_admin)} processos visiveis ao admin'
        so_a = await nuc.listar(db, adm, area=AREA_A)
        assert so_a and all(x['area'] == AREA_A for x in so_a), f'filtro por area: {so_a}'
        por_cliente = await nuc.listar(db, adm, q='cliente teste')
        assert any(x['id'] == ESTADO['p1'] for x in por_cliente), f'busca por cliente: {por_cliente}'
        por_pasta = await nuc.listar(db, adm, q='250')
        assert any(x['id'] == ESTADO['p1'] for x in por_pasta), f'busca por pasta: {por_pasta}'
        por_digitos = await nuc.listar(db, adm, q='0001234.56')
        assert any(x['id'] == ESTADO['p1'] for x in por_digitos), f'busca por digitos: {por_digitos}'
        por_fase = await nuc.listar(db, adm, fase='Sentença')
        assert all(x['fase'] == 'Sentença' for x in por_fase)
        # advogado com area A: ve os processos da area A e os sob sua responsabilidade
        do_adv = await nuc.listar(db, adv)
        for x in do_adv:
            assert nuc.ve_processo(adv, await db.get(pm.ProcProcesso, x['id'])), x
        # advogado da area B nao ve processo de area A nem de quem nao e ele
        advb = u['advb@teste.local']
        do_advb = await nuc.listar(db, advb)
        for x in do_advb:
            assert nuc.ve_processo(advb, await db.get(pm.ProcProcesso, x['id'])), x
        assert not any(x['id'] == ESTADO['p1'] for x in do_advb)
        r = await nuc.resumo(db, adm)
        assert r['ativos'] >= 2 and sum(r['por_fase'].values()) == r['ativos']


async def t_cliente_e_ficha():
    async with AsyncSessionLocal() as db:
        u = await _carrega_usuarios(db)
        adm = u['admin@teste.local']
        await espera_erro(nuc.criar_cliente(db, adm, {'nome': 'Fulano', 'cpf_cnpj': '123'}), 400)
        c = await nuc.criar_cliente(db, adm, {'nome': 'Fulana Nova', 'cpf_cnpj': '123.456.789-09',
                                             'uf': 'sp', 'email': 'FULANA@X.COM'})
        assert c.uf == 'SP' and c.email == 'fulana@x.com'
        c2 = await nuc.atualizar_cliente(db, adm, c.id, {'telefone': '11 99999-0000'})
        assert c2.telefone == '11 99999-0000'
        await espera_erro(nuc.atualizar_cliente(db, adm, c.id, {'nome': '  '}), 400)
        busca = await nuc.listar_clientes(db, adm, q='fulana')
        assert any(x['id'] == c.id for x in busca)
        # cliente com processo do admin, visto pelo advogado da area A (sem processo la): lista vazia
        cli_p1 = (await db.get(pm.ProcProcesso, ESTADO['p1'])).cliente_id
        ficha_adm = await nuc.ficha_cliente(db, adm, cli_p1)
        assert ficha_adm['processos'] and ficha_adm['cliente']['nome'] == 'Cliente Teste'


async def t_prazos_do_processo():
    async with AsyncSessionLocal() as db:
        u = await _carrega_usuarios(db)
        adm, adv = u['admin@teste.local'], u['adv@teste.local']
        pid = ESTADO['p1']
        todos = await nuc.prazos_do_processo(db, adm, pid)
        titulos = {x['titulo'] for x in todos}
        assert {'Contestação (PF 10/12)', 'Audiência', 'Juntar documento'} <= titulos, titulos
        do_adv = await nuc.prazos_do_processo(db, adv, pid)
        titulos_adv = {x['titulo'] for x in do_adv}
        assert 'Audiência' not in titulos_adv, 'prazo de outra pessoa nao aparece para o advogado'
        assert {'Contestação (PF 10/12)', 'Juntar documento'} <= titulos_adv


async def t_criar_de_conversa():
    async with AsyncSessionLocal() as db:
        u = await _carrega_usuarios(db)
        adm, adv = u['admin@teste.local'], u['adv@teste.local']
        conv_lead = (await db.execute(select(Conversa).where(Conversa.contato_nome == 'Lead Teste'))).scalar_one()
        conv = (await db.execute(select(Conversa).where(Conversa.contato_nome == 'Cliente Teste'))).scalar_one()
        previa_lead = await nuc.previa_conversa(db, adm, conv_lead)
        assert previa_lead['elegivel'] is False and 'lead' in previa_lead['motivo']
        await espera_erro(nuc.criar_de_conversa(db, adm, conv_lead, {}), 409)
        # ainda nao ha processo ligado a esta conversa: o card pode virar processo
        ativos = (await db.execute(select(pm.ProcProcesso).where(pm.ProcProcesso.conversa_id == conv.id))
                  ).scalars().all()
        assert ativos == [], 'nenhum processo deveria estar ligado a conversa ainda'
        previa = await nuc.previa_conversa(db, adm, conv)
        assert previa['elegivel'] is True
        assert previa['sugestao']['area'] == AREA_A
        assert previa['sugestao']['cliente_nome'] == 'Cliente Teste'
        p = await nuc.criar_de_conversa(db, adm, conv, {'pasta': 'P.401'})
        assert p.conversa_id == conv.id and p.area == AREA_A
        assert p.responsavel_email == 'adv@teste.local'
        cliente = await db.get(pm.ProcCliente, p.cliente_id)
        assert cliente.conversa_id == conv.id and cliente.nome == 'Cliente Teste'
        ESTADO['p_conv'] = p.id
        await db.refresh(conv)
        assert conv.pasta == '401'
        # ja existe ativo: nao cria outro
        previa2 = await nuc.previa_conversa(db, adm, conv)
        assert previa2['elegivel'] is False and previa2['processo_existente'] == p.id
        await espera_erro(nuc.criar_de_conversa(db, adm, conv, {}), 409)
        # encerrado: pode criar de novo e reaproveita o mesmo cliente
        await nuc.encerrar(db, adm, p.id, 'teste')
        p2 = await nuc.criar_de_conversa(db, adm, conv, {'pasta': 'P.401'})
        assert p2.cliente_id == cliente.id, 'o cliente da conversa deve ser reaproveitado'
        await nuc.encerrar(db, adm, p2.id, 'teste')


async def t_fases_admin():
    async with AsyncSessionLocal() as db:
        u = await _carrega_usuarios(db)
        adm = u['admin@teste.local']
        await espera_erro(nuc.criar_fase(db, adm, 'X', 'Sentença', None), 409)
        f = await nuc.criar_fase(db, adm, 'TESTE', 'Fase de teste', None)
        assert f.nome == 'Fase de teste'
        # renomear propaga para os processos que estao nela
        await nuc.mover_fase(db, adm, ESTADO['p_sem_numero'], 'Fase de teste')
        await nuc.atualizar_fase(db, f.id, nome='Fase renomeada')
        p = await db.get(pm.ProcProcesso, ESTADO['p_sem_numero'])
        assert p.fase == 'Fase renomeada'
        await espera_erro(nuc.apagar_fase(db, f.id), 409)
        await nuc.mover_fase(db, adm, p.id, 'A classificar')
        await nuc.apagar_fase(db, f.id)
        nomes = [x['nome'] for x in await nuc.listar_fases(db)]
        assert 'Fase renomeada' not in nomes and 'Sentença' in nomes


async def t_carga():
    async with AsyncSessionLocal() as db:
        antes = (await db.execute(select(func.count(pm.ProcProcesso.id)))).scalar()
        plano = await nuc.planejar_carga(db)
        depois = (await db.execute(select(func.count(pm.ProcProcesso.id)))).scalar()
        assert antes == depois, 'simular nao pode gravar'
        numeros = {x['digitos'] for x in plano['novos'] if x['digitos']}
        assert nuc.so_digitos(CNJ1) not in numeros, 'CNJ1 ja existe: nao deve ser criado de novo'
        assert nuc.so_digitos(CNJ3) in numeros, 'CNJ3 e novo'
        assert not any(x['pasta'] == '777' for x in plano['novos']), 'pasta sem CNJ fica de fora por padrao'
        plano_com = await nuc.planejar_carga(db, incluir_sem_processo=True)
        assert any(x['pasta'] == '777' and not x['numero'] for x in plano_com['novos'])
        # a pasta 401 ja tem processo criado pelo fluxo da conversa: a carga nao duplica
        assert not any(x['pasta'] == '401' for x in plano_com['novos'])
        cliente_ben = [x for x in plano['novos'] if x['pasta'] == '383/K74']
        assert cliente_ben and all(x['cliente'] == 'BELTRANO' for x in cliente_ben)
        # so a responsavel que for usuario ativo e unico nos prazos entra
        assert all(x['responsavel_email'] in ('', 'adv@teste.local', 'outro@teste.local') for x in plano['novos'])
        res = await nuc.aplicar_carga(db, plano)
        assert res['processos_criados'] == len(plano['novos'])
        de_novo = await nuc.planejar_carga(db)
        assert de_novo['novos'] == [], 'segunda leitura nao pode trazer nada novo'


async def t_http():
    app = FastAPI()
    app.include_router(rota.router)
    async with AsyncSessionLocal() as db:
        u = await _carrega_usuarios(db)
        tok = {
            'adm': criar_token('admin@teste.local', 'admin', 'admin'),
            'adv': criar_token('adv@teste.local', 'advogado', 'adv'),
            'sdr': criar_token('sdr@teste.local', 'sdr', 'sdr'),
        }
        conv_cliente = (await db.execute(select(Conversa).where(Conversa.contato_nome == 'Cliente Teste'))).scalar_one()
        conv_id = conv_cliente.id
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url='http://teste') as c:
        def h(k):
            return {'Authorization': f'Bearer {tok[k]}'}
        r = await c.get('/api/processos', headers=h('adm'))
        assert r.status_code == 200 and r.json()['total'] >= 3, r.text
        r = await c.get('/api/processos/fases', headers=h('adv'))
        assert r.status_code == 200 and any(f['nome'] == 'Sentença' for f in r.json()['items'])
        r = await c.get('/api/processos', headers=h('sdr'))
        assert r.status_code == 403
        r = await c.get('/api/processos')
        assert r.status_code == 401
        r = await c.post('/api/processos/fases', headers=h('adv'), json={'nome': 'X'})
        assert r.status_code == 403
        r = await c.post('/api/processos', headers=h('adv'), json={'numero': CNJ6, 'area': AREA_A,
                                                                    'cliente_nome': 'Nova Cliente HTTP'})
        assert r.status_code == 200, r.text
        novo = r.json()
        assert novo['processo']['numero'] == nuc.mascara_cnj(nuc.so_digitos(CNJ6)), novo
        assert novo['processo']['responsavel_email'] == 'adv@teste.local', 'quem cria vira responsavel por padrao'
        pid = novo['processo']['id']
        r = await c.post(f'/api/processos/{pid}/mover', headers=h('adv'), json={'fase': 'Audiência'})
        assert r.status_code == 200 and r.json()['processo']['fase'] == 'Audiência'
        r = await c.get(f'/api/processos/{pid}', headers=h('adv'))
        assert r.status_code == 200 and r.json()['historico'][0]['evento'] == 'fase'
        r = await c.get('/api/processos/resumo', headers=h('adm'))
        assert r.status_code == 200 and 'por_fase' in r.json()
        r = await c.get('/api/processos/pasta', params={'pasta': 'P. 250'}, headers=h('adm'))
        assert r.json()['cliente'] == 'FULANO DE TAL'
        r = await c.get('/api/processos/por-numero', params={'numero': CNJ2}, headers=h('adm'))
        assert r.json()['pasta'] == '383/K74'
        r = await c.get(f'/api/processos/{pid}/prazos', headers=h('adv'))
        assert r.status_code == 200
        r = await c.get(f'/api/processos/conversa/{conv_id}/elegivel', headers=h('adm'))
        assert r.status_code == 200 and r.json()['elegivel'] is True
        r = await c.post('/api/processos/clientes', headers=h('adv'), json={'nome': 'Cli HTTP'})
        assert r.status_code == 200
        r = await c.get('/api/processos/responsaveis', headers=h('adv'))
        assert any(x['email'] == 'adv@teste.local' for x in r.json()['items'])
        r = await c.get('/api/processos/99999', headers=h('adm'))
        assert r.status_code == 404
        # rota de uma palavra nao pode ser engolida pelo {pid}
        r = await c.get('/api/processos/clientes', headers=h('adm'))
        assert r.status_code == 200 and 'items' in r.json()


async def t_colunas_do_sistema_presentes():
    """Colunas que o modulo usa de tabelas do sistema existem (o kit so acrescenta; nao altera)."""
    async with engine.connect() as conn:
        def colunas(sync_conn):
            from sqlalchemy import inspect
            insp = inspect(sync_conn)
            return {t: {c['name'] for c in insp.get_columns(t)} for t in ('wa_conversas', 'pz_prazos', 'usuarios')}
        cols = await conn.run_sync(colunas)
    assert {'processo', 'pasta', 'tipo_contato', 'fechado_em'} <= cols['wa_conversas']


TESTES = [
    t_normalizacao, t_acesso, t_criar_e_achar, t_duplicado, t_pasta_preenche_processo,
    t_mover_fase, t_permissoes, t_encerrar_reabrir, t_partes, t_editar, t_listar_filtros,
    t_cliente_e_ficha, t_prazos_do_processo, t_criar_de_conversa, t_fases_admin, t_carga,
    t_http, t_colunas_do_sistema_presentes,
]


async def rodar():
    await preparar()
    falhas = 0
    for teste in TESTES:
        try:
            await teste()
            RESULTADOS.append((teste.__name__, 'PASSOU', ''))
        except Exception as e:  # noqa: BLE001
            falhas += 1
            RESULTADOS.append((teste.__name__, 'FALHOU', f'{type(e).__name__}: {e}'))
            traceback.print_exc()
    for nome, st, msg in RESULTADOS:
        print(f'{st:8} {nome}' + (f'  -> {msg}' if msg else ''))
    print(f'\n{len(TESTES) - falhas} de {len(TESTES)} testes passaram.')
    return falhas


if __name__ == '__main__':
    try:
        falhas = asyncio.run(rodar())
    finally:
        asyncio.run(engine.dispose())
        shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if falhas else 0)
