"""As ferramentas que um agente pode usar dentro do cofre, com as regras aplicadas no código.

O modelo de linguagem só pede ("deixe um recado para o dev"); quem executa é este módulo, e ele recusa o que
a nota do agente não permite. Regras que valem para qualquer modelo, do maior ao menor:

- o remetente de um recado é sempre o próprio agente (não dá para assinar como outro);
- só o maestro escreve para o humano (regra do Mural, em `mural.escrever_recado`);
- um agente só fecha recado endereçado a ele;
- um agente só escreve notas nas pastas listadas em `escreve_em` da sua nota em Agentes/;
- nada com cara de CPF, cartão ou chave de API é gravado (o cofre é público);
- toda chamada, aceita ou recusada, fica registrada para auditoria.
"""

from __future__ import annotations

import inspect
import json
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import mural
from .busca import Indice
from .cofre import ler_cofre, resolver
from .validar import _SENSIVEL


class Recusa(Exception):
    """A ferramenta recusou o pedido por uma regra do cofre. A mensagem volta para o modelo corrigir."""


@dataclass
class Registro:
    ferramenta: str
    argumentos: dict
    ok: bool
    resultado: str


@dataclass
class Bancada:
    """A bancada do agente: o que ele pode fazer num turno. `registros` é a trilha de auditoria do turno."""

    raiz: Path
    agente: str
    registros: list[Registro] = field(default_factory=list)
    pedido_padrao: str | None = None  # pedido da Entrada que acordou o agente: entra nos recados que não disserem outro

    def __post_init__(self) -> None:
        self.raiz = Path(self.raiz)
        self.agente = self.agente.lower()
        notas = ler_cofre(self.raiz)
        ficha = mural.agentes(notas).get(self.agente)
        if ficha is None:
            raise ValueError(f"'{self.agente}' não é um agente do cofre (falta a nota em Agentes/)")
        self.ficha = ficha
        self.pode_escrever = [str(p) for p in ficha.meta.get("escreve_em") or []]
        self.conhecidos = set(mural.agentes(notas)) | {mural.HUMANO, "todos"}

    # ---------------------------------------------------------------- ferramentas

    def ler_mural(self) -> str:
        """Recados abertos para mim, do mais antigo para o mais novo, com o texto inteiro."""
        abertos = mural.abertos_para(ler_cofre(self.raiz), self.agente)
        if not abertos:
            return "Nenhum recado aberto para você."
        partes = []
        for r in abertos:
            m = r.meta
            partes.append(f"### {r.nome}\nde: {m.get('de')} · assunto: {m.get('assunto')} · pedido: {m.get('pedido', '-')}\n"
                          f"{r.corpo.strip()}")
        return "\n\n".join(partes)

    def ler_nota(self, nome: str) -> str:
        """Conteúdo de uma nota do cofre pelo nome (como num link [[nome]])."""
        nota = resolver(ler_cofre(self.raiz), nome.strip("[] "))
        if nota is None:
            raise Recusa(f"não existe nota chamada '{nome}'. Use `buscar` para achar o nome certo.")
        return f"# {nota.nome} ({nota.caminho.as_posix()})\n{nota.corpo.strip()}"[:6000]

    def buscar(self, consulta: str, pasta: str | None = None) -> str:
        """As notas mais relevantes para a consulta (BM25), com um trecho de cada."""
        achados = Indice(ler_cofre(self.raiz)).buscar(consulta, limite=5, pasta=pasta)
        if not achados:
            return "Nada encontrado. Tente outras palavras."
        return "\n".join(f"- [[{r.nota.nome}]] ({r.nota.pasta or 'raiz'}, {r.pontos}): {r.trecho}" for r in achados)

    def listar_notas(self, pasta: str) -> str:
        """Nomes das notas de uma pasta do cofre."""
        nomes = sorted(n.nome for n in ler_cofre(self.raiz).values() if n.pasta.lower() == pasta.lower())
        return "\n".join(nomes) if nomes else f"A pasta '{pasta}' não tem notas."

    def deixar_recado(self, para: str, assunto: str, texto: str, responde: str | None = None,
                      pedido: str | None = None) -> str:
        """Escreve um recado no Mural. O remetente é sempre você."""
        para = para.lower().strip().strip("`@ ")
        if para not in self.conhecidos:
            raise Recusa(f"'{para}' não é um agente do cofre. Agentes: {', '.join(sorted(self.conhecidos))}")
        if para == self.agente:
            dica = ""
            if responde:
                original = resolver(ler_cofre(self.raiz), Path(responde.strip("[] ")).stem)
                if original is not None:
                    dica = f" Você está respondendo a um recado de '{original.meta.get('de')}': mande para ele."
            raise Recusa("você não pode deixar recado para você mesmo." + dica)
        self._checar_sensivel(texto + " " + assunto)
        notas = ler_cofre(self.raiz)
        meus = mural.abertos_para(notas, self.agente)
        if responde:
            responde = Path(responde.strip("[] ")).stem
            if resolver(notas, responde) is None:
                try:  # aceita um trecho único do nome, como o `cerebro fechar`
                    responde = mural.localizar(self.raiz, responde).stem
                except (FileNotFoundError, ValueError):
                    raise Recusa(f"o recado '{responde}' não existe; use o nome exato que aparece em ler_mural") from None
        else:
            # Esqueceu de dizer a qual recado responde: se só há um recado aberto deste destinatário para mim, é ele.
            do_destinatario = [r for r in meus if str(r.meta.get("de", "")).lower() == para]
            if len(do_destinatario) == 1:
                responde = do_destinatario[0].nome
        try:
            arquivo = mural.escrever_recado(self.raiz, self.agente, para, assunto, texto, responde=responde,
                                            pedido=pedido or (None if responde else self.pedido_padrao))
        except mural.RecadoRecusado as e:
            raise Recusa(str(e)) from e
        # Responder resolve: o recado que eu recebi e acabei de responder sai da minha fila.
        resolvido = next((r for r in meus if responde and r.nome.lower() == responde.lower()), None)
        if resolvido is not None:
            mural.mudar_status(self.raiz / resolvido.caminho, "feito")
            return f"Recado criado: {arquivo.stem}. O recado que você respondeu ({resolvido.nome}) foi marcado como resolvido."
        return f"Recado criado: {arquivo.stem}"

    def fechar_recado(self, nome: str, status: str = "feito") -> str:
        """Muda o status de um recado endereçado a você (feito ou recusado)."""
        if status not in ("feito", "recusado"):
            raise Recusa("status deve ser 'feito' ou 'recusado'")
        try:
            arquivo = mural.localizar(self.raiz, nome.strip("[] "))
        except (FileNotFoundError, ValueError) as e:
            raise Recusa(str(e)) from e
        nota = resolver(ler_cofre(self.raiz), arquivo.stem)
        para = str(nota.meta.get("para", "")).lower() if nota else ""
        if para not in (self.agente, "todos"):
            raise Recusa(f"este recado é para '{para}', não para você: só quem recebe pode fechar")
        mural.mudar_status(arquivo, status)
        return f"{arquivo.stem}: {status}"

    def escrever_nota(self, pasta: str, titulo: str, conteudo: str) -> str:
        """Cria ou substitui uma nota numa pasta onde você pode escrever."""
        if _chave(pasta) == "mural":
            raise Recusa("no Mural só se escreve com `deixar_recado`")
        pasta = next((p for p in self.pode_escrever if _chave(p) == _chave(pasta)), pasta)
        if pasta not in self.pode_escrever:
            raise Recusa(f"você só pode escrever em: {', '.join(self.pode_escrever) or 'nenhuma pasta'}")
        nome = re.sub(r'[\\/:*?"<>|\[\]#^]+', " ", titulo).strip()[:80]
        if not nome:
            raise Recusa("título vazio")
        self._checar_sensivel(conteudo)
        destino = self.raiz / pasta / f"{nome}.md"
        destino.parent.mkdir(parents=True, exist_ok=True)
        corpo = conteudo if conteudo.lstrip().startswith(("#", "---")) else f"# {nome}\n\n{conteudo.strip()}\n"
        destino.write_text(corpo, encoding="utf-8")
        return f"Nota salva: {pasta}/{nome}.md (link: [[{nome}]])"

    # ---------------------------------------------------------------- execução e esquema

    def _checar_sensivel(self, texto: str) -> None:
        for nome, padrao in _SENSIVEL.items():
            if padrao.search(texto):
                raise Recusa(f"o texto parece conter {nome}; o cofre é público e isso não pode ser gravado")

    def executar(self, nome: str, argumentos: dict) -> tuple[bool, str]:
        """Roda uma ferramenta pedida pelo modelo. Nunca levanta exceção: o erro volta como texto para o modelo."""
        funcao: Callable | None = getattr(self, nome, None) if nome in NOMES else None
        try:
            if funcao is None:
                raise Recusa(f"ferramenta desconhecida: {nome}. Disponíveis: {', '.join(NOMES)}")
            resultado, ok = str(funcao(**_ajustar_argumentos(nome, funcao, argumentos or {}))), True
        except Recusa as e:
            resultado, ok = f"RECUSADO: {e}", False
        except TypeError as e:
            resultado, ok = f"ERRO nos argumentos: {e}", False
        self.registros.append(Registro(nome, argumentos or {}, ok, resultado[:500]))
        return ok, resultado


