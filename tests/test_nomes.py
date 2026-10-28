from cadastro_rhgestor.nomes import escolher, mesmo_nome, nome_igual, termos_de_busca
from cadastro_rhgestor.plataforma import ler_mensagem_adicionado, ler_processamento


def test_mesmo_nome_tolerante():
    assert nome_igual("Joao Carlos Soares Nascimento", "JOÃO CARLOS SOARES NASCIMENTO")
    assert nome_igual("Cleyton Antonio Oliveira", "Cleyton Antônio de Oliveira")
    assert mesmo_nome("Bruno Oliveira", "Bruno Matias Gonçalo de Oliveira")
    assert not mesmo_nome("Bruno Oliveira", "Oliveira Bruno")
    assert not mesmo_nome("Gabriel Shalon", "Gabriel Godoi Candido")
    assert not mesmo_nome("Maria", "Maria Silva")


def test_escolher():
    lista = ["JOÃO DA SILVA PEREIRA", "MARCOS PAULO SOUZA", "Marcos Paulo de Souza", "BRUNO MATIAS DE OLIVEIRA",
             "ANA LIMA", "ANA LIMA COSTA"]
    assert escolher("Joao Silva Pereira", lista) == ("igual", [0])
    assert escolher("Marcos Paulo Souza", lista) == ("homonimo", [1, 2])
    assert escolher("Bruno Oliveira", lista) == ("parecido", [3])
    assert escolher("Ana Lima", lista) == ("igual", [4])  # o nome exato vence o parecido
    assert escolher("Fulano Inexistente", lista) == ("nenhum", [])


def test_termos_de_busca():
    assert termos_de_busca("Maria Clara Oliveira Macedo") == ["Maria Clara Oliveira Macedo", "maria macedo", "oliveira"]
    assert termos_de_busca("Renan Pereira") == ["Renan Pereira", "pereira"]


def test_mensagens():
    assert ler_mensagem_adicionado("JOÃO DA SILVA PEREIRA adicionado!") == "JOÃO DA SILVA PEREIRA"
    assert ler_mensagem_adicionado("Aluno Maria Souza adicionada com sucesso") == "Maria Souza"
    assert ler_mensagem_adicionado("Erro ao adicionar Maria") is None
    assert ler_processamento("Processamento concluído  3 de 4") == (3, 4)
    assert ler_processamento("Aguarde, adicionando alunos 1 de 4") is None
