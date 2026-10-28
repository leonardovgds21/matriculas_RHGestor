"""Automação da plataforma RHGestor (Sólides) em segundo plano.

Usa o Microsoft Edge que já vem no Windows (ou o Chrome, se o Edge falhar),
controlado pelo Selenium. O fluxo é o mesmo que a pessoa faz na mão:

1. Login (campos "Login" e "Senha", botão "Acessar").
2. Menu Treinamentos (T&D) > Universidade Corporativa.
3. Filtro "Início da turma" = 01/01/1900 e o botão de atualizar/pesquisar.
4. Card da turma (ex.: "Treinamentos Institucionais GAP SSMA") > "+ Alunos".
5. Na janela "Pesquisar Alunos", marca a caixinha de cada pessoa (achada pelo
   nome; a lista não mostra CPF). Nunca usa o botão "Todos".
6. "+ Adicionar" > "Confirmar" e lê as mensagens: "NOME adicionado!" de cada
   aluno e "Processamento concluído N de M" no fim.

Quem está na lista que abre é marcado e adicionado de uma vez. Quem não
aparece nela (lista com várias páginas) é procurado pelo campo "Busca por
Nome" e adicionado sozinho, porque uma nova pesquisa pode desmarcar o que já
estava marcado.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from .config import INICIO_DA_TURMA, URL_BASE, URL_UNIVERSIDADE, pasta_dados
from .email_alunos import email_no_texto
from .entrada import Colaborador
from .nomes import escolher, mesmo_nome, nome_igual, normalizar, palavras, termos_de_busca

Log = Callable[[str], None]

_JS_NORM = r"""
const norm = t => (t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/\s+/g, ' ').trim().toLowerCase();
const letras = t => norm(t).replace(/[^a-z0-9 ]+/g, ' ').replace(/\s+/g, ' ').trim();
const vis = e => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));
"""

# O elemento clicável visível cujo texto (ou value/title) é o procurado, sem
# contar símbolos e ícones ("+ Alunos" = "alunos"). Prefere o texto igual,
# depois o que começa com ele. arguments[1] limita a busca a um elemento.
_JS_ACHAR_BOTAO = _JS_NORM + r"""
const alvo = arguments[0], raiz = arguments[1] || document, soIgual = arguments[2];
const textos = e => [e.textContent, e.value, e.getAttribute('title'), e.getAttribute('aria-label')].map(letras);
const todos = [...raiz.querySelectorAll('a, button, input[type=button], input[type=submit], [role=button], [onclick], li, span, div, label')]
    .filter(vis);
const internos = l => l.filter(e => !l.some(o => o !== e && e.contains(o)));
let achados = internos(todos.filter(e => textos(e).some(t => t === alvo)));
if (!achados.length && !soIgual) achados = internos(todos.filter(e => textos(e).some(t => t.startsWith(alvo + ' '))));
const el = achados.find(e => e.matches('a, button, input, [role=button]')) || achados[0];
if (!el) return null;
return el.closest('a, button, input, [role=button], [onclick]') || el;
"""

# O campo de texto/data ligado a um rótulo (texto do <label>, placeholder ou
# nome), ou null.
_JS_CAMPO_DO_ROTULO = _JS_NORM + r"""
const alvo = arguments[0], raiz = arguments[1] || document;
const campos = [...raiz.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([type=radio]), textarea')];
let c = campos.find(e => vis(e) && [e.placeholder, e.getAttribute('aria-label'), e.title].some(t => letras(t).includes(alvo)));
if (c) return c;
const rotulos = [...raiz.querySelectorAll('label, span, div, p, th, td, strong, b, h5, h6')]
    .filter(e => vis(e) && letras(e.textContent) === alvo);
for (const r of rotulos) {
    if (r.htmlFor) { const f = document.getElementById(r.htmlFor); if (f && vis(f)) return f; }
    let pai = r;
    for (let i = 0; i < 4 && pai; i++, pai = pai.parentElement) {
        const f = [...pai.querySelectorAll('input:not([type=hidden]):not([type=checkbox]), textarea')].find(vis);
        if (f) return f;
    }
    const depois = campos.filter(vis).find(f => r.compareDocumentPosition(f) & Node.DOCUMENT_POSITION_FOLLOWING);
    if (depois) return depois;
}
return null;
"""

# Põe a data no campo, avisando a página (input/change), seja <input type=date> ou texto.
_JS_POR_DATA = r"""
const campo = arguments[0], ddmmaaaa = arguments[1];
const [d, m, a] = ddmmaaaa.split('/');
const $ = window.jQuery;
const widget = $ && ($(campo).data('kendoDatePicker') || $(campo).data('kendoDateInput') || $(campo).data('datepicker'));
if (widget && widget.value) {  // calendário do Kendo (o campo mostra dd-mm-aaaa)
    widget.value(new Date(+a, +m - 1, +d));
    if (widget.trigger) widget.trigger('change');
    return campo.value;
}
const sep = (campo.value.match(/\d([\/.-])\d/) || [null, '/'])[1];
const valor = campo.type === 'date' ? `${a}-${m}-${d}` : [d, m, a].join(sep);
const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
setter.call(campo, valor);
for (const ev of ['input', 'change', 'blur']) campo.dispatchEvent(new Event(ev, {bubbles: true}));
if (window.jQuery) { try { window.jQuery(campo).trigger('change'); } catch (e) {} }
return campo.value;
"""

# Põe o texto no campo como se tivesse sido digitado.
_JS_POR_VALOR = r"""
const campo = arguments[0], texto = arguments[1];
campo.focus();
const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(campo), 'value').set;
setter.call(campo, texto);
for (const ev of ['input', 'change']) campo.dispatchEvent(new Event(ev, {bubbles: true}));
campo.dispatchEvent(new KeyboardEvent('keyup', {bubbles: true, key: 'a'}));
"""

# O botão de atualizar/pesquisar da Universidade Corporativa (ícone no canto
# de cima, à direita), achado pelo título/dica ou pelo ícone.
_JS_BOTAO_ATUALIZAR = _JS_NORM + r"""
const dica = e => letras([e.title, e.getAttribute('data-original-title'), e.getAttribute('aria-label'),
                          e.getAttribute('data-bs-original-title'), e.getAttribute('data-tooltip')].join(' '));
const clicavel = e => e.closest('a, button, [role=button], [onclick]') || e;
const todos = [...document.querySelectorAll('a, button, i, span, [role=button], [onclick]')].filter(vis);
let el = todos.find(e => dica(e).includes('atualizar janela')) ||
         todos.find(e => /atualizar|pesquisar|refresh/.test(dica(e)));