def _chave(texto: str) -> str:
    return unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower().strip(" /")


# Nomes que modelos pequenos inventam para os parâmetros, por ferramenta.
_SINONIMOS = {
    "deixar_recado": {"nome": "responde", "recado": "responde", "resposta_a": "responde", "em_resposta_a": "responde",
                      "mensagem": "texto", "conteudo": "texto", "corpo": "texto", "destinatario": "para", "agente": "para",
                      "titulo": "assunto"},
    "fechar_recado": {"recado": "nome", "arquivo": "nome", "responde": "nome"},
    "escrever_nota": {"texto": "conteudo", "corpo": "conteudo", "nome": "titulo", "assunto": "titulo"},
    "ler_nota": {"titulo": "nome", "nota": "nome"},
    "buscar": {"termo": "consulta", "texto": "consulta", "query": "consulta"},
}


def _ajustar_argumentos(ferramenta: str, funcao: Callable, argumentos: dict) -> dict:
    """Corrige só a forma ("pasta:", sinônimo, parâmetro a mais); o conteúdo continua passando pelas regras."""
    aceitos = set(inspect.signature(funcao).parameters)
    sinonimos = _SINONIMOS.get(ferramenta, {})
    ajustados: dict = {}
    for chave, valor in argumentos.items():
        k = _chave(chave).strip(":").replace(" ", "_")
        k = k if k in aceitos else sinonimos.get(k, k)
        if k in aceitos and k not in ajustados and valor not in (None, ""):
            ajustados[k] = valor
    return ajustados


