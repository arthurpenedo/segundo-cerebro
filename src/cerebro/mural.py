"""O Mural: o lugar onde os agentes conversam.

Um recado é uma nota em Mural/ com frontmatter fixo:

    tipo: recado
    de: carreira            # agente que escreveu
    para: dev               # agente que deve agir (ou "todos", ou "arthur" para o humano)
    status: aberto          # aberto -> feito (ou recusado)
    criado: 2026-10-09
    responde: <nome de outro recado>   # opcional, forma a conversa

Todo agente começa o turno lendo os recados abertos para ele e termina deixando recados
para quem precisa agir em seguida. Assim a conversa fica registrada, versionada no git e
navegável no Obsidian.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from pathlib import Path

import yaml

from .cofre import Nota

STATUS = ("aberto", "feito", "recusado")
HUMANO = "arthur"


def recados(notas: dict[str, Nota]) -> list[Nota]:
    return sorted((n for n in notas.values() if n.tipo == "recado"),
                  key=lambda n: (str(n.meta.get("criado", "")), n.nome))


def agentes(notas: dict[str, Nota]) -> dict[str, Nota]:
    return {str(n.meta.get("id", n.nome)).lower(): n for n in notas.values() if n.tipo == "agente"}


def abertos_para(notas: dict[str, Nota], agente: str) -> list[Nota]:
    agente = agente.lower()
    return [r for r in recados(notas)
            if r.meta.get("status") == "aberto" and str(r.meta.get("para", "")).lower() in (agente, "todos")]


def conversas(notas: dict[str, Nota]) -> list[list[Nota]]:
    """Agrupa recados em fios: cada fio começa num recado que não responde a ninguém."""
    todos = recados(notas)
    filhos: dict[str, list[Nota]] = {}
    raizes = []
    for r in todos:
        pai = str(r.meta.get("responde") or "").strip("[]").lower()
        if pai and pai in notas:
            filhos.setdefault(pai, []).append(r)
        else:
            raizes.append(r)

    def descer(r: Nota) -> list[Nota]:
        fio = [r]
        for f in filhos.get(r.nome.lower(), []):
            fio += descer(f)
        return fio

    return [descer(r) for r in raizes]


def _slug(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", sem_acento.lower()).strip("-")[:50]


def escrever_recado(raiz: str | Path, de: str, para: str, assunto: str, texto: str,
                    responde: str | None = None, hoje: date | None = None) -> Path:
    """Cria Mural/AAAA-MM-DD de-para assunto.md. Usado pelos agentes via `cerebro recado`."""
    hoje = hoje or date.today()
    pasta = Path(raiz) / "Mural"
    pasta.mkdir(parents=True, exist_ok=True)
    base = f"{hoje.isoformat()} {de}→{para} {_slug(assunto)}"
    destino, n = pasta / f"{base}.md", 2
    while destino.exists():
        destino, n = pasta / f"{base}-{n}.md", n + 1
    meta = {"tipo": "recado", "de": de, "para": para, "status": "aberto", "criado": hoje.isoformat(), "assunto": assunto}
    if responde:
        meta["responde"] = responde
    cabecalho = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
    corpo = f"# {assunto}\n\n{texto.strip()}\n"
    if responde:
        corpo += f"\nEm resposta a [[{responde}]].\n"
    destino.write_text(f"---\n{cabecalho}\n---\n{corpo}", encoding="utf-8")
    return destino


def mudar_status(arquivo: str | Path, status: str) -> None:
    if status not in STATUS:
        raise ValueError(f"status inválido: {status} (use {', '.join(STATUS)})")
    arquivo = Path(arquivo)
    texto = arquivo.read_text(encoding="utf-8")
    novo, n = re.subn(r"^status: *\S+", f"status: {status}", texto, count=1, flags=re.M)
    if not n:
        raise ValueError(f"{arquivo.name} não tem campo status")
    arquivo.write_text(novo, encoding="utf-8")
