"""Motor próprio: bancada de ferramentas (regras no código), turno com LLM, ciclo completo, busca e init."""

import re
from pathlib import Path

import pytest

from cerebro import mural, orquestrador
from cerebro.agente import rodar_turno
from cerebro.busca import Indice
from cerebro.cofre import ler_cofre
from cerebro.ferramentas import Bancada, esquema_openai
from cerebro.init import criar_cofre
from cerebro.llm import Resposta, RoteiroLLM, chamar
from cerebro.validar import validar


@pytest.fixture
def cofre(tmp_path: Path) -> Path:
    return criar_cofre(tmp_path / "cofre")


def _recado(cofre: Path, de: str, para: str, assunto: str, pedido: str | None = None) -> str:
    return mural.escrever_recado(cofre, de, para, assunto, "texto do recado", pedido=pedido).stem


# ------------------------------------------------------------------ init

def test_init_cria_cofre_valido_com_9_agentes(cofre):
    notas = ler_cofre(cofre)
    assert validar(notas) == []
    assert len(mural.agentes(notas)) == 9
    assert (cofre / ".claude" / "agents" / "maestro.md").is_file()


def test_init_nao_sobrescreve_cofre_existente(cofre):
    with pytest.raises(FileExistsError):
        criar_cofre(cofre)


def test_init_com_outro_humano_troca_a_caixa(tmp_path):
    destino = criar_cofre(tmp_path / "ana", humano="ana")
    assert (destino / "Caixa do Ana.md").is_file()
    assert "Caixa do Arthur" not in (destino / "Inicio.md").read_text(encoding="utf-8")


# ------------------------------------------------------------------ bancada (regras no código)

def test_agente_so_escreve_nas_proprias_pastas(cofre):
    dev = Bancada(cofre, "dev")
    ok, saida = dev.executar("escrever_nota", {"pasta": "Conhecimento", "titulo": "X", "conteudo": "y"})
    assert not ok and "só pode escrever em" in saida
    ok, saida = dev.executar("escrever_nota", {"pasta": "Projetos", "titulo": "Status do CI", "conteudo": "verde"})
    assert ok and (cofre / "Projetos" / "Status do CI.md").is_file()


def test_mural_so_por_recado(cofre):
    ok, saida = Bancada(cofre, "dev").executar("escrever_nota", {"pasta": "Mural", "titulo": "x", "conteudo": "y"})
    assert not ok and "deixar_recado" in saida


def test_remetente_e_sempre_o_proprio_agente(cofre):
    dev = Bancada(cofre, "dev")
    ok, saida = dev.executar("deixar_recado", {"para": "critico", "assunto": "Revisar números", "texto": "confere?"})
    assert ok
    nome = saida.split(": ", 1)[1]
    assert ler_cofre(cofre)[nome.lower()].meta["de"] == "dev"


def test_so_o_maestro_fala_com_o_humano(cofre):
    ok, saida = Bancada(cofre, "dev").executar("deixar_recado", {"para": "arthur", "assunto": "a", "texto": "b"})
    assert not ok and "maestro" in saida
    ok, _ = Bancada(cofre, "maestro").executar("deixar_recado", {"para": "arthur", "assunto": "a", "texto": "b"})
    assert ok


def test_nao_fecha_recado_dos_outros(cofre):
    nome = _recado(cofre, "maestro", "critico", "Revisar post")
    ok, saida = Bancada(cofre, "dev").executar("fechar_recado", {"nome": nome})
    assert not ok and "só quem recebe" in saida
    ok, _ = Bancada(cofre, "critico").executar("fechar_recado", {"nome": nome})
    assert ok and ler_cofre(cofre)[nome.lower()].meta["status"] == "feito"


def test_dado_sensivel_nunca_e_gravado(cofre):
    ok, saida = Bancada(cofre, "dev").executar("escrever_nota", {"pasta": "Projetos", "titulo": "Cliente",
                                                                 "conteudo": "CPF 123.456.789-09"})
    assert not ok and "CPF" in saida
    assert not (cofre / "Projetos" / "Cliente.md").exists()