def _prop(tipo: str, descricao: str) -> dict:
    return {"type": tipo, "description": descricao}


ESQUEMA = [
    ("ler_mural", "Lê os recados abertos para você no Mural. Comece sempre por aqui.", {}, []),
    ("ler_nota", "Lê uma nota do cofre pelo nome.", {"nome": _prop("string", "nome da nota, como em [[nome]]")}, ["nome"]),
    ("buscar", "Busca notas do cofre por palavras.",
     {"consulta": _prop("string", "o que procurar"), "pasta": _prop("string", "opcional: limitar a uma pasta")}, ["consulta"]),
    ("listar_notas", "Lista as notas de uma pasta.", {"pasta": _prop("string", "nome da pasta")}, ["pasta"]),
    ("deixar_recado", "Escreve um recado no Mural para outro agente (ou para arthur, só o maestro).",
     {"para": _prop("string", "id do agente que deve agir"), "assunto": _prop("string", "assunto curto"),
      "texto": _prop("string", "o recado"), "responde": _prop("string", "nome do recado que você está respondendo"),
      "pedido": _prop("string", "nome da nota de pedido da Entrada, se for o primeiro recado do pedido")},
     ["para", "assunto", "texto"]),
    ("fechar_recado", "Fecha um recado endereçado a você depois de tratar.",
     {"nome": _prop("string", "nome do recado"), "status": _prop("string", "feito ou recusado")}, ["nome"]),
    ("escrever_nota", "Cria ou substitui uma nota numa pasta onde você pode escrever.",
     {"pasta": _prop("string", "pasta de destino"), "titulo": _prop("string", "título da nota"),
      "conteudo": _prop("string", "conteúdo em Markdown")}, ["pasta", "titulo", "conteudo"]),
]
NOMES = [nome for nome, *_ in ESQUEMA]


def esquema_openai() -> list[dict]:
    return [{"type": "function", "function": {"name": nome, "description": desc,
                                              "parameters": {"type": "object", "properties": props, "required": req}}}
            for nome, desc, props, req in ESQUEMA]


def resumo(registros: list[Registro]) -> str:
    return json.dumps([r.__dict__ for r in registros], ensure_ascii=False)
