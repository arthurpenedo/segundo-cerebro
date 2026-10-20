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
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

from . import caixa
from .cofre import Nota, ler_cofre
from .mural import HUMANO, recados

# Ferramentas liberadas para os agentes no modo automático: escrever no cofre e usar o `cerebro`.
# Nada de git push, rede ou comando arbitrário sem uma pessoa olhando.
# No Windows o modo não interativo do Claude Code usa o PowerShell como terminal; no Linux/macOS, o Bash.
_COMANDOS = ["cerebro", "ls", "mv", "gh run list", "git log"]
FERRAMENTAS = ["Read", "Write", "Edit", "Glob", "Grep",
               *(f"{shell}({c}:*)" for shell in ("Bash", "PowerShell") for c in _COMANDOS)]
CICLO_COMPLETO = "nenhum recado aberto para agentes"
ENTRADA = "nota nova na Entrada: "


class Executor(Protocol):
    def __call__(self, agente: str, instrucao: str, raiz: Path) -> str: ...


@dataclass
class Turno:
    agente: str
    motivo: str
    fechados: int
    novos: int
    saida: str = ""
    segundos: float = 0.0
    ferramentas: list = field(default_factory=list)  # trilha de auditoria (motor próprio)
    detalhes: list = field(default_factory=list)
    recusas: int = 0
    tokens: int = 0


@dataclass
class Execucao:
    turnos: list[Turno] = field(default_factory=list)
    parou_por: str = ""
    substituidos: int = 0


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
        return "maestro", f"{ENTRADA}{novas[0].nome}"
    return None


