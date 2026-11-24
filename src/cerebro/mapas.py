"""Notas-mapa: uma por pasta do cofre, ligando todas as notas dela, e uma seção "Mapas" no Inicio.md.

Pedido do Arthur (24/11/2026): o grafo do Obsidian não pode ter nota solta. Roda todo dia na rotina, por script
(custo de uso praticamente zero).
"""
from __future__ import annotations

import re
from pathlib import Path

PULAR = {"Mapas", ".obsidian", ".trash", ".git", ".rascunhos"}
RECENTES_PRIMEIRO = {"Diario", "Atividades", "Aprendizados"}
DESCRICOES = {
    "Vagas": "candidaturas, rotinas e preparação para entrevistas", "Diario": "o que foi feito em cada dia",
    "Estudos": "trilha de estudos", "Memoria": "memória do Claude (editável pelo Obsidian)",
    "Rascunhos": "textos em andamento", "Aprendizados": "aprendizados registrados dia a dia",
    "Manual": "passo a passo que cresce com cada aprendizado", "Projetos": "projetos em andamento",
    "Atividades": "cada atividade feita vira um ponto", "Ideias": "ideias guardadas",
    "Curriculos": "currículos e perfis nos sites", "Raiz": "notas principais do cofre",
}
INICIO_SECAO = re.compile(r"\n## Mapas\n.*?(?=\n## |\Z)", re.S)


def _mapa(destino: Path, nome: str, notas: list[Path], inicio: str) -> None:
    desc = DESCRICOES.get(nome, f"notas da pasta {nome}")
    linhas = ["---\ntipo: mapa\n---", f"# Mapa: {nome}", "",
              f"{desc[0].upper() + desc[1:]}. Voltar ao [[{inicio}]]. Gerado sozinho pela rotina (`cerebro mapas`).", "",
              f"{len(notas)} notas:", ""]
    linhas += [f"- [[{p.stem}]]" for p in notas]
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")


def gerar_mapas(raiz: str | Path, inicio: str = "Inicio") -> list[Path]:
    raiz = Path(raiz)
    pasta_mapas = raiz / "Mapas"
    pasta_mapas.mkdir(exist_ok=True)
    feitos = []
    pastas = sorted(p for p in raiz.iterdir() if p.is_dir() and p.name not in PULAR and not p.name.startswith("."))
    for pasta in pastas:
        notas = sorted(pasta.rglob("*.md"), reverse=pasta.name in RECENTES_PRIMEIRO)
        if not notas:
            continue
        destino = pasta_mapas / f"Mapa - {pasta.name}.md"
        _mapa(destino, pasta.name, notas, inicio)
        feitos.append(destino)
    raiz_notas = sorted(p for p in raiz.glob("*.md") if p.stem != inicio)
    if raiz_notas:
        destino = pasta_mapas / "Mapa - Raiz.md"
        _mapa(destino, "Raiz", raiz_notas, inicio)
        feitos.append(destino)
    for velho in pasta_mapas.glob("Mapa - *.md"):
        if velho not in feitos:
            velho.unlink()
    arq_inicio = raiz / f"{inicio}.md"
    texto = arq_inicio.read_text(encoding="utf-8") if arq_inicio.exists() else f"# {inicio}\n"
    secao = "\n## Mapas\n" + "\n".join(f"- [[{p.stem}]]" for p in feitos) + "\n"
    texto = INICIO_SECAO.sub("", texto).rstrip("\n") + "\n" + secao
    arq_inicio.write_text(texto, encoding="utf-8")
    return feitos
