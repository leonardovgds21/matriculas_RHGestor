"""O e-mail aos colaboradores no padrão visual da GAP (HTML) e a abertura no Outlook.

O texto é o mesmo de email_alunos.CORPO, só organizado em blocos: logo,
saudação, caixa de destaque, seções numeradas, tabela com os dados que o
e-mail já trazia e lista de módulos. O HTML usa só tabelas e estilos na
própria tag, que é o que o Outlook mostra direito.

Abertura (do melhor para o mais simples):
1. Outlook clássico (automação COM): rascunho já formatado, com a logo embutida.
2. Senão (ex.: Outlook novo, que não tem COM): o link mailto abre o e-mail
   com destinatários e assunto, e o texto formatado vai para a área de
   transferência para colar com Ctrl+V.
"""

from __future__ import annotations

import base64
import html
import sys
from pathlib import Path

from .config import TURMA_PADRAO, recurso

VERDE = "#2e7d32"
VERDE_ESCURO = "#1b5e20"
VERDE_CLARO = "#e8f5e9"
AZUL = "#1f4e79"
CINZA = "#f2f2f2"
TEXTO = "#333333"
ID_LOGO = "logo_gap"


def arquivo_logo() -> Path | None:
    """assets/logo_gap.png, se existir (vai junto no executável)."""
    caminho = recurso("assets/logo_gap.png")
    return caminho if caminho.exists() else None


def _logo(src: str | None) -> str:
    if src:
        return f'<img src="{src}" alt="GAP" height="48" style="display:block;border:0;height:48px">'
    # sem o arquivo da logo: "GAP" em texto, nas cores da marca
    return (f'<span style="font:bold 30px Arial,sans-serif;color:{VERDE}">&#10138;</span>'
            f'<span style="font:bold 30px Arial,sans-serif;color:{AZUL};letter-spacing:1px">GAP</span>')


def _secao(numero: int, titulo: str) -> str:
    return (f'<tr><td style="padding:22px 0 8px 0">'
            f'<div style="border-left:4px solid {VERDE};padding-left:10px;font:bold 17px Arial,sans-serif;'
            f'color:{VERDE_ESCURO}">{numero}. {html.escape(titulo)}</div></td></tr>')


def _paragrafo(texto: str, estilo: str = "") -> str:
    return (f'<tr><td style="padding:6px 0;font:15px/1.5 Arial,sans-serif;color:{TEXTO};{estilo}">'
            f'{texto}</td></tr>')


def _linha_tabela(rotulo: str, valor: str) -> str:
    return (f'<tr><td style="background:{CINZA};padding:9px 12px;font:bold 14px Arial,sans-serif;color:#555;'
            f'width:170px;border-bottom:1px solid #ffffff">{html.escape(rotulo)}</td>'
            f'<td style="padding:9px 12px;font:14px Arial,sans-serif;color:{TEXTO};border-bottom:1px solid {CINZA}">'
            f'{valor}</td></tr>')


def montar_html(logo_src: str | None = None) -> str:
    """O e-mail completo em HTML. `logo_src` é "cid:..." (Outlook) ou "data:..." (colar)."""
    e = html.escape
    linhas = [
        f'<tr><td style="padding:0 0 18px 0;border-bottom:3px solid {VERDE}">{_logo(logo_src)}</td></tr>',
        _paragrafo(f'<span style="font-size:17px"><b>Olá. Como vai?</b></span>', "padding-top:18px"),
        _paragrafo(e("Para garantir que você comece sua trajetória com mais segurança e alinhamento com os "
                     "nossos valores e rotinas:")),
        f'<tr><td style="padding:10px 0"><div style="background:{VERDE_CLARO};border-left:5px solid {VERDE};'
        f'padding:14px 16px;font:15px/1.5 Arial,sans-serif;color:{VERDE_ESCURO}">'
        f'<b>ATENÇÃO:</b> é obrigatório que você faça os <b>{e(TURMA_PADRAO)}</b> na plataforma '
        f'<b>RH Gestor</b> antes do seu primeiro dia oficial de trabalho.</div></td></tr>',
        _secao(1, "Seus dados de acesso"),
        '<tr><td><table role="presentation" cellpadding="0" cellspacing="0" width="100%" '
        'style="border-collapse:collapse">'
        + _linha_tabela("Plataforma", "<b>RH Gestor</b>")
        + _linha_tabela("Trilha", e(TURMA_PADRAO))
        + _linha_tabela("Login e senha", "Você já deve ter recebido o seu login e senha de acesso por e-mail.")
        + "</table></td></tr>",
        _secao(2, "Comece por estes módulos"),
        _paragrafo("👉🏼 Damos destaque especial para que você realize primeiramente os seguintes módulos:"),
        f'<tr><td style="padding:4px 0"><ol style="margin:0;padding-left:24px;font:15px/1.7 Arial,sans-serif;'
        f'color:{TEXTO}"><li><b>Integração Institucional e Código de Conduta GAP</b></li>'
        f'<li><b>PGR e EPI – Promoção à Saúde</b></li></ol></td></tr>',
        _paragrafo(e("Esses conteúdos são fundamentais para o início da sua atuação e trazem informações que você "
                     "já utilizará desde o primeiro dia, sendo essencial para sua compreensão dos nossos "
                     "processos internos.")),
        _secao(3, "Prazo e certificado"),
        _paragrafo("📅 <b>Poderia nos informar até que dia consegue concluir?</b>"),
        _paragrafo(e("Lembrando que, ao final de cada módulo, será necessário realizar o teste para validar seu "
                     "conhecimento e gerar o certificado.")),
        _paragrafo(e("Caso tenha qualquer dúvida ou precise de suporte com o acesso, estamos à disposição!"),
                   "padding-top:18px"),
        _paragrafo("<b>Nos vemos em breve!</b>"),
        f'<tr><td style="padding:18px 0 0 0;border-top:1px solid {CINZA};font:13px Arial,sans-serif;color:#777">'
        f'<b>Observação:</b> se o treinamento já foi realizado, desconsiderar o e-mail.</td></tr>',
    ]
    return ('<!DOCTYPE html><html><head><meta charset="utf-8"></head>'
            '<body style="margin:0;padding:0;background:#ffffff">'
            '<table role="presentation" cellpadding="0" cellspacing="0" width="100%"><tr><td align="left" '
            'style="padding:20px">'
            '<table role="presentation" cellpadding="0" cellspacing="0" width="640" style="max-width:640px">'
            + "".join(linhas) + "</table></td></tr></table></body></html>")


