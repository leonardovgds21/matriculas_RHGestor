"""Lista de colaboradores digitada ou colada na tela: nome completo e CPF.

A busca na turma é pelo nome (a lista da plataforma não mostra CPF); o CPF
serve para conferir a lista e achar repetidos, e pode faltar.

Aceita um colaborador por linha, em qualquer ordem e com qualquer separador
("123.456.789-09 Maria Silva", "Maria Silva;12345678909", colado do Excel
com tabulação...). Também aceita CPF numa linha e o nome na linha seguinte
(ou o contrário).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_CPF = re.compile(r"(?<!\d)(\d{3}\.?\d{3}\.?\d{3}-?\d{2})(?!\d)")


@dataclass
class Colaborador:
    nome: str
    cpf: str  # só números
    avisos: list[str] = field(default_factory=list)
    origem: str = ""  # arquivo e página, quando veio de uma ficha em PDF

    @property
    def cpf_formatado(self) -> str:
        return formatar_cpf(self.cpf)


def so_numeros(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")


def formatar_cpf(cpf: str) -> str:
    c = so_numeros(cpf)
    return f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}" if len(c) == 11 else cpf


def cpf_valido(cpf: str) -> bool:
    c = so_numeros(cpf)
    if len(c) != 11 or c == c[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(c[i]) * (tamanho + 1 - i) for i in range(tamanho))
        digito = (soma * 10) % 11 % 10
        if digito != int(c[tamanho]):
            return False
    return True


def limpar_nome(texto: str) -> str:
    """Tira separadores e números soltos das pontas e espaços repetidos."""
    nome = re.sub(r"[;,\t|]+", " ", texto or "")
    nome = re.sub(r"^\s*\d+\s*[-.)]\s*", "", nome)  # "1. Maria" / "1 - Maria"
    nome = re.sub(r"\s+", " ", nome).strip(" -–:")
    return nome


def _separar(linha: str) -> tuple[str, str]:
    """(cpf, nome) de uma linha; qualquer um pode vir vazio."""
    achado = _CPF.search(linha)
    if not achado:
        return "", limpar_nome(linha)
    resto = linha[:achado.start()] + " " + linha[achado.end():]
    return so_numeros(achado.group(1)), limpar_nome(resto)


def ler_lista(texto: str) -> list[Colaborador]:
    """Monta os colaboradores a partir do texto colado."""
    partes = [_separar(l) for l in (texto or "").splitlines() if l.strip()]
    colaboradores: list[Colaborador] = []
    i = 0
    while i < len(partes):
        cpf, nome = partes[i]
        # CPF sozinho numa linha e nome sozinho na outra (ou ao contrário)
        if i + 1 < len(partes):
            cpf2, nome2 = partes[i + 1]
            if cpf and not nome and nome2 and not cpf2:
                nome, i = nome2, i + 1
            elif nome and not cpf and cpf2 and not nome2:
                cpf, i = cpf2, i + 1
        if cpf or nome:
            colaboradores.append(Colaborador(nome=nome, cpf=cpf))
        i += 1

    from .nomes import palavras

    cpfs, nomes = set(), set()
    for c in colaboradores:
        c.avisos = validar(c)
        chave = " ".join(palavras(c.nome))
        if c.cpf and c.cpf in cpfs:
            c.avisos.append("CPF repetido na lista")
        elif chave and chave in nomes:
            c.avisos.append("nome repetido na lista")
        cpfs.add(c.cpf)
        nomes.add(chave)
    return colaboradores


def validar(c: Colaborador) -> list[str]:
    problemas = []
    if c.cpf and not cpf_valido(c.cpf):
        problemas.append("CPF inválido")
    if not c.nome:
        problemas.append("sem nome")
    elif len(c.nome.split()) < 2:
        problemas.append("informe o nome completo")
    return problemas
