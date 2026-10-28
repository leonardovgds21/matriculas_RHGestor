"""Comparação de nomes da lista com os nomes da plataforma.

Os nomes são comparados sem acento, sem maiúsculas, sem espaços repetidos e
sem as preposições (da, de, do, dos, das, e): "Joao Carlos Silva" acha
"JOÃO CARLOS DA SILVA".
"""

from __future__ import annotations

import re
import unicodedata

PARTICULAS = {"da", "de", "do", "das", "dos", "e", "d"}


def sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn")


def normalizar(nome: str) -> str:
    texto = re.sub(r"[^\w\s]", " ", sem_acento(nome or "").lower())
    return re.sub(r"\s+", " ", texto).strip()


def palavras(nome: str) -> list[str]:
    """As palavras do nome que contam (sem preposições)."""
    return [p for p in normalizar(nome).split() if p not in PARTICULAS]


def nome_igual(a: str, b: str) -> bool:
    """O mesmo nome, sem contar acento, maiúsculas e preposições."""
    pa = palavras(a)
    return bool(pa) and pa == palavras(b)


def mesmo_nome(procurado: str, achado: str) -> bool:
    """Nome igual, ou o achado tem todas as palavras do procurado, na mesma
    ordem e começando pelo primeiro nome (ex.: "Bruno Oliveira" acha
    "Bruno Matias Goncalo de Oliveira"). Exige 2 palavras ou mais."""
    p, a = palavras(procurado), palavras(achado)
    if not p or not a:
        return False
    if p == a:
        return True
    if len(p) < 2 or p[0] != a[0]:
        return False
    resto = iter(a)
    return all(any(x == y for y in resto) for x in p)


def termos_de_busca(nome: str) -> list[str]:
    """O nome inteiro e, se a busca não achar, o primeiro + último nome e o
    sobrenome mais longo (a busca da plataforma procura o texto inteiro)."""
    p = palavras(nome)
    termos = [" ".join(nome.split())]
    if len(p) > 2:
        termos.append(f"{p[0]} {p[-1]}")
    if len(p) > 1:
        termos.append(max(p[1:], key=len))
    return list(dict.fromkeys(t for t in termos if t))


def escolher(procurado: str, nomes_da_lista: list[str]) -> tuple[str, list[int]]:
    """Quem da lista da plataforma é a pessoa procurada.

    Devolve (tipo, posições): "igual" com uma posição; "parecido" (uma só
    pessoa com as palavras do nome, ex.: nome do meio a mais); "homonimo"
    (duas ou mais com o mesmo nome) ou "nenhum".
    """
    iguais = [i for i, n in enumerate(nomes_da_lista) if nome_igual(procurado, n)]
    if len(iguais) == 1:
        return "igual", iguais
    if len(iguais) > 1:
        return "homonimo", iguais
    parecidos = [i for i, n in enumerate(nomes_da_lista) if mesmo_nome(procurado, n)]
    if len(parecidos) == 1:
        return "parecido", parecidos
    if len(parecidos) > 1:
        return "homonimo", parecidos
    return "nenhum", []