if (!el) {
    const icones = todos.filter(e => /(^|[\s-])(refresh|sync|redo|rotate|arrows-rotate|autorenew|cached)\b/.test(
        (typeof e.className === 'string' ? e.className : '') + ' ' + norm(e.textContent).slice(0, 20)));
    icones.sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top
                          || b.getBoundingClientRect().left - a.getBoundingClientRect().left);
    el = icones[0];
}
return el ? clicavel(el) : null;
"""

# O card da turma: o menor bloco visível com o nome da turma, subindo até o
# que é clicável. Devolve [elemento, quantos cards têm esse nome].
_JS_CARD_TURMA = _JS_NORM + r"""
const alvo = arguments[0];
const todos = [...document.querySelectorAll('body *')].filter(e => vis(e) && letras(e.textContent).includes(alvo));
const internos = todos.filter(e => !todos.some(o => o !== e && e.contains(o)));
if (!internos.length) return null;
const el = internos[0];
// clica no título (o ícone ao lado dele duplica a turma)
const card = el.closest('a, [onclick]') || el;
return [card, internos.length];
"""

# A janela "Pesquisar Alunos": o bloco que tem o campo "Busca por Nome" e as
# caixinhas da lista. null enquanto não abriu.
_JS_JANELA_ALUNOS = _JS_NORM + r"""
const campos = [...document.querySelectorAll('input:not([type=hidden]):not([type=checkbox])')].filter(vis);
const busca = campos.find(e => [e.placeholder, e.getAttribute('aria-label'), e.name, e.id, e.title]
                                .some(t => /busca|nome|pesquis/.test(letras(t))));
const modais = [...document.querySelectorAll('.modal, [role=dialog], .modal-dialog, .ui-dialog, .k-window')].filter(vis);
const comTitulo = modais.find(m => letras(m.textContent).includes('pesquisar alunos'));
if (comTitulo) return comTitulo;
if (!busca) return null;
let el = busca;
while (el && el !== document.body) {
    if (el.querySelector('tbody input[type=checkbox], [role=row] input[type=checkbox]')) return el;
    el = el.parentElement;
}
// lista vazia (ex.: depois de uma pesquisa sem resultado): a página continua sendo a de Pesquisar Alunos
return /pesquisar alunos/.test(letras(document.body.innerText)) ? document.body : null;
"""

# As linhas da lista de alunos: [nome, resto do texto, marcada]. A linha é a
# que tem uma caixinha; a do cabeçalho ("marcar todos") fica de fora. O nome
# vem da coluna "Nome" do cabeçalho, se houver; senão, a 1ª coluna com texto.
_JS_LINHAS_ALUNOS = _JS_NORM + r"""
const raiz = arguments[0] || document;
const caixas = [...raiz.querySelectorAll('input[type=checkbox]')].filter(c => !c.closest('thead'));
const linhas = [];
for (const c of caixas) {
    const tr = c.closest('tr, li, [role=row]') || c.parentElement.parentElement;
    if (!tr || !vis(tr) || linhas.some(l => l.tr === tr)) continue;
    let nome = '', resto = '';
    if (tr.tagName === 'TR') {
        const tabela = tr.closest('table');
        const cab = tabela ? [...tabela.querySelectorAll('thead th, thead td')].map(th => letras(th.textContent)) : [];
        const celulas = [...tr.children];
        let i = cab.findIndex(t => t === 'nome' || t.startsWith('nome ') || t === 'aluno' || t === 'colaborador');
        if (i < 0 || !celulas[i] || !celulas[i].innerText.trim()) i = celulas.findIndex(td => td.innerText.trim());
        const linhasNome = i >= 0 ? celulas[i].innerText.split('\n').map(t => t.trim()).filter(t => t) : [];
        nome = linhasNome[0] || '';
        // cargo, telefone e e-mail ficam na mesma célula do nome, embaixo dele
        resto = linhasNome.slice(1).concat(celulas.filter((_, j) => j !== i).map(td => td.innerText.replace(/\s+/g, ' ').trim()))
            .filter(t => t).join(' | ');
    } else {
        const partes = tr.innerText.split('\n').map(t => t.trim()).filter(t => t);
        nome = partes[0] || ''; resto = partes.slice(1).join(' | ');
    }
    if (nome) linhas.push({tr, caixa: c, nome, resto});
}
window.__rhLinhas = linhas;
return linhas.map(l => [l.nome, l.resto, l.caixa.checked || /selected|active|checked/.test(l.tr.className)]);
"""

# Marca a caixinha da linha arguments[0] (de _JS_LINHAS_ALUNOS) e diz se ficou marcada.
_JS_MARCAR = _JS_NORM + r"""
const l = (window.__rhLinhas || [])[arguments[0]];
if (!l) return null;
const marcada = () => l.caixa.checked || /selected|checked/.test(l.tr.className);
if (marcada()) return true;
l.tr.scrollIntoView({block: 'center'});
const alvos = [l.caixa, l.caixa.closest('label'), l.caixa.nextElementSibling, l.caixa.parentElement].filter(e => e);
for (const a of alvos) {
    if (!vis(a) && a !== l.caixa) continue;
    a.click();
    if (marcada()) return true;
}
return marcada();
"""

# "Exibindo itens 1 - 62 de 62" -> [1, 62, 62], ou null.
_JS_CONTADOR = _JS_NORM + r"""
const raiz = arguments[0] || document;
const m = norm(raiz.innerText).match(/exibindo(?: itens)?\s*(\d+)\s*(?:-|a|ate)\s*(\d+)\s*de\s*(\d+)/);
return m ? [+m[1], +m[2], +m[3]] : null;
"""

# Guarda o texto de tudo que aparece na tela enquanto os alunos são
# adicionados (avisos que somem sozinhos, janelas, contador), para o app
# mostrar todas as mensagens da plataforma.
_JS_OUVIR_MENSAGENS = r"""
window.__rhMsgs = [];
if (window.__rhOuvinte) window.__rhOuvinte.disconnect();
const tipo = /toast|alert|noty|notif|swal|snack|message|mensag|growl|modal|popup|dialog|process|aguard|loading|bootbox|msg/i;
const chave = /adicionad|erro|falh|process|aguard|nao |não |sucesso|aten[cç]|aviso|inv[aá]lid|j[aá] /i;
const guardar = el => {
    if (!el || el.nodeType !== 1) return;
    const texto = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
    if (!texto || texto.length > 400 || el.querySelector('input[type=checkbox], table')) return;
    let pai = el, tipado = false;
    for (let i = 0; i < 6 && pai; i++, pai = pai.parentElement) {
        if (tipo.test((typeof pai.className === 'string' ? pai.className : '') + ' ' + (pai.id || '') + ' ' + (pai.getAttribute('role') || ''))) { tipado = true; break; }
    }
    if (tipado || (chave.test(texto) && texto.length < 200)) window.__rhMsgs.push(texto);
};
window.__rhOuvinte = new MutationObserver(lista => {
    for (const m of lista) {
        if (m.type === 'characterData') guardar(m.target.parentElement);
        else for (const n of m.addedNodes) guardar(n.nodeType === 1 ? n : n.parentElement);
    }
});
window.__rhOuvinte.observe(document.body, {childList: true, subtree: true, characterData: true});
"""

# Os textos visíveis de avisos/janelas na tela agora (para não perder o que
# já estava na tela quando o ouvinte começou e o contador da janela de espera).
_JS_MENSAGENS_NA_TELA = _JS_NORM + r"""
const sel = '.toast, .toast-message, .toast-title, [class*=toast], .alert, .noty_body, [class*=notif], .swal2-popup, ' +
            '.modal.show .modal-body, .modal.in .modal-body, .modal[style*=block] .modal-body, .bootbox-body, ' +
            '[role=alert], [role=dialog], [class*=process], [class*=aguard]';
