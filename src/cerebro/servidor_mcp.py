"""Servidor MCP do segundo-cerebro: o Claude Desktop ou o Claude Code conversam com o cofre como o humano.

    cerebro --cofre <pasta> mcp        # stdio

O cliente MCP fala no lugar de quem recebe as decisões (o humano, `arthur` por padrão): busca e lê notas,
vê o Mural e a Caixa de decisões, faz pedidos novos para a equipe (uma nota em 00-Entrada, que acorda o
maestro no próximo `cerebro rodar`) e responde às decisões pendentes. Ele não escreve como agente nem
publica nada: as mesmas regras do cofre continuam valendo.

Primitivas expostas:
- tools: buscar_notas, ler_nota, mural, caixa_de_decisoes, fazer_pedido, decidir, validar_cofre;
- resource `cerebro://caixa`: a Caixa de decisões em Markdown;
- prompt `revisar_caixa`: roteiro para o modelo ajudar o humano a decidir os recados pendentes.
"""

from __future__ import annotations

import functools
import re
from datetime import datetime
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import caixa, mural, validar
from .busca import Indice
from .cofre import ler_cofre, resolver
from .validar import _SENSIVEL

INSTRUCOES = """Ferramentas de um segundo cérebro (cofre do Obsidian) onde 9 agentes de IA trabalham por recados.
Você age no lugar do humano dono do cofre. Para saber algo, use buscar_notas e ler_nota.
Para pedir trabalho à equipe, use fazer_pedido (o maestro distribui). Para ver o que espera decisão,
use caixa_de_decisoes; para responder, use decidir. Nunca grave dado pessoal: o cofre pode ser público."""