def instrucao(agente: str, motivo: str) -> str:
    pedido = ""
    if motivo.startswith(ENTRADA):
        nome = motivo[len(ENTRADA):]
        pedido = (f'Este é um pedido novo: em TODO recado que abrir para ele, use `--pedido "{nome}"`, para a '
                  f"conversa ficar agrupada. ")
    return (f"Você foi acordado pelo laço automático do segundo-cerebro ({motivo}). {pedido}"
            f"Só o maestro escreve para `{HUMANO}`; os outros agentes entregam o resultado final ao maestro. "
            f"Siga as regras do CLAUDE.md "
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


class ExecutorLLM:
    """Executor do motor próprio: roda o turno com qualquer LLM compatível com a OpenAI (ex.: Ollama, de graça).

    Guarda o último `ResultadoTurno` para o laço registrar ferramentas, recusas e tokens no Diário.
    """

    def __init__(self, llm, max_passos: int = 12):
        self.llm, self.max_passos, self.ultimo = llm, max_passos, None

    def __call__(self, agente: str, texto: str, raiz: Path) -> str:
        from .agente import rodar_turno, sugerir_agentes
        m = re.search(r"segundo-cerebro \((.*?)\)\. ", texto, re.S)
        motivo = m.group(1) if m else texto
        pedido = None
        if motivo.startswith(ENTRADA):
            nome = motivo[len(ENTRADA):]
            arquivo = Path(raiz) / "00-Entrada" / f"{nome}.md"
            texto_pedido = arquivo.read_text(encoding="utf-8").strip() if arquivo.is_file() else ""
            pedido = nome
            sugestao = ", ".join(sugerir_agentes(Path(raiz), texto_pedido or nome)) or "veja a lista da equipe"
            motivo += (f'. É um pedido novo do humano. Em todo recado que abrir para ele, passe pedido="{nome}". '
                       f"Pelo papel, quem mais combina com este pedido: {sugestao} (sugestão do sistema; a escolha é sua). "
                       f"Texto do pedido:\n\n{texto_pedido}")
        self.ultimo = rodar_turno(raiz, agente, motivo, self.llm, self.max_passos, pedido=pedido)
        return self.ultimo.resposta


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
        if motivo.startswith(ENTRADA):
            for n in _entrada_pendente(notas):
                ja_viu_entrada.add(n.nome)
                marcar(raiz / n.caminho, "encaminhado")
        antes = {r.nome for r in _abertos(notas) if str(r.meta.get("para", "")).lower() in (agente, "todos")}
        total_antes = len(recados(notas))

        aviso(f"[{len(execucao.turnos) + 1}] {agente} ← {motivo}")
        inicio = time.perf_counter()
        saida = executor(agente, instrucao(agente, motivo), raiz)
        segundos = time.perf_counter() - inicio

        depois_notas = ler_cofre(raiz)
        ainda = {r.nome for r in _abertos(depois_notas)}
        turno = Turno(agente, motivo, len(antes - ainda), len(recados(depois_notas)) - total_antes, saida, segundos)
        _anotar_motor(turno, executor)
        execucao.turnos.append(turno)
        trabalhou = True
        aviso(f"    fechou {turno.fechados}, criou {turno.novos}" + (f" · {saida.splitlines()[0][:120]}" if saida else ""))
        if antes and not turno.fechados:
            execucao.parou_por = f"{agente} não fechou nenhum recado (parei para não girar em falso)"
            break

    if trabalhou and diario and execucao.parou_por == CICLO_COMPLETO:
        aviso("[fim] secretario ← escrever o diário do ciclo")
        inicio = time.perf_counter()
        saida = executor("secretario", instrucao("secretario", "fim do ciclo: escreva/atualize o Diário de hoje e processe a Entrada"), raiz)
        turno = Turno("secretario", "diário do ciclo", 0, 0, saida, time.perf_counter() - inicio)
        _anotar_motor(turno, executor)
        execucao.turnos.append(turno)
    if trabalhou:
        execucao.substituidos = caixa.consolidar(raiz)
        caixa.gerar_nota(raiz)
        if execucao.substituidos:
            aviso(f"[caixa] {execucao.substituidos} recado(s) antigo(s) para {HUMANO} substituído(s) pelo mais recente do pedido")
        _registrar(raiz, execucao)
    aviso(f"Fim: {execucao.parou_por}. {len(execucao.turnos)} turnos.")
    return execucao


def _resumo_chamada(r) -> str:
    a = r.argumentos or {}
    chave = next((str(a[k]) for k in ("para", "pasta", "nome", "consulta") if a.get(k)), "")
    extra = f" ({a.get('assunto') or a.get('titulo')})" if (a.get("assunto") or a.get("titulo")) else ""
    return f"{r.ferramenta}({chave[:50]}){extra[:70]}" + ("" if r.ok else f" RECUSADO: {r.resultado[10:90]}")


def _anotar_motor(turno: Turno, executor) -> None:
    ultimo = getattr(executor, "ultimo", None)
    if ultimo is not None:
        turno.ferramentas = [(r.ferramenta, r.ok) for r in ultimo.registros]
        turno.detalhes = [_resumo_chamada(r) for r in ultimo.registros]
        turno.recusas = ultimo.recusas
        turno.tokens = ultimo.tokens_entrada + ultimo.tokens_saida


def _registrar(raiz: Path, execucao: Execucao) -> Path:
    agora = datetime.now()
    destino = raiz / "Diario" / f"Execucao {agora:%Y-%m-%d %H%M}.md"
    destino.parent.mkdir(exist_ok=True)
    linhas = "\n".join(f"| {i} | {t.agente} | {t.motivo} | {t.fechados} | {t.novos} | {t.segundos:.0f} s |"
                       for i, t in enumerate(execucao.turnos, 1))
    respostas = "\n\n".join(f"**{i}. {t.agente}:** " + " ".join(t.saida.split())[:600]
                              for i, t in enumerate(execucao.turnos, 1) if t.saida)
    trilha = "\n".join(f"| {i} | {t.agente} | " + ", ".join(f"{n}{'' if ok else ' (recusado)'}" for n, ok in t.ferramentas)
                       + f" | {t.recusas} | {t.tokens} |" for i, t in enumerate(execucao.turnos, 1) if t.ferramentas)
    if trilha:
        trilha = ("\n## Ferramentas usadas (motor próprio)\n\n| # | Agente | Ferramentas | Recusas | Tokens |\n"
                  "|---|---|---|---|---|\n" + trilha + "\n")
    caixa_nome = caixa.NOTA[:-3]
    destino.write_text(f"""---
tipo: execucao
data: {agora:%Y-%m-%d}
turnos: {len(execucao.turnos)}
---
# Execução do laço automático · {agora:%d/%m/%Y %H:%M}

Parou por: {execucao.parou_por}. Recados para {HUMANO} substituídos pelo mais recente do pedido: {execucao.substituidos}. Decisões pendentes: [[{caixa_nome}]].

| # | Agente | Por quê | Recados fechados | Recados criados | Tempo |
|---|---|---|---|---|---|
{linhas}
{trilha}
## O que cada agente respondeu

{respostas}

Veja [[Como os agentes trabalham]] e o [[Mural]].
""", encoding="utf-8")
    return destino
