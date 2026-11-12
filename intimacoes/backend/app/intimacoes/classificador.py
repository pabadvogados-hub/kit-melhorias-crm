"""Classificador de ato de intimacao civel (heuristica por palavras-chave).

E' uma SUGESTAO. Quem confere e' a equipe juridica: a tela marca tudo o que veio daqui
como "sugestao do classificador". Nao inventa fundamento: o prazo de cada ato e' o que
o CPC fixa (ou o numero de dias escrito no proprio texto da intimacao).

Ordem importa: a primeira regra que casa vence (ex.: "contrarrazoes ao recurso de
apelacao" tem de cair em contrarrazoes, nao em apelacao).
"""
import re
import unicodedata

# (tipo, rotulo, dias pela lei ou None, padrao regex sobre o texto normalizado)
REGRAS = (
    ('embargos_declaracao', 'Embargos de declaracao', 5,
     r'embargos (de declaracao|declaratorios)'),
    ('impugnacao_cumprimento', 'Impugnacao ao cumprimento de sentenca', 15,
     r'impugnacao ao cumprimento'),
    ('embargos_execucao', 'Embargos a execucao', 15,
     r'embargos (a execucao|do devedor)'),
    ('cumprimento_sentenca', 'Cumprimento de sentenca', 15,
     r'cumprimento de sentenca'),
    ('contrarrazoes', 'Contrarrazoes', 15,
     r'contra-?rr?azo'),
    ('agravo_instrumento', 'Agravo de instrumento', 15,
     r'agravo de instrumento'),
    ('agravo_interno', 'Agravo interno', 15,
     r'agravo (interno|regimental)'),
    ('agravo', 'Agravo', 15,
     r'\bagravo\b'),
    ('recurso_superior', 'Recurso especial ou extraordinario', 15,
     r'recurso (especial|extraordinario)'),
    ('apelacao', 'Apelacao', 15,
     r'\bapelacao\b'),
    ('contestacao', 'Contestacao', 15,
     r'\bcontestacao\b'),
    ('replica', 'Replica', 15,
     r'\breplica\b'),
    ('audiencia', 'Audiencia', None,
     r'\baudiencia\b'),
    ('manifestacao', 'Manifestacao (depende do despacho)', None,
     r'\b(manifest\w*|diga|digam|manifeste-se)\b'),
    ('ciencia', 'Ciencia de decisao (sem prazo deduzido)', None,
     r'\b(sentenca|decisao|despacho|ciencia)\b'),
)
_REGRAS_RE = tuple((t, r, d, re.compile(p)) for t, r, d, p in REGRAS)

# numeros escritos por extenso que aparecem em "prazo de quinze dias"
_EXTENSO = {'cinco': 5, 'dez': 10, 'quinze': 15, 'vinte': 20, 'trinta': 30}
_RE_PRAZO_TEXTO = re.compile(
    r'prazo[^.;]{0,40}?\b(\d{1,3}|cinco|dez|quinze|vinte|trinta)\b\s*'
    r'(?:\([^)]{0,40}\)\s*)?dias\b\s*(uteis|corridos)?')
_RE_DOBRO = re.compile(r'fazenda|defensoria|ministerio publico|litisconsort')

ALERTA_CONFERIR = ('Classificacao automatica pelas palavras do texto: confira o ato antes '
                   'de confirmar.')
ALERTA_DOBRO = ('O texto menciona ente publico, defensoria, MP ou litisconsortes. Pode haver '
                'prazo em dobro (CPC arts. 180, 183 e 229), que esta contagem NAO calcula.')


def normalizar(texto: str) -> str:
    t = unicodedata.normalize('NFKD', texto or '')
    t = ''.join(c for c in t if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', t.lower()).strip()


def classificar(texto: str) -> dict:
    """Devolve tipo_ato, rotulo, prazo_dias, prazo_origem, tipo_item e alertas."""
    t = normalizar(texto)
    tipo, rotulo, dias_lei = 'providencia', 'Providencia (conferir o texto)', None
    for tp, rot, dias, rx in _REGRAS_RE:
        if rx.search(t):
            tipo, rotulo, dias_lei = tp, rot, dias
            break

    alertas = [ALERTA_CONFERIR]
    dias_texto = None
    m = _RE_PRAZO_TEXTO.search(t)
    if m:
        bruto = m.group(1)
        dias_texto = int(bruto) if bruto.isdigit() else _EXTENSO[bruto]
        if m.group(2) == 'corridos':
            alertas.append('O texto fala em dias corridos. Esta contagem usa dias uteis: conferir '
                           'a data fatal antes de confirmar.')
    if dias_texto and dias_lei and dias_texto != dias_lei:
        alertas.append(f'O texto indica prazo de {dias_texto} dias; a regra usual deste ato e de '
                       f'{dias_lei}. Conferir.')
    if _RE_DOBRO.search(t):
        alertas.append(ALERTA_DOBRO)

    if dias_texto:
        dias, origem = dias_texto, 'texto'
    elif dias_lei:
        dias, origem = dias_lei, 'lei'
    else:
        dias, origem = None, ''

    if tipo == 'audiencia':
        tipo_item = 'audiencia'
    elif dias:
        tipo_item = 'prazo'
    else:
        tipo_item = 'tarefa'
    return {'tipo_ato': tipo, 'rotulo': rotulo, 'tipo_item': tipo_item,
            'prazo_dias': dias, 'prazo_origem': origem, 'alertas': alertas}


def sugestao_item(tipo_ato: str, rotulo: str, prazo_dias, numero: str, data_fatal) -> dict:
    """A providencia sugerida para a tela de conferencia (sempre marcada como sugestao)."""
    if tipo_ato == 'audiencia':
        tipo, titulo = 'audiencia', f'Audiencia - {numero}'.strip(' -')
    elif prazo_dias:
        tipo, titulo = 'prazo', f'{rotulo} - {numero}'.strip(' -')
    else:
        tipo, titulo = 'tarefa', f'{rotulo} - {numero}'.strip(' -')
    return {'tipo': tipo, 'titulo': titulo[:300], 'data': data_fatal,
            'prazo_dias': prazo_dias if tipo == 'prazo' else None, 'sugerido': True}
