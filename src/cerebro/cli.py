"""Linha de comando usada pelos agentes (via Bash) e pelo CI.

    cerebro mural --para dev          # o que está esperando pelo agente
    cerebro recado --de dev --para carreira --assunto "..." --texto "..." [--responde NOME]
    cerebro fechar "Mural/2026-10-09 ... .md" [--status feito]
    cerebro validar                   # links, recados, agentes, dados sensíveis
    cerebro painel --html site/index.html
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import cofre, mural, painel, validar


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="cerebro")
    parser.add_argument("--cofre", default=".", help="raiz do cofre (padrão: pasta atual)")
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("mural", help="recados abertos")
    p.add_argument("--para", help="só os recados para este agente")
    p = sub.add_parser("recado", help="deixa um recado para outro agente")
    for campo in ("de", "para", "assunto", "texto"):
        p.add_argument(f"--{campo}", required=True)
    p.add_argument("--responde", help="nome do recado ao qual este responde")
    p = sub.add_parser("fechar", help="muda o status de um recado")
    p.add_argument("arquivo")
    p.add_argument("--status", default="feito", choices=mural.STATUS)
    sub.add_parser("validar", help="checa o cofre (usado no CI)")
    p = sub.add_parser("painel", help="gera o painel HTML")
    p.add_argument("--html", default="site/index.html")

    args = parser.parse_args(argv)
    raiz = Path(args.cofre)

    if args.comando == "recado":
        destino = mural.escrever_recado(raiz, args.de, args.para, args.assunto, args.texto, args.responde)
        print(destino.relative_to(raiz).as_posix())
        return 0
    if args.comando == "fechar":
        mural.mudar_status(raiz / args.arquivo if not Path(args.arquivo).is_absolute() else args.arquivo, args.status)
        print(f"{args.arquivo}: {args.status}")
        return 0

    notas = cofre.ler_cofre(raiz)
    if args.comando == "mural":
        lista = mural.abertos_para(notas, args.para) if args.para else \
            [r for r in mural.recados(notas) if r.meta.get("status") == "aberto"]
        for r in lista:
            print(f"- [{r.meta.get('de')} → {r.meta.get('para')}] {r.meta.get('assunto')}  ({r.caminho.as_posix()})")
        if not lista:
            print("Nenhum recado aberto.")
        return 0
    if args.comando == "validar":
        problemas = validar.validar(notas)
        for p in problemas:
            print(f"✗ {p}")
        print(f"{len(notas)} notas, {len(mural.recados(notas))} recados, {len(problemas)} problemas")
        return 1 if problemas else 0
    if args.comando == "painel":
        destino = Path(args.html)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(painel.gerar(notas), encoding="utf-8")
        print(f"Painel salvo em {destino}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
