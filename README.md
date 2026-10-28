# Cadastro RHGestor

App desktop (Windows) que inclui colaboradores numa turma da Universidade
Corporativa do RHGestor (Sólides), https://sistema.rhgestor.com.br:

- Entrada: nome completo e CPF, colados (vários de uma vez) ou lidos das
  fichas em PDF (Registro de Empregado ou EPI), com conferência antes.
- Treinamentos (T&D) > Universidade Corporativa > filtro "Início da turma"
  01/01/1900 > card da turma (padrão "Treinamentos Institucionais GAP SSMA")
  > "+ Alunos" > marca cada pessoa pelo nome > "+ Adicionar" > "Confirmar".
- Mostra no registro todas as mensagens da plataforma e lista quem precisa
  ser resolvido à mão (não encontrado, homônimo, erro).
- Abre no Outlook o e-mail aos colaboradores adicionados ("treinamentos RH
  GESTOR - GAP"), com o e-mail da lista do RHGestor ou a regra
  nome.sobrenome@gapgestao.com.br do FormaSeg.

## Uso

Baixe a pasta `executavel/CadastroRHGestor` e rode `CadastroRHGestor.exe`
(instruções no `LEIA-ME.txt`). O login é pedido na hora e, se marcado, fica
só no Cofre de Credenciais do Windows.

## Desenvolvimento

- Python 3.12, Tkinter, Selenium (Edge), keyring, pdfplumber, PyInstaller.
- `python main.py` abre o app; `python -m pytest -q tests` roda os testes.
- `tests/site_simulado/` imita as telas do RHGestor:
  `python tests/site_simulado/e2e.py` testa a automação de ponta a ponta nele.
- `build.bat` gera `executavel/CadastroRHGestor` (pasta portátil).
- `assets/referencia/` guarda prints das telas reais, para referência.
