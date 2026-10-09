"""Painel HTML do cofre (publicado no GitHub Pages): agentes, conversas do Mural e o grafo de notas."""

from __future__ import annotations

import html
import json
import re
from collections import Counter
from datetime import date

from .cofre import Nota, resolver
from .caixa import abertos_para_humano
from .mural import agentes, conversas, recados

CORES = {"Agentes": "#7c5cff", "Mural": "#f08c2e", "Projetos": "#2f9e6e", "Carreira": "#4c8dd5",
         "Conhecimento": "#d5487c", "Diario": "#9a9aa6", "00-Entrada": "#c9a227"}

_CSS = """
:root{--fundo:#f6f6f8;--cartao:#fff;--texto:#1d1d22;--suave:#5f5f6a;--borda:#e2e2e8;--destaque:#7c5cff}
@media (prefers-color-scheme:dark){:root{--fundo:#121216;--cartao:#1b1b21;--texto:#ececf1;--suave:#a3a3ae;--borda:#2c2c35}}
*{box-sizing:border-box}body{margin:0;background:var(--fundo);color:var(--texto);font:15px/1.55 system-ui,Segoe UI,Roboto,sans-serif}
main{max-width:1100px;margin:0 auto;padding:32px 16px 64px}h1{font-size:28px;margin:0 0 4px}h2{font-size:20px;margin:40px 0 12px}
.sub{color:var(--suave);margin:0 0 20px}.grade{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px}
.cartao{background:var(--cartao);border:1px solid var(--borda);border-radius:12px;padding:14px 16px}
.cartao h3{margin:0 0 4px;font-size:16px}.det{font-size:13px;color:var(--suave)}
.num{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}.num div{background:var(--cartao);border:1px solid var(--borda);
border-radius:12px;padding:10px 16px}.num b{display:block;font-size:24px}
.fio{background:var(--cartao);border:1px solid var(--borda);border-radius:12px;padding:6px 16px;margin-bottom:14px}
.msg{border-left:3px solid var(--borda);padding:6px 0 6px 12px;margin:12px 0}.msg .quem{font-weight:600}
.msg .corpo{white-space:pre-wrap;margin-top:4px}.etq{font-size:12px;border-radius:999px;padding:1px 8px;margin-left:6px;
border:1px solid var(--borda)}.aberto{color:#c46a00}.feito{color:#2f9e6e}.recusado{color:#c0392b}.substituido{color:#888;text-decoration:line-through}.caixa{border-left:4px solid var(--destaque)}
.link{color:var(--destaque);font-weight:500}#grafo{width:100%;height:520px;background:var(--cartao);
border:1px solid var(--borda);border-radius:12px}.leg span{display:inline-block;margin-right:14px;font-size:13px}
.leg i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px}
footer{margin-top:48px;color:var(--suave);font-size:13px}a{color:var(--destaque)}
"""


