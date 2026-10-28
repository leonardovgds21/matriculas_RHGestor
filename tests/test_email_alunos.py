from urllib.parse import unquote

from cadastro_rhgestor.email_alunos import (
    ASSUNTO, CORPO, LIMITE_MAILTO, destinatarios, email_base, email_disponivel, email_no_texto, link_mailto,
    preparar_link,
)


def test_email_base_regra_do_formaseg():
    assert email_base("MARIA APARECIDA DE SOUZA") == "maria.souza"
    assert email_base("JOÃO DA CONCEIÇÃO") == "joao.conceicao"
    assert email_base("JOSE DA SILVA FILHO") == "jose.silva"
    assert email_base("PEDRO D'ÁVILA JÚNIOR") == "pedro.davila"


def test_homonimos_recebem_numero():
    assert email_disponivel("maria.souza", set()) == "maria.souza@gapgestao.com.br"
    assert email_disponivel("maria.souza", {"maria.souza@gapgestao.com.br"}) == "maria.souza2@gapgestao.com.br"


def test_destinatarios_preferem_o_email_da_plataforma():
    pessoas = [("Maria de Souza", ""), ("Maria Souza", ""), ("Adauto Pereira Caetano", "ADAUTO.CAETANO@GAPGESTAO.COM.BR")]
    assert destinatarios(pessoas) == [
        ("Maria de Souza", "maria.souza@gapgestao.com.br", "regra"),
        ("Maria Souza", "maria.souza2@gapgestao.com.br", "regra"),
        ("Adauto Pereira Caetano", "adauto.caetano@gapgestao.com.br", "plataforma"),
    ]


def test_email_no_texto():
    assert email_no_texto("ASSESSOR | 64999388471 | ADAUTO.CAETANO@GAPGESTAO.COM.BR | SYNGENTA") == \
        "adauto.caetano@gapgestao.com.br"
    assert email_no_texto("Auxiliar | Matriz") == ""


def test_assunto_e_corpo():
    assert ASSUNTO == "treinamentos RH GESTOR - GAP"
    assert CORPO.startswith("Olá. Como vai?\n\nPara garantir que você comece sua trajetória")
    assert "rotinas, é obrigatório que você faça os Treinamentos Institucionais GAP SSMA" in CORPO
    assert "▪️ Integração Institucional e Código de Conduta GAP\n▪️ PGR e EPI – Promoção à Saúde\n" in CORPO
    assert "📅 Poderia nos informar até que dia consegue concluir?" in CORPO
    assert CORPO.endswith("Observação: se o treinamento já foi realizado, desconsiderar o e-mail.")


def test_link_mailto():
    link = link_mailto(["a@x.com", "b@x.com"], "Olá & tchau", "linha 1\nlinha 2")
    assert link.startswith("mailto:a@x.com,b@x.com?subject=")
    assert unquote(link.split("body=")[1]) == "linha 1\r\nlinha 2"


def test_link_longo_tira_corpo_e_depois_destinatarios():
    poucos = [f"aluno{i}@gapgestao.com.br" for i in range(5)]
    assert preparar_link(poucos, ASSUNTO, "texto")[1:] == (True, True)
    assert preparar_link(poucos, ASSUNTO, "x" * LIMITE_MAILTO)[1:] == (True, False)
    link, dest, corpo = preparar_link([f"aluno{i}@gapgestao.com.br" for i in range(200)], ASSUNTO, "texto")
    assert not dest and not corpo and len(link) <= LIMITE_MAILTO
