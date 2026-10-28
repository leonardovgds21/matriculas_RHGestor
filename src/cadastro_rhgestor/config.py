"""Caminhos do app e endereços da plataforma.

Quando roda como executável, os dados ficam ao lado do .exe (dados/), para a
pasta poder ser copiada inteira para outro computador.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# RHGESTOR_URL e RHGESTOR_EAD_URL trocam os endereços (usado nos testes com o site simulado).
URL_BASE = os.environ.get("RHGESTOR_URL", "https://sistema.rhgestor.com.br").rstrip("/")
URL_UNIVERSIDADE = os.environ.get("RHGESTOR_EAD_URL",
                                  "https://ead.sistema.rhgestor.com.br/TedCorporativa/Index")
TURMA_PADRAO = "Treinamentos Institucionais GAP SSMA"
INICIO_DA_TURMA = "01/01/1900"


def pasta_base() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def pasta_dados() -> Path:
    pasta = pasta_base() / "dados"
    pasta.mkdir(exist_ok=True)
    return pasta
