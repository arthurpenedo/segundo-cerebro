"""Aprendizados: cada micro atividade deixa uma lição no cofre.

    cerebro aprendi "push travou: o gerenciador de credenciais abriu janela invisível; usar o gh" --tema "Publicar no GitHub"

Grava em dois lugares:
- Aprendizados/AAAA-MM-DD.md: o registro do dia, em ordem, com hora e link para o tema;
- Manual/<tema>.md: o passo a passo do tema, que cresce com cada lição e é lido antes de repetir a tarefa.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def aprendi(raiz: str | Path, texto: str, tema: str | None = None, quando: datetime | None = None) -> list[Path]:
    raiz, quando = Path(raiz), quando or datetime.now()
    texto = " ".join(texto.split())
    escritos = []

    dia = raiz / "Aprendizados" / f"Aprendizados {quando:%Y-%m-%d}.md"
    dia.parent.mkdir(parents=True, exist_ok=True)
    if not dia.exists():
        dia.write_text(f"---\ntipo: aprendizados\ndata: {quando:%Y-%m-%d}\n---\n# Aprendizados de {quando:%d/%m/%Y}\n\n",
                       encoding="utf-8")
    with dia.open("a", encoding="utf-8") as f:
        f.write(f"- {quando:%H:%M} " + (f"[[{tema}]] · " if tema else "") + f"{texto}\n")
    escritos.append(dia)

    if tema:
        manual = raiz / "Manual" / f"{tema}.md"
        manual.parent.mkdir(parents=True, exist_ok=True)
        if not manual.exists():
            manual.write_text(f"---\ntipo: manual\n---\n# {tema}\n\nPasso a passo que cresce com cada aprendizado. "
                              f"Ler antes de repetir a tarefa.\n\n## Aprendizados\n", encoding="utf-8")
        with manual.open("a", encoding="utf-8") as f:
            f.write(f"- {texto} ([[{quando:%Y-%m-%d}]])\n")
        escritos.append(manual)
    return escritos