def logo_data_uri() -> str | None:
    logo = arquivo_logo()
    if not logo:
        return None
    return "data:image/png;base64," + base64.b64encode(logo.read_bytes()).decode()


# ---------- Outlook clássico (COM) ----------
def abrir_no_outlook(destinatarios: list[str], assunto: str) -> bool:
    """Cria o rascunho formatado no Outlook clássico e mostra na tela.
    Devolve False se o Outlook clássico não estiver disponível."""
    if sys.platform != "win32":
        return False
    try:
        import win32com.client  # pywin32
    except ImportError:
        return False
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        email = outlook.CreateItem(0)  # olMailItem
        email.To = "; ".join(destinatarios)
        email.Subject = assunto
        logo = arquivo_logo()
        if logo:
            anexo = email.Attachments.Add(str(logo), 1, 0)
            # PR_ATTACH_CONTENT_ID: a imagem fica no corpo, não como anexo
            anexo.PropertyAccessor.SetProperty("http://schemas.microsoft.com/mapi/proptag/0x3712001F", ID_LOGO)
        email.HTMLBody = montar_html(f"cid:{ID_LOGO}" if logo else None)
        email.Display()
        return True
    except Exception:  # Outlook novo, Outlook fechado com erro, perfil não configurado...
        return False


# ---------- área de transferência com HTML ----------
def _cf_html(fragmento: str) -> bytes:
    """O formato "HTML Format" do Windows: cabeçalho com as posições em bytes."""
    modelo = ("Version:0.9\r\nStartHTML:{:010d}\r\nEndHTML:{:010d}\r\n"
              "StartFragment:{:010d}\r\nEndFragment:{:010d}\r\n")
    inicio, fim = "<html><body><!--StartFragment-->", "<!--EndFragment--></body></html>"
    tam_cab = len(modelo.format(0, 0, 0, 0).encode())
    corpo = fragmento.encode("utf-8")
    start_html = tam_cab
    start_frag = start_html + len(inicio.encode())
    end_frag = start_frag + len(corpo)
    end_html = end_frag + len(fim.encode())
    return (modelo.format(start_html, end_html, start_frag, end_frag).encode()
            + inicio.encode() + corpo + fim.encode())


def copiar_html(html_completo: str, texto: str, janela: int | None = None) -> bool:
    """Põe o e-mail na área de transferência como HTML (cola formatado no
    Outlook) e como texto simples. `janela` é o HWND do app: com ele a área de
    transferência tem dono (sem dono, o SetClipboardData pode falhar e o e-mail
    sai em branco ao colar). Devolve False fora do Windows ou se falhar."""
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    corpo = html_completo.split("<body", 1)[-1].split(">", 1)[-1].rsplit("</body>", 1)[0]
    dados_html = _cf_html(corpo) + b"\0"
    dados_texto = (texto + "\0").encode("utf-16-le")

    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.RegisterClipboardFormatW.restype = wintypes.UINT
    user32.OpenClipboard.argtypes = [wintypes.HWND]

    def colocar(formato: int, dados: bytes) -> bool:
        memoria = kernel32.GlobalAlloc(0x0002, len(dados))  # GMEM_MOVEABLE
        if not memoria:
            return False
        ponteiro = kernel32.GlobalLock(memoria)
        ctypes.memmove(ponteiro, dados, len(dados))
        kernel32.GlobalUnlock(memoria)
        return bool(user32.SetClipboardData(formato, memoria))

    import time

    for _ in range(10):  # outro programa pode estar com a área de transferência aberta
        if user32.OpenClipboard(janela):
            break
        time.sleep(0.05)
    else:
        return False
    try:
        user32.EmptyClipboard()
        ok = colocar(user32.RegisterClipboardFormatW("HTML Format"), dados_html)
        ok = colocar(13, dados_texto) and ok  # CF_UNICODETEXT
        return ok
    finally:
        user32.CloseClipboard()
