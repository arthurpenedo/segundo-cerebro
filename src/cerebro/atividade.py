"""Cada atividade feita vira um ponto no grafo do Obsidian (pedido do Arthur em 24/11/2026).

A informacao detalhada continua numa fonte unica (ex.: Vagas/Candidaturas.md); a nota da atividade e curta e so
liga o dia, o que foi feito e onde estao os detalhes.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path


def _nome(titulo: str) -> str:
    limpo = re.sub(r'[\/:*?"<>|#^\[\]]', " ", titulo)
    return " ".join(limpo.split())[:80]


def atividade(raiz: str | Path, titulo: str, texto: str = "", links=(), quando: datetime | None = None) -> list[Path]:
    """Cria `Atividades/AAAA-MM-DD HHhMM titulo.md` ligada ao dia e as notas-fonte, e aponta o diario para ela."""
    raiz, quando = Path(raiz), quando or datetime.now()
    links = [l.strip().removesuffix(".md") for l in links if l and l.strip()]
    nome = f"{quando:%Y-%m-%d %Hh%M} {_nome(titulo)}"
    nota = raiz / "Atividades" / f"{nome}.md"
    nota.parent.mkdir(parents=True, exist_ok=True)
    corpo = [f"---\ntipo: atividade\ndata: {quando:%Y-%m-%d}\nhora: \"{quando:%H:%M}\"\n---",
             f"# {titulo.strip()}", "", f"Dia: [[{quando:%Y-%m-%d}]]"]
    if links:
        corpo.append("Detalhes em: " + " · ".join(f"[[{l}]]" for l in links))
    if texto.strip():
        corpo += ["", " ".join(texto.split())]
    nota.write_text("\n".join(corpo) + "\n", encoding="utf-8")

    dia = raiz / "Diario" / f"{quando:%Y-%m-%d}.md"
    dia.parent.mkdir(parents=True, exist_ok=True)
    atual = dia.read_text(encoding="utf-8") if dia.exists() else f"# {quando:%d/%m/%Y}\n"
    if "## Atividades" not in atual:
        atual = atual.rstrip("\n") + "\n\n## Atividades\n"
    dia.write_text(atual.rstrip("\n") + f"\n- {quando:%H:%M} [[{nome}|{titulo.strip()}]]\n", encoding="utf-8")
    return [nota, dia]
