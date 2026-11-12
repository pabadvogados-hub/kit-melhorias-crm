"""Contagem de prazo processual em dias uteis (CPC, civel).

Regra usada (CPC arts. 224 e 219; Lei 11.419/2006, art. 4o, par. 3o):
- a DISPONIBILIZACAO no DJEN e' o dia D;
- a PUBLICACAO e' o primeiro dia util depois de D;
- o prazo COMECA no primeiro dia util depois da publicacao (o dia do comeco nao conta);
- o VENCIMENTO e' o n-esimo dia util depois do comeco.

Dias nao uteis: sabado, domingo e feriados NACIONAIS fixos + Sexta-feira Santa
(Lei 662/1949). Carnaval e Corpus Christi sao pontos facultativos: aqui contam como dia
util, o que deixa a data sugerida igual ou mais cedo (o lado seguro).

O QUE NAO ENTRA NO CALCULO (a tela avisa):
- feriados locais e municipais;
- suspensoes de expediente decretadas pelo tribunal;
- prazo em dobro (CPC arts. 180, 183 e 229): o classificador so' alerta;
- recesso forense (20/12 a 20/01, CPC art. 220): so' gera alerta quando o prazo o atravessa.
"""
from datetime import date, timedelta
from functools import lru_cache

# (mes, dia) dos feriados nacionais fixos. 20/11 e' feriado nacional desde a Lei 14.759/2023.
FERIADOS_FIXOS = ((1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (11, 20), (12, 25))


def pascoa(ano: int) -> date:
    """Domingo de Pascoa (algoritmo de Meeus/Jones/Butcher)."""
    a = ano % 19
    b, c = divmod(ano, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return date(ano, mes, dia)


@lru_cache(maxsize=64)
def feriados_nacionais(ano: int) -> frozenset:
    fer = {date(ano, mes, dia) for mes, dia in FERIADOS_FIXOS}
    fer.add(pascoa(ano) - timedelta(days=2))  # Sexta-feira Santa
    return frozenset(fer)


def e_dia_util(d: date) -> bool:
    return d.weekday() < 5 and d not in feriados_nacionais(d.year)


def proximo_dia_util(d: date) -> date:
    """Primeiro dia util DEPOIS de `d` (o proprio `d` nao conta)."""
    x = d + timedelta(days=1)
    while not e_dia_util(x):
        x += timedelta(days=1)
    return x


def somar_dias_uteis(inicio: date, n: int) -> date:
    """n-esimo dia util depois de `inicio` (o dia do comeco nao conta, o vencimento conta)."""
    x, feitos = inicio, 0
    while feitos < n:
        x += timedelta(days=1)
        if e_dia_util(x):
            feitos += 1
    return x


def em_recesso(d: date) -> bool:
    return (d.month == 12 and d.day >= 20) or (d.month == 1 and d.day <= 20)


def calcular(disponibilizada: date, dias: int | None) -> dict:
    """Datas do prazo a partir da disponibilizacao no DJEN.

    Devolve publicada_em, inicio_prazo, data_fatal (None sem numero de dias) e alertas.
    """
    publicada = proximo_dia_util(disponibilizada)
    inicio = proximo_dia_util(publicada)
    fatal = somar_dias_uteis(inicio, dias) if dias else None
    alertas = []
    if fatal:
        x = inicio
        while x <= fatal:
            if em_recesso(x):
                alertas.append('Prazo atravessa o recesso forense (20/12 a 20/01, CPC art. 220): '
                               'a data sugerida nao desconta o recesso. Conferir antes de confirmar.')
                break
            x += timedelta(days=1)
    return {'publicada_em': publicada, 'inicio_prazo': inicio,
            'data_fatal': fatal, 'alertas': alertas}
