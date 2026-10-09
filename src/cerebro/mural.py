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
from datetime import date, datetime
from pathlib import Path

import yaml

from .cofre import Nota

STATUS = ("aberto", "feito", "recusado", "substituido")
HUMANO = "arthur"


def recados(notas: dict[str, Nota]) -> list[Nota]:
    # `criado` tem data e hora ("2026-10-09 14:05:31"); recados antigos só têm a data e ficam antes no mesmo dia.
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


class RecadoRecusado(ValueError):
    """Regra do Mural violada: o recado não é escrito."""


def _meta_do_recado(raiz: Path, nome: str) -> dict:
    arquivo = raiz / "Mural" / f"{nome}.md"
    if not arquivo.is_file():
        return {}
    texto = arquivo.read_text(encoding="utf-8")
    m = re.match(r"---\r?\n(.*?)\r?\n---", texto, re.S)
    return (yaml.safe_load(m.group(1)) or {}) if m else {}


def escrever_recado(raiz: str | Path, de: str, para: str, assunto: str, texto: str,
                    responde: str | None = None, hoje: date | datetime | None = None,
                    pedido: str | None = None) -> Path:
    """Cria Mural/AAAA-MM-DD de para para assunto.md. Usado pelos agentes via `cerebro recado`.

    Regras aplicadas aqui, no código (não só no prompt dos agentes):
    - só o maestro escreve para o Arthur, para ele receber uma voz só;
    - o recado herda o `pedido` do recado ao qual responde, para agrupar a conversa por pedido.
    """
    raiz = Path(raiz)
    if para.lower() == HUMANO and de.lower() != "maestro":
        raise RecadoRecusado(f"só o maestro fala com o {HUMANO}: mande este recado para o maestro "
                             f"(--para maestro) e ele leva ao {HUMANO}")
    quando = hoje or datetime.now()
    pasta = raiz / "Mural"
    pasta.mkdir(parents=True, exist_ok=True)
    # Só ASCII no nome do arquivo: o PowerShell do Windows não repassa bem caracteres como "→" para os comandos.
    base = f"{quando.strftime('%Y-%m-%d')} {de} para {para} {_slug(assunto)}"
    destino, n = pasta / f"{base}.md", 2
    while destino.exists():
        destino, n = pasta / f"{base}-{n}.md", n + 1
    criado = quando.isoformat(sep=" ", timespec="seconds") if isinstance(quando, datetime) else quando.isoformat()
    if responde and not pedido:
        pedido = _meta_do_recado(raiz, responde).get("pedido")
    meta = {"tipo": "recado", "de": de, "para": para, "status": "aberto", "criado": criado, "assunto": assunto}
    if pedido:
        meta["pedido"] = str(pedido).strip("[]")
    if responde:
        meta["responde"] = responde
    cabecalho = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
    corpo = f"# {assunto}\n\n{texto.strip()}\n"
    if responde:
        corpo += f"\nEm resposta a [[{responde}]].\n"
    destino.write_text(f"---\n{cabecalho}\n---\n{corpo}", encoding="utf-8")
    return destino


def localizar(raiz: str | Path, referencia: str) -> Path:
    """Acha o arquivo de um recado pelo caminho, pelo nome ou por um trecho único do nome."""
    raiz = Path(raiz)
    direto = Path(referencia) if Path(referencia).is_absolute() else raiz / referencia
    if direto.is_file():
        return direto
    trecho = Path(referencia).stem.lower() if referencia.lower().endswith(".md") else referencia.lower()
    candidatos = [p for p in (raiz / "Mural").glob("*.md") if trecho in p.stem.lower()]
    if len(candidatos) == 1:
        return candidatos[0]
    if not candidatos:
        raise FileNotFoundError(f"nenhum recado com '{referencia}' no nome")
    raise ValueError(f"'{referencia}' bate com {len(candidatos)} recados; use um trecho mais específico: "
                     + "; ".join(p.stem for p in candidatos[:5]))


def mudar_status(arquivo: str | Path, status: str) -> None:
    if status not in STATUS:
        raise ValueError(f"status inválido: {status} (use {', '.join(STATUS)})")
    arquivo = Path(arquivo)
    texto = arquivo.read_text(encoding="utf-8")
    novo, n = re.subn(r"^status: *\S+", f"status: {status}", texto, count=1, flags=re.M)
    if not n:
        raise ValueError(f"{arquivo.name} não tem campo status")
    arquivo.write_text(novo, encoding="utf-8")
