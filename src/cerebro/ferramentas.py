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
from .cofre import _LINK, ler_cofre, resolver
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
    pedido_padrao: str | None = None  # pedido do turno (da Entrada ou do recado que acordou o agente)
    indicados: list[str] = field(default_factory=list)  # agentes que o papel indica para um pedido novo (maestro)
    bloquear_recados: bool = False  # turno só de Diário: não abre recado novo

    def __post_init__(self) -> None:
        self._insistiu: set[str] = set()
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
            passo = ""
            if self.agente == "maestro" and m.get("responde") and str(m.get("de", "")).lower() != mural.HUMANO:
                passo = (f"\nPRÓXIMO PASSO: isto é o resultado do {m.get('de')}. Entregue a {mural.HUMANO} com "
                         f'deixar_recado(para="{mural.HUMANO}", responde="{r.nome}", ...), resumindo o resultado.')
            elif self.agente != "maestro":
                passo = (f'\nPRÓXIMO PASSO: faça o trabalho e responda com deixar_recado(para="{m.get("de")}", '
                         f'responde="{r.nome}", ...).')
            partes.append(f"### {r.nome}\nde: {m.get('de')} · assunto: {m.get('assunto')} · pedido: {m.get('pedido', '-')}\n"
                          f"{r.corpo.strip()}{passo}")
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

    def deixar_recado(self, para: str, assunto: str = "", texto: str = "", responde: str | None = None,
                      pedido: str | None = None) -> str:
        """Escreve um recado no Mural. O remetente é sempre você."""
        if self.bloquear_recados:
            raise Recusa("agora é só o Diário: a Entrada já foi encaminhada e não há recado novo a abrir.")
        para = para.lower().strip().strip("`@ ")
        if para not in self.conhecidos:
            raise Recusa(f"'{para}' não é um agente do cofre. Agentes: {', '.join(sorted(self.conhecidos))}")
        if not str(texto).strip():
            raise Recusa("o recado está sem texto: escreva em `texto` o resultado ou o pedido")
        redirecionado = ""
        if para == self.agente:
            # Recado para si mesmo é engano de endereço: se dá para saber a quem ele responde, corrige o destino.
            meus_abertos = mural.abertos_para(ler_cofre(self.raiz), self.agente)
            original = None
            if responde:
                original = resolver(ler_cofre(self.raiz), Path(responde.strip("[] ")).stem)
            elif len(meus_abertos) == 1:
                original = meus_abertos[0]
                responde = original.nome
            destino = str(original.meta.get("de", "")).lower() if original is not None else ""
            if not destino or destino == self.agente:
                raise Recusa("você não pode deixar recado para você mesmo; mande para quem pediu o trabalho.")
            para, redirecionado = destino, f" (destino corrigido: você mandou para si mesmo, foi para '{destino}', que pediu)"
        self._checar_sensivel(texto + " " + assunto)
        texto = _SEM_FECHAR.sub("", texto)  # "[[" sem "]]" juntaria com o próximo link e quebraria o cofre
        notas = ler_cofre(self.raiz)
        quebrados = [alvo for alvo in _LINK.findall(texto) if resolver(notas, alvo.split("|")[0].split("#")[0]) is None]
        if quebrados:
            raise Recusa(f"o texto cita [[{quebrados[0]}]], que não existe no cofre. Crie a nota antes com escrever_nota "
                         f"ou tire os colchetes.")
        meus = mural.abertos_para(notas, self.agente)
        if responde:
            responde = Path(responde.strip("[] ")).stem
            if resolver(notas, responde) is None:
                try:  # aceita um trecho único do nome, como o `cerebro fechar`
                    responde = mural.localizar(self.raiz, responde).stem
                except (FileNotFoundError, ValueError):
                    raise Recusa(f"o recado '{responde}' não existe; use o nome exato que aparece em ler_mural") from None
        else:
            # Esqueceu de dizer a qual recado responde: é o mais recente aberto deste destinatário para mim.
            do_destinatario = [r for r in meus if str(r.meta.get("de", "")).lower() == para]
            if self.agente == "maestro" and para == mural.HUMANO:
                # Entrega ao humano responde ao resultado que um agente trouxe (do pedido do turno, se houver).
                do_destinatario = [r for r in meus if str(r.meta.get("de", "")).lower() not in (mural.HUMANO, "maestro")
                                   and (not self.pedido_padrao
                                        or str(r.meta.get("pedido", "")).strip("[] ") == self.pedido_padrao)]
            if do_destinatario:
                responde = do_destinatario[-1].nome
        original = resolver(notas, responde) if responde else None

        # O pedido vem do código, não do que o modelo escreve: o do recado respondido, senão o do turno.
        # O valor que o modelo passa só vale se for o nome de um pedido da Entrada.
        herdado = str(original.meta.get("pedido", "")).strip("[] ") if original is not None else ""
        if herdado:
            pedido = herdado
        elif self.pedido_padrao:
            pedido = self.pedido_padrao
        elif pedido and not (self.raiz / "00-Entrada" / f"{Path(str(pedido).strip('[] ')).stem}.md").is_file():
            pedido = None
        if not str(assunto).strip():
            assunto = (str(original.meta.get("assunto", "")) if original is not None else "") or pedido or "recado"

        # Roteamento: o primeiro recado de um pedido novo vai para quem o papel indica, salvo insistência.
        if (self.agente == "maestro" and self.indicados and para not in self.indicados
                and para not in (mural.HUMANO, "critico") and para not in self._insistiu):
            self._insistiu.add(para)
            raise Recusa(f"pelo papel, este pedido é de {' ou '.join(self.indicados)}. Mande para um deles; se tiver "
                          f"certeza de que é de '{para}', repita a mesma chamada.")
        de_quem = str(original.meta.get("de", "")).lower() if original is not None else ""
        revisor = str(self.ficha.meta.get("revisado_por") or "").lower()
        if self.agente not in ("maestro", "secretario") and para not in ("maestro", "critico", mural.HUMANO, revisor):
            # Só o maestro distribui trabalho: os outros respondem a quem pediu, pedem revisão ou falam com o maestro.
            quem_pediu = {str(r.meta.get("de", "")).lower() for r in mural.recados(notas)
                          if str(r.meta.get("para", "")).lower() == self.agente
                          and (not pedido or str(r.meta.get("pedido", "")).strip("[] ") == pedido)}
            if para not in quem_pediu:
                raise Recusa(f"você não distribui trabalho: o seu é fazer e responder a quem pediu "
                             f"({', '.join(sorted(quem_pediu - {mural.HUMANO})) or 'maestro'}). Se precisar de outro "
                             f"agente, explique ao maestro.")
        if (revisor and revisor in self.conhecidos and para == "maestro" and pedido
                and not self._aprovado_por(notas, revisor, pedido)):
            # A nota do agente diz quem revisa a entrega dele: antes do maestro, passa pelo revisor.
            para, redirecionado = revisor, (f" (sua nota pede revisão do {revisor} antes do maestro: o recado foi "
                                            f"para o {revisor}; quando ele aprovar, segue para o maestro)")
        elif self.agente == "critico" and para != "maestro" and _APROVADO.search(texto) and not _AJUSTAR.search(texto):
            # Revisão termina no maestro: "aprovado" vai direto para quem entrega ao humano.
            para, redirecionado = "maestro", " (revisão aprovada: foi direto para o maestro, que entrega)"
        elif pedido and para not in ("maestro", mural.HUMANO):
            idas = [r for r in mural.recados(notas) if str(r.meta.get("pedido", "")).strip("[] ") == pedido
                    and str(r.meta.get("de", "")).lower() == self.agente and str(r.meta.get("para", "")).lower() == para]
            if len(idas) >= 2:
                redirecionado = (f" (já eram {len(idas)} recados seus para '{para}' neste pedido: este foi para o "
                                 f"maestro decidir, para a conversa não girar em falso)")
                para = "maestro"
        if (self.agente == "maestro" and para == mural.HUMANO and original is not None
                and de_quem not in (mural.HUMANO, "maestro", "")):
            # A entrega ao humano leva a resposta de quem fez o trabalho, não só o resumo do maestro.
            texto = f"{texto.strip()}\n\n**Resposta do {de_quem}:**\n\n" + _citar(original.corpo)

        try:
            arquivo = mural.escrever_recado(self.raiz, self.agente, para, assunto, texto, responde=responde,
                                            pedido=pedido)
        except mural.RecadoRecusado as e:
            raise Recusa(str(e)) from e
        # Responder resolve: o recado respondido sai da minha fila, e com ele os mais antigos da mesma pessoa
        # neste pedido (a resposta vale para a conversa toda).
        resolvidos = [r for r in meus if original is not None and (
            r.nome.lower() == original.nome.lower()
            or (str(r.meta.get("de", "")).lower() == de_quem and str(r.meta.get("pedido", "")).strip("[] ") == (herdado or "-")))]
        for r in resolvidos:
            mural.mudar_status(self.raiz / r.caminho, "feito")
        if resolvidos:
            return (f"Recado criado: {arquivo.stem}{redirecionado}. Marcado como resolvido: "
                    f"{', '.join(r.nome for r in resolvidos)}.")
        return f"Recado criado: {arquivo.stem}{redirecionado}"

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

    def escrever_nota(self, pasta: str = "", titulo: str = "", conteudo: str = "") -> str:
        """Cria ou substitui uma nota numa pasta onde você pode escrever."""
        if not str(conteudo).strip():
            raise Recusa("a nota está sem conteúdo: escreva o texto em `conteudo`")
        if not str(titulo).strip():
            # Sem título: usa o primeiro cabeçalho do texto, senão o pedido do turno.
            m = re.search(r"^#\s+(.+)$", conteudo, re.M)
            titulo = m.group(1) if m else (self.pedido_padrao or "")
        if _chave(pasta) == "mural":
            raise Recusa("no Mural só se escreve com `deixar_recado`")
        pasta = next((p for p in self.pode_escrever if _chave(p) == _chave(pasta)), pasta)
        if pasta not in self.pode_escrever:
            # Pasta é forma: se o agente só tem uma pasta de notas, a nota vai para ela (a regra de onde escrever continua valendo).
            suas = [p for p in self.pode_escrever if _chave(p) not in ("mural", "00-entrada")]
            if len(suas) != 1:
                raise Recusa(f"você só pode escrever em: {', '.join(self.pode_escrever) or 'nenhuma pasta'}")
            pasta = suas[0]
        nome = re.sub(r'[\\/:*?"<>|\[\]#^]+', " ", titulo).strip()[:80]
        if not nome:
            raise Recusa("título vazio")
        self._checar_sensivel(conteudo)
        # Link para nota que não existe quebraria o cofre: vira texto simples, e o agente fica sabendo.
        notas = ler_cofre(self.raiz)
        sem_destino: list[str] = []

        def _trocar(m: re.Match) -> str:
            alvo = m.group(1).strip()
            if resolver(notas, alvo) is not None or alvo.lower() == nome.lower():
                return m.group(0)
            sem_destino.append(alvo)
            rotulo = m.group(0)[2:-2].split("|")[-1] if "|" in m.group(0) else alvo
            return rotulo
        conteudo = _LINK.sub(_trocar, _SEM_FECHAR.sub("", conteudo))
        destino = self.raiz / pasta / f"{nome}.md"
        destino.parent.mkdir(parents=True, exist_ok=True)
        corpo = conteudo if conteudo.lstrip().startswith(("#", "---")) else f"# {nome}\n\n{conteudo.strip()}\n"
        destino.write_text(corpo, encoding="utf-8")
        aviso = (f" Links sem nota no cofre viraram texto: {', '.join(sem_destino[:5])}." if sem_destino else "")
        return f"Nota salva: {pasta}/{nome}.md (link: [[{nome}]]).{aviso}"

    # ---------------------------------------------------------------- execução e esquema

    def _aprovado_por(self, notas: dict, revisor: str, pedido: str) -> bool:
        return any(str(r.meta.get("de", "")).lower() == revisor and str(r.meta.get("pedido", "")).strip("[] ") == pedido
                   and _APROVADO.search(r.corpo) and not _AJUSTAR.search(r.corpo) for r in mural.recados(notas))

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


_SEM_FECHAR = re.compile(r"\[\[(?![^\[\]\n]*\]\])")
_APROVADO = re.compile(r"\baprovad[oa]s?\b", re.I)
_AJUSTAR = re.compile(r"\bajust(ar|e|es)\b|\bcorrig|\breprovad", re.I)


def _citar(corpo: str, limite: int = 1500) -> str:
    """Corpo de um recado como citação: sem o título e sem a linha "Em resposta a"."""
    linhas = [li for li in corpo.strip().splitlines() if not li.startswith("Em resposta a [[")]
    if linhas and linhas[0].startswith("# "):
        linhas = linhas[1:]
    texto = "\n".join(linhas).strip()[:limite]
    return "\n".join(f"> {li}" if li.strip() else ">" for li in texto.splitlines())


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
