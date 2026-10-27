"""
Contagem de prazos processuais.

Regras (padrão do processo administrativo — Lei 9.784/1999, art. 66):
- exclui-se o dia do começo e inclui-se o do vencimento;
- prazo em dias ÚTEIS conta apenas dias úteis (sem sábados, domingos e
  feriados/pontos facultativos cadastrados);
- prazo em dias CORRIDOS conta todos os dias, mas se o vencimento cair em dia
  não útil, prorroga-se para o primeiro dia útil seguinte;
- sobrestamento suspende a contagem: ao retomar, o prazo é estendido pelo
  número de dias (úteis ou corridos, conforme o prazo) em que ficou suspenso.
"""
from datetime import date, timedelta


def _easter_sunday(year: int) -> date:
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    lday = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * lday) // 451
    month = (h + lday - 7 * m + 114) // 31
    day = ((h + lday - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def national_holidays(year: int) -> list[tuple[date, str, str]]:
    """
    Feriados nacionais (Lei 662/1949, 6.802/1980, 14.759/2023) e pontos
    facultativos usuais (Carnaval, Corpus Christi). Retorna (data, nome, tipo).
    """
    e = _easter_sunday(year)
    fixed = [
        (date(year, 1, 1), "Confraternização Universal"), (date(year, 4, 21), "Tiradentes"),
        (date(year, 5, 1), "Dia do Trabalho"), (date(year, 9, 7), "Independência do Brasil"),
        (date(year, 10, 12), "Nossa Senhora Aparecida"), (date(year, 11, 2), "Finados"),
        (date(year, 11, 15), "Proclamação da República"), (date(year, 12, 25), "Natal"),
    ]
    if year >= 2024:
        fixed.append((date(year, 11, 20), "Dia Nacional de Zumbi e da Consciência Negra"))
    out = [(d, n, "NACIONAL") for d, n in fixed]
    out.append((e - timedelta(days=2), "Sexta-feira Santa", "NACIONAL"))
    out += [
        (e - timedelta(days=48), "Carnaval (segunda-feira)", "PONTO_FACULTATIVO"),
        (e - timedelta(days=47), "Carnaval (terça-feira)", "PONTO_FACULTATIVO"),
        (e + timedelta(days=60), "Corpus Christi", "PONTO_FACULTATIVO"),
    ]
    return sorted(out)


def is_business_day(day: date, holidays: frozenset) -> bool:
    return day.weekday() < 5 and day not in holidays


def next_business_day(day: date, holidays: frozenset) -> date:
    while not is_business_day(day, holidays):
        day += timedelta(days=1)
    return day


def add_days(start: date, days: int, business: bool, holidays: frozenset) -> date:
    """Vencimento de um prazo de `days` dias contados a partir de `start` (exclusive)."""
    if days <= 0:
        return start
    current = start
    if business:
        counted = 0
        while counted < days:
            current += timedelta(days=1)
            if is_business_day(current, holidays):
                counted += 1
        return current
    return next_business_day(start + timedelta(days=days), holidays)


def count_days(start: date, end: date, business: bool, holidays: frozenset) -> int:
    """Dias entre start (exclusive) e end (inclusive) — usado para o tempo de sobrestamento."""
    if end <= start:
        return 0
    if not business:
        return (end - start).days
    return sum(1 for i in range(1, (end - start).days + 1)
               if is_business_day(start + timedelta(days=i), holidays))


def remaining(due: date, today: date, business: bool, holidays: frozenset) -> int:
    """Dias que faltam (negativo = atrasado)."""
    if due >= today:
        return count_days(today, due, business, holidays)
    return -count_days(due, today, business, holidays)
