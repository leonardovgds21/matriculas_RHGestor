"""Ponto de entrada: python main.py (ou o executável CadastroRHGestor.exe)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from cadastro_rhgestor.gui import main  # noqa: E402

if __name__ == "__main__":
    main()
