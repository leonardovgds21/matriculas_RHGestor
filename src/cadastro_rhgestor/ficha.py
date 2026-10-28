"""Leitura de CPF e nome das fichas em PDF (sem OCR e sem IA).

- "Ficha de Registro de Empregado" do Domínio (a mesma do FormaSeg): o nome é a
  linha logo abaixo do rótulo "Empregado", na coluna da esquerda.
- Outras fichas (ex.: ficha de EPI): o nome vem depois (ou embaixo) de um
  rótulo como "Empregado", "Funcionário", "Colaborador" ou "Nome".

O CPF é o número no formato 000.000.000-00 (ou depois do rótulo "CPF").
Uma pessoa pode ocupar várias páginas: páginas com o mesmo CPF viram uma só.
"""

from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from .entrada import Colaborador, so_numeros, validar

_RE_CPF = re.compile(r"(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)")
_RE_CPF_ROTULO = re.compile(r"CPF\s*(?:n[º°o.]*)?\s*[:\-]?\s*(\d{3}\.?\d{3}\.?\d{3}-?\d{2})(?!\d)", re.I)
_ROTULOS_NOME = ("empregado", "funcionario", "funcionaria", "colaborador", "colaboradora",
                 "trabalhador", "nome do empregado", "nome do funcionario", "nome completo", "nome")
# Palavras que encerram o nome quando vêm na mesma linha ("Nome: FULANO   CPF: ...").
_FIM_DO_NOME = re.compile(
    r"\s+(?:CPF|RG|PIS|CTPS|Matr[íi]cula|Cargo|Fun[çc][ãa]o|Setor|Admiss[ãa]o|Data|C[óo]d(?:igo)?|Registro|"
    r"Empresa|CNPJ|Se[çc][ãa]o|Departamento|Nasc|Sexo|Local|Centro)\b.*$", re.I)


def _sem_acento(texto: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def ler_fichas(caminho_pdf: str | Path) -> list[Colaborador]:
    """Lê todas as páginas e devolve um colaborador por CPF encontrado."""
    colaboradores: list[Colaborador] = []
    por_cpf: dict[str, Colaborador] = {}
    nome_arquivo = Path(caminho_pdf).name
    with pdfplumber.open(str(caminho_pdf)) as pdf:
        for numero, pagina in enumerate(pdf.pages, start=1):
            palavras = pagina.extract_words(keep_blank_chars=False, use_text_flow=False)
            texto = pagina.extract_text() or ""
            if not palavras or not texto.strip():
                continue
            if _achar(palavras, "REGISTRO") and _achar(palavras, "Empregado") and _achar(palavras, "Residência"):
                nome = _nome_registro(palavras)
            else:
                nome = _nome_por_rotulo(texto)
            cpf = _cpf(texto)
            if not cpf and not nome:
                continue
            if cpf and cpf in por_cpf:  # mesma pessoa em outra página
                if not por_cpf[cpf].nome and nome:
                    por_cpf[cpf].nome = nome
                continue
            c = Colaborador(nome=nome, cpf=cpf, origem=f"{nome_arquivo}, pág. {numero}")
            colaboradores.append(c)
            if cpf:
                por_cpf[cpf] = c
    for c in colaboradores:
        c.avisos = validar(c)
    return colaboradores


def _cpf(texto: str) -> str:
    achado = _RE_CPF_ROTULO.search(texto) or _RE_CPF.search(texto)
    if not achado:
        return ""
    return so_numeros(achado.group(1) if achado.re is _RE_CPF_ROTULO else achado.group(0))


def _limpar_nome(texto: str) -> str:
    texto = _FIM_DO_NOME.sub("", texto)
    texto = re.sub(r"^\s*\d+\s*[-–]\s*", "", texto)  # "123 - FULANO" (código do empregado)
    texto = re.sub(r"[^A-Za-zÀ-ÿ' ]+", " ", texto)
    texto = " ".join(texto.split())
    return texto if len(texto.split()) >= 2 else ""


def _nome_por_rotulo(texto: str) -> str:
    """O texto depois de "Empregado:", "Nome:"... na mesma linha ou na de baixo."""
    linhas = [l.strip() for l in texto.splitlines()]
    for rotulo in _ROTULOS_NOME:
        padrao = re.compile(r"(?:^|\b)" + rotulo.replace(" ", r"\s+") + r"\b\s*[:\-]?\s*(.*)$", re.I)
        for i, linha in enumerate(linhas):
            achado = padrao.search(_sem_acento(linha))
            if not achado:
                continue
            resto = linha[achado.start(1):] if achado.group(1) else ""
            nome = _limpar_nome(resto)
            if not nome and i + 1 < len(linhas):
                nome = _limpar_nome(linhas[i + 1])
            if nome:
                return nome
    return ""


def _nome_registro(palavras: list[dict]) -> str:
    """Ficha de Registro do Domínio: linha abaixo de "Empregado", sem a coluna "Beneficiários"."""
    empregado = _achar(palavras, "Empregado")
    residencia = _achar(palavras, "Residência")
    beneficiarios = _achar(palavras, "Beneficiários")
    limite_x = beneficiarios["x0"] - 2 if beneficiarios else 9999
    dentro = [p for p in palavras if p["top"] > empregado["bottom"] - 1 and p["bottom"] < residencia["top"] + 1
              and p["x0"] < limite_x]
    dentro.sort(key=lambda p: (round(p["top"]), p["x0"]))
    return " ".join(" ".join(p["text"] for p in dentro).split())


def _achar(palavras: list[dict], texto: str) -> dict | None:
    return next((p for p in palavras if p["text"] == texto), None)
