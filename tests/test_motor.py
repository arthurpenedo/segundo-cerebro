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
    assert ok and (cofre / "Projetos" / "X.md").is_file() and not (cofre / "Conhecimento" / "X.md").exists()
    ok, saida = Bancada(cofre, "maestro").executar("escrever_nota", {"pasta": "Projetos", "titulo": "X", "conteudo": "y"})
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
    # recado para si mesmo respondendo a um recado: o destino é corrigido para quem pediu
    ok, saida = b.executar("deixar_recado", {"para": "dev", "assunto": "x", "texto": "y", "nome": nome})
    assert ok and "destino corrigido" in saida and "'maestro'" in saida
    assert ler_cofre(cofre)[nome.lower()].meta["status"] == "feito"
    # sem nenhum recado aberto para deduzir, continua recusado
    ok, saida = b.executar("deixar_recado", {"para": "dev", "assunto": "x", "mensagem": "y"})
    assert not ok and "você mesmo" in saida
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


def test_mural_mostra_o_proximo_passo(cofre):
    pedido = _recado(cofre, "maestro", "dev", "Status")
    assert f'responde="{pedido}"' in Bancada(cofre, "dev").ler_mural()
    resposta = mural.escrever_recado(cofre, "dev", "maestro", "CI verde", "verde", responde=pedido).stem
    texto = Bancada(cofre, "maestro").ler_mural()
    assert "Entregue a arthur" in texto and f'responde="{resposta}"' in texto


def test_nota_vai_para_a_unica_pasta_do_agente_e_link_quebrado_e_recusado(cofre):
    b = Bancada(cofre, "pesquisador")
    ok, saida = b.executar("escrever_nota", {"pasta": "pesquisador", "titulo": "MCP", "conteudo": "tomada padrão"})
    assert ok and (cofre / "Conhecimento" / "MCP.md").is_file()
    ok, saida = b.executar("deixar_recado", {"para": "maestro", "assunto": "pronto", "texto": "veja [[Nota que nao existe]]"})
    assert not ok and "não existe" in saida
    ok, _ = b.executar("deixar_recado", {"para": "maestro", "assunto": "pronto", "texto": "veja [[MCP]]"})
    assert ok


# ------------------------------------------------------------------ regras de 21/10 (avaliação com o 7b)

def _pedido(cofre: Path, nome: str, texto: str = "faça algo") -> str:
    (cofre / "00-Entrada" / f"{nome}.md").write_text(f"# {nome}\n\n{texto}\n", encoding="utf-8")
    return nome


def test_nota_com_link_sem_destino_vira_texto(cofre):
    ok, saida = Bancada(cofre, "pesquisador").executar(
        "escrever_nota", {"pasta": "Conhecimento", "titulo": "MCP", "conteudo": "Veja [[Model_context_protocol|o protocolo]]."})
    texto = (cofre / "Conhecimento" / "MCP.md").read_text(encoding="utf-8")
    assert ok and "[[" not in texto and "o protocolo" in texto and "viraram texto" in saida
    assert validar(ler_cofre(cofre)) == []


def test_pedido_vem_do_codigo_e_nao_do_modelo(cofre):
    _pedido(cofre, "Publicar o post hoje")
    pedido = _recado(cofre, "maestro", "conteudo", "post", pedido="Publicar o post hoje")
    ok, _ = Bancada(cofre, "conteudo").executar("deixar_recado", {"para": "maestro", "texto": "pronto",
                                                                  "pedido": "Post sobre a versão 1.0"})
    novo = [r for r in mural.recados(ler_cofre(cofre)) if r.meta.get("de") == "conteudo"][-1]
    assert ok and novo.meta["pedido"] == "Publicar o post hoje" and novo.meta["responde"] == pedido
    assert novo.meta["assunto"] == "post"  # sem assunto: herda o do recado respondido


def test_maestro_segue_o_papel_salvo_insistencia(cofre):
    maestro = Bancada(cofre, "maestro", pedido_padrao="x", indicados=["carreira"])
    ok, saida = maestro.executar("deixar_recado", {"para": "dev", "assunto": "a", "texto": "b"})
    assert not ok and "carreira" in saida
    ok, _ = maestro.executar("deixar_recado", {"para": "dev", "assunto": "a", "texto": "b"})
    assert ok  # repetiu: a escolha é dele


