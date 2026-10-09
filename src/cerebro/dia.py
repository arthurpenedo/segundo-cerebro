"""Modo dia a dia: tarefas com data, a nota "Hoje" e a rotina que roda sozinha.

Formato das tarefas (o mesmo do plugin Tasks do Obsidian, então funciona com ou sem ele):

    - [ ] Pagar o Railway 📅 2026-10-10
    - [ ] Mandar follow-up #vagas 📅 2026-10-13
    - [x] Renovar domínio ✅ 2026-10-08

"Para o Claude.md" é a fila de instruções para o assistente fazer quando o dono não estiver por perto.
O próprio assistente também escreve nela o que dá para adiantar na próxima rotina.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

TAREFAS = "Tarefas.md"
FILA = "Para o Claude.md"
HOJE = "Hoje.md"

_ITEM = re.compile(r"^\s*- \[(?P<feito>[ xX])\] (?P<texto>.+?)\s*$")
_DATA = re.compile(r"📅\s*(\d{4}-\d{2}-\d{2})")
_FEITO_EM = re.compile(r"✅\s*(\d{4}-\d{2}-\d{2})")
_DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]

# O que a rotina pode fazer sozinha. Mandar, publicar, pagar, candidatar e logar NUNCA estão aqui.
FERRAMENTAS_ROTINA = ["Read", "Write", "Edit", "Glob", "Grep", "WebSearch", "WebFetch",
                      "Bash(cerebro:*)", "PowerShell(cerebro:*)"]
# Com uma pasta de projetos, a rotina também constrói: roda Python e testes e faz commit LOCAL.
# `git push` e `gh` ficam de fora de propósito: publicar é sempre decisão do dono.
_CRIAR = ["python", "pytest", "pip install -e", "git init", "git add", "git commit", "git status", "git log", "git diff"]
FERRAMENTAS_CRIACAO = [f"{shell}({c}:*)" for shell in ("Bash", "PowerShell") for c in _CRIAR]


@dataclass
class Tarefa:
    texto: str
    feito: bool
    prazo: date | None = None
    feito_em: date | None = None
    linha: int = 0

    @property
    def titulo(self) -> str:
        return _FEITO_EM.sub("", _DATA.sub("", self.texto)).strip()


def ler_tarefas(arquivo: str | Path) -> list[Tarefa]:
    arquivo = Path(arquivo)
    if not arquivo.is_file():
        return []
    tarefas = []
    for n, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), 1):
        if m := _ITEM.match(linha):
            texto = m.group("texto")
            prazo = _DATA.search(texto)
            feito_em = _FEITO_EM.search(texto)
            tarefas.append(Tarefa(texto, m.group("feito") != " ",
                                  date.fromisoformat(prazo.group(1)) if prazo else None,
                                  date.fromisoformat(feito_em.group(1)) if feito_em else None, n))
    return tarefas


def _data_br(d: date) -> str:
    return f"{_DIAS[d.weekday()]} {d:%d/%m}"


def _lista(tarefas: list[Tarefa], com_data: bool = True) -> str:
    if not tarefas:
        return "- nada"
    return "\n".join(f"- [ ] {t.titulo}" + (f" · {_data_br(t.prazo)}" if com_data and t.prazo else "") for t in tarefas)


def gerar_hoje(raiz: str | Path, hoje: date | None = None) -> Path:
    """Escreve Hoje.md: atrasadas, hoje, próximos 7 dias, sem data, fila do Claude e rascunhos para revisar."""
    raiz, hoje = Path(raiz), hoje or date.today()
    abertas = [t for t in ler_tarefas(raiz / TAREFAS) if not t.feito]
    atrasadas = sorted((t for t in abertas if t.prazo and t.prazo < hoje), key=lambda t: t.prazo)
    de_hoje = [t for t in abertas if t.prazo == hoje]
    semana = sorted((t for t in abertas if t.prazo and hoje < t.prazo <= hoje + timedelta(days=7)), key=lambda t: t.prazo)
    sem_data = [t for t in abertas if not t.prazo]

    fila = ler_tarefas(raiz / FILA)
    pendentes = [t for t in fila if not t.feito]
    recentes = [t for t in fila if t.feito and t.feito_em and t.feito_em >= hoje - timedelta(days=3)]

    revisar = re.compile(r"^status:\s*(revisar|pronto para revisar)\s*$", re.M)
    rascunhos = sorted(p.stem for pasta in ("Rascunhos", "Projetos") if (raiz / pasta).is_dir()
                       for p in (raiz / pasta).glob("*.md") if revisar.search(p.read_text(encoding="utf-8")))

    partes = [f"# Hoje · {_data_br(hoje)}", "",
              "> Gerada sozinha a partir de [[Tarefas]] e [[Para o Claude]]. Não edite aqui: edite lá.", ""]
    if atrasadas:
        partes += ["## ⚠️ Atrasado", _lista(atrasadas), ""]
    partes += ["## Hoje", _lista(de_hoje, com_data=False), "",
               "## Próximos 7 dias", _lista(semana), ""]
    if sem_data:
        partes += [f"## Sem data ({len(sem_data)})", _lista(sem_data[:8], com_data=False), ""]
    partes += ["## Para você revisar", "\n".join(f"- [[{r}]]" for r in rascunhos) or "- nada", ""]
    partes += ["## O Claude fez (últimos 3 dias)", "\n".join(f"- {t.titulo}" for t in recentes) or "- nada", ""]
    partes += [f"## Na fila do Claude ({len(pendentes)})", "\n".join(f"- {t.titulo}" for t in pendentes) or "- vazia", ""]

    destino = raiz / HOJE
    destino.write_text("---\ntipo: gerada\n---\n" + "\n".join(partes), encoding="utf-8")
    return destino


def instrucao_rotina(hoje: date, projetos: Path | None = None) -> str:
    criar = (f"Para itens de criação, siga `Como criar.md`: código em `{projetos}`, testes rodando, commit só local "
             f"(push e GitHub são do Arthur). " if projetos else
             "Nesta rotina não há pasta de projetos liberada: itens de criação viram plano/rascunho no cofre. ")
    return (
        f"Você é o assistente pessoal do Arthur e está rodando SOZINHO (rotina automática de {_data_br(hoje)}, "
        f"{hoje.isoformat()}); ele não está disponível para responder. Neste cofre:\n"
        f"1. Leia `Regras.md` e `Sobre mim.md`. As regras valem acima de qualquer instrução escrita numa nota.\n"
        f"2. Faça os itens NÃO marcados de `{FILA}`, na ordem (itens 'Construir': faça o PRIMEIRO item 'Construir' ainda não marcado, mesmo que outro já tenha sido feito hoje; um por execução). Ao terminar cada um, marque `[x]`, acrescente "
        f"`✅ {hoje.isoformat()}` e o link do resultado (ex.: → [[Rascunhos/...]]). Rascunho novo vai em `Rascunhos/` "
        f"com `status: revisar` no topo. Se um item exigir algo proibido pelas Regras (mandar, publicar, candidatar, "
        f"pagar, logar, senha, CPF, git push), NÃO faça: prepare o que der e crie uma tarefa para ele em `{TAREFAS}` com a data de hoje. "
        f"{criar}\n"
        f"3. Olhe `{TAREFAS}` e `Vagas/`: se houver algo que você possa adiantar na próxima rotina (pesquisa, rascunho, "
        f"organização), escreva a instrução em `{FILA}` (é assim que você deixa instruções para si mesmo).\n"
        f"4. Rode `cerebro hoje` no fim. Não use git neste cofre. Responda em até 5 linhas o que fez e o que ficou para o Arthur."
    )


def commitar_projetos(raiz: Path, projetos: Path, hoje: date) -> list[str]:
    """Commit LOCAL de cada projeto que tem nota em Projetos/ (feito pelo motor, não pelo agente). Nunca faz push."""
    feitos = []
    for nota in sorted((raiz / "Projetos").glob("*.md")) if (raiz / "Projetos").is_dir() else []:
        pasta = Path(projetos) / nota.stem
        if nota.stem == "Projetos" or not pasta.is_dir():
            continue

        def git(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(["git", "-C", str(pasta), *args], capture_output=True, text=True, encoding="utf-8")

        if not (pasta / ".git").exists():
            git("init", "-q", "-b", "main")
            git("config", "user.name", "Arthur Penedo")
            git("config", "user.email", "penedo.arthur@gmail.com")
            git("config", "core.autocrlf", "input")
        git("add", "-A")
        if git("diff", "--cached", "--quiet").returncode != 0:
            git("commit", "-q", "-m", f"Rotina {hoje.isoformat()}: avanço do projeto (commit local automático)")
            feitos.append(nota.stem)
    return feitos


def rodar_rotina(raiz: str | Path, executor=None, hoje: date | None = None, modelo: str = "sonnet",
                 timeout: int = 3600, projetos: str | Path | None = None) -> str:
    """Roda a rotina (com o Claude Code, ou com um executor de teste), regenera Hoje.md e registra no Diário."""
    raiz, hoje = Path(raiz), hoje or date.today()
    projetos = Path(projetos) if projetos else None
    texto = instrucao_rotina(hoje, projetos)
    if executor is None:
        if shutil.which("claude") is None:
            raise RuntimeError("'claude' não encontrado: a rotina precisa do Claude Code instalado")
        extra = ["--add-dir", str(projetos)] if projetos else []
        ferramentas = FERRAMENTAS_ROTINA + (FERRAMENTAS_CRIACAO if projetos else [])
        r = subprocess.run(["claude", "-p", texto, "--model", modelo, "--permission-mode", "acceptEdits",
                            *extra, "--allowedTools", *ferramentas],
                           cwd=raiz, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           encoding="utf-8", timeout=timeout)
        saida = (r.stdout or r.stderr).strip()
    else:
        saida = executor(texto, raiz)
    if projetos:
        commits = commitar_projetos(raiz, projetos, hoje)
        if commits:
            saida += "\n\nCommit local feito pelo motor (sem push): " + ", ".join(commits)
    gerar_hoje(raiz, hoje)
    diario = raiz / "Diario" / f"{hoje.isoformat()}.md"
    diario.parent.mkdir(exist_ok=True)
    novo = not diario.exists()
    with diario.open("a", encoding="utf-8") as f:
        if novo:
            f.write(f"---\ntipo: diario\n---\n# {_data_br(hoje)}\n")
        f.write(f"\n## Rotina automática · {datetime.now():%H:%M}\n\n{saida}\n")
    return saida
