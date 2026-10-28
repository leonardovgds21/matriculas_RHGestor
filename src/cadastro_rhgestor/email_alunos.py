"""E-mail aos colaboradores adicionados na turma, aberto no Outlook.

O endereço segue a mesma regra do FormaSeg: primeironome.ultimonome@gapgestao.com.br
(sem acento, sem preposições e sem sufixo como Filho/Júnior; homônimos da
mesma lista recebem 2, 3...). Se a lista "Pesquisar Alunos" do RHGestor
mostrou o e-mail da pessoa, vale o da plataforma.

O Outlook novo não tem a automação (COM) do Outlook clássico, então o
e-mail é aberto por um link mailto:, que o Windows entrega ao app de e-mail
padrão. Links muito longos são cortados pelo Windows; nesse caso o corpo vai
para a área de transferência e o link leva só destinatários e assunto.
"""

from __future__ import annotations

import re
from urllib.parse import quote

from .config import DOMINIO_EMAIL
from .nomes import sem_acento

# O Windows aceita ~2048 caracteres num link; fica uma folga.
LIMITE_MAILTO = 1900
# Podem ir sem codificar no assunto/corpo de um mailto (RFC 6068), o que encurta o link.
SEGUROS = "!'()*,:@/"

SUFIXOS = {"filho", "filha", "junior", "jr", "neto", "neta", "sobrinho", "sobrinha", "segundo", "terceiro"}
PARTICULAS = {"da", "das", "de", "do", "dos", "e"}

ASSUNTO = "treinamentos RH GESTOR - GAP"

CORPO = """Olá. Como vai?

Para garantir que você comece sua trajetória com mais segurança e alinhamento com os nossos valores e rotinas, \
é obrigatório que você faça os Treinamentos Institucionais GAP SSMA na plataforma RH Gestor antes do seu primeiro \
dia oficial de trabalho.

Você já deve ter recebido o seu login e senha de acesso por e-mail.

👉🏼 Damos destaque especial para que você realize primeiramente os seguintes módulos:

▪️ Integração Institucional e Código de Conduta GAP
▪️ PGR e EPI – Promoção à Saúde

Esses conteúdos são fundamentais para o início da sua atuação e trazem informações que você já utilizará desde \
o primeiro dia, sendo essencial para sua compreensão dos nossos processos internos.

📅 Poderia nos informar até que dia consegue concluir?

Lembrando que, ao final de cada módulo, será necessário realizar o teste para validar seu conhecimento e gerar \
o certificado.

Caso tenha qualquer dúvida ou precise de suporte com o acesso, estamos à disposição!

Nos vemos em breve!

Observação: se o treinamento já foi realizado, desconsiderar o e-mail."""

_RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def _slug(palavra: str) -> str:
    return re.sub(r"[^a-z]", "", sem_acento(palavra).lower())


def email_base(nome_completo: str) -> str:
    """primeironome.ultimonome (sem acento, sem sufixo como Filho/Júnior)."""
    palavras = [p for p in (_slug(p) for p in nome_completo.split()) if p]
    if not palavras:
        return ""
    primeiro = palavras[0]
    resto = [p for p in palavras[1:] if p not in PARTICULAS]
    while len(resto) > 1 and resto[-1] in SUFIXOS:
        resto.pop()
    ultimo = resto[-1] if resto else ""
    return f"{primeiro}.{ultimo}" if ultimo else primeiro


def email_disponivel(base: str, existentes: set[str]) -> str:
    """maria.souza, ou maria.souza2, maria.souza3... se já existir."""
    existentes = {e.lower() for e in existentes}
    email = f"{base}@{DOMINIO_EMAIL}"
    n = 2
    while email in existentes:
        email = f"{base}{n}@{DOMINIO_EMAIL}"
        n += 1
    return email


def email_no_texto(texto: str) -> str:
    """O primeiro e-mail que aparece no texto (ex.: a linha da lista de alunos), em minúsculas."""
    achado = _RE_EMAIL.search(texto or "")
    return achado.group(0).lower() if achado else ""


def destinatarios(pessoas: list[tuple[str, str]]) -> list[tuple[str, str, str]]:
    """[(nome, e-mail da plataforma ou "")] -> [(nome, e-mail, origem)], origem "plataforma" ou "regra"."""
    usados = {e.lower() for _, e in pessoas if e}
    saida = []
    for nome, da_plataforma in pessoas:
        if da_plataforma:
            saida.append((nome, da_plataforma.lower(), "plataforma"))
            continue
        base = email_base(nome)
        if not base:
            continue
        email = email_disponivel(base, usados)
        usados.add(email)
        saida.append((nome, email, "regra"))
    return saida


def link_mailto(destinatarios: list[str], assunto: str, corpo: str = "") -> str:
    """Link mailto: com destinatários separados por vírgula (RFC 6068)."""
    para = ",".join(quote(e, safe="@") for e in destinatarios)
    partes = [f"subject={quote(assunto, safe=SEGUROS)}"]
    if corpo:
        partes.append(f"body={quote(corpo.replace(chr(10), chr(13) + chr(10)), safe=SEGUROS)}")
    return f"mailto:{para}?{'&'.join(partes)}"


def preparar_link(destinatarios: list[str], assunto: str, corpo: str) -> tuple[str, bool, bool]:
    """Devolve (link, com_destinatarios, com_corpo), tirando o que não couber."""
    for com_dest, com_corpo in ((True, True), (True, False), (False, False)):
        link = link_mailto(destinatarios if com_dest else [], assunto, corpo if com_corpo else "")
        if len(link) <= LIMITE_MAILTO:
            return link, com_dest, com_corpo
    return link_mailto([], assunto), False, False
