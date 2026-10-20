"""Busca no cofre: BM25 em Python puro sobre título, metadados e corpo de cada nota.

Sem dependência nem serviço externo: roda igual no notebook, no CI e dentro do servidor MCP.
O título pesa mais que o corpo (quem procura "LGPD" quer a nota LGPD antes da nota que cita LGPD).
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from .cofre import Nota

_PALAVRA = re.compile(r"[a-z0-9]+")
# Palavras muito comuns em português que só atrapalham o ranking.
_VAZIAS = set("""a o as os um uma uns umas de do da dos das e em no na nos nas por para com sem que se ao aos
à às é ser foi como mais mas ou ele ela isso este esta esse essa eu voce você nao não sim ja já tem""".split())


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def _radical(t: str) -> str:
    """Plural e diminutivos mais comuns do português, sem dicionário: "notas" e "nota" viram o mesmo termo."""
    if len(t) <= 3 or t.isdigit():
        return t
    for sufixo, troca in (("oes", "ao"), ("aes", "ao"), ("ais", "al"), ("eis", "el"), ("is", "il"), ("ns", "m"), ("es", ""), ("s", "")):
        if t.endswith(sufixo) and len(t) - len(sufixo) >= (2 if troca else 3):
            novo = t[: -len(sufixo)] + troca
            # "es" só sai quando a palavra fica terminando em consoante que pede o "e" (flores, mulheres, vezes)
            if sufixo == "es" and not novo.endswith(("r", "z", "l")):
                novo = t[:-1]
            return novo
    return t


def termos(texto: str) -> list[str]:
    return [_radical(t) for t in _PALAVRA.findall(_sem_acento(texto)) if t not in _VAZIAS and len(t) > 1]


@dataclass
class Resultado:
    nota: Nota
    pontos: float
    trecho: str


class Indice:
    """Índice BM25 do cofre. `k1` e `b` são os valores clássicos de Robertson."""

    def __init__(self, notas: dict[str, Nota], k1: float = 1.5, b: float = 0.75, peso_titulo: int = 3):
        self.notas = list(notas.values())
        self.k1, self.b = k1, b
        self.docs: list[Counter] = []
        for n in self.notas:
            meta = " ".join(str(v) for k, v in n.meta.items() if k in ("papel", "assunto", "tags", "tipo"))
            self.docs.append(Counter(termos(n.nome) * peso_titulo + termos(meta) + termos(n.corpo)))
        self.tamanhos = [sum(d.values()) for d in self.docs]
        self.media = (sum(self.tamanhos) / len(self.tamanhos)) if self.tamanhos else 0.0
        df: Counter = Counter()
        for d in self.docs:
            df.update(d.keys())
        total = len(self.docs)
        self.idf = {t: math.log(1 + (total - n + 0.5) / (n + 0.5)) for t, n in df.items()}

    def buscar(self, consulta: str, limite: int = 5, pasta: str | None = None) -> list[Resultado]:
        q = termos(consulta)
        resultados = []
        for nota, doc, tam in zip(self.notas, self.docs, self.tamanhos, strict=True):
            if pasta and nota.pasta.lower() != pasta.lower():
                continue
            pontos = 0.0
            for t in q:
                f = doc.get(t, 0)
                if f:
                    pontos += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * tam / (self.media or 1)))
            if pontos > 0:
                titulo = set(termos(nota.nome))
                if q and titulo and set(q) <= titulo:
                    pontos *= 1 + len(q) / len(titulo)  # o título é praticamente a consulta: nota sobre o assunto
                if nota.tipo == "recado":
                    pontos *= 0.8  # conversa vem depois da nota de conhecimento sobre o mesmo tema
                resultados.append(Resultado(nota, round(pontos, 3), trecho(nota.corpo, q)))
        resultados.sort(key=lambda r: (-r.pontos, r.nota.nome))
        return resultados[:limite]


def trecho(corpo: str, q: list[str], largura: int = 220) -> str:
    """O pedaço do corpo com mais termos da consulta, para mostrar por que a nota apareceu."""
    texto = " ".join(corpo.split())
    if not texto:
        return ""
    sem = _sem_acento(texto)
    melhor, inicio = -1, 0
    for i in range(0, max(1, len(texto) - largura + 1), 40):
        janela = sem[i:i + largura]
        n = sum(janela.count(t[:5]) for t in q)
        if n > melhor:
            melhor, inicio = n, i
    pedaco = texto[inicio:inicio + largura]
    return ("…" if inicio else "") + pedaco + ("…" if inicio + largura < len(texto) else "")