const vistos = [...document.querySelectorAll(sel)].filter(e => vis(e) && !e.querySelector('input[type=checkbox], table'))
    .map(e => (e.innerText || '').replace(/\s+/g, ' ').trim()).filter(t => t && t.length <= 400);
return [...new Set(vistos)];
"""

# O texto da pergunta "Você confirma adicionar...?" (o bloco mais interno), ou null.
_JS_PERGUNTA = _JS_NORM + r"""
const l = [...document.querySelectorAll('body *')].filter(e => vis(e) && /confirma adicionar/.test(letras(e.textContent)));
const internos = l.filter(e => !l.some(o => o !== e && e.contains(o)));
return internos.length ? internos[0].innerText.replace(/\s+/g, ' ').trim() : null;
"""

# O texto da janela que diz "Processamento concluído" (com o contador "N de M").
_JS_JANELA_PROCESSAMENTO = _JS_NORM + r"""
const l = [...document.querySelectorAll('body *')].filter(e => vis(e) && /processamento conclu/.test(letras(e.textContent)));
const internos = l.filter(e => !l.some(o => o !== e && e.contains(o)));
if (!internos.length) return null;
let el = internos[0];
for (let i = 0; i < 4 && el.parentElement; i++) {
    if (/\d+\s*de\s*\d+/.test(norm(el.innerText))) break;
    el = el.parentElement;
}
return el.innerText;
"""

# A página de verificação de segurança do site (Cloudflare: "Just a moment...").
_JS_VERIFICACAO = _JS_NORM + r"""
const titulo = norm(document.title), texto = norm(document.body ? document.body.innerText : '').slice(0, 3000);
return /just a moment|um momento|attention required/.test(titulo)
    || /verify you are human|confirme que (voce )?e humano|verifique se (voce )?e humano|checking your browser|verificando (seu navegador|se a conexao)/.test(texto)
    || !!document.querySelector('iframe[src*="challenges.cloudflare.com"], #challenge-form, #challenge-running, #cf-challenge-running');
"""

# A pesquisa de avaliação (NPS da Track.co) aberta: ["iframe", frame] ou
# ["botao", X], ou null. O X é procurado só em volta do texto da pesquisa.
_JS_PESQUISA = _JS_NORM + r"""
const frames = [...document.querySelectorAll('iframe')].filter(f => vis(f) &&
    /track\.co|tracksale|trackco|nps|survey|pesquisa/i.test([f.src, f.id, f.name, f.className, f.title].join(' ')));
if (frames.length) return ['iframe', frames[0]];
const ehPesquisa = t => /recomendaria|escala de 0 a 10|track co/.test(t);
const blocos = [...document.querySelectorAll('body *')].filter(e => vis(e) && ehPesquisa(letras(e.innerText || '')));
const internos = blocos.filter(e => !blocos.some(o => o !== e && e.contains(o)));
const ehX = e => vis(e) && (/^[x×✕✖]$/i.test((e.innerText || e.textContent || '').trim()) ||
    /(^|[\s_-])(close|fechar|dismiss)/i.test([typeof e.className === 'string' ? e.className : '',
        e.getAttribute('aria-label') || '', e.title || ''].join(' ')));
for (const b of internos) {
    let el = b;
    for (let i = 0; i < 6 && el && el !== document.body; i++, el = el.parentElement) {
        const x = [...el.querySelectorAll('button, a, span, i, svg, div, [role=button]')].find(ehX);
        if (x) return ['botao', x.closest('button, a, [role=button]') || x];
    }
}
return null;
"""

# O X dentro do iframe da pesquisa.
_JS_X_NO_FRAME = _JS_NORM + r"""
const ehX = e => vis(e) && (/^[x×✕✖]$/i.test((e.innerText || e.textContent || '').trim()) ||
    /(^|[\s_-])(close|fechar|dismiss)/i.test([typeof e.className === 'string' ? e.className : '',
        e.getAttribute('aria-label') || '', e.title || ''].join(' ')));
const x = [...document.querySelectorAll('button, a, span, i, svg, div, [role=button]')].find(ehX);
return x ? (x.closest('button, a, [role=button]') || x) : null;
"""

# Um X logo fora do iframe (no mesmo bloco que o envolve).
_JS_X_PERTO = _JS_NORM + r"""
let el = arguments[0].parentElement;
for (let i = 0; i < 3 && el && el !== document.body; i++, el = el.parentElement) {
    const x = [...el.querySelectorAll('button, a, span, i, [role=button]')].find(e => vis(e) &&
        (/^[x×✕✖]$/i.test((e.innerText || '').trim()) || /close|fechar/i.test((e.className || '') + (e.getAttribute('aria-label') || ''))));
    if (x) return x;
}
return null;
"""

_JS_ESCONDER_PESQUISA = r"""
for (const f of document.querySelectorAll('iframe')) {
    if (/track\.co|tracksale|trackco|nps|survey|pesquisa/i.test([f.src, f.id, f.name, f.className, f.title].join(' '))) {
        (f.closest('[style*=fixed], [class*=modal], [class*=overlay], [class*=track]') || f).style.display = 'none';
    }
}
"""

# Mensagens de "carregando" na frente da tela.
_JS_CARREGANDO = _JS_NORM + r"""
return [...document.querySelectorAll('.blockUI, .loading, .loader, .spinner, .spinner-border, .k-loading-mask, ' +
        '[class*=loading], [class*=carregando]')].some(e => vis(e) && e.getBoundingClientRect().width > 20);
"""

_JS_ALERTA = _JS_NORM + r"""
const a = [...document.querySelectorAll('.alert-danger, .alert-warning, .alert, .validation-summary-errors, ' +
           '.field-validation-error, .text-danger, .toast-error, .swal2-popup, [role=alert]')].find(vis);
