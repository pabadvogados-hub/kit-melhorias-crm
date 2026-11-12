"""Tabelas PROPRIAS do modulo de intimacoes. Nao altera nenhuma tabela existente.

- int_intimacoes: cada publicacao capturada (chave unica = id/hash do DJEN).
- int_capturas: log de cada rodada por OAB, com as tentativas e o que a API respondeu.
- int_oabs: OABs monitoradas (alem das que vierem de INT_OABS no .env).

CREATE ... IF NOT EXISTS: pode rodar a cada subida (e o faz, em main.py).
"""
from sqlalchemy import text

DDL = (
    """CREATE TABLE IF NOT EXISTS int_intimacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chave_externa VARCHAR(120) NOT NULL UNIQUE,
        oab VARCHAR(40) NOT NULL DEFAULT '',
        numero_processo VARCHAR(40) NOT NULL DEFAULT '',
        numero_limpo VARCHAR(30) NOT NULL DEFAULT '',
        tribunal VARCHAR(20) NOT NULL DEFAULT '',
        orgao VARCHAR(200) NOT NULL DEFAULT '',
        tipo_comunicacao VARCHAR(80) NOT NULL DEFAULT '',
        texto TEXT NOT NULL DEFAULT '',
        link VARCHAR(600) NOT NULL DEFAULT '',
        disponibilizada_em DATE,
        publicada_em DATE,
        inicio_prazo DATE,
        tipo_ato VARCHAR(40) NOT NULL DEFAULT 'providencia',
        rotulo_ato VARCHAR(120) NOT NULL DEFAULT '',
        prazo_dias INTEGER,
        prazo_origem VARCHAR(12) NOT NULL DEFAULT '',
        data_fatal DATE,
        alertas TEXT NOT NULL DEFAULT '[]',
        status VARCHAR(12) NOT NULL DEFAULT 'nova',
        processo_id INTEGER,
        conferida_por VARCHAR(200) NOT NULL DEFAULT '',
        conferida_em DATETIME,
        descartada_motivo VARCHAR(400) NOT NULL DEFAULT '',
        capturada_em DATETIME NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS ix_int_status_data ON int_intimacoes (status, disponibilizada_em)",
    "CREATE INDEX IF NOT EXISTS ix_int_numero ON int_intimacoes (numero_limpo)",
    """CREATE TABLE IF NOT EXISTS int_capturas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        iniciada_em DATETIME NOT NULL,
        terminada_em DATETIME,
        origem VARCHAR(20) NOT NULL DEFAULT 'cron',
        por VARCHAR(200) NOT NULL DEFAULT '',
        oab VARCHAR(40) NOT NULL DEFAULT '',
        janela_ini DATE,
        janela_fim DATE,
        resultado VARCHAR(20) NOT NULL DEFAULT '',
        recebidas INTEGER NOT NULL DEFAULT 0,
        novas INTEGER NOT NULL DEFAULT 0,
        ja_existiam INTEGER NOT NULL DEFAULT 0,
        tentativas INTEGER NOT NULL DEFAULT 0,
        ocupados INTEGER NOT NULL DEFAULT 0,
        vazios INTEGER NOT NULL DEFAULT 0,
        detalhe TEXT NOT NULL DEFAULT ''
    )""",
    "CREATE INDEX IF NOT EXISTS ix_int_capturas_em ON int_capturas (iniciada_em)",
    """CREATE TABLE IF NOT EXISTS int_oabs (
        oab VARCHAR(40) PRIMARY KEY,
        rotulo VARCHAR(120) NOT NULL DEFAULT '',
        ativo BOOLEAN NOT NULL DEFAULT 1,
        criado_em DATETIME NOT NULL
    )""",
)


async def garantir_tabelas(db) -> None:
    """Cria as tabelas do modulo se nao existirem. `db` e' uma AsyncSession."""
    for stmt in DDL:
        await db.execute(text(stmt))
    await db.commit()