def _texto(corpo: str) -> str:
    corpo = re.sub(r"^# .*\n+", "", corpo.strip())
    corpo = re.sub(r"\nEm resposta a \[\[[^\]]+\]\]\.\s*$", "", corpo)
    seguro = html.escape(corpo)
    return re.sub(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", lambda m: f"<span class='link'>{m.group(2) or m.group(1)}</span>", seguro)


def _grafo(notas: dict[str, Nota]) -> dict:
    nos = [{"id": n.nome, "grupo": n.pasta or "raiz", "cor": CORES.get(n.pasta, "#888")} for n in notas.values()]
    arestas = []
    for n in notas.values():
        for alvo in set(n.links):
            if (destino := resolver(notas, alvo)) and destino.nome != n.nome:
                arestas.append({"source": n.nome, "target": destino.nome})
    return {"nodes": nos, "links": arestas}


def gerar(notas: dict[str, Nota], titulo: str = "segundo-cerebro") -> str:
    todos_recados = recados(notas)
    status = Counter(str(r.meta.get("status")) for r in todos_recados)
    por_agente = Counter(str(r.meta.get("de")) for r in todos_recados)

    cartoes = ""
    for id_, a in sorted(agentes(notas).items()):
        abertos = sum(1 for r in todos_recados if str(r.meta.get("para")).lower() == id_ and r.meta.get("status") == "aberto")
        cartoes += (f"<div class='cartao'><h3>{html.escape(str(a.meta.get('nome', id_)))}</h3>"
                    f"<div>{html.escape(str(a.meta.get('papel', '')))}</div>"
                    f"<div class='det'>escreve em: {html.escape(', '.join(a.meta.get('escreve_em', [])))}</div>"
                    f"<div class='det'>{por_agente.get(id_, 0)} recados enviados · {abertos} esperando por ele</div></div>")

    fios = ""
    for fio in sorted(conversas(notas), key=lambda f: str(f[-1].meta.get("criado", "")), reverse=True):
        msgs = "".join(
            f"<div class='msg'><span class='quem'>{html.escape(str(r.meta.get('de')))} → {html.escape(str(r.meta.get('para')))}</span>"
            f"<span class='etq {html.escape(str(r.meta.get('status')))}'>{html.escape(str(r.meta.get('status')))}</span>"
            f"<span class='det'> · {html.escape(str(r.meta.get('criado')))}</span>"
            f"<div class='corpo'>{_texto(r.corpo)}</div></div>" for r in fio)
        fios += f"<div class='fio'><h3>{html.escape(str(fio[0].meta.get('assunto', fio[0].nome)))}</h3>{msgs}</div>"

    pendentes = abertos_para_humano(notas)
    caixa_html = "".join(
        f"<div class='cartao caixa'><div class='det'>pedido: {html.escape(pedido)}</div>"
        f"<h3>{html.escape(str(lista[-1].meta.get('assunto')))}</h3><div class='corpo'>{_texto(lista[-1].corpo)}</div></div>"
        for pedido, lista in sorted(pendentes.items(), key=lambda g: str(g[1][-1].meta.get("criado")), reverse=True)) or "<p class='det'>Nada esperando pelo Arthur.</p>"

    legenda = "".join(f"<span><i style='background:{c}'></i>{p}</span>" for p, c in CORES.items())
    dados = json.dumps(_grafo(notas), ensure_ascii=False)

    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Segundo cérebro · painel</title>
<style>{_CSS}</style></head><body><main>
<h1>{html.escape(titulo)} · painel</h1>
<p class="sub">Um cofre do Obsidian onde agentes de IA trabalham e conversam por recados. Gerado a partir das notas em {date.today():%d/%m/%Y}.</p>
<div class="num"><div><b>{len(notas)}</b>notas</div><div><b>{len(agentes(notas))}</b>agentes</div>
<div><b>{len(todos_recados)}</b>recados</div><div><b>{status.get('aberto', 0)}</b>abertos</div><div><b>{status.get('feito', 0)}</b>resolvidos</div></div>
<h2>Esperando pelo Arthur</h2><p class="sub">Só o Maestro fala com o humano, e só o recado mais recente de cada pedido fica aberto.</p>
<div class="grade">{caixa_html}</div>
<h2>Agentes</h2><div class="grade">{cartoes}</div>
<h2>Grafo do cofre</h2><p class="sub">Cada ponto é uma nota; cada linha, um link [[...]]. Arraste para explorar.</p>
<div class="leg">{legenda}</div><svg id="grafo"></svg>
<h2>Conversas no Mural</h2><p class="sub">Os agentes não se chamam diretamente: deixam recados uns para os outros, e cada um lê os seus ao começar.</p>
{fios or "<p class='det'>Nenhum recado ainda.</p>"}
<footer>Gerado pelo <a href="https://github.com/arthurpenedo/segundo-cerebro">segundo-cerebro</a>.</footer>
</main>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"></script>
<script>
const dados = {dados};
const svg = d3.select("#grafo"), w = svg.node().clientWidth, h = 520;
const sim = d3.forceSimulation(dados.nodes).force("link", d3.forceLink(dados.links).id(d => d.id).distance(60))
  .force("charge", d3.forceManyBody().strength(-120)).force("center", d3.forceCenter(w / 2, h / 2)).force("collide", d3.forceCollide(14));
const g = svg.append("g");
svg.call(d3.zoom().scaleExtent([0.3, 3]).on("zoom", e => g.attr("transform", e.transform)));
const linha = g.append("g").attr("stroke", "#9995").selectAll("line").data(dados.links).join("line");
const no = g.append("g").selectAll("g").data(dados.nodes).join("g").call(d3.drag()
  .on("start", (e, d) => {{ if (!e.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; }})
  .on("drag", (e, d) => {{ d.fx = e.x; d.fy = e.y; }})
  .on("end", (e, d) => {{ if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }}));
no.append("circle").attr("r", d => 4 + Math.min(8, dados.links.filter(l => l.target === d || l.target.id === d.id).length)).attr("fill", d => d.cor);
no.append("text").text(d => d.id.length > 28 ? d.id.slice(0, 27) + "…" : d.id).attr("x", 10).attr("y", 4)
  .attr("font-size", 10).attr("fill", "currentColor").attr("opacity", 0.75);
sim.on("tick", () => {{
  linha.attr("x1", d => d.source.x).attr("y1", d => d.source.y).attr("x2", d => d.target.x).attr("y2", d => d.target.y);
  no.attr("transform", d => `translate(${{d.x}},${{d.y}})`);
}});
</script></body></html>"""