def test_critico_aprovado_vai_para_o_maestro(cofre):
    _pedido(cofre, "Post")
    pedido = _recado(cofre, "conteudo", "critico", "revisar", pedido="Post")
    ok, saida = Bancada(cofre, "critico").executar("deixar_recado", {"para": "conteudo", "texto": "aprovado, números conferem"})
    novo = [r for r in mural.recados(ler_cofre(cofre)) if r.meta.get("de") == "critico"][-1]
    assert ok and novo.meta["para"] == "maestro" and "maestro" in saida
    assert ler_cofre(cofre)[pedido.lower()].meta["status"] == "feito"


def test_terceira_ida_e_volta_vai_para_o_maestro(cofre):
    _pedido(cofre, "Post")
    for _ in range(2):
        _recado(cofre, "conteudo", "critico", "revisar", pedido="Post")
    ok, saida = Bancada(cofre, "conteudo", pedido_padrao="Post").executar(
        "deixar_recado", {"para": "critico", "assunto": "revisar", "texto": "nova versão"})
    novo = [r for r in mural.recados(ler_cofre(cofre)) if r.meta.get("de") == "conteudo"][-1]
    assert ok and novo.meta["para"] == "maestro" and "não girar em falso" in saida


def test_entrega_ao_humano_leva_a_resposta_do_agente(cofre):
    _pedido(cofre, "Status")
    resposta = mural.escrever_recado(cofre, "dev", "maestro", "status", "1.240 vagas e 20 testes (fonte: radar-skills)", pedido="Status").stem
    ok, _ = Bancada(cofre, "maestro").executar("deixar_recado", {"para": mural.HUMANO, "assunto": "status", "texto": "Pronto."})
    entrega = [r for r in mural.recados(ler_cofre(cofre)) if r.meta.get("para") == mural.HUMANO][-1]
    assert ok and "1.240 vagas e 20 testes" in entrega.corpo and "Resposta do dev" in entrega.corpo
    assert entrega.meta["responde"] == resposta and entrega.meta["pedido"] == "Status"


def test_responder_fecha_os_recados_antigos_da_mesma_pessoa_no_pedido(cofre):
    _pedido(cofre, "Post")
    a = _recado(cofre, "conteudo", "critico", "v1", pedido="Post")
    b = _recado(cofre, "conteudo", "critico", "v2", pedido="Post")
    ok, _ = Bancada(cofre, "critico").executar("deixar_recado", {"para": "conteudo", "texto": "ajustar: tirar o emoji"})
    notas = ler_cofre(cofre)
    assert ok and notas[a.lower()].meta["status"] == "feito" and notas[b.lower()].meta["status"] == "feito"


def test_turno_de_diario_nao_abre_recado(cofre):
    ok, saida = Bancada(cofre, "secretario", bloquear_recados=True).executar(
        "deixar_recado", {"para": "dev", "assunto": "a", "texto": "b"})
    assert not ok and "Diário" in saida


def test_agente_recebe_as_notas_do_pedido(cofre):
    from cerebro.agente import notas_do_pedido
    (cofre / "Projetos" / "radar-skills.md").write_text("# radar-skills\n\n1.240 vagas analisadas, 20 testes.\n", encoding="utf-8")
    contexto = notas_do_pedido(cofre, "quantas vagas o radar-skills analisou e quantos testes tem?")
    assert "[[radar-skills]]" in contexto and "1.240" in contexto


def test_juntar_relatorios_parciais(tmp_path):
    from cerebro import avaliacao
    base = {"entregou": True, "ciclo_completo": True, "cofre_integro": True, "checagens_ok": 1, "checagens_total": 1,
            "turnos": 3, "agentes": ["maestro"], "recusas": 0, "tokens": 10, "segundos": 1.0, "parou_por": "x"}
    for i, cid in enumerate(["entrevista", "nota-de-conceito"]):
        (tmp_path / f"{i}.json").write_text(
            __import__("json").dumps({"cenarios": [base | {"id": cid, "aprovado": True}]}), encoding="utf-8")
    rel = avaliacao.juntar(sorted(tmp_path.glob("*.json")), "qwen2.5:7b")
    assert rel["modelo"] == "qwen2.5:7b" and rel["resumo"]["aprovados"] == 2
    assert [c["id"] for c in rel["cenarios"]] == ["nota-de-conceito", "entrevista"]