return a ? a.innerText.replace(/\s+/g, ' ').trim() : '';
"""

_RE_ADICIONADO = re.compile(r"^(?:aluno\(?a?\)?\s*:?\s*)?(.+?)\s+adicionad[oa]s?\b", re.I)
_RE_PROCESSAMENTO = re.compile(r"processamento\s+conclu\w*\D*?(\d+)\s*de\s*(\d+)", re.I)
_RE_CONCLUIDO = re.compile(r"processamento\s+conclu", re.I)
_RE_BOTOES_NO_FIM = re.compile(r"(?:\s+(?:Confirmar|Fechar|Cancelar|OK|Ok|×))+\s*$")
_RE_PROBLEMA = re.compile(r"erro|falh|n[aã]o\s|inv[aá]lid|j[aá]\s+(est[aá]|consta|existe|matricul|cadastr)|aten[cç][aã]o|aviso",
                          re.I)


def ler_mensagem_adicionado(texto: str) -> str | None:
    """'NOME adicionado!' -> 'NOME'; None se a mensagem não for de aluno adicionado."""
    texto = " ".join((texto or "").split())
    if _RE_PROBLEMA.search(texto):
        return None
    achado = _RE_ADICIONADO.search(texto)
    return achado.group(1).strip(" :-") if achado else None


def ler_processamento(texto: str) -> tuple[int, int] | None:
    """'Processamento concluído 3 de 4' -> (3, 4)."""
    achado = _RE_PROCESSAMENTO.search(" ".join((texto or "").split()))
    return (int(achado.group(1)), int(achado.group(2))) if achado else None


class ErroPlataforma(Exception):
    pass


@dataclass
class Resultado:
    """O que aconteceu com uma pessoa da lista."""
    situacao: str  # adicionado, marcado (modo teste), nao_encontrado, homonimo, sem_confirmacao, erro
    detalhe: str = ""
    nome_na_lista: str = ""
    email: str = ""  # o e-mail que a lista de alunos mostrou, se mostrou


@dataclass
class _Linha:
    nome: str
    resto: str
    marcada: bool
    indice: int = -1


@dataclass
class _Lote:
    pessoas: list[tuple[int, Colaborador, str]] = field(default_factory=list)  # (posição, colaborador, nome na lista)


class Plataforma:
    def __init__(self, log: Log = print, visivel: bool = False, espera: int = 30):
        self.log = log
        self.visivel = visivel
        self.espera = espera
        self.driver: webdriver.Remote | None = None
        self.url_turma = ""
        self.emails: dict[str, str] = {}  # nome na lista -> e-mail mostrado na lista

    # ---------- navegador ----------
    def __enter__(self):
        self.driver = self._abrir_navegador()
        self.driver.set_page_load_timeout(120)
        return self

    def __exit__(self, *_):
        if self.driver:
            self.driver.quit()

    def _abrir_navegador(self):
        """Edge (ou Chrome) com um perfil próprio do app em dados/, para a
        verificação de segurança do site, quando aparecer, valer nas próximas vezes."""
        erros = []
        for nome, classe, criar_opcoes in [
            ("Edge", webdriver.Edge, webdriver.EdgeOptions),
            ("Chrome", webdriver.Chrome, webdriver.ChromeOptions),
        ]:
            for com_perfil in (True, False):  # sem perfil se ele estiver em uso por outra janela
                opcoes = criar_opcoes()
                if not self.visivel:
                    opcoes.add_argument("--headless=new")
                opcoes.add_argument("--window-size=1400,1000")
                opcoes.add_argument("--lang=pt-BR")
                if com_perfil:
                    opcoes.add_argument(f"--user-data-dir={pasta_dados() / ('navegador_' + nome.lower())}")
                try:
                    driver = classe(options=opcoes)
                    self.log(f"Navegador {nome} aberto{' (invisível)' if not self.visivel else ''}.")
                    return driver
                except WebDriverException as erro:
                    erros.append(f"{nome}{'' if com_perfil else ' sem perfil'}: {(erro.msg or '').splitlines()[0:1]}")
        raise ErroPlataforma("Não consegui abrir o Edge nem o Chrome.\n" + "\n".join(erros))

    def _reabrir_visivel(self) -> None:
        if self.driver:
            self.driver.quit()
        self.visivel = True
        self.driver = self._abrir_navegador()
        self.driver.set_page_load_timeout(120)

    def _esperar(self, condicao, tempo: int | None = None, o_que: str | None = None):
        """Espera a condição. Com `o_que`, um tempo esgotado vira um erro claro
        dizendo o que faltou, com print e resumo da página salvos em dados/erros."""
        try:
            return WebDriverWait(
                self.driver, tempo or self.espera, poll_frequency=0.3,
                ignored_exceptions=[StaleElementReferenceException]
            ).until(condicao)
        except TimeoutException:
            if not o_que:
                raise
            raise self._erro(f"Não encontrei {o_que} na página {self.driver.current_url}", o_que) from None

    def _erro(self, mensagem: str, etapa: str) -> ErroPlataforma:
        pasta = self.salvar_diagnostico(etapa)
        return ErroPlataforma(f"{mensagem}\n\nPrint e resumo da página salvos em:\n{pasta}")

    def salvar_diagnostico(self, etapa: str) -> Path | None:
        """Salva um print da tela e a lista de campos, botões e avisos da página."""
        d = self.driver
        try:
            pasta = pasta_dados() / "erros"
            pasta.mkdir(parents=True, exist_ok=True)
            base = pasta / datetime.now().strftime("%Y-%m-%d_%H%M%S")
            d.save_screenshot(str(base.with_suffix(".png")))
            linhas = [f"Etapa: {etapa}", f"URL: {d.current_url}", f"Título: {d.title}",
                      f"Abas abertas: {len(d.window_handles)}", "", "Campos:"]
            for e in d.find_elements(By.CSS_SELECTOR, "input, select, textarea"):
                linhas.append(
                    f"  <{e.tag_name} type={e.get_attribute('type')} name={e.get_attribute('name')} "
                    f"id={e.get_attribute('id')} placeholder={e.get_attribute('placeholder')} "
                    f"class={(e.get_attribute('class') or '')[:60]} visível={e.is_displayed()}>")
            linhas += ["", "Botões e links:"]
            for e in d.find_elements(By.CSS_SELECTOR, "button, a, input[type='submit'], input[type='button']"):
                texto = (e.text or e.get_attribute("value") or e.get_attribute("title") or "").strip().replace("\n", " ")
                if texto:
                    linhas.append(f"  <{e.tag_name}> {texto[:60]}  href={e.get_attribute('href')} "
                                  f"class={(e.get_attribute('class') or '')[:60]}")
            linhas += ["", "Cabeçalhos de tabela:"]
            for t in d.find_elements(By.CSS_SELECTOR, "table"):
                cab = " | ".join(th.text.strip() for th in t.find_elements(By.CSS_SELECTOR, "th") if th.text.strip())
                if cab:
                    linhas.append(f"  {cab[:300]}")
            mensagens = d.execute_script(_JS_MENSAGENS_NA_TELA) or []
            if mensagens:
                linhas += ["", "Avisos na tela: " + " | ".join(mensagens)]
            texto = (d.execute_script("return document.body ? document.body.innerText : ''") or "").strip()
            linhas += ["", "Texto da página (início):", texto[:2500] or "(vazia)"]
            base.with_suffix(".txt").write_text("\n".join(linhas), encoding="utf-8")
            return base.with_suffix(".png")
        except Exception:  # o diagnóstico nunca pode esconder o erro original
            return None

    def _clicar(self, elemento):
        """Clique de mouse; se ele não chegar à página (acontece com o navegador
        invisível em algumas máquinas), clica via JavaScript."""
        d = self.driver
        antes = d.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});"
            "if (window.__rhCliques === undefined) { window.__rhCliques = 0;"
            "  document.addEventListener('click', () => window.__rhCliques++, true); }"
            "return window.__rhCliques;", elemento)
        try:
            elemento.click()
        except WebDriverException:  # coberto por outro elemento
            d.execute_script("arguments[0].click();", elemento)
            return
        try:
            chegou = d.execute_script("return window.__rhCliques;") != antes
        except WebDriverException:  # a página já mudou: o clique chegou
            return
        if not chegou:
            try:
                d.execute_script("arguments[0].click();", elemento)
            except (StaleElementReferenceException, WebDriverException):
                pass

    def _digitar(self, campo, texto: str) -> None:
        """Apaga o campo e digita; se a digitação não chegar ao campo, põe o
        valor via JavaScript (avisando a página com input/change/keyup)."""
        try:
            campo.click()
            campo.send_keys(Keys.CONTROL, "a")
            campo.send_keys(Keys.DELETE)
            campo.send_keys(texto)
        except WebDriverException:
            pass
        if (campo.get_attribute("value") or "") != texto:
            self.driver.execute_script(_JS_POR_VALOR, campo, texto)

    def _botao(self, texto: str, raiz=None, so_igual: bool = False):
        return self.driver.execute_script(_JS_ACHAR_BOTAO, _letras(texto), raiz, so_igual)

    def _esperar_carregar(self, tempo: int = 30):
        """Espera a página e o "carregando" da plataforma sumirem."""
        time.sleep(0.3)
        try:
            WebDriverWait(self.driver, tempo, poll_frequency=0.3).until(
                lambda drv: drv.execute_script("return document.readyState") == "complete"
                and not drv.execute_script(_JS_CARREGANDO))
        except (TimeoutException, WebDriverException):
            pass

    def _ir_para_nova_aba(self, abas_antes: list[str]) -> bool:
        """Se o clique abriu outra aba, passa a usar a nova."""
        try:
            WebDriverWait(self.driver, 3, poll_frequency=0.3).until(
                lambda drv: len(drv.window_handles) > len(abas_antes))
        except TimeoutException:
            return False
        nova = [a for a in self.driver.window_handles if a not in abas_antes][-1]
        self.driver.switch_to.window(nova)
        return True

    # ---------- login ----------
    def login(self, usuario: str, senha: str) -> None:
        d = self.driver
        self.log("Entrando na plataforma...")
        campo_senha = self._abrir_login()
        d = self.driver
        campo_usuario = d.execute_script(_JS_CAMPO_DO_ROTULO, "login") or self._campo_texto_visivel()
        if not campo_usuario:
            raise self._erro("Não encontrei o campo Login.", "login")
        self._digitar(campo_usuario, usuario.strip())
        self._digitar(campo_senha, senha)
        botao = self._botao("acessar") or self._botao("entrar")
        if botao:
            self._clicar(botao)
        else:
            campo_senha.send_keys(Keys.ENTER)

        def saiu_do_login(drv):
            if "/login" not in drv.current_url.lower():
                return "ok"
            alerta = drv.execute_script(_JS_ALERTA)
            return ("recusado", alerta) if alerta else False

        try:
            resultado = self._esperar(saiu_do_login, 40)
        except TimeoutException:
            raise self._erro("Login recusado (a página de login não saiu da tela).", "login") from None
        if isinstance(resultado, tuple):
            raise self._erro(f"Login recusado: {resultado[1]}", "login")
        self._esperar_carregar()
        self.log("Login feito.")
        self.fechar_popups(espera=8)

    def _abrir_login(self):
        """Abre o login e devolve o campo Senha. Se o site mostrar a verificação
        de segurança ("Just a moment..." / "Confirme que é humano"), abre o
        navegador visível para a pessoa fazer a verificação e espera."""
        senha_visivel = EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type='password']"))

        def carregar():
            try:
                self.driver.get(f"{URL_BASE}/login")
            except TimeoutException:
                self.log("A página de login demorou para carregar; conferindo se o formulário apareceu...")

        def senha_ou_verificacao(drv):
            try:
                return senha_visivel(drv)
            except StaleElementReferenceException:
                return False
            except WebDriverException:
                pass
            return False

        carregar()
        fim = time.time() + 60
        while time.time() < fim:
            campo = senha_ou_verificacao(self.driver)
            if campo:
                return campo
            if self._verificacao_de_seguranca():
                break
            time.sleep(0.5)
        else:
            raise self._erro("Não encontrei o campo Senha do login (a página não carregou o formulário).",
                             "o campo Senha do login")

        if not self.visivel:
            self.log("O RHGestor pediu a verificação de segurança do site. Vou abrir o navegador na tela: "
                     "se aparecer \"Confirme que é humano\", clique na caixinha.")
            self._reabrir_visivel()
            carregar()
        else:
            self.log("O RHGestor pediu a verificação de segurança do site: se aparecer \"Confirme que é humano\" "
                     "no navegador, clique na caixinha.")
        try:
            return self._esperar(senha_ou_verificacao_sem_desafio(senha_visivel), 240)
        except TimeoutException:
            raise self._erro("A verificação de segurança do site não terminou em 4 minutos.",
                             "verificação de segurança no login") from None

    def _verificacao_de_seguranca(self) -> bool:
        try:
            return bool(self.driver.execute_script(_JS_VERIFICACAO))
        except WebDriverException:
            return False

    def fechar_popups(self, espera: float = 0) -> None:
        """Fecha a pesquisa de avaliação (NPS da Track.co: "recomendaria a RHGestor...")
        clicando no X. Pode aparecer logo depois do login ou mais tarde; se não
        estiver na tela, não faz nada. `espera` dá um tempo para ela surgir."""
        d = self.driver
        fim = time.time() + espera
        while True:
            try:
                achado = d.execute_script(_JS_PESQUISA)
            except WebDriverException:
                achado = None
            if achado or time.time() >= fim:
                break
            time.sleep(0.5)
        if not achado:
            return
        tipo, elemento = achado
        fechou = False
        try:
            if tipo == "botao":
                self._clicar(elemento)
            else:  # a pesquisa está dentro de um iframe: o X fica lá dentro (ou logo fora dele)
                d.switch_to.frame(elemento)
                try:
                    x = d.execute_script(_JS_X_NO_FRAME)
                    if x:
                        self._clicar(x)
                        fechou = True
                finally:
                    d.switch_to.default_content()
                if not fechou:
                    x = d.execute_script(_JS_X_PERTO, elemento)
                    if x:
                        self._clicar(x)
            time.sleep(0.8)
            if d.execute_script(_JS_PESQUISA):
                # o X não fechou: esconde a pesquisa para ela não ficar na frente dos cliques
                d.execute_script(_JS_ESCONDER_PESQUISA)
                self.log("A pesquisa de avaliação não fechou pelo X; escondi para continuar.")
            else:
                self.log("Fechei a pesquisa de avaliação do RHGestor.")
        except WebDriverException as erro:
            try:
                d.switch_to.default_content()
                d.execute_script(_JS_ESCONDER_PESQUISA)
            except WebDriverException:
                pass
            self.log(f"AVISO: não consegui fechar a pesquisa de avaliação ({type(erro).__name__}); escondi e segui.")

    def _campo_texto_visivel(self):
        for seletor in ("input[name*='login' i]", "input[id*='login' i]", "input[type='email']", "input[type='text']"):
            for campo in self.driver.find_elements(By.CSS_SELECTOR, seletor):
                if campo.is_displayed():
                    return campo
        return None

    # ---------- turma ----------
    def abrir_universidade(self) -> None:
        """Menu Treinamentos (T&D) > Universidade Corporativa (abre na mesma aba ou numa nova)."""
        d = self.driver
        self.fechar_popups()
        self.log("Abrindo Treinamentos (T&D) > Universidade Corporativa...")
        menu = None
        for texto in ("treinamentos t d", "treinamentos"):
            menu = self._botao(texto)
            if menu:
                break
        if menu:
            self._clicar(menu)
            time.sleep(0.8)
        abas = list(d.window_handles)
        item = None
        try:
            item = self._esperar(lambda drv: self._botao("universidade corporativa"), 8)
        except TimeoutException:
            pass
        if item:
            url_antes = d.current_url
            href = item.get_attribute("href") or ""
            self._clicar(item)
            if self._ir_para_nova_aba(abas):
                self.log("A Universidade Corporativa abriu em outra aba; seguindo nela.")
            elif d.current_url == url_antes:  # o clique não levou a lugar nenhum: tenta pelo link
                d.execute_script("arguments[0].click();", item)
                if not self._ir_para_nova_aba(abas) and d.current_url == url_antes:
                    destino = href if href.startswith("http") else URL_UNIVERSIDADE
                    self.log(f"O clique no menu não abriu a página; abrindo {destino}")
                    d.get(destino)
        else:
            self.log(f"Não achei o item Universidade Corporativa no menu; abrindo {URL_UNIVERSIDADE}")
            d.get(URL_UNIVERSIDADE)
        self._esperar_carregar()
        self._esperar(lambda drv: drv.execute_script(_JS_CAMPO_DO_ROTULO, "inicio da turma"), 40,
                      'o filtro "Início da turma" da Universidade Corporativa')

    def filtrar_turmas(self) -> None:
        """Início da turma = 01/01/1900 e clica no botão de atualizar/pesquisar."""
        d = self.driver
        self.fechar_popups()
        campo = d.execute_script(_JS_CAMPO_DO_ROTULO, "inicio da turma")
        if (campo.get_attribute("type") or "").lower() != "date":
            atual = campo.get_attribute("value") or ""
            separador = "-" if re.search(r"\d-\d", atual) else "."if re.search(r"\d\.\d", atual) else "/"
            self._digitar(campo, INICIO_DA_TURMA.replace("/", separador))
        valor = d.execute_script(_JS_POR_DATA, campo, INICIO_DA_TURMA)
        if "1900" not in (valor or ""):
            self.log(f"AVISO: o campo Início da turma ficou com \"{valor}\" em vez de 01/01/1900.")
        self.log(f"Início da turma: {INICIO_DA_TURMA} (campo ficou com {valor or 'vazio'}).")
        botao = d.execute_script(_JS_BOTAO_ATUALIZAR)
        if botao:
            self._clicar(botao)
        else:
            self.log("Não achei o botão de atualizar; tentando com Enter no campo de data.")
            campo.send_keys(Keys.ENTER)
        self._esperar_carregar()

    def abrir_turma(self, turma: str) -> None:
        d = self.driver
        self.abrir_universidade()
        self.filtrar_turmas()
        alvo = _letras(turma)
        achado = self._esperar(lambda drv: drv.execute_script(_JS_CARD_TURMA, alvo), 30,
                               f'o card da turma "{turma}" (depois de filtrar o Início da turma)')
        self.fechar_popups()
        card, quantos = achado
        if quantos > 1:
            self.log(f'AVISO: há {quantos} cards com o nome "{turma}"; abrindo o primeiro.')
        abas = list(d.window_handles)
        self._clicar(card)
        if self._ir_para_nova_aba(abas):
            self.log("A turma abriu em outra aba; seguindo nela.")
        self._esperar_carregar()
        self._esperar(lambda drv: self._botao("alunos", so_igual=True), 30, 'o botão "+ Alunos" da turma')
        self.url_turma = d.current_url
        self.log(f'Turma "{turma}" aberta.')

    # ---------- alunos ----------
    def _janela_alunos(self, abrir: bool = True):
        d = self.driver
        janela = d.execute_script(_JS_JANELA_ALUNOS)
        if janela or not abrir:
            return janela
        self.fechar_popups()
        botao = self._esperar(lambda drv: self._botao("alunos", so_igual=True), 30, 'o botão "+ Alunos"')
        self._clicar(botao)
        janela = self._esperar(lambda drv: drv.execute_script(_JS_JANELA_ALUNOS), 30,
                               'a janela "Pesquisar Alunos" (lista com caixinhas e "Busca por Nome")')
        self._esperar_carregar()
        self._lista_estavel(janela)
        return d.execute_script(_JS_JANELA_ALUNOS)

    def _linhas(self, janela) -> list[_Linha]:
        brutas = self.driver.execute_script(_JS_LINHAS_ALUNOS, janela) or []
        return [_Linha(n, r, bool(m), i) for i, (n, r, m) in enumerate(brutas)]

    def _lista_estavel(self, janela, tempo: float = 20) -> list[_Linha]:
        """Espera a lista parar de mudar (a pesquisa recarrega as linhas)."""
        fim = time.time() + tempo
        anterior, desde = None, time.time()
        linhas: list[_Linha] = []
        while time.time() < fim:
            try:
                linhas = self._linhas(janela)
            except (StaleElementReferenceException, WebDriverException):
                janela = self.driver.execute_script(_JS_JANELA_ALUNOS) or janela
                linhas = []
            assinatura = tuple(l.nome for l in linhas)
            if assinatura != anterior:
                anterior, desde = assinatura, time.time()
            elif time.time() - desde >= 1.2 and not self.driver.execute_script(_JS_CARREGANDO):
                break
            time.sleep(0.3)
        return linhas

    def _pesquisar(self, janela, termo: str) -> list[_Linha]:
        d = self.driver
        campo = d.execute_script(_JS_CAMPO_DO_ROTULO, "busca por nome", janela) or \
            d.execute_script(_JS_CAMPO_DO_ROTULO, "nome", janela)
        if not campo:
            raise self._erro('Não encontrei o campo "Busca por Nome".', "busca por nome")
        self._digitar(campo, termo)
        botao = self._botao("pesquisar", janela, so_igual=True)
        if botao:
            self._clicar(botao)
        else:
            campo.send_keys(Keys.ENTER)
        time.sleep(0.5)
        self._esperar_carregar()
        return self._lista_estavel(d.execute_script(_JS_JANELA_ALUNOS) or janela)

    def _marcar(self, linha: _Linha) -> bool:
        return bool(self.driver.execute_script(_JS_MARCAR, linha.indice))

    def adicionar(self, pessoas: list[tuple[int, Colaborador]], confirmar: bool,
                  aviso: Callable[[int, Resultado], None]) -> None:
        """Marca e adiciona as pessoas na turma aberta. `aviso(posição, resultado)`
        é chamado para cada pessoa assim que se sabe o que aconteceu com ela."""
        d = self.driver
        janela = self._janela_alunos()
        linhas = self._lista_estavel(janela)
        contador = d.execute_script(_JS_CONTADOR, janela)
        if contador:
            self.log(f"Lista de alunos: exibindo {contador[0]} - {contador[1]} de {contador[2]}.")
        else:
            self.log(f"Lista de alunos: {len(linhas)} pessoa(s) na tela.")
        lista_completa = bool(contador) and contador[0] <= 1 and contador[1] >= contador[2] \
            and len(linhas) >= contador[2]
        nomes = [l.nome for l in linhas]
        ja_marcadas = [l.nome for l in linhas if l.marcada]
        if ja_marcadas:
            self.log(f"AVISO: a lista já veio com {len(ja_marcadas)} marcado(s): {', '.join(ja_marcadas)}")

        # 1ª etapa: quem está na lista que abriu, todos de uma vez
        lote = _Lote()
        faltam: list[tuple[int, Colaborador]] = []
        for pos, c in pessoas:
            tipo, achados = escolher(c.nome, nomes)
            if tipo == "homonimo":
                descricao = "; ".join(f"{linhas[i].nome} ({linhas[i].resto})" for i in achados)
                self.log(f"AVISO: {c.nome}: mais de uma pessoa com esse nome na lista, não marquei: {descricao}")
                aviso(pos, Resultado("homonimo", f"mais de um com esse nome: {descricao}"))
            elif tipo == "nenhum":
                faltam.append((pos, c))
            else:
                self._marcar_no_lote(lote, pos, c, linhas[achados[0]], tipo, aviso)
        self._enviar_lote(lote, confirmar, aviso)

        # 2ª etapa: quem não estava na lista que abriu, pela "Busca por Nome", um por vez
        for pos, c in faltam:
            if lista_completa:
                self._nao_encontrado(pos, c, aviso)
                continue
            self.log(f"{c.nome} não está na lista que abriu; procurando pela Busca por Nome...")
            achou = False
            for termo in termos_de_busca(c.nome):
                janela = self._janela_alunos()
                linhas = self._pesquisar(janela, termo)
                tipo, achados = escolher(c.nome, [l.nome for l in linhas])
                if tipo == "homonimo":
                    descricao = "; ".join(f"{linhas[i].nome} ({linhas[i].resto})" for i in achados)
                    self.log(f"AVISO: {c.nome}: mais de uma pessoa com esse nome, não marquei: {descricao}")
                    aviso(pos, Resultado("homonimo", f"mais de um com esse nome: {descricao}"))
                    achou = True
                    break
                if tipo != "nenhum":
                    lote = _Lote()
                    self._marcar_no_lote(lote, pos, c, linhas[achados[0]], tipo, aviso)
                    self._enviar_lote(lote, confirmar, aviso)
                    achou = True
                    break
            if not achou:
                self._nao_encontrado(pos, c, aviso)

    def _nao_encontrado(self, pos: int, c: Colaborador, aviso) -> None:
        self.log(f"AVISO: {c.nome} não está na lista de alunos (pode já estar na turma ou não ser colaborador).")
        aviso(pos, Resultado("nao_encontrado", "não está na lista de alunos (já na turma ou não é colaborador?)"))

    def _marcar_no_lote(self, lote: _Lote, pos: int, c: Colaborador, linha: _Linha, tipo: str, aviso) -> None:
        if not self._marcar(linha):
            pasta = self.salvar_diagnostico(f"marcar {linha.nome}")
            self.log(f"ERRO: não consegui marcar {linha.nome}. Print em {pasta}")
            aviso(pos, Resultado("erro", "não consegui marcar a caixinha", linha.nome))
            return
        if tipo == "parecido":
            self.log(f"AVISO: {c.nome}: marquei \"{linha.nome}\" (nome parecido, confira).")
        else:
            self.log(f"Marcado: {linha.nome} ({linha.resto})")
        self.emails[linha.nome] = email_no_texto(linha.resto)
        lote.pessoas.append((pos, c, linha.nome))

    def _enviar_lote(self, lote: _Lote, confirmar: bool, aviso) -> None:
        if not lote.pessoas:
            return
        d = self.driver
        janela = self._janela_alunos(abrir=False)
        # confere que as marcações continuam lá antes de adicionar
        linhas = self._linhas(janela) if janela else []
        marcadas = [l.nome for l in linhas if l.marcada]
        for pos, c, nome in list(lote.pessoas):
            if not any(nome_igual(nome, m) for m in marcadas):
                self.log(f"ERRO: {nome} ficou desmarcado antes de adicionar.")
                aviso(pos, Resultado("erro", "a marcação sumiu antes de adicionar; tente de novo", nome))
                lote.pessoas.remove((pos, c, nome))
        if not lote.pessoas:
            return
        if not confirmar:
            for pos, c, nome in lote.pessoas:
                aviso(pos, Resultado("teste", "marcado; não cliquei em Adicionar", nome, self.emails.get(nome, "")))
            self.log(f"Modo teste: {len(lote.pessoas)} marcado(s); não cliquei em \"+ Adicionar\".")
            for linha in linhas:  # desmarca, para a lista ficar como estava
                if linha.marcada and any(nome_igual(linha.nome, n) for _, _, n in lote.pessoas):
                    d.execute_script("const l = (window.__rhLinhas || [])[arguments[0]]; if (l && l.caixa.checked) l.caixa.click();",
                                     linha.indice)
            return

        d.execute_script(_JS_OUVIR_MENSAGENS)
        botao = self._botao("adicionar", janela, so_igual=True) or self._botao("adicionar", so_igual=True)
        if not botao:
            raise self._erro('Não encontrei o botão "+ Adicionar".', "+ Adicionar")
        self.log(f"Clicando em \"+ Adicionar\" ({len(lote.pessoas)} aluno(s))...")
        self._clicar(botao)
        pergunta = self._confirmar_adicao()
        mensagens, processado = self._ler_mensagens(len(lote.pessoas), [pergunta] if pergunta else [])
        self._conferir_mensagens(lote, mensagens, processado, aviso)
        self._fechar_janelas()

    def _confirmar_adicao(self) -> str | None:
        """Clica "Confirmar" na pergunta "Você confirma adicionar todos os alunos selecionados?"."""
        d = self.driver
        try:
            pergunta = self._esperar(lambda drv: drv.execute_script(_JS_PERGUNTA), 15)
        except TimeoutException:
            self.log("Não apareceu a pergunta de confirmação; lendo as mensagens...")
            return None
        self.log(f"PLATAFORMA: {pergunta}")
        botao = self._esperar(lambda drv: self._botao("confirmar", so_igual=True)
                              or self._botao("sim", so_igual=True), 10, 'o botão "Confirmar"')
        self._clicar(botao)
        return pergunta

    def _ler_mensagens(self, quantos: int, vistas: list[str]) -> tuple[list[str], tuple[int, int] | None]:
        """Mostra no registro cada mensagem da plataforma até o "Processamento concluído"."""
        d = self.driver
        mensagens: list[str] = list(vistas)
        processado = None
        concluido = False
        fim = time.time() + 60 + 8 * quantos
        ultima_novidade = time.time()
        while time.time() < fim:
            try:
                novas = (d.execute_script("return (window.__rhMsgs || []).splice(0);") or []) + \
                    (d.execute_script(_JS_MENSAGENS_NA_TELA) or [])
            except WebDriverException:
                novas = []
            for texto in novas:
                texto = _sem_botoes(texto)
                if self._mensagem_nova(texto, mensagens):
                    mensagens.append(texto)
                    ultima_novidade = time.time()
                    self.log(f"PLATAFORMA: {texto}")
                concluido = concluido or bool(_RE_CONCLUIDO.search(texto))
                processado = processado or ler_processamento(texto)
            if concluido and not processado:
                # "Processamento concluído" e o contador "N de M" ficam em partes separadas da janela
                try:
                    janela = _sem_botoes(d.execute_script(_JS_JANELA_PROCESSAMENTO) or "")
                except WebDriverException:
                    janela = ""
                processado = ler_processamento(janela)
                if processado and self._mensagem_nova(janela, mensagens):
                    mensagens.append(janela)
                    self.log(f"PLATAFORMA: {janela}")
            if concluido and time.time() - ultima_novidade > 1.5:
                break
            if not concluido and time.time() - ultima_novidade > 30:
                self.log("AVISO: a plataforma ficou 30 s sem mostrar mensagens e não disse \"Processamento concluído\".")
                break
            time.sleep(0.25)
        else:
            self.log("AVISO: tempo esgotado esperando \"Processamento concluído\".")
        return mensagens, processado

    @staticmethod
    def _mensagem_nova(texto: str, mensagens: list[str]) -> bool:
        if any(texto in m for m in mensagens):
            return False
        resto = texto
        for m in sorted(mensagens, key=len, reverse=True):
            resto = resto.replace(m, " ")
        # "×", contador sozinho ("2 de 4") ou só repetição do que já apareceu
        return len(re.sub(r"[^A-Za-zÀ-ÿ]", "", resto)) >= 3

    def _conferir_mensagens(self, lote: _Lote, mensagens: list[str], processado, aviso) -> None:
        adicionados = [n for n in (ler_mensagem_adicionado(m) for m in mensagens) if n]
        problemas = [m for m in mensagens if _RE_PROBLEMA.search(m) and not ler_processamento(m)]
        for pos, c, nome in lote.pessoas:
            if any(nome_igual(nome, a) or mesmo_nome(a, nome) for a in adicionados):
                aviso(pos, Resultado("adicionado", "", nome, self.emails.get(nome, "")))
                continue
            dele = [m for m in problemas if _cita(m, nome)]
            if dele:
                aviso(pos, Resultado("erro", " | ".join(dele), nome))
            else:
                aviso(pos, Resultado("sem_confirmacao", "não vi a mensagem \"adicionado!\"; confira na turma", nome,
                                     self.emails.get(nome, "")))
        if processado:
            self.log(f"PLATAFORMA: Processamento concluído {processado[0]} de {processado[1]}")
            if processado[0] < processado[1]:
                self.log(f"AVISO: a plataforma adicionou {processado[0]} de {processado[1]}; veja as mensagens acima.")

    def _fechar_janelas(self) -> None:
        """Fecha a janela de "Processamento concluído" (OK/Fechar), se ainda estiver aberta."""
        d = self.driver
        for _ in range(3):
            botao = None
            for texto in ("ok", "fechar", "concluir"):
                botao = self._botao(texto, so_igual=True)
                if botao:
                    break
            if not botao:
                break
            try:
                self._clicar(botao)
            except WebDriverException:
                break
            time.sleep(0.6)
        self._esperar_carregar()
        if d.execute_script(_JS_JANELA_ALUNOS):
            return
        if self.url_turma and not self._botao("alunos", so_igual=True):
            d.get(self.url_turma)
            self._esperar_carregar()


def senha_ou_verificacao_sem_desafio(senha_visivel):
    """Condição de espera: o campo Senha visível (a verificação já passou)."""
    def condicao(drv):
        try:
            return senha_visivel(drv)
        except (StaleElementReferenceException, WebDriverException):
            return False
    return condicao


def _sem_botoes(texto: str) -> str:
    """Tira os botões que vêm junto no texto das janelas ("... Confirmar Fechar")."""
    return _RE_BOTOES_NO_FIM.sub("", " ".join((texto or "").split())).strip()


def _letras(texto: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", normalizar(texto))).strip()


def _cita(mensagem: str, nome: str) -> bool:
    """A mensagem fala dessa pessoa (todas as palavras do nome aparecem nela)."""
    texto = f" {normalizar(mensagem)} "
    return all(f" {p} " in texto for p in palavras(nome))
