"""`cerebro init <pasta>`: cria um cofre novo com os 9 agentes, pronto para abrir no Obsidian.

O modelo vem dentro do pacote (`cerebro/modelo`). A pasta `_claude` vira `.claude` no destino: pastas com
ponto não entram bem como dado de pacote em todo sistema. Nada é sobrescrito: se o destino já tem notas,
o comando para.
"""

from __future__ import annotations

import shutil
from pathlib import Path

MODELO = Path(__file__).parent / "modelo"


def criar_cofre(destino: str | Path, humano: str = "arthur") -> Path:
    destino = Path(destino)
    if destino.exists() and any(destino.rglob("*.md")):
        raise FileExistsError(f"{destino} já tem notas; escolha uma pasta vazia")
    for origem in MODELO.rglob("*"):
        if origem.is_dir() or "__pycache__" in origem.parts:
            continue
        relativo = Path(*[(".claude" if p == "_claude" else p) for p in origem.relative_to(MODELO).parts])
        alvo = destino / relativo
        alvo.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origem, alvo)
    if humano.lower() != "arthur":
        _trocar_humano(destino, humano)
    (destino / ".rascunhos").mkdir(exist_ok=True)
    (destino / ".gitignore").write_text(".rascunhos/\n.obsidian/workspace*.json\n.trash/\nsite/\n", encoding="utf-8")
    return destino


def _trocar_humano(destino: Path, humano: str) -> None:
    """Troca o nome de quem recebe as decisões nas notas e no arquivo da Caixa (use CEREBRO_HUMANO ao rodar)."""
    nome = humano.strip().lower()
    for arquivo in destino.rglob("*.md"):
        texto = arquivo.read_text(encoding="utf-8")
        novo = texto.replace("Caixa do Arthur", f"Caixa do {humano.title()}").replace("`arthur`", f"`{nome}`") \
                    .replace("o Arthur", f"o(a) {humano.title()}").replace("Arthur", humano.title())
        if novo != texto:
            arquivo.write_text(novo, encoding="utf-8")
    velha = destino / "Caixa do Arthur.md"
    if velha.exists():
        velha.rename(destino / f"Caixa do {humano.title()}.md")
