"""Leitura do cofre: cada nota .md vira uma Nota com metadados (frontmatter YAML) e links [[...]].

O cofre é só uma pasta de Markdown, exatamente o que o Obsidian abre. Nada aqui depende do
Obsidian estar instalado: agentes, testes e CI leem os mesmos arquivos.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Pastas que não são notas: código, configuração do Obsidian, saída do painel.
IGNORAR = {".git", ".obsidian", ".claude", ".github", "src", "tests", "site", "modelos", ".venv", "node_modules"}
ARQUIVOS_DO_SISTEMA = {"README.md", "CLAUDE.md", "LICENSE.md"}

_LINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
_FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.S)


@dataclass
class Nota:
    caminho: Path  # relativo à raiz do cofre
    meta: dict
    corpo: str
    links: list[str] = field(default_factory=list)

    @property
    def nome(self) -> str:
        return self.caminho.stem

    @property
    def pasta(self) -> str:
        return self.caminho.parts[0] if len(self.caminho.parts) > 1 else ""

    @property
    def tipo(self) -> str:
        return str(self.meta.get("tipo", "nota"))


def ler_nota(raiz: Path, arquivo: Path) -> Nota:
    texto = arquivo.read_text(encoding="utf-8")
    meta, corpo = {}, texto
    if m := _FRONTMATTER.match(texto):
        meta = yaml.safe_load(m.group(1)) or {}
        corpo = texto[m.end():]
    links = [alvo.strip().split("/")[-1] for alvo in _LINK.findall(corpo)]
    return Nota(arquivo.relative_to(raiz), meta, corpo, links)


def ler_cofre(raiz: str | Path) -> dict[str, Nota]:
    """Todas as notas do cofre, indexadas pelo nome em minúsculas (como o Obsidian resolve links)."""
    raiz = Path(raiz)
    notas: dict[str, Nota] = {}
    for arquivo in sorted(raiz.rglob("*.md")):
        relativo = arquivo.relative_to(raiz)
        if set(relativo.parts) & IGNORAR or (len(relativo.parts) == 1 and relativo.name in ARQUIVOS_DO_SISTEMA):
            continue
        nota = ler_nota(raiz, arquivo)
        notas[nota.nome.lower()] = nota
    return notas


def resolver(notas: dict[str, Nota], alvo: str) -> Nota | None:
    return notas.get(alvo.strip().lower())
