"""Linha de comando usada pelos agentes (via Bash) e pelo CI.

    cerebro mural --para dev          # o que está esperando pelo agente
    cerebro recado --de dev --para carreira --assunto "..." --texto "..." [--responde NOME]
    cerebro fechar "Mural/2026-10-09 ... .md" [--status feito]
    cerebro validar                   # links, recados, agentes, dados sensíveis
    cerebro painel --html site/index.html
    cerebro rodar [--max-turnos 15] [--modelo sonnet]   # laço automático com o Claude Code
    cerebro caixa                     # junta os recados para o Arthur e atualiza a Caixa do Arthur
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import caixa, cofre, mural, painel, validar


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="cerebro")
    parser.add_argument("--cofre", default=".", help="raiz do cofre (padrão: pasta atual)")
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("mural", help="recados abertos")
    p.add_argument("--para", help="só os recados para este agente")
    p = sub.add_parser("recado", help="deixa um recado para outro agente")
    for campo in ("de", "para", "assunto"):
        p.add_argument(f"--{campo}", required=True)
    texto = p.add_mutually_exclusive_group(required=True)
    texto.add_argument("--texto")
    texto.add_argument("--texto-arquivo", help="lê o texto de um arquivo (melhor para textos longos)")
    p.add_argument("--responde", help="nome do recado ao qual este responde")
    p.add_argument("--pedido", help="nota da Entrada que originou a conversa (herdado de --responde)")
    p = sub.add_parser("fechar", help="muda o status de um recado")
    p.add_argument("arquivo")
    p.add_argument("--status", default="feito", choices=mural.STATUS)
    sub.add_parser("validar", help="checa o cofre (usado no CI)")
    sub.add_parser("caixa", help="junta os recados para o Arthur por pedido e atualiza a nota da caixa")
    p = sub.add_parser("painel", help="gera o painel HTML")
    p.add_argument("--html", default="site/index.html")
    p = sub.add_parser("rodar", help="acorda os agentes enquanto houver recado aberto")
    p.add_argument("--max-turnos", type=int, default=15)
    p.add_argument("--modelo", default="sonnet")
    p.add_argument("--sem-diario", action="store_true")

    args = parser.parse_args(argv)
    raiz = Path(args.cofre)

    if args.comando == "recado":
        texto = args.texto if args.texto is not None else (raiz / args.texto_arquivo).read_text(encoding="utf-8-sig")
        try:
            destino = mural.escrever_recado(raiz, args.de, args.para, args.assunto, texto, args.responde,
                                            pedido=args.pedido)
        except mural.RecadoRecusado as erro:
            print(f"✗ recado não escrito: {erro}")
            return 1
        print(destino.relative_to(raiz).as_posix())
        return 0
    if args.comando == "fechar":
        try:
            arquivo = mural.localizar(raiz, args.arquivo)
            mural.mudar_status(arquivo, args.status)
        except (FileNotFoundError, ValueError) as erro:
            print(f"✗ {erro}")
            return 1
        print(f"{arquivo.relative_to(raiz).as_posix()}: {args.status}")
        return 0

    if args.comando == "rodar":
        from . import orquestrador

        execucao = orquestrador.rodar(raiz, orquestrador.executor_claude(args.modelo), args.max_turnos,
                                      diario=not args.sem_diario)
        return 0 if execucao.parou_por == orquestrador.CICLO_COMPLETO else 1

    if args.comando == "caixa":
        n = caixa.consolidar(raiz)
        destino = caixa.gerar_nota(raiz)
        print(f"{n} recado(s) substituído(s); caixa em {destino.name}")
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