def test_conteudo_passa_pelo_critico_antes_do_maestro(cofre):
    _pedido(cofre, "Post")
    pedido = _recado(cofre, "maestro", "conteudo", "post", pedido="Post")
    ok, saida = Bancada(cofre, "conteudo").executar("deixar_recado", {"para": "maestro", "texto": "post pronto"})
    novo = [r for r in mural.recados(ler_cofre(cofre)) if r.meta.get("de") == "conteudo"][-1]
    assert ok and novo.meta["para"] == "critico" and "revisão do critico" in saida
    assert ler_cofre(cofre)[pedido.lower()].meta["status"] == "feito"
    Bancada(cofre, "critico").executar("deixar_recado", {"para": "conteudo", "texto": "aprovado"})
    ok, _ = Bancada(cofre, "conteudo", pedido_padrao="Post").executar("deixar_recado", {"para": "maestro", "texto": "ok"})
    assert [r for r in mural.recados(ler_cofre(cofre)) if r.meta.get("de") == "conteudo"][-1].meta["para"] == "maestro"


def test_nota_sem_titulo_usa_o_cabecalho(cofre):
    ok, saida = Bancada(cofre, "carreira").executar("escrever_nota", {"conteudo": "# Perguntas\n\n1. O que é RAG?"})
    assert ok and (cofre / "Carreira" / "Perguntas.md").is_file()


def test_motor_entrega_o_que_o_agente_salvou_sem_responder(cofre):
    _pedido(cofre, "Nota MCP")
    pedido = _recado(cofre, "maestro", "pesquisador", "nota", pedido="Nota MCP")
    llm = RoteiroLLM([chamar("escrever_nota", pasta="Conhecimento", titulo="MCP", conteudo="MCP é..."),
                      Resposta("terminei", []), Resposta("terminei de novo", [])])
    rodar_turno(cofre, "pesquisador", f"recado aberto: {pedido}", llm, pedido="Nota MCP")
    notas = ler_cofre(cofre)
    resposta = [r for r in mural.recados(notas) if r.meta.get("de") == "pesquisador"][-1]
    assert notas[pedido.lower()].meta["status"] == "feito" and resposta.meta["para"] == "maestro"
    assert "[[MCP]]" in resposta.corpo and "automática" in resposta.corpo


def test_colchete_sem_fechar_nao_quebra_o_cofre(cofre):
    _pedido(cofre, "Nota MCP")
    _recado(cofre, "pesquisador", "maestro", "nota", pedido="Nota MCP")
    ok, _ = Bancada(cofre, "maestro").executar("deixar_recado", {"para": mural.HUMANO, "texto": "Veja [[MCP (Machine Conc."})
    assert ok and validar(ler_cofre(cofre)) == []


def test_diario_de_execucao_sem_link_inventado(cofre):
    execucao = orquestrador.Execucao()
    execucao.turnos.append(orquestrador.Turno("secretario", "fim", 0, 0, "Atualizei o [[Diário do dia 2026-10-21]].", 1.0))
    orquestrador._registrar(cofre, execucao)
    assert validar(ler_cofre(cofre)) == []


def test_so_o_maestro_distribui_trabalho(cofre):
    _pedido(cofre, "Post")
    _recado(cofre, "maestro", "conteudo", "post", pedido="Post")
    conteudo = Bancada(cofre, "conteudo", pedido_padrao="Post")
    ok, saida = conteudo.executar("deixar_recado", {"para": "carreira", "assunto": "faz pra mim", "texto": "prepare o post"})
    assert not ok and "não distribui trabalho" in saida
    ok, _ = conteudo.executar("deixar_recado", {"para": "critico", "assunto": "revisar", "texto": "post: ..."})
    assert ok  # o revisor dele pode


def test_ninguem_diz_que_publicou(cofre):
    _pedido(cofre, "Publicar")
    _recado(cofre, "critico", "maestro", "revisão", pedido="Publicar")
    maestro = Bancada(cofre, "maestro")
    for texto in ("O post foi publicado no LinkedIn.", "Pronto: https://www.linkedin.com/posts/arthur-123", "Postei hoje."):
        ok, saida = maestro.executar("deixar_recado", {"para": mural.HUMANO, "texto": texto})
        assert not ok and "NÃO foi publicado" in saida
    ok, _ = maestro.executar("deixar_recado", {"para": mural.HUMANO, "texto": "O post está pronto; publico quando você aprovar."})
    assert ok


def test_checagem_entrega_nao_cita():
    from cerebro import avaliacao
    c = [c for c in avaliacao.carregar_cenarios() if c["id"] == "nao-publica-sozinho"][0]
    assert any("entrega_nao_cita" in ch for ch in c["checagens"])
