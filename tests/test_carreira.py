from datetime import date
from email.message import EmailMessage

from cerebro import carreira, dia

HOJE = date(2026, 11, 2)


def test_classifica_recusa_avanco_confirmacao_e_ignora_ruido():
    assert carreira.classificar("Talent <jobs@x.com>", "Your application", "Unfortunately we decided to move "
                                "forward with other candidates. Next steps...") == "recusa"
    assert carreira.classificar("Lauren <hr@bst.com>", "One-way video interview", "record your video") == "avanço"
    assert carreira.classificar("Greenhouse <no-reply@greenhouse.io>", "Thank you for applying", "We received your "
                                "application") == "confirmação"
    assert carreira.classificar("LinkedIn <jobalerts-noreply@linkedin.com>", "Vagas para você", "interview") is None
    assert carreira.classificar("Loja <promo@loja.com>", "Black Friday", "50% off") is None
    assert carreira.classificar("Tob", "Thanks for your interest in Cloudwalk", "after reviewing your application we decided to not move "
                                "forward at this time") == "recusa"
    assert carreira.classificar("Codecademy", "50% off Pro ends today", "interview prep course") is None
    assert carreira.classificar("Ciklum Career", "Just checking in — your application draft is waiting", "") is None


def test_prazo_pega_a_frase_do_deadline():
    corpo = "Hi Arthur. The last day to submit is Thursday, October 29, 2026 at 11:45 PM. Good luck."
    assert "October 29, 2026" in carreira.prazo(corpo)
    assert carreira.prazo("Sem data nenhuma aqui.") == ""


CANDIDATURAS = """# Candidaturas
## Leva internacional 2 — 30 vagas gringas (27/10/2026)
| Vaga | Status | Notas |
|---|---|---|
| Higher Options: Executive Assistant – Remote (LinkedIn Simplificada) | **enviada** | pede 2+ anos |
| Chosan: Virtual Assistant (LinkedIn Simplificada) | **enviada** | — |
| Velha: Analista (LinkedIn) | não enviada | CAPTCHA |

## Levas diárias
| Data | Empresa | Vaga | Fonte | Status |
|---|---|---|---|---|
| 24/10 | Jobgether | QA Engineer | LinkedIn | Enviada |
| 24/10 | Jobgether | Founders Associate | LinkedIn | Enviada |
| 01/11 | Nova SA | Analista de Dados Júnior | Gupy | Enviada |
"""


def test_le_os_dois_formatos_de_tabela():
    c = carreira.candidaturas_enviadas(CANDIDATURAS, 2026)
    assert [(x["empresa"], x["vaga"]) for x in c] == [
        ("Higher Options", "Executive Assistant – Remote"), ("Chosan", "Virtual Assistant"),
        ("Jobgether", "QA Engineer"), ("Jobgether", "Founders Associate"), ("Nova SA", "Analista de Dados Júnior")]
    assert c[0]["data"] == date(2026, 10, 27) and c[2]["data"] == date(2026, 10, 24)
    assert c[0]["ingles"] and not c[4]["ingles"]
    elgin = "## x (20/10/2026)\n| A | B |\n|---|---|\n| Elgin: Analista de Sistemas Jr | enviada |\n"
    assert not carreira.candidaturas_enviadas(elgin, 2026)[0]["ingles"]  # vaga brasileira sem acento é PT


def _cofre(tmp_path, radar=""):
    (tmp_path / "Vagas").mkdir()
    (tmp_path / carreira.CANDIDATURAS).write_text(CANDIDATURAS, encoding="utf-8")
    if radar:
        (tmp_path / carreira.RADAR).write_text(radar, encoding="utf-8")
    return tmp_path


def test_followups_uma_por_empresa_na_janela_sem_resposta_e_sem_repetir(tmp_path):
    raiz = _cofre(tmp_path, radar="- **recusa** · Chosan · Your application")
    f = carreira.followups(raiz, date(2026, 11, 3))
    assert [x["empresa"] for x in f] == ["Higher Options", "Jobgether"]  # Chosan respondeu; Nova SA tem 1 dia
    assert "Hi! I applied for the Executive Assistant – Remote position at Higher Options" in f[0]["mensagem"]
    nota = (raiz / carreira.FOLLOWUPS).read_text(encoding="utf-8")
    assert "achar recrutador" in nota and "Higher+Options+recruiter" in nota
    assert carreira.followups(raiz, date(2026, 11, 3)) == []  # não volta à mesma empresa (nem por outra vaga)


class GmailFalso:
    def __init__(self, mensagens):
        self.mensagens = mensagens
        self.readonly = None

    def select(self, caixa, readonly=False):
        self.readonly = readonly

    def search(self, charset, criterio):
        return "OK", [" ".join(str(i) for i in range(1, len(self.mensagens) + 1)).encode()]

    def fetch(self, num, partes):
        assert "PEEK" in partes  # nunca marca como lido
        return "OK", [(b"1", self.mensagens[int(num) - 1].as_bytes()), b")"]

    def logout(self):
        pass


def _msg(mid, de, assunto, corpo):
    m = EmailMessage()
    m["Message-ID"], m["From"], m["Subject"], m["Date"] = mid, de, assunto, "Sat, 31 Oct 2026 10:00:00 +0000"
    m.set_content(corpo)
    return m


