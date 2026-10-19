from datetime import date

from cerebro import dia
from cerebro.cli import main

HOJE = date(2026, 10, 9)  # sexta

TAREFAS = """# Tarefas

## Pessoal
- [ ] Pagar a conta 📅 2026-10-07
- [ ] Ligar para o banco 📅 2026-10-09
- [ ] Mandar follow-up da entrevista 📅 2026-10-13
- [ ] Coisa para daqui a um mês 📅 2026-11-09
- [ ] Ler um livro
- [x] Renovar domínio 📅 2026-10-01 ✅ 2026-10-01
"""

FILA = """# Para o Claude
- [ ] Procurar 5 vagas novas de IA júnior
- [x] Rascunhar agradecimento da entrevista ✅ 2026-10-08 → [[Agradecimento]]
- [x] Coisa antiga ✅ 2026-09-01
"""


def _cofre(tmp_path):
    (tmp_path / "Tarefas.md").write_text(TAREFAS, encoding="utf-8")
    (tmp_path / "Para o Claude.md").write_text(FILA, encoding="utf-8")
    (tmp_path / "Rascunhos").mkdir()
    (tmp_path / "Rascunhos" / "Agradecimento.md").write_text("---\nstatus: revisar\n---\nOi", encoding="utf-8")
    (tmp_path / "Rascunhos" / "Velho.md").write_text("---\nstatus: enviado\n---\nOi", encoding="utf-8")
    (tmp_path / "Rascunhos" / "Rascunhos.md").write_text("# Rascunhos\nCada um tem `status: revisar` até ser usado.",
                                                          encoding="utf-8")
    return tmp_path


def test_le_tarefas_com_prazo_e_conclusao(tmp_path):
    tarefas = dia.ler_tarefas(_cofre(tmp_path) / "Tarefas.md")
    assert len(tarefas) == 6
    assert tarefas[0].titulo == "Pagar a conta" and tarefas[0].prazo == date(2026, 10, 7)
    assert tarefas[-1].feito and tarefas[-1].feito_em == date(2026, 10, 1)


def test_hoje_separa_atrasado_hoje_semana_e_mostra_o_que_o_claude_fez(tmp_path):
    texto = dia.gerar_hoje(_cofre(tmp_path), HOJE).read_text(encoding="utf-8")
    assert "# Hoje · sexta 09/10" in texto
    atrasado = texto.split("## ⚠️ Atrasado")[1].split("##")[0]
    assert "Pagar a conta · quarta 07/10" in atrasado
    assert "Ligar para o banco" in texto.split("## Hoje\n")[1].split("##")[0]
    semana = texto.split("## Próximos 7 dias")[1].split("##")[0]
    assert "Mandar follow-up da entrevista · terça 13/10" in semana and "daqui a um mês" not in semana
    assert "Renovar domínio" not in texto  # feita
    revisar = texto.split("## Para você revisar")[1].split("##")[0]
    assert "[[Agradecimento]]" in revisar and "Velho" not in revisar  # só rascunho com status: revisar
    assert "[[Rascunhos]]" not in revisar  # nota-índice que só menciona o status no texto
    feito = texto.split("## O Claude fez")[1].split("##")[0]
    assert "Rascunhar agradecimento" in feito and "Coisa antiga" not in feito
    assert "## Na fila do Claude (1)" in texto


def test_rotina_usa_o_executor_regera_hoje_e_registra_no_diario(tmp_path):
    raiz = _cofre(tmp_path)
    recebido = {}

    def executor(texto, raiz_):
        recebido["texto"] = texto
        fila = raiz_ / "Para o Claude.md"
        fila.write_text(fila.read_text(encoding="utf-8").replace(
            "- [ ] Procurar 5 vagas", "- [x] Procurar 5 vagas") .replace("júnior\n", "júnior ✅ 2026-10-09\n"),
            encoding="utf-8")
        return "Achei 5 vagas."

    saida = dia.rodar_rotina(raiz, executor, hoje=HOJE)
    assert saida == "Achei 5 vagas."
    assert "NÃO faça" in recebido["texto"] and "Regras.md" in recebido["texto"]
    assert "## Na fila do Claude (0)" in (raiz / "Hoje.md").read_text(encoding="utf-8")
    assert "Achei 5 vagas." in (raiz / "Diario" / "2026-10-09.md").read_text(encoding="utf-8")


def test_rotina_nao_libera_ferramentas_de_acao_externa():
    proibidas = ("Bash", "PowerShell", "mcp__")
    for f in dia.FERRAMENTAS_ROTINA:
        assert not f.startswith(proibidas) or "(cerebro:*)" in f


def test_cli_hoje(tmp_path, capsys):
    raiz = _cofre(tmp_path)
    assert main(["--cofre", str(raiz), "hoje"]) == 0
    assert (raiz / "Hoje.md").exists()


def test_criacao_libera_testes_e_commit_local_mas_nunca_publicar():
    assert "Bash(git commit:*)" in dia.FERRAMENTAS_CRIACAO and "PowerShell(pytest:*)" in dia.FERRAMENTAS_CRIACAO
    for f in dia.FERRAMENTAS_CRIACAO + dia.FERRAMENTAS_ROTINA:
        assert "push" not in f and "gh" not in f.split("(")[-1]


def test_instrucao_muda_com_pasta_de_projetos(tmp_path):
    from pathlib import Path

    com = dia.instrucao_rotina(HOJE, Path("C:/projetos"))
    sem = dia.instrucao_rotina(HOJE)
    assert "Como criar.md" in com and "NÃO usa git" in com
    assert "não há pasta de projetos" in sem


