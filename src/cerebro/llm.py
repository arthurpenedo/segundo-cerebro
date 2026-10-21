"""Clientes de modelo de linguagem com tool calling, no formato da API da OpenAI.

Funciona com qualquer servidor compatível: Ollama (modelos abertos, de graça, na própria máquina ou no CI),
vLLM, LM Studio, Groq, OpenAI. O `RoteiroLLM` devolve respostas pré-escritas e serve para os testes e
para a demonstração do CI rodarem sem modelo nenhum.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Protocol

import httpx


@dataclass
class ChamadaFerramenta:
    id: str
    nome: str
    argumentos: dict


@dataclass
class Resposta:
    texto: str
    chamadas: list[ChamadaFerramenta] = field(default_factory=list)
    chamada_em_texto: bool = False  # o modelo escreveu a chamada como texto, e nós convertemos
    tokens_entrada: int = 0
    tokens_saida: int = 0


class LLM(Protocol):
    nome: str

    def conversar(self, mensagens: list[dict], ferramentas: list[dict]) -> Resposta: ...


_JSON_CHAMADA = re.compile(r"\{[^{}]*\"name\"\s*:\s*\"(\w+)\"[^{}]*\"arguments\"\s*:\s*(\{.*?\})\s*\}", re.DOTALL)


def chamadas_escritas_como_texto(texto: str, nomes: set[str]) -> list[ChamadaFerramenta]:
    """Modelos pequenos às vezes devolvem {"name": ..., "arguments": {...}} no texto em vez de tool_calls."""
    chamadas = []
    for m in _JSON_CHAMADA.finditer(texto or ""):
        if m.group(1) in nomes:
            try:
                chamadas.append(ChamadaFerramenta(f"txt_{uuid.uuid4().hex[:8]}", m.group(1), json.loads(m.group(2))))
            except json.JSONDecodeError:
                pass
    return chamadas


@dataclass
class ClienteOpenAI:
    """Chat com ferramentas em qualquer servidor compatível com a OpenAI (padrão: Ollama local)."""

    modelo: str
    url_base: str = "http://localhost:11434/v1"
    chave: str | None = None
    timeout: float = 900.0  # 7B na CPU do CI com contexto longo passa de 5 min
    seed: int = 42
    temperatura: float = 0.0
    max_tokens: int = 1200  # corta resposta que entra em loop (modelos pequenos às vezes não param)

    @property
    def nome(self) -> str:
        return self.modelo

    def conversar(self, mensagens: list[dict], ferramentas: list[dict]) -> Resposta:
        corpo = {"model": self.modelo, "messages": mensagens, "temperature": self.temperatura, "seed": self.seed,
                 "max_tokens": self.max_tokens}
        if ferramentas:
            corpo["tools"] = ferramentas
        cabecalhos = {"Authorization": f"Bearer {self.chave}"} if self.chave else {}
        for tentativa in range(3):
            try:
                r = httpx.post(f"{self.url_base}/chat/completions", json=corpo, headers=cabecalhos, timeout=self.timeout)
                r.raise_for_status()
                break
            except httpx.HTTPError:
                if tentativa == 2:
                    raise
                time.sleep(3 * (tentativa + 1))
        dados = r.json()
        msg = dados["choices"][0]["message"]
        uso = dados.get("usage") or {}
        chamadas = []
        for c in msg.get("tool_calls") or []:
            args = c["function"].get("arguments") or "{}"
            try:
                args = json.loads(args) if isinstance(args, str) else args
            except json.JSONDecodeError:
                args = {}
            chamadas.append(ChamadaFerramenta(c.get("id") or f"c_{uuid.uuid4().hex[:8]}", c["function"]["name"], args))
        em_texto = False
        if not chamadas and ferramentas:
            chamadas = chamadas_escritas_como_texto(msg.get("content") or "", {f["function"]["name"] for f in ferramentas})
            em_texto = bool(chamadas)
        return Resposta(texto="" if em_texto else (msg.get("content") or ""), chamadas=chamadas,
                        chamada_em_texto=em_texto, tokens_entrada=uso.get("prompt_tokens", 0),
                        tokens_saida=uso.get("completion_tokens", 0))


@dataclass
class RoteiroLLM:
    """LLM falso: devolve as respostas de uma lista, em ordem, e guarda o que recebeu."""

    respostas: list[Resposta]
    nome: str = "roteiro"
    recebido: list[list[dict]] = field(default_factory=list)

    def conversar(self, mensagens: list[dict], ferramentas: list[dict]) -> Resposta:
        self.recebido.append(json.loads(json.dumps(mensagens)))
        return self.respostas.pop(0) if self.respostas else Resposta("Terminei.")


def chamar(ferramenta: str, /, **argumentos) -> Resposta:
    """Atalho para roteiros: uma resposta que só chama uma ferramenta."""
    return Resposta("", [ChamadaFerramenta(f"r_{uuid.uuid4().hex[:6]}", ferramenta, argumentos)])
