"""Linha de comando usada pelos agentes (via Bash) e pelo CI.

    cerebro mural --para dev          # o que está esperando pelo agente
    cerebro recado --de dev --para carreira --assunto "..." --texto "..." [--responde NOME]
    cerebro fechar "Mural/2026-10-09 ... .md" [--status feito]
    cerebro validar                   # links, recados, agentes, dados sensíveis
    cerebro painel --html site/index.html
    cerebro rodar [--max-turnos 15] [--modelo sonnet]   # laço automático com o Claude Code
    cerebro caixa                     # junta os recados para o Arthur e atualiza a Caixa do Arthur
    cerebro hoje                      # dia a dia: gera Hoje.md a partir de Tarefas.md e Para o Claude.md
    cerebro rotina                    # dia a dia: o assistente faz a fila "Para o Claude" sozinho
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import caixa, cofre, mural, painel, validar


def _opcoes_motor(p, padrao: str = "claude") -> None:
    p.add_argument("--motor", choices=["claude", "ollama", "openai"], default=padrao,
                   help="claude = Claude Code da máquina; ollama/openai = motor próprio com tool calling")
    p.add_argument("--url", default=None, help="URL base compatível com a OpenAI (padrão do ollama: http://localhost:11434/v1)")


def _cliente(args, modelo: str):
    import os

    from .llm import ClienteOpenAI

    if args.motor == "openai":
        return ClienteOpenAI(modelo, url_base=args.url or "https://api.openai.com/v1", chave=os.getenv("OPENAI_API_KEY"))
    return ClienteOpenAI(modelo, url_base=args.url or "http://localhost:11434/v1")


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
    sub.add_parser("hoje", help="gera a nota Hoje a partir das tarefas e da fila do Claude")
    p = sub.add_parser("aprendi", help="registra um aprendizado no cofre (diário + manual do tema)")
    p.add_argument("texto")
    p.add_argument("--tema")
    p = sub.add_parser("arte", help="gera a imagem vertical do post a partir do rascunho")
    p.add_argument("post")
    p = sub.add_parser("agendar", help="põe um projeto no próximo dia livre do calendário de publicação")
    p.add_argument("nome")
    p = sub.add_parser("rotina", help="o assistente executa sozinho a fila 'Para o Claude' e atualiza Hoje")
    p.add_argument("--modelo", default="sonnet")
    p.add_argument("--projetos", help="pasta onde a rotina pode criar projetos (commit local)")
    p.add_argument("--publicar", action="store_true",
                   help="o motor faz push dos projetos alterados (só com testes passando e sem segredo no diff)")
    p.add_argument("--ignorar", default="", help="projetos que a rotina nunca publica, separados por vírgula")
    p = sub.add_parser("painel", help="gera o painel HTML")
    p.add_argument("--html", default="site/index.html")
    p = sub.add_parser("rodar", help="acorda os agentes enquanto houver recado aberto")
    p.add_argument("--max-turnos", type=int, default=15)
    p.add_argument("--modelo", default=None, help="claude: sonnet/opus; ollama/openai: nome do modelo (ex.: qwen2.5:3b)")
    p.add_argument("--sem-diario", action="store_true")
    _opcoes_motor(p)
    p = sub.add_parser("turno", help="acorda um agente uma vez (motor próprio)")
    p.add_argument("agente")
    p.add_argument("--motivo", default="pedido manual")
    p.add_argument("--modelo", default="qwen2.5:3b")
    p.add_argument("--max-passos", type=int, default=12)
    _opcoes_motor(p, padrao="ollama")
    p = sub.add_parser("buscar", help="busca notas do cofre (BM25)")
    p.add_argument("consulta")
    p.add_argument("--pasta")
    p.add_argument("--limite", type=int, default=5)
    p = sub.add_parser("avaliar", help="roda os cenários da equipe com um modelo de verdade e salva as métricas")
    p.add_argument("--modelo", default="qwen2.5:3b")
    p.add_argument("--saida", default="resultados/avaliacao.json")
    p.add_argument("--cenario", action="append", help="rodar só estes cenários (id); pode repetir")
    p.add_argument("--max-turnos", type=int, default=14)
    _opcoes_motor(p, padrao="ollama")
    sub.add_parser("mcp", help="servidor MCP (stdio) para o Claude Desktop/Code ler e escrever no cofre")
    p = sub.add_parser("init", help="cria um cofre novo com os 9 agentes, pronto para abrir no Obsidian")
    p.add_argument("destino")
    p.add_argument("--humano", default="arthur", help="id de quem recebe as decisões (padrão: arthur)")

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

        if args.motor == "claude":
            executor = orquestrador.executor_claude(args.modelo or "sonnet")
        else:
            executor = orquestrador.ExecutorLLM(_cliente(args, args.modelo or "qwen2.5:3b"))
        execucao = orquestrador.rodar(raiz, executor, args.max_turnos, diario=not args.sem_diario)
        return 0 if execucao.parou_por == orquestrador.CICLO_COMPLETO else 1

    if args.comando == "turno":
        from .agente import rodar_turno

        r = rodar_turno(raiz, args.agente, args.motivo, _cliente(args, args.modelo), args.max_passos)
        for reg in r.registros:
            print(f"  {'✓' if reg.ok else '✗'} {reg.ferramenta}({', '.join(f'{k}={str(v)[:40]}' for k, v in reg.argumentos.items())})")
        print(f"{r.agente}: {r.resposta}  [{r.passos} passos, {r.recusas} recusas, {r.segundos:.0f} s]")
        return 0
    if args.comando == "avaliar":
        from . import avaliacao

        cenarios = [c for c in avaliacao.carregar_cenarios() if not args.cenario or c["id"] in args.cenario]
        relatorio = avaliacao.avaliar(_cliente(args, args.modelo), cenarios, args.max_turnos, parcial=raiz / args.saida)
        destino = avaliacao.salvar(relatorio, raiz / args.saida)
        r = relatorio["resumo"]
        print(f"{r['aprovados']}/{r['cenarios']} cenários aprovados · entregou {r['entregou']:.0%} · "
              f"checagens {r['checagens']:.0%} · {r['recusas_total']} recusas · salvo em {destino}")
        return 0
    if args.comando == "mcp":
        from .servidor_mcp import main as mcp_main

        mcp_main(raiz)
        return 0
    if args.comando == "init":
        from .init import criar_cofre

        destino = criar_cofre(args.destino, humano=args.humano)
        print(f"Cofre criado em {destino}. Abra a pasta no Obsidian e rode `cerebro validar` dentro dela.")
        return 0

    if args.comando == "aprendi":
        from .aprendizado import aprendi

        for p in aprendi(raiz, args.texto, args.tema):
            print(p.relative_to(raiz).as_posix())
        return 0
    if args.comando == "arte":
        from .arte import gerar_arte

        print(gerar_arte(args.post))
        return 0
    if args.comando in ("hoje", "rotina", "agendar"):
        from . import dia

        if args.comando == "agendar":
            print(f"{args.nome}: {dia.agendar(raiz, args.nome):%d/%m/%Y}")
            dia.gerar_hoje(raiz)
            return 0
        if args.comando == "hoje":
            print(f"Atualizado: {dia.gerar_hoje(raiz).name}")
        else:
            print(dia.rodar_rotina(raiz, modelo=args.modelo, projetos=args.projetos, publicar=args.publicar,
                                   ignorar={n.strip() for n in args.ignorar.split(",") if n.strip()}))
        return 0
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
    if args.comando == "buscar":
        from .busca import Indice

        achados = Indice(notas).buscar(args.consulta, args.limite, args.pasta)
        for r in achados:
            print(f"{r.pontos:6.2f}  {r.nota.caminho.as_posix()}\n        {r.trecho}")
        if not achados:
            print("Nada encontrado.")
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
        import json

        avaliacoes = [json.loads(a.read_text(encoding="utf-8")) for a in sorted((raiz / "resultados").glob("*.json"))]
        destino.write_text(painel.gerar(notas, avaliacoes=avaliacoes), encoding="utf-8")
        print(f"Painel salvo em {destino}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