def test_agente_inexistente_e_ferramenta_desconhecida(cofre):
    with pytest.raises(ValueError):
        Bancada(cofre, "hacker")
    b = Bancada(cofre, "dev")
    ok, saida = b.executar("apagar_tudo", {})
    assert not ok and "desconhecida" in saida
    ok, saida = b.executar("ler_nota", {"nome_errado": "x"})
    assert not ok and "ERRO nos argumentos" in saida
    assert [r.ok for r in b.registros] == [False, False]


def test_esquema_tem_todas_as_ferramentas():
    nomes = {f["function"]["name"] for f in esquema_openai()}
    assert nomes == {"ler_mural", "ler_nota", "buscar", "listar_notas", "deixar_recado", "fechar_recado", "escrever_nota"}


# ------------------------------------------------------------------ turno com LLM

def test_turno_executa_ferramentas_e_termina(cofre):
    nome = _recado(cofre, "maestro", "dev", "Status do CI do agente-banco")
    llm = RoteiroLLM([
        chamar("escrever_nota", pasta="Projetos", titulo="agente-banco CI", conteudo="CI verde em 20/10"),
        chamar("deixar_recado", para="maestro", assunto="CI verde", texto="Ver [[agente-banco CI]]", responde=nome),
        chamar("fechar_recado", nome=nome),
        Resposta("Conferi o CI e avisei o maestro."),
    ])
    r = rodar_turno(cofre, "dev", "recado aberto", llm)
    assert r.resposta == "Conferi o CI e avisei o maestro."
    assert [x.ferramenta for x in r.registros] == ["escrever_nota", "deixar_recado", "fechar_recado"]
    assert r.recusas == 0 and r.passos == 4
    # o motor entrega os recados abertos na primeira mensagem, mesmo que o modelo não peça
    assert "Status do CI do agente-banco" in llm.recebido[0][1]["content"]
    # a nota do agente (editável no Obsidian) é a instrução de sistema
    assert "Dev" in llm.recebido[0][0]["content"] and "Projetos" in llm.recebido[0][0]["content"]
    # a resposta da ferramenta volta para o modelo
    assert any(m.get("role") == "tool" for m in llm.recebido[-1])


def test_recusa_volta_para_o_modelo_corrigir(cofre):
    llm = RoteiroLLM([chamar("deixar_recado", para="arthur", assunto="pronto", texto="feito"),
                      chamar("deixar_recado", para="maestro", assunto="pronto", texto="feito"),
                      Resposta("Entreguei ao maestro.")])
    r = rodar_turno(cofre, "dev", "teste", llm)
    assert r.recusas == 1
    tool_msgs = [m for m in llm.recebido[1] if m.get("role") == "tool"]
    assert tool_msgs[0]["content"].startswith("RECUSADO") and "maestro" in tool_msgs[0]["content"]


def test_turno_para_no_limite_de_passos(cofre):
    llm = RoteiroLLM([chamar("ler_mural") for _ in range(10)])
    r = rodar_turno(cofre, "dev", "teste", llm, max_passos=3)
    assert r.parou_no_limite and r.passos == 3


# ------------------------------------------------------------------ ciclo completo pelo laço

class EquipeFalsa:
    """LLM falso que responde conforme o agente acordado (lido da instrução de sistema)."""

    nome = "equipe-falsa"

    def __init__(self, roteiros: dict):
        self.roteiros = roteiros

    def conversar(self, mensagens, ferramentas):
        agente = re.search(r"Você é o agente `(\w+)`", mensagens[0]["content"]).group(1)
        fila = self.roteiros.get(agente, [])
        passo = sum(1 for m in mensagens if m["role"] == "assistant")
        if passo < len(fila):
            item = fila[passo]
            return item(mensagens) if callable(item) else item
        return Resposta(f"{agente} terminou.")


