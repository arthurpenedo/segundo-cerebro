"""Servidor MCP: o cliente (Claude Desktop/Code) busca, lê, faz pedidos e decide, sem furar as regras do cofre."""

import asyncio
import json

import pytest

pytest.importorskip("mcp")

from mcp.client import Client  # noqa: E402

from cerebro import mural  # noqa: E402
from cerebro.cofre import ler_cofre  # noqa: E402
from cerebro.init import criar_cofre  # noqa: E402
from cerebro.servidor_mcp import construir  # noqa: E402


def _dados(resultado):
    texto = resultado.content[0].text
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        return texto


def test_mcp_fluxo_do_humano(tmp_path):
    cofre = criar_cofre(tmp_path / "c")
    (cofre / "Conhecimento" / "RAG.md").write_text("# RAG\n\nBusca + geração com fonte.", encoding="utf-8")
    recado = mural.escrever_recado(cofre, "maestro", "arthur", "Post pronto", "Aprova?").stem

    async def rodar():
        async with Client(construir(cofre)) as c:
            nomes = {t.name for t in (await c.list_tools()).tools}
            busca = await c.call_tool("buscar_notas", {"consulta": "rag"})
            nota = await c.call_tool("ler_nota", {"nome": "RAG"})
            caixa = await c.call_tool("caixa_de_decisoes", {})
            pedido = await c.call_tool("fazer_pedido", {"titulo": "Resumo da semana", "pedido": "Faça o resumo"})
            ruim = await c.call_tool("fazer_pedido", {"titulo": "Cliente", "pedido": "CPF 123.456.789-09"})
            decisao = await c.call_tool("decidir", {"recado": recado, "decisao": "aprovado", "comentario": "pode postar"})
            outro = await c.call_tool("decidir", {"recado": "Mural", "decisao": "aprovado"})
            recurso = (await c.read_resource("cerebro://caixa")).contents[0].text
            validacao = await c.call_tool("validar_cofre", {})
            return nomes, busca, nota, caixa, pedido, ruim, decisao, outro, recurso, validacao

    nomes, busca, nota, caixa, pedido, ruim, decisao, outro, recurso, validacao = asyncio.run(rodar())
    assert {"buscar_notas", "ler_nota", "mural_aberto", "caixa_de_decisoes", "fazer_pedido", "decidir", "validar_cofre"} <= nomes
    assert "RAG" in busca.content[0].text
    assert "Busca + geração" in str(_dados(nota))
    assert "Post pronto" in str(_dados(caixa))
    assert (cofre / "00-Entrada" / "Resumo da semana.md").is_file() and "Pedido criado" in str(_dados(pedido))
    assert ruim.is_error and "CPF" in ruim.content[0].text
    assert "aprovado" in str(_dados(decisao))
    assert ler_cofre(cofre)[recado.lower()].meta["status"] == "feito"
    assert list((cofre / "00-Entrada").glob("Retorno sobre*.md")), "o comentário vira pedido para o maestro"
    assert outro.is_error
    assert "Nada esperando decisão" in recurso
    assert _dados(validacao)["problemas"] == []