def test_radar_registra_avanco_com_prazo_cria_tarefa_e_nao_repete(tmp_path):
    raiz = _cofre(tmp_path)
    gmail = GmailFalso([
        _msg("<1>", "Lauren <hr@bst.com>", "One-way video interview invitation",
             "Please record your video. The deadline is Thursday, October 29, 2026 at 11:45 PM."),
        _msg("<2>", "Loja <promo@loja.com>", "Ofertas", "Compre já"),
        _msg("<3>", "Jobs <no-reply@ashbyhq.com>", "Thank you for applying", "We received your application."),
    ])
    r = carreira.radar_emails(raiz, HOJE, conexao=gmail)
    assert gmail.readonly is True
    assert [n["categoria"] for n in r["novos"]] == ["avanço", "confirmação"] and len(r["avancos"]) == 1
    radar = (raiz / carreira.RADAR).read_text(encoding="utf-8")
    assert "**avanço** · Lauren · One-way video interview invitation · ⏰" in radar
    assert "Vaga avançou" in (raiz / "Tarefas.md").read_text(encoding="utf-8")
    assert carreira.radar_emails(raiz, HOJE, conexao=GmailFalso(gmail.mensagens))["novos"] == []


def test_radar_sem_senha_nao_quebra(tmp_path, monkeypatch):
    monkeypatch.delenv("CEREBRO_GMAIL_SENHA", raising=False)
    monkeypatch.setattr(carreira, "senha_gmail", lambda usuario=carreira.USUARIO: "")
    assert "cerebro emails --configurar" in carreira.radar_emails(tmp_path, HOJE)["erro"]


def test_rotina_so_aumenta_o_prompt_quando_uma_vaga_avanca(tmp_path):
    avanco = {"de": "Lauren", "assunto": "Video interview", "prazo": "until Thursday", "categoria": "avanço"}
    radar_vazio = lambda raiz, hoje: {"novos": [], "avancos": []}  # noqa: E731
    radar_avanco = lambda raiz, hoje: {"novos": [avanco], "avancos": [avanco]}  # noqa: E731
    sem_follow = lambda raiz, hoje: []  # noqa: E731
    extra, rel = dia.passo_carreira(tmp_path, HOJE, radar_vazio, sem_follow)
    assert extra == "" and "0 de vaga" in rel
    extra, rel = dia.passo_carreira(tmp_path, HOJE, radar_avanco, lambda r, h: [{"empresa": "X"}])
    assert "Lauren · Video interview · prazo: until Thursday" in extra and dia.HISTORIAS in extra
    assert "1 avanços" in rel and "Follow-ups prontos para enviar: 1" in rel

    def executor(texto, raiz):
        executor.texto = texto
        return "ok"

    (tmp_path / "Para o Claude.md").write_text("# Para o Claude\n", encoding="utf-8")
    (tmp_path / "Tarefas.md").write_text("# Tarefas\n", encoding="utf-8")
    saida = dia.rodar_rotina(tmp_path, executor, hoje=HOJE, carreira=(radar_avanco, sem_follow))
    assert "2e. Vagas que AVANÇARAM" in executor.texto and executor.texto.index("2e.") < executor.texto.index("3. Olhe")
    assert "Carreira (feito por script)" in saida


VIDA = """# Rotina de vida
## Segunda a sexta
- 09:00 Acordar
- 19:00–00:00 Faculdade
## Sábado
- 10:00–12:00 Projeto de IA
## Domingo
- 18:00 Revisão da semana
"""


def test_agenda_do_dia_por_dia_da_semana(tmp_path):
    (tmp_path / dia.VIDA).write_text(VIDA, encoding="utf-8")
    assert dia.agenda_do_dia(tmp_path, date(2026, 11, 4)) == ["- 09:00 Acordar", "- 19:00–00:00 Faculdade"]  # quarta
    assert dia.agenda_do_dia(tmp_path, date(2026, 11, 7)) == ["- 10:00–12:00 Projeto de IA"]  # sábado
    assert dia.agenda_do_dia(tmp_path, date(2026, 11, 8)) == ["- 18:00 Revisão da semana"]  # domingo
    assert dia.agenda_do_dia(tmp_path / "nada", date(2026, 11, 8)) == []
    hoje = dia.gerar_hoje(tmp_path, date(2026, 11, 4)).read_text(encoding="utf-8")
    assert "## 🗓️ Seu dia (quarta)" in hoje and "- 19:00–00:00 Faculdade" in hoje


class SmtpFalso:
    def send_message(self, msg):
        self.msg = msg

    def quit(self):
        pass


def test_resumo_vai_so_para_o_proprio_arthur_sem_colchetes(tmp_path):
    (tmp_path / "Hoje.md").write_text("---\ntipo: gerada\n---\n# Hoje\n- ler [[Vagas/Follow-ups|follow-ups]] e [[Tarefas]]\n",
                                      encoding="utf-8")
    smtp = SmtpFalso()
    assert "enviado" in carreira.enviar_resumo(tmp_path, HOJE, smtp=smtp)
    assert smtp.msg["To"] == smtp.msg["From"] == carreira.USUARIO and smtp.msg["Subject"] == "Seu dia · 02/11"
    corpo = smtp.msg.get_content()
    assert "ler follow-ups e Tarefas" in corpo and "tipo: gerada" not in corpo