def _abertos(mensagens, para):
    """Nome do recado aberto citado na primeira mensagem do turno."""
    return re.search(r"### (\S.*)", mensagens[1]["content"]).group(1)


def test_ciclo_completo_entrada_maestro_dev_maestro_humano(cofre):
    (cofre / "00-Entrada" / "Status do portfolio.md").write_text("# Status do portfolio\n\nComo está o CI?", encoding="utf-8")
    equipe = EquipeFalsa({
        "maestro": [
            lambda m: chamar("deixar_recado", para="dev", assunto="Status do CI", texto="Confira o CI",
                             pedido="Status do portfolio") if "Entrada" in m[1]["content"] else
            chamar("deixar_recado", para="arthur", assunto="CI verde, pronto", texto="Tudo verde",
                   responde=_abertos(m, "maestro")),
            lambda m: Resposta("ok") if "Entrada" in m[1]["content"] else chamar("fechar_recado", nome=_abertos(m, "maestro")),
        ],
        "dev": [lambda m: chamar("deixar_recado", para="maestro", assunto="CI verde", texto="verde",
                                 responde=_abertos(m, "dev")),
                lambda m: chamar("fechar_recado", nome=_abertos(m, "dev"))],
    })
    execucao = orquestrador.rodar(cofre, orquestrador.ExecutorLLM(equipe), max_turnos=10, aviso=lambda _: None)
    assert execucao.parou_por == orquestrador.CICLO_COMPLETO
    assert [t.agente for t in execucao.turnos] == ["maestro", "dev", "maestro", "secretario"]
    notas = ler_cofre(cofre)
    para_humano = [r for r in mural.recados(notas) if r.meta["para"] == "arthur" and r.meta["status"] == "aberto"]
    assert len(para_humano) == 1 and para_humano[0].meta.get("pedido") == "Status do portfolio"
    assert validar(notas) == []
    diario = next((cofre / "Diario").glob("Execucao *.md")).read_text(encoding="utf-8")
    assert "Ferramentas usadas (motor próprio)" in diario and "deixar_recado" in diario


# ------------------------------------------------------------------ busca

def test_busca_poe_a_nota_do_assunto_primeiro(cofre):
    (cofre / "Conhecimento" / "LGPD.md").write_text("# LGPD\n\nLei de proteção de dados pessoais.", encoding="utf-8")
    (cofre / "Projetos" / "lgpd-guard.md").write_text("# lgpd-guard\n\nFiltro que aplica a LGPD em prompts.", encoding="utf-8")
    achados = Indice(ler_cofre(cofre)).buscar("lgpd", limite=2)
    assert [r.nota.nome for r in achados][0] == "LGPD"
    assert Indice(ler_cofre(cofre)).buscar("palavraquenaoexiste") == []
    assert all(r.nota.pasta == "Projetos" for r in Indice(ler_cofre(cofre)).buscar("lgpd", pasta="Projetos"))


# ------------------------------------------------------------------ avaliação

def test_avaliacao_mede_o_cenario(tmp_path):
    from cerebro import avaliacao

    cenario = next(c for c in avaliacao.carregar_cenarios() if c["id"] == "nota-de-conceito")
    equipe = EquipeFalsa({
        "maestro": [
            lambda m: chamar("deixar_recado", para="pesquisador", assunto="Nota MCP", texto="Explique MCP",
                             pedido="Nota sobre MCP") if "Entrada" in m[1]["content"] else
            chamar("deixar_recado", para="arthur", assunto="Nota pronta", texto="A nota [[MCP para leigos]] explica MCP.",
                   responde=_abertos(m, "maestro")),
            lambda m: Resposta("ok") if "Entrada" in m[1]["content"] else chamar("fechar_recado", nome=_abertos(m, "maestro")),
        ],
        "pesquisador": [
            chamar("escrever_nota", pasta="Conhecimento", titulo="MCP para leigos", conteudo="MCP é como uma tomada padrão."),
            lambda m: chamar("deixar_recado", para="maestro", assunto="Pronta", texto="[[MCP para leigos]]",
                             responde=_abertos(m, "pesquisador")),
            lambda m: chamar("fechar_recado", nome=_abertos(m, "pesquisador")),
        ],
    })
    rel = avaliacao.avaliar(equipe, [cenario], aviso=lambda _: None)
    r = rel["cenarios"][0]
    assert r["aprovado"], r
    assert r["checagens_ok"] == 3 and r["agentes"][:3] == ["maestro", "pesquisador", "maestro"]
    assert rel["resumo"]["aprovados"] == 1
    assert avaliacao.salvar(rel, tmp_path / "r.json").is_file()


