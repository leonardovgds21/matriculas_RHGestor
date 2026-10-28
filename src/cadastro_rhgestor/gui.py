"""Tela do app: cola os colaboradores (nome e CPF) ou abre as fichas, confere e
adiciona na turma da Universidade Corporativa."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import __version__, credenciais, email_alunos
from .config import TURMA_PADRAO
from .entrada import Colaborador, ler_lista

SITUACOES = {
    "adicionado": ("adicionado", "ok"),
    "teste": ("modo teste", ""),
    "nao_encontrado": ("não encontrado", "aviso"),
    "homonimo": ("homônimos (não marquei)", "aviso"),
    "sem_confirmacao": ("sem confirmação", "aviso"),
    "erro": ("erro", "erro"),
}
PENDENTES = {"nao_encontrado", "homonimo", "sem_confirmacao", "erro"}


def detalhe_do_erro(erro: Exception) -> str:
    """A mensagem do Selenium traz um stacktrace sem utilidade; fica só a 1ª linha."""
    linhas = (getattr(erro, "msg", None) or str(erro)).strip().splitlines()
    return f"{type(erro).__name__}: {linhas[0] if linhas else 'sem detalhes'}"


class Registro(tk.Text):
    def __init__(self, pai, **kw):
        super().__init__(pai, state="disabled", wrap="word", **kw)
        self.tag_configure("plataforma", foreground="#1d4ed8")
        self.tag_configure("aviso", foreground="#b45309")
        self.tag_configure("erro", foreground="#b91c1c")

    def escrever(self, texto: str):
        tag = ("plataforma" if texto.startswith("PLATAFORMA:") else "erro" if texto.startswith("ERRO")
               else "aviso" if texto.startswith(("AVISO", "RESOLVER")) else "")
        self.config(state="normal")
        self.insert("end", f"{datetime.now():%H:%M:%S}  {texto}\n", tag)
        self.see("end")
        self.config(state="disabled")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Cadastro RHGestor {__version__}")
        self.geometry("1050x760")
        self.minsize(880, 600)
        self.colaboradores: list[Colaborador] = []
        self.situacoes: dict[int, tuple[str, str]] = {}
        self.emails_plataforma: dict[int, str] = {}
        self.fila: queue.Queue = queue.Queue()
        self.enviando = False
        self.modo_teste = tk.BooleanVar(value=False)
        self.mostrar_navegador = tk.BooleanVar(value=False)
        self.turma = tk.StringVar(value=TURMA_PADRAO)
        self._montar_tela()
        self.after(200, self._processar_fila)

    # ---------- montagem ----------
    def _montar_tela(self):
        topo = ttk.Frame(self, padding=8)
        topo.pack(fill="x")
        ttk.Label(topo, text="Colaboradores: nome completo e CPF, um por linha (pode colar vários de uma vez), "
                             "ou abra as fichas em PDF.").pack(side="left")

        self.txt = tk.Text(self, height=8, wrap="none")
        self.txt.pack(fill="x", padx=8)
        botoes = ttk.Frame(self, padding=(8, 6))
        botoes.pack(fill="x")
        ttk.Button(botoes, text="Abrir fichas (PDF)...", command=self.abrir_fichas).pack(side="left")
        ttk.Button(botoes, text="Conferir lista", command=self.conferir).pack(side="left", padx=6)
        ttk.Button(botoes, text="Limpar", command=self.limpar).pack(side="left", padx=6)
        self.lbl_total = ttk.Label(botoes, text="")
        self.lbl_total.pack(side="left", padx=10)

        colunas = ("nome", "cpf", "situacao")
        self.tabela = ttk.Treeview(self, columns=colunas, show="headings", height=9)
        for col, titulo, largura in [("nome", "Nome completo", 300), ("cpf", "CPF", 130),
                                     ("situacao", "Situação", 500)]:
            self.tabela.heading(col, text=titulo)
            self.tabela.column(col, width=largura, anchor="w")
        self.tabela.tag_configure("ok", foreground="#15803d")
        self.tabela.tag_configure("aviso", foreground="#b45309")
        self.tabela.tag_configure("erro", foreground="#b91c1c")
        self.tabela.pack(fill="both", expand=True, padx=8)

        linha_turma = ttk.Frame(self, padding=(8, 8, 8, 0))
        linha_turma.pack(fill="x")
        ttk.Label(linha_turma, text="Turma (card na Universidade Corporativa):").pack(side="left")
        ttk.Entry(linha_turma, textvariable=self.turma, width=50).pack(side="left", padx=6)

        rodape = ttk.Frame(self, padding=8)
        rodape.pack(fill="x")
        self.btn_adicionar = ttk.Button(rodape, text="Adicionar na turma", command=self.adicionar)
        self.btn_adicionar.pack(side="right")
        self.btn_email = ttk.Button(rodape, text="Enviar e-mail aos colaboradores", command=self.enviar_email,
                                    state="disabled")
        self.btn_email.pack(side="right", padx=(0, 8))
        ttk.Checkbutton(rodape, text="Mostrar navegador", variable=self.mostrar_navegador).pack(side="right", padx=8)
        ttk.Checkbutton(rodape, text="Modo teste (só marca, não adiciona)",
                        variable=self.modo_teste).pack(side="right", padx=8)
        ttk.Button(rodape, text="Esquecer login salvo", command=self.esquecer_login).pack(side="left")
        ttk.Button(rodape, text="Copiar pendências", command=self.copiar_pendencias).pack(side="left", padx=6)

        ttk.Label(self, text="Registro (todas as mensagens da plataforma aparecem aqui):").pack(anchor="w", padx=8)
        self.log = Registro(self, height=11)
        self.log.pack(fill="both", padx=8, pady=(0, 8))

    # ---------- lista ----------
    def conferir(self) -> bool:
        self.colaboradores = ler_lista(self.txt.get("1.0", "end"))
        self.situacoes.clear()
        self.emails_plataforma.clear()
        self.btn_email.config(state="disabled")
        self.tabela.delete(*self.tabela.get_children())
        for i, c in enumerate(self.colaboradores):
            self.tabela.insert("", "end", iid=str(i), values=(c.nome, c.cpf_formatado, "; ".join(c.avisos)),
                               tags=("erro",) if c.avisos else ())
        validos = sum(1 for c in self.colaboradores if not c.avisos)
        self.lbl_total.config(text=f"{len(self.colaboradores)} na lista, {validos} pronto(s) para adicionar")
        if not self.colaboradores:
            messagebox.showinfo("Conferir lista", "Digite ou cole ao menos um nome completo.")
            return False
        return True

    def abrir_fichas(self):
        """Lê CPF e nome das fichas (Registro de Empregado, EPI...) e põe na caixa de texto."""
        if self.enviando:
            return
        caminhos = filedialog.askopenfilenames(title="Escolha as fichas (Registro de Empregado ou EPI)",
                                               filetypes=[("PDF", "*.pdf")])
        if not caminhos:
            return
        from .ficha import ler_fichas

        lidos, problemas = [], []
        for caminho in caminhos:
            try:
                achados = ler_fichas(caminho)
            except Exception as erro:  # PDF corrompido, protegido etc.
                problemas.append(f"{Path(caminho).name}: {erro}")
                continue
            if not achados:
                problemas.append(f"{Path(caminho).name}: não achei CPF nem nome (o PDF pode ser uma imagem escaneada)")
            lidos += achados
        existentes = {c.cpf for c in ler_lista(self.txt.get("1.0", "end")) if c.cpf}
        novos = [c for c in lidos if not c.cpf or c.cpf not in existentes]
        if novos:
            atual = self.txt.get("1.0", "end").strip()
            linhas = [f"{c.cpf_formatado} {c.nome}".strip() for c in novos]
            self.txt.delete("1.0", "end")
            self.txt.insert("1.0", "\n".join(([atual] if atual else []) + linhas))
        for c in lidos:
            if c.avisos:
                self.log.escrever(f"{c.origem}: {', '.join(c.avisos)} (confira e corrija na caixa de texto)")
        for p in problemas:
            self.log.escrever(f"AVISO: {p}")
        self.log.escrever(f"Fichas lidas: {len(novos)} colaborador(es) adicionado(s) à lista"
                          + (f", {len(lidos) - len(novos)} já estavam na lista." if len(lidos) > len(novos) else "."))
        if novos:
            self.conferir()
        elif problemas:
            messagebox.showwarning("Abrir fichas", "\n".join(problemas))

    def limpar(self):
        if self.enviando:
            return
        self.txt.delete("1.0", "end")
        self.tabela.delete(*self.tabela.get_children())
        self.colaboradores = []
        self.situacoes.clear()
        self.lbl_total.config(text="")

    def _situacao(self, i: int, situacao: str, detalhe: str):
        c = self.colaboradores[i]
        self.situacoes[i] = (situacao, detalhe)
        rotulo, tag = SITUACOES.get(situacao, (situacao, ""))
        texto = f"{rotulo}: {detalhe}" if rotulo and detalhe else rotulo or detalhe
        self.tabela.item(str(i), values=(c.nome, c.cpf_formatado, texto), tags=(tag,) if tag else ())
        self.tabela.see(str(i))

    def _pendencias(self) -> list[str]:
        linhas = []
        for i, (situacao, detalhe) in sorted(self.situacoes.items()):
            if situacao in PENDENTES:
                c = self.colaboradores[i]
                linhas.append(f"{c.nome}\t{c.cpf_formatado}\t{SITUACOES[situacao][0]}\t{detalhe}")
        return linhas

    def copiar_pendencias(self):
        linhas = self._pendencias()
        if not linhas:
            self.log.escrever("Nenhuma pendência para copiar.")
            return
        self.clipboard_clear()
        self.clipboard_append("\n".join(["Nome\tCPF\tSituação\tDetalhe"] + linhas))
        self.log.escrever(f"{len(linhas)} pendência(s) copiada(s) (cole no Excel ou no e-mail).")

    # ---------- adicionar ----------
    def adicionar(self):
        if self.enviando or not self.conferir():
            return
        validos = [i for i, c in enumerate(self.colaboradores) if not c.avisos]
        if not validos:
            messagebox.showerror("Adicionar", "Nenhum colaborador está pronto: corrija os avisos da lista.")
            return
        turma = self.turma.get().strip()
        if not turma:
            messagebox.showerror("Adicionar", "Informe o nome da turma.")
            return
        pulados = len(self.colaboradores) - len(validos)
        texto = (f"Adicionar {len(validos)} colaborador(es) na turma\n\"{turma}\"?"
                 + (f"\n\n{pulados} linha(s) com problema serão puladas (veja a coluna Situação)." if pulados else "")
                 + ("\n\nModo teste: só marca na lista, não clica em Adicionar." if self.modo_teste.get() else ""))
        if not messagebox.askyesno("Adicionar na turma", texto):
            return
        login = DialogoLogin(self, "Entrar e adicionar")
        if not login.resultado:
            return
        usuario, senha, lembrar = login.resultado
        if lembrar:
            credenciais.salvar(usuario, senha)
        self.enviando = True
        self.btn_adicionar.config(state="disabled")
        for i in validos:
            self._situacao(i, "", "aguardando")
        threading.Thread(target=self._adicionar_em_segundo_plano,
                         args=(validos, turma, usuario, senha, self.modo_teste.get(), self.mostrar_navegador.get()),
                         daemon=True).start()

    def _adicionar_em_segundo_plano(self, indices, turma, usuario, senha, teste, visivel):
        from .plataforma import ErroPlataforma, Plataforma

        log = lambda texto: self.fila.put(("log", texto))  # noqa: E731
        def avisar(i, r):
            if r.email:
                self.fila.put(("email", i, r.email))
            self.fila.put(("situacao", i, r.situacao, r.detalhe))

        try:
            with Plataforma(log=log, visivel=visivel) as p:
                p.login(usuario, senha)
                p.abrir_turma(turma)
                p.adicionar([(i, self.colaboradores[i]) for i in indices], confirmar=not teste, aviso=avisar)
            self.fila.put(("fim", teste))
        except ErroPlataforma as erro:
            self.fila.put(("erro", str(erro)))
        except Exception as erro:
            self.fila.put(("erro", detalhe_do_erro(erro)))
        finally:
            self.fila.put(("liberar",))

    def _resumo(self, teste: bool):
        contagem: dict[str, int] = {}
        for situacao, _ in self.situacoes.values():
            if situacao:
                contagem[situacao] = contagem.get(situacao, 0) + 1
        resumo = ", ".join(f"{SITUACOES[s][0]}: {q}" for s, q in contagem.items() if s in SITUACOES)
        self.log.escrever(("Modo teste concluído. " if teste else "Concluído. ") + resumo)
        pendencias = self._pendencias()
        if pendencias:
            self.log.escrever(f"RESOLVER À MÃO ({len(pendencias)}):")
            for linha in pendencias:
                self.log.escrever("RESOLVER   " + linha.replace("\t", " | "))
        messagebox.showinfo("Adicionar na turma", ("Modo teste concluído.\n" if teste else "Concluído.\n") + resumo
                            + (f"\n\n{len(pendencias)} pessoa(s) para resolver à mão: veja o registro "
                               f"(ou \"Copiar pendências\")." if pendencias else ""))

    def _processar_fila(self):
        try:
            while True:
                tipo, *dado = self.fila.get_nowait()
                if tipo == "log":
                    self.log.escrever(dado[0])
                elif tipo == "situacao":
                    self._situacao(*dado)
                elif tipo == "email":
                    self.emails_plataforma[dado[0]] = dado[1]
                elif tipo == "erro":
                    self.log.escrever(f"ERRO: {dado[0]}")
                    for i, (situacao, _) in list(self.situacoes.items()):
                        if situacao == "":
                            self._situacao(i, "erro", "não processado (o app parou antes)")
                    self._resumo_erro(dado[0])
                elif tipo == "fim":
                    self._resumo(dado[0])
                elif tipo == "liberar":
                    self.enviando = False
                    self.btn_adicionar.config(state="normal")
                    if self._cadastrados():
                        self.btn_email.config(state="normal")
        except queue.Empty:
            pass
        self.after(200, self._processar_fila)

    def _resumo_erro(self, texto: str):
        pendencias = self._pendencias()
        if pendencias:
            self.log.escrever(f"RESOLVER À MÃO ({len(pendencias)}):")
            for linha in pendencias:
                self.log.escrever("RESOLVER   " + linha.replace("\t", " | "))
        messagebox.showerror("Erro", texto)

    # ---------- e-mail aos colaboradores ----------
    def _cadastrados(self) -> list[int]:
        """Quem foi adicionado na turma (no modo teste, quem foi marcado)."""
        return [i for i, (s, _) in sorted(self.situacoes.items()) if s in ("adicionado", "teste")]

    def enviar_email(self):
        """Abre um e-mail novo no Outlook (app de e-mail padrão) para os colaboradores adicionados."""
        indices = self._cadastrados()
        if not indices:
            messagebox.showinfo("E-mail aos colaboradores", "Ninguém foi adicionado na turma ainda.")
            return
        lista = email_alunos.destinatarios(
            [(self.colaboradores[i].nome, self.emails_plataforma.get(i, "")) for i in indices])
        if not lista:
            return
        for nome, email, origem in lista:
            self.log.escrever(f"E-mail de {nome}: {email}"
                              + (" (o que a lista do RHGestor mostra)" if origem == "plataforma" else " (regra nome.sobrenome)"))
        enderecos = [e for _, e, _ in lista]
        link, com_dest, com_corpo = email_alunos.preparar_link(enderecos, email_alunos.ASSUNTO, email_alunos.CORPO)
        texto_dest = "; ".join(enderecos)
        try:
            if sys.platform == "win32":
                os.startfile(link)  # noqa: S606
            else:
                subprocess.Popen(["xdg-open", link])
        except OSError as erro:
            self._copiar(texto_dest)
            messagebox.showerror(
                "E-mail aos colaboradores",
                f"Não consegui abrir o app de e-mail ({erro}).\n\n"
                "Os e-mails foram copiados: cole no campo Para de um e-mail novo.\n\n"
                "Dica: no Windows, em Configurações > Aplicativos > Aplicativos padrão, "
                "escolha o Outlook (novo) para o tipo de link MAILTO.")
            return
        self.log.escrever(f"E-mail aberto para: {texto_dest}")
        if not com_dest:
            self._copiar(texto_dest)
            messagebox.showinfo("E-mail aos colaboradores",
                                "São muitos destinatários para caber no link. Os e-mails foram copiados:\n"
                                "cole no campo Para (ou Cco) do e-mail que abriu.\n\n"
                                "Clique OK depois de colar para copiar o texto da mensagem.")
        if not com_corpo:
            self._copiar(email_alunos.CORPO)
            messagebox.showinfo("E-mail aos colaboradores",
                                "O texto da mensagem é grande demais para o link e foi copiado:\n"
                                "cole no corpo do e-mail (Ctrl+V).")
        else:
            self._copiar(texto_dest)

    def _copiar(self, texto: str):
        self.clipboard_clear()
        self.clipboard_append(texto)
        self.update()

    def esquecer_login(self):
        credenciais.apagar()
        self.log.escrever("Login salvo apagado deste computador.")


class DialogoLogin(tk.Toplevel):
    """Pede o login do RHGestor. Nada é gravado em arquivo."""

    def __init__(self, pai, texto_ok: str):
        super().__init__(pai)
        self.title("Login do RHGestor")
        self.resizable(False, False)
        self.transient(pai)
        self.resultado = None
        usuario, senha = credenciais.carregar()
        self.usuario = tk.StringVar(value=usuario)
        self.senha = tk.StringVar(value=senha)
        self.lembrar = tk.BooleanVar(value=True)

        quadro = ttk.Frame(self, padding=12)
        quadro.pack()
        ttk.Label(quadro, text="Login").grid(row=0, column=0, sticky="w")
        entrada = ttk.Entry(quadro, textvariable=self.usuario, width=36)
        entrada.grid(row=1, column=0, pady=(0, 8))
        ttk.Label(quadro, text="Senha").grid(row=2, column=0, sticky="w")
        ttk.Entry(quadro, textvariable=self.senha, show="•", width=36).grid(row=3, column=0, pady=(0, 8))
        ttk.Checkbutton(quadro, text="Lembrar neste computador (Cofre do Windows)",
                        variable=self.lembrar).grid(row=4, column=0, sticky="w")
        botoes = ttk.Frame(quadro)
        botoes.grid(row=5, column=0, pady=(10, 0), sticky="e")
        ttk.Button(botoes, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(botoes, text=texto_ok, command=self._ok).pack(side="right", padx=6)
        self.bind("<Return>", lambda _: self._ok())
        entrada.focus_set()
        self.grab_set()
        pai.wait_window(self)

    def _ok(self):
        if self.usuario.get().strip() and self.senha.get():
            self.resultado = (self.usuario.get().strip(), self.senha.get(), self.lembrar.get())
            self.destroy()


def main():
    App().mainloop()
