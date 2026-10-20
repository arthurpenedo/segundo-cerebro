"""Avaliação da equipe de agentes com um modelo de verdade (ex.: Ollama no CI, custo zero).

Cada cenário cria um cofre novo com `cerebro init`, põe um pedido na Entrada e roda o laço com o motor
próprio. Depois mede o que importa num sistema multiagente supervisionado:

- **entregou:** o pedido terminou num recado do maestro para o humano, ligado ao pedido;
- **ciclo completo:** o laço parou porque não havia mais trabalho (e não por limite ou agente travado);
- **cofre íntegro:** `validar` não encontrou problema (link quebrado, recado malformado, dado sensível);
- **checagens do cenário:** notas que deviam existir, palavras que a entrega devia citar;
- **custo do processo:** turnos, recusas das regras (tentativas barradas no código), tokens e tempo.

Saída: um JSON por modelo, lido pelo painel.

    cerebro avaliar --modelo qwen2.5:3b --saida resultados/qwen2.5-3b.json
"""

from __future__ import annotations

import json
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

from . import mural, orquestrador
from .cofre import ler_cofre
from .init import criar_cofre
from .llm import LLM
from .validar import validar

CENARIOS = Path(__file__).parent / "cenarios.yaml"


@dataclass
class ResultadoCenario:
    id: str
    entregou: bool
    ciclo_completo: bool
    cofre_integro: bool
    checagens_ok: int
    checagens_total: int
    turnos: int
    agentes: list[str]
    recusas: int
    tokens: int
    segundos: float
    parou_por: str
    entrega: str = ""
    problemas: list[str] = field(default_factory=list)
    trilha: list[str] = field(default_factory=list)

    @property
    def aprovado(self) -> bool:
        return self.entregou and self.ciclo_completo and self.cofre_integro and self.checagens_ok == self.checagens_total


def carregar_cenarios(arquivo: Path = CENARIOS) -> list[dict]:
    return yaml.safe_load(arquivo.read_text(encoding="utf-8"))["cenarios"]


def rodar_cenario(cenario: dict, llm: LLM, max_turnos: int = 14, pasta: Path | None = None) -> ResultadoCenario:
    base = Path(pasta or tempfile.mkdtemp(prefix="cerebro-aval-"))
    cofre = criar_cofre(base / cenario["id"])
    for nome, texto in (cenario.get("notas") or {}).items():
        destino = cofre / nome
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto, encoding="utf-8")
    titulo = cenario["titulo"]
    (cofre / "00-Entrada" / f"{titulo}.md").write_text(f"# {titulo}\n\n{cenario['pedido'].strip()}\n", encoding="utf-8")

    antes = {n.caminho for n in ler_cofre(cofre).values()}
    executor = orquestrador.ExecutorLLM(llm)
    inicio = time.perf_counter()
    execucao = orquestrador.rodar(cofre, executor, max_turnos=max_turnos, aviso=lambda _: None)
    segundos = time.perf_counter() - inicio

    notas = ler_cofre(cofre)
    entregas = [r for r in mural.recados(notas)
                if str(r.meta.get("para", "")).lower() == mural.HUMANO and str(r.meta.get("de", "")).lower() == "maestro"
                and str(r.meta.get("pedido", "")).strip("[]") == titulo]
    entrega = entregas[-1].corpo.strip() if entregas else ""
    problemas = [str(p) for p in validar(notas)]

    checagens = cenario.get("checagens") or []
    ok = 0
    for ch in checagens:
        if "nota_em" in ch:
            ok += any(n.pasta == ch["nota_em"] and n.caminho not in antes for n in notas.values())
        elif "entrega_cita" in ch:
            ok += any(p.lower() in entrega.lower() for p in ch["entrega_cita"])
        elif "agente_trabalhou" in ch:
            ok += ch["agente_trabalhou"] in {t.agente for t in execucao.turnos}

    return ResultadoCenario(
        id=cenario["id"], entregou=bool(entregas), ciclo_completo=execucao.parou_por == orquestrador.CICLO_COMPLETO,
        cofre_integro=not problemas, checagens_ok=ok, checagens_total=len(checagens), turnos=len(execucao.turnos),
        agentes=[t.agente for t in execucao.turnos], recusas=sum(t.recusas for t in execucao.turnos),
        tokens=sum(t.tokens for t in execucao.turnos), segundos=round(segundos, 1), parou_por=execucao.parou_por,
        entrega=entrega[:1500], problemas=problemas[:10],
        trilha=[f"{t.agente}: " + "; ".join(t.detalhes) + (f" → {t.saida[:120]}" if t.saida else "") for t in execucao.turnos])


def avaliar(llm: LLM, cenarios: list[dict] | None = None, max_turnos: int = 14, aviso=print) -> dict:
    resultados = []
    for c in cenarios or carregar_cenarios():
        aviso(f"→ {c['id']}")
        r = rodar_cenario(c, llm, max_turnos)
        aviso(f"   {'✓' if r.aprovado else '✗'} entregou={r.entregou} ciclo={r.ciclo_completo} íntegro={r.cofre_integro} "
              f"checagens={r.checagens_ok}/{r.checagens_total} turnos={r.turnos} recusas={r.recusas} {r.segundos}s")
        resultados.append(r)
    n = len(resultados) or 1
    return {
        "modelo": getattr(llm, "nome", "?"), "data": datetime.now().isoformat(timespec="minutes"),
        "resumo": {
            "cenarios": len(resultados),
            "aprovados": sum(r.aprovado for r in resultados),
            "entregou": round(sum(r.entregou for r in resultados) / n, 3),
            "ciclo_completo": round(sum(r.ciclo_completo for r in resultados) / n, 3),
            "cofre_integro": round(sum(r.cofre_integro for r in resultados) / n, 3),
            "checagens": round(sum(r.checagens_ok for r in resultados) / max(1, sum(r.checagens_total for r in resultados)), 3),
            "turnos_medio": round(sum(r.turnos for r in resultados) / n, 1),
            "recusas_total": sum(r.recusas for r in resultados),
            "tokens_total": sum(r.tokens for r in resultados),
            "segundos_total": round(sum(r.segundos for r in resultados), 1),
        },
        "cenarios": [asdict(r) | {"aprovado": r.aprovado} for r in resultados],
    }


def salvar(relatorio: dict, destino: str | Path) -> Path:
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(relatorio, ensure_ascii=False, indent=1), encoding="utf-8")
    return destino
