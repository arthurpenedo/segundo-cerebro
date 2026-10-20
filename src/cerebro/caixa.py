"""Caixa do Arthur: uma voz só para o humano.

No fim de cada ciclo:
1. os recados abertos para o Arthur são agrupados por pedido (campo `pedido`, ou o início da conversa);
2. em cada pedido fica aberto só o mais recente; os anteriores viram `substituido`, com link para o novo;
3. a nota `Caixa do Arthur.md`, na raiz do cofre, lista o que falta ele decidir, por pedido.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .cofre import Nota, ler_cofre
from .mural import HUMANO, conversas, mudar_status, recados

NOTA = f"Caixa do {HUMANO.title()}.md"


def _pedido_de(notas: dict[str, Nota]) -> dict[str, str]:
    """nome do recado -> pedido. Sem o campo `pedido`, herda do fio de conversa (ou é o próprio início do fio)."""
    mapa: dict[str, str] = {}
    for fio in conversas(notas):
        pedido = next((str(r.meta["pedido"]).strip("[]") for r in fio if r.meta.get("pedido")), fio[0].nome)
        for r in fio:
            mapa[r.nome] = str(r.meta.get("pedido") or pedido).strip("[]")
    return mapa


def abertos_para_humano(notas: dict[str, Nota]) -> dict[str, list[Nota]]:
    pedido = _pedido_de(notas)
    grupos: dict[str, list[Nota]] = defaultdict(list)
    for r in recados(notas):
        if r.meta.get("status") == "aberto" and str(r.meta.get("para", "")).lower() == HUMANO:
            grupos[pedido.get(r.nome, r.nome)].append(r)
    return dict(grupos)


def consolidar(raiz: str | Path) -> int:
    """Deixa aberto só o recado mais recente para o Arthur em cada pedido. Devolve quantos foram substituídos."""
    raiz = Path(raiz)
    substituidos = 0
    for lista in abertos_para_humano(ler_cofre(raiz)).values():
        *antigos, atual = lista  # recados() já vem em ordem de criação
        for r in antigos:
            arquivo = raiz / r.caminho
            mudar_status(arquivo, "substituido")
            with arquivo.open("a", encoding="utf-8") as f:
                f.write(f"\nSubstituído por [[{atual.nome}]].\n")
            substituidos += 1
    return substituidos


def gerar_nota(raiz: str | Path) -> Path:
    raiz = Path(raiz)
    notas = ler_cofre(raiz)
    grupos = abertos_para_humano(notas)
    if grupos:
        blocos = []
        for pedido, lista in sorted(grupos.items(), key=lambda g: str(g[1][-1].meta.get("criado")), reverse=True):
            atual = lista[-1]
            titulo = f"[[{pedido}]]" if pedido.lower() in notas else pedido
            blocos.append(f"## {titulo}\n\n- **{atual.meta.get('assunto')}** · [[{atual.nome}|abrir recado]] "
                          f"· {atual.meta.get('criado')}")
        corpo = "\n\n".join(blocos)
    else:
        corpo = "Nada esperando por você. 🎉"
    destino = raiz / NOTA
    destino.write_text(f"""---
tipo: guia
---
# Caixa do Arthur

Só o [[Maestro]] escreve aqui, e só fica aberto o recado mais recente de cada pedido. Para responder,
mude o `status` do recado para `feito` (ou `recusado`) e, se quiser, escreva um pedido novo na [[Entrada]].

{corpo}
""", encoding="utf-8")
    return destino
