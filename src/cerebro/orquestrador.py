"""O laço automático: enquanto houver recado aberto para um agente, acorda esse agente.

    cerebro rodar                      # usa o Claude Code da máquina (claude -p --agent <id>)
    cerebro rodar --max-turnos 12 --modelo sonnet

Regras do laço:
- Nota nova em 00-Entrada (sem status) acorda o maestro e é marcada `status: encaminhado`, para ninguém
  encaminhar de novo.
- A cada turno, acorda o agente com o recado aberto mais antigo. Recados para `arthur` nunca
  acordam ninguém: são decisões humanas e encerram o ciclo.
- Se um agente termina o turno sem fechar nenhum dos recados dele, o laço para (evita girar em falso).
- Quando o ciclo termina bem e alguém trabalhou, o secretário é acordado uma vez para escrever o diário.
- Cada execução vira uma nota em Diario/ com os turnos, para dar para auditar depois.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Protocol

from .cofre import Nota, ler_cofre
from .mural import HUMANO, recados

# Ferramentas liberadas para os agentes no modo automático: escrever no cofre e usar o `cerebro`.
# Nada de git push, rede ou comando arbitrário sem uma pessoa olhando.
# No Windows o modo não interativo do Claude Code usa o PowerShell como terminal; no Linux/macOS, o Bash.
_COMANDOS = ["cerebro", "ls", "mv", "gh run list", "git log"]
FERRAMENTAS = ["Read", "Write", "Edit", "Glob", "Grep",
               *(f"{shell}({c}:*)" for shell in ("Bash", "PowerShell") for c in _COMANDOS)]
CICLO_COMPLETO = "nenhum recado aberto para agentes"


class Executor(Protocol):
    def __call__(self, agente: str, instrucao: str, raiz: Path) -> str: ...


@dataclass
class Turno:
    agente: str
    motivo: str
    fechados: int
    novos: int
    saida: str = ""


@dataclass
class Execucao:
    turnos: list[Turno] = field(default_factory=list)
    parou_por: str = ""


def _abertos(notas: dict[str, Nota]) -> list[Nota]:
    return [r for r in recados(notas) if r.meta.get("status") == "aberto"]


def _entrada_pendente(notas: dict[str, Nota]) -> list[Nota]:
    return [n for n in notas.values() if n.pasta == "00-Entrada" and n.tipo != "guia" and not n.meta.get("status")]


def proximo(notas: dict[str, Nota], ja_viu_entrada: set[str]) -> tuple[str, str] | None:
    """(agente, motivo) de quem deve agir agora, ou None se o ciclo acabou."""
    for r in _abertos(notas):
        para = str(r.meta.get("para", "")).lower()
        if para not in (HUMANO, "todos"):
            return para, f"recado aberto: {r.nome}"
    novas = [n for n in _entrada_pendente(notas) if n.nome not in ja_viu_entrada]
    if novas:
        return "maestro", f"nota nova na Entrada: {novas[0].nome}"
    return None


def instrucao(agente: str, motivo: str) -> str:
    return (f"Você foi acordado pelo laço automático do segundo-cerebro ({motivo}). Siga as regras do CLAUDE.md "
            f"e da sua nota em Agentes/. Comece com `cerebro mural --para {agente}`, trate o que for seu, deixe "
            f"recados para quem age em seguida (com --responde), feche o que resolveu com `cerebro fechar`, "
            f"e termine com `cerebro validar` sem problemas. Rode UM comando por vez, sem encadear com ; ou &&. "
            f"Para texto de recado longo ou com várias linhas, escreva-o com a ferramenta Write em "
            f"`.rascunhos/<nome>.txt` e use `cerebro recado ... --texto-arquivo .rascunhos/<nome>.txt`. "
            f"Não use git. Responda em 2 linhas o que fez.")


def marcar(arquivo: Path, status: str) -> None:
    """Põe/atualiza `status:` no frontmatter de uma nota (cria o frontmatter se não houver)."""
    texto = arquivo.read_text(encoding="utf-8")
    if texto.startswith("---"):
        if re.search(r"^status:", texto, flags=re.M):
            texto = re.sub(r"^status: *.*$", f"status: {status}", texto, count=1, flags=re.M)
        else:
            texto = texto.replace("---\n", f"---\nstatus: {status}\n", 1)
    else:
        texto = f"---\nstatus: {status}\n---\n{texto}"
    arquivo.write_text(texto, encoding="utf-8")


def executor_claude(modelo: str = "sonnet", comando: str = "claude", timeout: int = 900) -> Executor:
    """Roda o subagente do cofre com o Claude Code em modo não interativo (usa a assinatura, sem API)."""
    if shutil.which(comando) is None:
        raise RuntimeError(f"'{comando}' não encontrado: instale o Claude Code ou use outro executor")

    def executar(agente: str, texto: str, raiz: Path) -> str:
        r = subprocess.run([comando, "-p", texto, "--agent", agente, "--model", modelo,
                            "--permission-mode", "acceptEdits", "--allowedTools", *FERRAMENTAS],
                           cwd=raiz, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", timeout=timeout)
        return (r.stdout or r.stderr).strip()

    return executar


def rodar(raiz: str | Path, executor: Executor, max_turnos: int = 15,
          aviso: Callable[[str], None] = print, diario: bool = True) -> Execucao:
    raiz = Path(raiz)
    execucao, ja_viu_entrada = Execucao(), set()
    trabalhou = False

    while True:
        notas = ler_cofre(raiz)
        quem = proximo(notas, ja_viu_entrada)
        if quem is None:
            execucao.parou_por = CICLO_COMPLETO
            break
        if len(execucao.turnos) >= max_turnos:
            execucao.parou_por = f"limite de {max_turnos} turnos"
            break
        agente, motivo = quem
        if motivo.startswith("nota nova"):
            for n in _entrada_pendente(notas):
                ja_viu_entrada.add(n.nome)
                marcar(raiz / n.caminho, "encaminhado")
        antes = {r.nome for r in _abertos(notas) if str(r.meta.get("para", "")).lower() in (agente, "todos")}
        total_antes = len(recados(notas))

        aviso(f"[{len(execucao.turnos) + 1}] {agente} ← {motivo}")
        saida = executor(agente, instrucao(agente, motivo), raiz)

        depois_notas = ler_cofre(raiz)
        ainda = {r.nome for r in _abertos(depois_notas)}
        turno = Turno(agente, motivo, len(antes - ainda), len(recados(depois_notas)) - total_antes, saida)
        execucao.turnos.append(turno)
        trabalhou = True
        aviso(f"    fechou {turno.fechados}, criou {turno.novos}" + (f" · {saida.splitlines()[0][:120]}" if saida else ""))
        if antes and not turno.fechados:
            execucao.parou_por = f"{agente} não fechou nenhum recado (parei para não girar em falso)"
            break

    if trabalhou and diario and execucao.parou_por == CICLO_COMPLETO:
        aviso("[fim] secretario ← escrever o diário do ciclo")
        execucao.turnos.append(Turno("secretario", "diário do ciclo", 0, 0,
                                     executor("secretario", instrucao("secretario", "fim do ciclo: escreva/atualize o Diário de hoje e processe a Entrada"), raiz)))
    if trabalhou:
        _registrar(raiz, execucao)
    aviso(f"Fim: {execucao.parou_por}. {len(execucao.turnos)} turnos.")
    return execucao


def _registrar(raiz: Path, execucao: Execucao) -> Path:
    agora = datetime.now()
    destino = raiz / "Diario" / f"Execucao {agora:%Y-%m-%d %H%M}.md"
    destino.parent.mkdir(exist_ok=True)
    linhas = "\n".join(f"| {i} | {t.agente} | {t.motivo} | {t.fechados} | {t.novos} |"
                       for i, t in enumerate(execucao.turnos, 1))
    respostas = "\n\n".join(f"**{i}. {t.agente}:** " + " ".join(t.saida.split())[:600]
                              for i, t in enumerate(execucao.turnos, 1) if t.saida)
    destino.write_text(f"""---
tipo: execucao
data: {agora:%Y-%m-%d}
turnos: {len(execucao.turnos)}
---
# Execução do laço automático · {agora:%d/%m/%Y %H:%M}

Parou por: {execucao.parou_por}.

| # | Agente | Por quê | Recados fechados | Recados criados |
|---|---|---|---|---|
{linhas}

## O que cada agente respondeu

{respostas}

Veja [[Como os agentes trabalham]] e o [[Mural]].
""", encoding="utf-8")
    return destino
