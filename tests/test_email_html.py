import re
from html import unescape

from cadastro_rhgestor.email_alunos import CORPO
from cadastro_rhgestor.email_html import _cf_html, montar_html


def _texto(html: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def test_html_tem_o_mesmo_conteudo_do_texto():
    texto = _texto(montar_html())
    for trecho in ("Olá. Como vai?", "alinhamento com os nossos valores e rotinas",
                   "é obrigatório que você faça os Treinamentos Institucionais GAP SSMA na plataforma RH Gestor "
                   "antes do seu primeiro dia oficial de trabalho",
                   "Você já deve ter recebido o seu login e senha de acesso por e-mail.",
                   "Integração Institucional e Código de Conduta GAP", "PGR e EPI – Promoção à Saúde",
                   "Poderia nos informar até que dia consegue concluir?",
                   "realizar o teste para validar seu conhecimento e gerar o certificado",
                   "estamos à disposição!", "Nos vemos em breve!",
                   "se o treinamento já foi realizado, desconsiderar o e-mail."):
        assert trecho in texto, trecho
    assert "Olá. Como vai?" in CORPO  # o texto simples continua igual


def test_html_no_padrao_visual():
    html = montar_html()
    assert "ATENÇÃO:" in html and "border-left:5px solid" in html
    assert "1. Seus dados de acesso" in html and "2. Comece por estes módulos" in html
    assert ">GAP</span>" in html  # sem o arquivo da logo, "GAP" em texto
    assert 'src="cid:logo_gap"' in montar_html("cid:logo_gap")


def test_formato_html_da_area_de_transferencia():
    dados = _cf_html("<b>Olá</b>")
    cab = dados.decode("utf-8")
    pos = {k: int(v) for k, v in re.findall(r"(StartHTML|EndHTML|StartFragment|EndFragment):(\d+)", cab)}
    assert dados[pos["StartFragment"]:pos["EndFragment"]] == "<b>Olá</b>".encode()
    assert pos["EndHTML"] == len(dados)
