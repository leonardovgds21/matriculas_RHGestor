"""Teste de ponta a ponta da automação no site simulado (abre o Edge).

    python tests/site_simulado/e2e.py            (navegador invisível)
    python tests/site_simulado/e2e.py --mostrar  (vendo o navegador)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from servidor import iniciar  # noqa: E402

servidor, URL = iniciar()
os.environ["RHGESTOR_URL"] = URL
os.environ["RHGESTOR_EAD_URL"] = URL + "/TedCorporativa/Index"

from cadastro_rhgestor.entrada import ler_lista  # noqa: E402
from cadastro_rhgestor.plataforma import ErroPlataforma, Plataforma  # noqa: E402

TURMA = "Treinamentos Institucionais GAP SSMA"
falhas = []
registro = []


def log(texto):
    registro.append(texto)
    print("   log:", texto)


def confere(descricao, obtido, esperado):
    ok = obtido == esperado
    print(f"{'OK ' if ok else 'FALHOU'} {descricao}: {obtido!r}" + ("" if ok else f" (esperado {esperado!r})"))
    if not ok:
        falhas.append(descricao)


def rodar(p, texto, confirmar):
    lista = ler_lista(texto)
    resultados = {}
    p.adicionar(list(enumerate(lista)), confirmar=confirmar,
                aviso=lambda i, r: resultados.__setitem__(lista[i].nome, r.situacao))
    return resultados


with Plataforma(log=log, visivel="--mostrar" in sys.argv, espera=15) as p:
    try:
        p.login("gestor", "errada")
        confere("login errado recusado", "entrou", "recusado")
    except ErroPlataforma as erro:
        confere("login errado recusado", str(erro).startswith("Login recusado"), True)

    p.login("gestor", "teste")
    p.driver.execute_script("localStorage.removeItem('turma2'); localStorage.removeItem('tamPagina');")
    p.abrir_turma(TURMA)
    confere("abriu a turma certa", "Turma=" in p.driver.current_url or "id=2" in p.driver.current_url, True)

    r = rodar(p, "Joao Silva Pereira 529.982.247-25\nBeatriz Lima", confirmar=False)
    confere("modo teste", r, {"Joao Silva Pereira": "teste", "Beatriz Lima": "teste"})
    confere("modo teste não adicionou", p.driver.execute_script("return localStorage.getItem('turma2')"), None)

    r = rodar(p, """Joao Silva Pereira 529.982.247-25
Marcos Paulo Souza
Fulano Inexistente
Ana Paula Erro Teste
Bruno Oliveira
Beatriz Lima 111.444.777-35""", confirmar=True)
    confere("adicionar", r, {
        "Joao Silva Pereira": "adicionado", "Marcos Paulo Souza": "homonimo", "Fulano Inexistente": "nao_encontrado",
        "Ana Paula Erro Teste": "erro", "Bruno Oliveira": "adicionado", "Beatriz Lima": "adicionado"})
    confere("mensagens da plataforma no registro",
            [any(t.startswith("PLATAFORMA:") and frag in t for t in registro) for frag in (
                "JOÃO DA SILVA PEREIRA adicionado!", "Erro ao adicionar ANA PAULA", "Processamento concluído",
                "Você confirma adicionar")], [True] * 4)

    # lista com páginas: quem não aparece é procurado pela Busca por Nome
    p.driver.execute_script("localStorage.setItem('tamPagina', '3');")
    p.driver.get(p.url_turma)
    r = rodar(p, "Carla Mendes Rocha\nFernanda Costa\nCiclano Inexistente", confirmar=True)
    confere("busca por nome", r, {"Carla Mendes Rocha": "adicionado", "Fernanda Costa": "adicionado",
                                  "Ciclano Inexistente": "nao_encontrado"})
    confere("turma no fim", sorted(p.driver.execute_script("return JSON.parse(localStorage.getItem('turma2'))")),
            ["BEATRIZ LIMA", "BRUNO MATIAS DE OLIVEIRA", "CARLA MENDES ROCHA", "FERNANDA COSTA",
             "JOÃO DA SILVA PEREIRA"])

servidor.shutdown()
print("TUDO CERTO" if not falhas else f"{len(falhas)} FALHA(S): {', '.join(falhas)}")
sys.exit(1 if falhas else 0)
