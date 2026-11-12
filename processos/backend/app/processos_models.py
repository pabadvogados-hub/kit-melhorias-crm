"""Modelos do modulo Processos: clientes, processos, partes, fases e historico.

Tabelas NOVAS (proc_*). Usam o mesmo Base do sistema, entao entram no create_all
que o init_db ja roda a cada subida. Nao alteram nenhuma tabela existente.

Destino: backend/app/processos_models.py
"""
from datetime import datetime

from sqlalchemy import String, DateTime, Integer, Text, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class ProcFase(Base):
    """Catalogo editavel de fases. Vira as colunas do quadro.

    O processo guarda o NOME da fase (proc_processos.fase), nao o id: assim a
    lista e o CSV saem legiveis sem join. Renomear uma fase atualiza os processos
    no mesmo passo (ver processos_nucleo.renomear_fase).
    """
    __tablename__ = 'proc_fases'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    grupo: Mapped[str] = mapped_column(String(60), default='')
    nome: Mapped[str] = mapped_column(String(120), unique=True)
    ordem: Mapped[int] = mapped_column(Integer, default=0, index=True)


class ProcCliente(Base):
    __tablename__ = 'proc_clientes'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(200), index=True)
    cpf_cnpj: Mapped[str] = mapped_column(String(20), default='')
    telefone: Mapped[str] = mapped_column(String(30), default='')
    email: Mapped[str] = mapped_column(String(200), default='')
    endereco: Mapped[str] = mapped_column(String(300), default='')
    cidade: Mapped[str] = mapped_column(String(120), default='')
    uf: Mapped[str] = mapped_column(String(2), default='')
    # ligacao opcional com a conversa do CRM de onde o cliente veio
    conversa_id: Mapped[int] = mapped_column(Integer, nullable=True, index=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    criado_por: Mapped[str] = mapped_column(String(200), default='')


class ProcProcesso(Base):
    __tablename__ = 'proc_processos'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # CNJ com pontuacao (NNNNNNN-DD.AAAA.J.TR.OOOO). NULL quando ainda nao ha numero:
    # NULL repete sem violar o UNIQUE; string vazia nao.
    numero: Mapped[str] = mapped_column(String(40), nullable=True, unique=True, index=True)
    # so os 20 digitos: e por aqui que se acha o processo (achar_processo)
    numero_limpo: Mapped[str] = mapped_column(String(25), nullable=True, unique=True, index=True)
    cliente_id: Mapped[int] = mapped_column(Integer, ForeignKey('proc_clientes.id'), nullable=True, index=True)
    area: Mapped[str] = mapped_column(String(120), default='', index=True)
    fase: Mapped[str] = mapped_column(String(120), default='A classificar', index=True)
    # desde quando esta na fase atual (base do "dias na fase")
    fase_desde: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    responsavel_email: Mapped[str] = mapped_column(String(200), default='', index=True)
    # pasta da REDE no mesmo formato de routers/prazos.pasta_normalizada (ex.: 250, 383/K74)
    pasta: Mapped[str] = mapped_column(String(120), default='', index=True)
    comarca: Mapped[str] = mapped_column(String(120), default='')
    vara: Mapped[str] = mapped_column(String(120), default='')
    tribunal: Mapped[str] = mapped_column(String(60), default='')
    parte_contraria: Mapped[str] = mapped_column(String(200), default='')
    valor_causa: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default='ativo', index=True)  # ativo | encerrado
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    criado_por: Mapped[str] = mapped_column(String(200), default='')
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # ligacao opcional com wa_conversas (quando o processo nasceu de um card do CRM)
    conversa_id: Mapped[int] = mapped_column(Integer, nullable=True, index=True)
    observacao: Mapped[str] = mapped_column(Text, default='')


class ProcParte(Base):
    __tablename__ = 'proc_partes'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    processo_id: Mapped[int] = mapped_column(Integer, ForeignKey('proc_processos.id'), index=True)
    nome: Mapped[str] = mapped_column(String(200))
    papel: Mapped[str] = mapped_column(String(40), default='PARTE CONTRÁRIA')
    documento: Mapped[str] = mapped_column(String(20), default='')


class ProcHistorico(Base):
    """Trilha do processo. Nunca se apaga linha daqui."""
    __tablename__ = 'proc_historico'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    processo_id: Mapped[int] = mapped_column(Integer, index=True)
    # criado | fase | editado | encerrado | reaberto | parte+ | parte-
    evento: Mapped[str] = mapped_column(String(30))
    de: Mapped[str] = mapped_column(Text, default='')
    para: Mapped[str] = mapped_column(Text, default='')
    detalhe: Mapped[str] = mapped_column(Text, default='')
    por: Mapped[str] = mapped_column(String(200), default='')
    em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