def test_todos_os_cenarios_sao_validos():
    from cerebro import avaliacao

    ids = [c["id"] for c in avaliacao.carregar_cenarios()]
    assert len(ids) == len(set(ids)) >= 5
    for c in avaliacao.carregar_cenarios():
        assert c["titulo"] and c["pedido"] and c["checagens"]


# ------------------------------------------------------------------ cliente HTTP (formato OpenAI)

def test_cliente_openai_le_tool_calls_e_chamada_escrita_como_texto(monkeypatch):
    import httpx

    from cerebro.llm import ClienteOpenAI

    respostas = [
        {"choices": [{"message": {"content": "", "tool_calls": [
            {"id": "c1", "function": {"name": "ler_mural", "arguments": "{}"}}]}}], "usage": {"prompt_tokens": 10, "completion_tokens": 2}},
        {"choices": [{"message": {"content": 'vou chamar {"name": "buscar", "arguments": {"consulta": "rag"}}'}}]},
        {"choices": [{"message": {"content": "pronto"}}]},
    ]
    enviados = []

    def falso_post(url, json=None, headers=None, timeout=None):
        enviados.append(json)
        return httpx.Response(200, json=respostas.pop(0), request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", falso_post)
    cliente = ClienteOpenAI("qwen2.5:3b")
    ferramentas = esquema_openai()
    r1 = cliente.conversar([{"role": "user", "content": "oi"}], ferramentas)
    assert r1.chamadas[0].nome == "ler_mural" and r1.tokens_entrada == 10
    r2 = cliente.conversar([], ferramentas)
    assert r2.chamada_em_texto and r2.chamadas[0].argumentos == {"consulta": "rag"} and r2.texto == ""
    r3 = cliente.conversar([], [])
    assert r3.texto == "pronto" and "tools" not in enviados[-1]
    assert enviados[0]["model"] == "qwen2.5:3b" and enviados[0]["temperature"] == 0


def test_painel_mostra_a_avaliacao(cofre):
    from cerebro import painel

    vazio = painel.gerar(ler_cofre(cofre))
    assert "Ainda sem avaliação" in vazio
    rel = {"modelo": "qwen2.5:3b", "data": "2026-10-20T10:00",
           "resumo": {"cenarios": 2, "aprovados": 1, "entregou": 1.0, "ciclo_completo": 0.5, "cofre_integro": 1.0,
                      "checagens": 0.75, "turnos_medio": 4.5, "recusas_total": 3, "tokens_total": 900, "segundos_total": 600},
           "cenarios": [{"id": "nota-de-conceito", "aprovado": True, "checagens_ok": 3, "checagens_total": 3,
                         "agentes": ["maestro", "pesquisador"], "recusas": 1, "parou_por": "fim"}]}
    html_ = painel.gerar(ler_cofre(cofre), avaliacoes=[rel])
    assert "qwen2.5:3b" in html_ and "1/2" in html_ and "nota-de-conceito" in html_ and "maestro → pesquisador" in html_


def test_instrucao_tem_a_equipe_e_o_protocolo(cofre):
    from cerebro.agente import instrucao_de_sistema

    m = instrucao_de_sistema(cofre, "maestro")
    assert "- pesquisador:" in m and "- dev:" in m and "Pedido novo da Entrada" in m
    assert "Responda a quem pediu" in instrucao_de_sistema(cofre, "dev")


def test_motor_lembra_quem_para_com_recado_aberto(cofre):
    nome = _recado(cofre, "maestro", "dev", "Status")
    llm = RoteiroLLM([Resposta("feito"), chamar("fechar_recado", nome=nome), Resposta("agora sim")])
    r = rodar_turno(cofre, "dev", "teste", llm)
    assert r.lembretes == 1 and r.resposta == "agora sim"
    assert "Ainda estão abertos" in llm.recebido[1][-1]["content"]


def test_motor_corrige_so_a_forma_dos_argumentos(cofre):
    nome = _recado(cofre, "maestro", "dev", "Status")
    b = Bancada(cofre, "dev")
    ok, _ = b.executar("escrever_nota", {"pasta:": "projetos", "nome": "Status", "texto": "ok", "extra": 1})
    assert ok and (cofre / "Projetos" / "Status.md").is_file()
    ok, saida = b.executar("deixar_recado", {"para": "dev", "assunto": "x", "texto": "y", "nome": nome})
    assert not ok and "você mesmo" in saida and "'maestro'" in saida
    ok, _ = b.executar("deixar_recado", {"para": "maestro", "assunto": "x", "mensagem": "y", "recado": nome})
    assert ok
    ok, _ = b.executar("fechar_recado", {"recado": nome})
    assert ok


def test_pedido_padrao_vai_no_recado_e_sugestao_de_agente(cofre):
    from cerebro.agente import sugerir_agentes

    b = Bancada(cofre, "maestro", pedido_padrao="Nota sobre MCP")
    ok, saida = b.executar("deixar_recado", {"para": "pesquisador", "assunto": "MCP", "texto": "explique"})
    assert ok and ler_cofre(cofre)[saida.split(": ", 1)[1].lower()].meta["pedido"] == "Nota sobre MCP"
    assert sugerir_agentes(cofre, "Quero uma nota curta explicando um conceito")[0] == "pesquisador"
    assert sugerir_agentes(cofre, "Escreva um post de LinkedIn")[0] == "conteudo"


def test_busca_entende_plural():
    from cerebro.busca import termos

    assert termos("notas posts ações") == termos("nota post ação")


def test_responder_resolve_e_responde_e_deduzido(cofre):
    nome = _recado(cofre, "maestro", "dev", "Status do CI")
    ok, saida = Bancada(cofre, "dev").executar("deixar_recado", {"para": "maestro", "assunto": "CI verde", "texto": "verde"})
    assert ok and "resolvido" in saida
    notas = ler_cofre(cofre)
    assert notas[nome.lower()].meta["status"] == "feito"
    resposta = next(r for r in mural.recados(notas) if r.meta["de"] == "dev")
    assert resposta.meta["responde"] == nome  # deduzido: era o único recado aberto do maestro para o dev
    # recado para outro agente (não quem pediu) não fecha nada
    outro = _recado(cofre, "maestro", "dev", "Outro pedido")
    ok, saida = Bancada(cofre, "dev").executar("deixar_recado", {"para": "critico", "assunto": "revisa", "texto": "x"})
    assert ok and "resolvido" not in saida and ler_cofre(cofre)[outro.lower()].meta["status"] == "aberto"


def test_avaliacao_sobrevive_a_cenario_que_quebra(tmp_path):
    from cerebro import avaliacao

    class Quebrado:
        nome = "quebrado"

        def conversar(self, mensagens, ferramentas):
            raise TimeoutError("modelo não respondeu")

    cenarios = avaliacao.carregar_cenarios()[:2]
    rel = avaliacao.avaliar(Quebrado(), cenarios, aviso=lambda _: None, parcial=tmp_path / "p.json")
    assert rel["resumo"]["cenarios"] == 2 and all(c["parou_por"].startswith("erro: TimeoutError") for c in rel["cenarios"])
    assert (tmp_path / "p.json").is_file()