def _erros_para_o_modelo(fn):
    @functools.wraps(fn)
    def embrulho(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (ValueError, KeyError, FileNotFoundError) as e:
            raise ToolError(str(e.args[0]) if e.args else str(e)) from e
    return embrulho


def _pendentes(raiz: Path) -> list:
    """Recados abertos para o humano, de todos os pedidos (a caixa vem agrupada por pedido)."""
    return [r for grupo in caixa.abertos_para_humano(ler_cofre(raiz)).values() for r in grupo]


def construir(raiz: str | Path) -> MCPServer:
    raiz = Path(raiz)
    servidor = MCPServer("segundo-cerebro", instructions=INSTRUCOES)

    def ferramenta():
        return lambda fn: servidor.tool()(_erros_para_o_modelo(fn))

    @ferramenta()
    def buscar_notas(consulta: str, pasta: str | None = None, limite: int = 5) -> list[dict]:
        """Busca notas do cofre por relevância (BM25). Devolve nome, pasta, pontuação e um trecho."""
        return [{"nota": r.nota.nome, "pasta": r.nota.pasta, "pontos": r.pontos, "trecho": r.trecho}
                for r in Indice(ler_cofre(raiz)).buscar(consulta, limite, pasta)]

    @ferramenta()
    def ler_nota(nome: str) -> dict:
        """Lê uma nota pelo nome (como em [[nome]]): metadados, texto e links."""
        nota = resolver(ler_cofre(raiz), nome.strip("[] "))
        if nota is None:
            raise ValueError(f"não existe nota '{nome}'; use buscar_notas")
        return {"nota": nota.nome, "caminho": nota.caminho.as_posix(), "meta": {k: str(v) for k, v in nota.meta.items()},
                "texto": nota.corpo.strip()[:12000], "links": nota.links}

    @ferramenta()
    def mural_aberto(para: str | None = None) -> list[dict]:
        """Recados abertos no Mural (de todos, ou só os de um agente)."""
        notas = ler_cofre(raiz)
        lista = mural.abertos_para(notas, para) if para else \
            [r for r in mural.recados(notas) if r.meta.get("status") == "aberto"]
        return [{"recado": r.nome, "de": r.meta.get("de"), "para": r.meta.get("para"), "assunto": r.meta.get("assunto"),
                 "pedido": r.meta.get("pedido")} for r in lista]

    @ferramenta()
    def caixa_de_decisoes() -> list[dict]:
        """O que espera decisão do humano: o recado mais recente de cada pedido, com o texto."""
        return [{"recado": r.nome, "assunto": r.meta.get("assunto"), "pedido": r.meta.get("pedido"),
                 "texto": r.corpo.strip()[:4000]} for r in _pendentes(raiz)]

    @ferramenta()
    def fazer_pedido(titulo: str, pedido: str) -> str:
        """Cria um pedido para a equipe em 00-Entrada. O maestro distribui no próximo `cerebro rodar`."""
        for nome, padrao in _SENSIVEL.items():
            if padrao.search(pedido):
                raise ValueError(f"o pedido parece conter {nome}; o cofre pode ser público")
        nome = re.sub(r'[\\/:*?"<>|\[\]#^]+', " ", titulo).strip()[:80]
        if not nome:
            raise ValueError("título vazio")
        destino = raiz / "00-Entrada" / f"{nome}.md"
        if destino.exists():
            raise ValueError(f"já existe um pedido '{nome}'")
        destino.parent.mkdir(exist_ok=True)
        destino.write_text(f"---\ntipo: pedido\ncriado: {datetime.now():%Y-%m-%d %H:%M}\n---\n# {nome}\n\n{pedido.strip()}\n",
                           encoding="utf-8")
        return f"Pedido criado: 00-Entrada/{nome}.md. Rode `cerebro rodar` para a equipe trabalhar."

    @ferramenta()
    def decidir(recado: str, decisao: str, comentario: str = "") -> str:
        """Responde a um recado da Caixa: decisao = 'aprovado' (feito) ou 'recusado'. O comentário vai para o maestro."""
        if decisao not in ("aprovado", "recusado"):
            raise ValueError("decisao deve ser 'aprovado' ou 'recusado'")
        arquivo = mural.localizar(raiz, recado)
        nota = resolver(ler_cofre(raiz), arquivo.stem)
        humano = mural.HUMANO
        if nota is None or str(nota.meta.get("para", "")).lower() != humano:
            raise ValueError(f"só dá para decidir recados endereçados a {humano}")
        mural.mudar_status(arquivo, "feito" if decisao == "aprovado" else "recusado")
        if comentario.strip():
            # Comentário do humano vira nota na Entrada: o maestro lê e age, sem o humano escrever no Mural.
            fazer_pedido(f"Retorno sobre {arquivo.stem[:60]}", f"Decisão: {decisao}. {comentario}\n\nSobre [[{arquivo.stem}]].")
        return f"{arquivo.stem}: {decisao}"

    @ferramenta()
    def validar_cofre() -> dict:
        """Roda as checagens do cofre (links, recados, agentes, dados sensíveis)."""
        notas = ler_cofre(raiz)
        problemas = validar.validar(notas)
        return {"notas": len(notas), "recados": len(mural.recados(notas)), "problemas": [str(p) for p in problemas]}

    @servidor.resource("cerebro://caixa", name="caixa", mime_type="text/markdown",
                       description="A Caixa de decisões: o que a equipe preparou e espera aprovação.")
    def recurso_caixa() -> str:
        itens = _pendentes(raiz)
        if not itens:
            return "# Caixa de decisões\n\nNada esperando decisão."
        return "# Caixa de decisões\n\n" + "\n\n".join(
            f"## {r.meta.get('assunto')}\n_{r.nome}_\n\n{r.corpo.strip()}" for r in itens)

    @servidor.prompt(title="Revisar a Caixa de decisões")
    def revisar_caixa() -> str:
        """Ajuda a decidir os recados que a equipe deixou para o humano."""
        return ("Leia a Caixa de decisões abaixo. Para cada item: resuma em uma frase, aponte qualquer número sem fonte "
                "ou risco, e recomende aprovar ou recusar com o motivo. Não decida sozinho: espere a minha resposta "
                "e só então use `decidir`.\n\n" + recurso_caixa())

    return servidor


def main(raiz: str | Path = ".") -> None:
    construir(raiz).run("stdio")
