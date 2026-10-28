from cadastro_rhgestor.entrada import cpf_valido, formatar_cpf, ler_lista

# CPFs fictícios (só com os dígitos verificadores certos)
CPF1, CPF2 = "52998224725", "11144477735"


def test_cpf_valido():
    assert cpf_valido(CPF1)
    assert cpf_valido("111.444.777-35")
    assert not cpf_valido("52998224724")
    assert not cpf_valido("11111111111")
    assert not cpf_valido("123")


def test_formatar():
    assert formatar_cpf(CPF1) == "529.982.247-25"


def test_formatos_de_linha():
    texto = f"""
    529.982.247-25 Maria da Silva
    João Pereira;{CPF2}
    1. Ana Souza\t123.456.789-09
    """
    lista = ler_lista(texto)
    assert [(c.nome, c.cpf) for c in lista] == [
        ("Maria da Silva", CPF1), ("João Pereira", CPF2), ("Ana Souza", "12345678909")]
    assert lista[0].avisos == [] and lista[1].avisos == []


def test_cpf_e_nome_em_linhas_separadas():
    lista = ler_lista(f"Maria da Silva\n{CPF1}\n{CPF2}\nJoão Pereira")
    assert [(c.nome, c.cpf) for c in lista] == [("Maria da Silva", CPF1), ("João Pereira", CPF2)]


def test_avisos():
    lista = ler_lista(f"Maria {CPF1}\nSem Documento\n52998224724 José Lima\nOutra Maria {CPF1}\nsem documento")
    assert lista[0].avisos == ["informe o nome completo"]
    assert lista[1].avisos == []  # sem CPF pode: a busca é pelo nome
    assert lista[2].avisos == ["CPF inválido"]
    assert "CPF repetido na lista" in lista[3].avisos
    assert lista[4].avisos == ["nome repetido na lista"]