def test_projeto_pronto_aparece_para_revisar(tmp_path):
    raiz = _cofre(tmp_path)
    (raiz / "Projetos").mkdir()
    (raiz / "Projetos" / "meu-projeto.md").write_text("---\nstatus: pronto para revisar\n---\n# x", encoding="utf-8")
    (raiz / "Projetos" / "outro.md").write_text("---\nstatus: construindo\n---\n# y", encoding="utf-8")
    revisar = dia.gerar_hoje(raiz, HOJE).read_text(encoding="utf-8").split("## Para você revisar")[1].split("##")[0]
    assert "[[meu-projeto]]" in revisar and "outro" not in revisar


def test_calendario_um_por_dia_e_aparece_no_hoje(tmp_path):
    raiz = _cofre(tmp_path)
    assert dia.agendar(raiz, "a", HOJE) == HOJE
    assert dia.agendar(raiz, "b", HOJE) == date(2026, 10, 10)  # padrão: todo dia
    assert dia.agendar(raiz, "c", HOJE, so_dias_uteis=True) == date(2026, 10, 13)  # sexta → terça (fim de semana + feriado)
    assert dia.agendar(raiz, "a", HOJE) == HOJE  # já agendado: não duplica
    texto = dia.gerar_hoje(raiz, HOJE).read_text(encoding="utf-8")
    publicar = texto.split("Publicar hoje")[1].split("##")[0]
    assert "[[a]]" in publicar and "[[b]]" not in publicar


def test_so_dias_uteis_e_reorganizar(tmp_path):
    raiz = _cofre(tmp_path)
    assert dia.agendar(raiz, "a", HOJE) == HOJE  # sexta
    assert dia.agendar(raiz, "b", HOJE, so_dias_uteis=True) == date(2026, 10, 13)  # pula fim de semana e o feriado de 12/10
    novo = dict(dia.reorganizar(raiz, date(2026, 10, 10), so_dias_uteis=True))
    assert novo == {"a": date(2026, 10, 13), "b": date(2026, 10, 14)}


def _repo_com_origem(tmp_path, nome):
    import subprocess

    origem = tmp_path / "remotos" / f"{nome}.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origem)], check=True)
    pasta = tmp_path / "projetos" / nome
    pasta.mkdir(parents=True)

    def git(*a):
        return subprocess.run(["git", "-C", str(pasta), *a], capture_output=True, text=True, check=True).stdout

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    git("remote", "add", "origin", str(origem))
    (pasta / "a.txt").write_text("1", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "inicio")
    git("push", "-q", "-u", "origin", "main")
    return pasta, git


def test_publicar_faz_push_com_a_mensagem_do_agente(tmp_path):
    pasta, git = _repo_com_origem(tmp_path, "proj")
    (pasta / "a.txt").write_text("2", encoding="utf-8")
    (pasta / dia.MSG_COMMIT).write_text("Adiciona teste do parser\n", encoding="utf-8")
    rel = dia.publicar_projetos(tmp_path / "projetos", HOJE, remoto="remotos", testes=lambda p: True)
    assert rel == ["proj: publicado · Adiciona teste do parser"]
    assert not (pasta / dia.MSG_COMMIT).exists()
    assert git("status", "-sb").splitlines()[0] == "## main...origin/main"  # nada pendente de push
    assert "Adiciona teste do parser" in git("log", "-1", "--format=%s")


def test_publicar_sem_mudanca_nao_commita(tmp_path):
    _repo_com_origem(tmp_path, "proj")
    assert dia.publicar_projetos(tmp_path / "projetos", HOJE, remoto="remotos", testes=lambda p: True) == []


def test_publicar_barra_teste_falhando_remoto_alheio_e_segredo(tmp_path):
    pasta, git = _repo_com_origem(tmp_path, "falha")
    (pasta / "a.txt").write_text("2", encoding="utf-8")
    rel = dia.publicar_projetos(tmp_path / "projetos", HOJE, remoto="remotos", testes=lambda p: False)
    assert rel == ["falha: commit só local, sem push (testes falharam)"]
    assert "ahead 1" in git("status", "-sb")

    (pasta / "a.txt").write_text("3", encoding="utf-8")
    rel = dia.publicar_projetos(tmp_path / "projetos", HOJE, testes=lambda p: True)  # remoto padrão: github arthurpenedo
    assert rel == ["falha: commit só local (o remoto não é do Arthur)"]

    (pasta / "chave.txt").write_text("sk-ant-" + "x" * 30, encoding="utf-8")
    rel = dia.publicar_projetos(tmp_path / "projetos", HOJE, remoto="remotos", testes=lambda p: True)
    assert rel == ["falha: NÃO commitado, o diff parece ter uma chave ou segredo"]
    assert "chave.txt" in git("status", "--porcelain")


def test_publicar_respeita_ignorar(tmp_path):
    pasta, _ = _repo_com_origem(tmp_path, "site")
    (pasta / "a.txt").write_text("2", encoding="utf-8")
    assert dia.publicar_projetos(tmp_path / "projetos", HOJE, ignorar={"site"}, remoto="remotos",
                                 testes=lambda p: True) == []


def test_instrucao_pede_melhorias_reais_com_mensagem():
    from pathlib import Path

    texto = dia.instrucao_rotina(HOJE, Path("C:/projetos"))
    assert dia.MELHORIAS in texto and dia.MSG_COMMIT in texto and "REAIS" in texto
