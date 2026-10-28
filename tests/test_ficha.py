from cadastro_rhgestor.ficha import _cpf, _nome_por_rotulo

# Textos fictícios no formato de fichas de EPI comuns
EPI_MESMA_LINHA = """FICHA DE CONTROLE DE ENTREGA DE EPI
Empresa: GAP GESTAO AMBIENTAL CNPJ: 00.000.000/0001-00
Empregado: 123 - MARIA DA SILVA SOUZA Função: AUXILIAR
CPF: 529.982.247-25 Admissão: 01/02/2026"""

EPI_LINHA_DE_BAIXO = """Ficha de EPI
Nome do Funcionário
JOÃO PEREIRA LIMA
CPF 11144477735"""

EPI_NOME_E_CPF = "Nome: José Antônio dos Santos CPF: 111.444.777-35 Setor: Obras"


def test_nome_na_mesma_linha():
    assert _nome_por_rotulo(EPI_MESMA_LINHA) == "MARIA DA SILVA SOUZA"
    assert _cpf(EPI_MESMA_LINHA) == "52998224725"


def test_nome_na_linha_de_baixo():
    assert _nome_por_rotulo(EPI_LINHA_DE_BAIXO) == "JOÃO PEREIRA LIMA"
    assert _cpf(EPI_LINHA_DE_BAIXO) == "11144477735"


def test_nome_seguido_de_cpf():
    assert _nome_por_rotulo(EPI_NOME_E_CPF) == "José Antônio dos Santos"
    assert _cpf(EPI_NOME_E_CPF) == "11144477735"
