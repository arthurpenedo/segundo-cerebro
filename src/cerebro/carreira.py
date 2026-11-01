"""Funil de carreira sem gastar tokens: radar dos e-mails de recrutamento e rascunhos de follow-up.

Tudo aqui é script (regex e IMAP), sem modelo de linguagem. A rotina só passa ao agente o resumo do que é novo.

    cerebro emails [--dias 3]        # lê o Gmail (só leitura) e registra respostas de vagas e prazos
    cerebro emails --configurar      # guarda a senha de app do Gmail no cofre de senhas do Windows
    cerebro followups [--max 5]      # rascunhos de follow-up para candidaturas de 7 a 14 dias sem resposta

A senha vem do cofre do sistema (`keyring`, serviço "cerebro-gmail") ou da variável CEREBRO_GMAIL_SENHA. Nunca de arquivo.
"""

from __future__ import annotations

import email
import imaplib
import json
import os
import re
from datetime import date, timedelta
from email.header import decode_header, make_header
from email.utils import parseaddr
from html import unescape
from pathlib import Path
from urllib.parse import quote_plus

RADAR = "Vagas/Radar de emails.md"
VISTOS = "Vagas/.radar-emails.json"
FOLLOWUPS = "Vagas/Follow-ups.md"
FEITOS = "Vagas/.followups.json"
CANDIDATURAS = "Vagas/Candidaturas.md"
SERVICO = "cerebro-gmail"
USUARIO = "penedo.arthur@gmail.com"

# Ordem importa: recusa antes de avanço ("unfortunately ... next steps" é recusa).
CATEGORIAS = [
    ("recusa", r"unfortunately|not (be )?moving forward|decided to (move|proceed) with other|other candidates|"
               r"infelizmente|não (vamos|seguiremos|daremos)|nao (vamos|seguiremos)|outros candidatos|position has been filled"),
    ("avanço", r"interview|entrevista|assessment|avalia[çc][ãa]o|teste (t[ée]cnico|online)|video|vídeo|survey|questionnaire|"
               r"question[áa]rio|next step|pr[óo]xima etapa|moving forward|move forward|schedule|agendar|calendly|"
               r"few (more )?questions|case study|desafio|exam|prova|invitation|convite|offer|proposta"),
    ("confirmação", r"received your application|thank you for applying|application (was )?(received|submitted)|"
                    r"recebemos (a )?sua candidatura|candidatura (recebida|enviada)|obrigad[oa] por se candidatar"),
]
RECRUTAMENTO = re.compile(r"applica|candidat|vaga|job|position|role|recruit|recrut|talent|hiring|interview|entrevista|"
                          r"greenhouse|lever|ashby|workable|gupy|inhire|smartrecruiters|teamtailor|recruitee", re.I)
RUIDO = re.compile(r"jobalerts?|job alert|alerta de vaga|newsletter|digest|vagas para você|jobs you may|"
                   r"linkedin\.com.*(notifications|messages-noreply)|unsubscribe from job", re.I)
PRAZO = re.compile(r"[^.\n]{0,120}\b(deadline|due|by (monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
                   r"last day|expires?|within \d+|prazo|até (o dia|dia|segunda|terça|quarta|quinta|sexta)|"
                   r"no máximo|in the next (one|two|\d+)|nas próximas)[^.\n]{0,140}", re.I)


def _txt(valor: str | None) -> str:
    try:
        return str(make_header(decode_header(valor or "")))
    except (UnicodeDecodeError, LookupError):
        return valor or ""


def _corpo(msg: email.message.Message, limite: int = 6000) -> str:
    partes = msg.walk() if msg.is_multipart() else [msg]
    texto, html_txt = "", ""
    for p in partes:
        tipo = p.get_content_type()
        if tipo not in ("text/plain", "text/html") or p.get_filename():
            continue
        try:
            bruto = p.get_payload(decode=True).decode(p.get_content_charset() or "utf-8", errors="replace")
        except (AttributeError, LookupError):
            continue
        if tipo == "text/plain" and not texto:
            texto = bruto
        elif tipo == "text/html" and not html_txt:
            html_txt = unescape(re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(style|script).*?</\1>", "", bruto)))
    return re.sub(r"\s+", " ", texto or html_txt)[:limite]


def classificar(remetente: str, assunto: str, corpo: str) -> str | None:
    """Categoria de um e-mail de recrutamento (recusa, avanço, confirmação) ou None se não for de vaga."""
    tudo = f"{assunto} {corpo[:3000]}"
    if RUIDO.search(f"{remetente} {assunto}") or not RECRUTAMENTO.search(f"{remetente} {tudo}"):
        return None
    for nome, padrao in CATEGORIAS:
        if re.search(padrao, tudo, re.I):
            return nome
    return None


def prazo(corpo: str) -> str:
    m = PRAZO.search(corpo)
    return m.group(0).strip(" ,;") if m else ""


def senha_gmail(usuario: str = USUARIO) -> str:
    if os.environ.get("CEREBRO_GMAIL_SENHA"):
        return os.environ["CEREBRO_GMAIL_SENHA"]
    try:
        import keyring
    except ImportError:
        return ""
    return keyring.get_password(SERVICO, usuario) or ""


def configurar(usuario: str = USUARIO) -> str:
    """Pede a senha de app do Gmail no terminal (sem eco) e guarda no cofre do Windows."""
    import getpass

    import keyring

    keyring.set_password(SERVICO, usuario, getpass.getpass(f"Senha de app do Gmail para {usuario}: ").replace(" ", ""))
    return "Senha guardada no cofre de senhas do Windows."


def radar_emails(raiz: str | Path, hoje: date | None = None, dias: int = 3, conexao=None,
                 usuario: str = USUARIO) -> dict:
    """Lê (sem marcar como lido) os e-mails recentes, registra os de vaga no radar e cria tarefa para os avanços.

    Devolve {"novos": [...], "avancos": [...]} — cada item tem data, de, assunto, categoria, prazo.
    """
    raiz, hoje = Path(raiz), hoje or date.today()
    if conexao is None:
        senha = senha_gmail(usuario)
        if not senha:
            return {"erro": "sem senha do Gmail: rode `cerebro emails --configurar`", "novos": [], "avancos": []}
        conexao = imaplib.IMAP4_SSL("imap.gmail.com")
        conexao.login(usuario, senha)
    arq_vistos = raiz / VISTOS
    vistos = set(json.loads(arq_vistos.read_text(encoding="utf-8"))) if arq_vistos.exists() else set()
    conexao.select("INBOX", readonly=True)
    desde = (hoje - timedelta(days=dias)).strftime("%d-%b-%Y")
    _, dados = conexao.search(None, f"(SINCE {desde})")
    novos = []
    for num in (dados[0] or b"").split():
        _, partes = conexao.fetch(num, "(BODY.PEEK[])")
        bruto = next((p[1] for p in partes if isinstance(p, tuple)), b"")
        msg = email.message_from_bytes(bruto)
        mid = msg.get("Message-ID") or f"{msg.get('Date')}|{msg.get('Subject')}"
        if mid in vistos:
            continue
        vistos.add(mid)
        de, assunto = _txt(msg.get("From")), _txt(msg.get("Subject"))
        corpo = _corpo(msg)
        cat = classificar(de, assunto, corpo)
        if cat:
            nome, end = parseaddr(de)
            novos.append({"data": (msg.get("Date") or "")[:22], "de": nome or end, "email": end, "assunto": assunto[:140],
                          "categoria": cat, "prazo": prazo(corpo)[:240]})
    try:
        conexao.logout()
    except (imaplib.IMAP4.error, OSError):
        pass
    arq_vistos.parent.mkdir(parents=True, exist_ok=True)
    arq_vistos.write_text(json.dumps(sorted(vistos)[-3000:]), encoding="utf-8")
    avancos = [n for n in novos if n["categoria"] == "avanço"]
    if novos:
        radar = raiz / RADAR
        cab = "" if radar.exists() else "---\ntipo: radar\n---\n# Radar de e-mails de recrutamento\n\nGerado por `cerebro emails` (só leitura).\n"
        linhas = [f"\n## {hoje.isoformat()}"] + [
            f"- **{n['categoria']}** · {n['de']} · {n['assunto']}" + (f" · ⏰ {n['prazo']}" if n["prazo"] else "")
            for n in sorted(novos, key=lambda n: ["avanço", "recusa", "confirmação"].index(n["categoria"]))]
        with radar.open("a", encoding="utf-8") as f:
            f.write(cab + "\n".join(linhas) + "\n")
    if avancos:
        tarefas = raiz / "Tarefas.md"
        texto = tarefas.read_text(encoding="utf-8") if tarefas.exists() else "# Tarefas\n"
        novas = "".join(f"- [ ] Vaga avançou: responder \"{n['assunto'][:90]}\" ({n['de']})"
                        f"{' — prazo: ' + n['prazo'][:120] if n['prazo'] else ''} 📅 {hoje.isoformat()}\n" for n in avancos)
        tarefas.write_text(texto + ("" if texto.endswith("\n") else "\n") + novas, encoding="utf-8")
    return {"novos": novos, "avancos": avancos}


EN = re.compile(r"(engineer|analyst|specialist|assistant|associate|developer|support|manager|agent|trainer|tester|"
                r"representative|executive|coordinator|writer|rater|annotator|evaluator|operations|customer|remote)", re.I)
PT = re.compile(r"(analista|desenvolvedor|assistente|engenheiro|programador|estagi|atendimento|suporte|cientista|"
                r"qualidade|dados|opera[çc][õo]es|automa[çc])", re.I)
_DATA_SECAO = re.compile(r"(\d{4})-(\d{2})-(\d{2})|(\d{1,2})/(\d{1,2})(?:/(\d{4}))?")


def _data(texto: str, ano: int) -> date | None:
    m = _DATA_SECAO.search(texto)
    if not m:
        return None
    try:
        if m.group(1):
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return date(int(m.group(6) or ano), int(m.group(5)), int(m.group(4)))
    except ValueError:
        return None


def candidaturas_enviadas(texto: str, ano: int) -> list[dict]:
    """Lê as tabelas de Candidaturas.md (dois formatos) e devolve [{empresa, vaga, data, ingles}] das enviadas."""
    saida, secao_data, secao, cab = [], None, "", []
    for linha in texto.splitlines():
        if linha.startswith("#"):
            secao, secao_data, cab = linha, _data(linha, ano) or secao_data, []
            continue
        if not linha.startswith("|"):
            continue
        cel = [c.strip() for c in linha.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cel if c):
            continue
        if not cab and not re.search(r"enviad", linha, re.I):
            cab = [c.lower() for c in cel]
            continue
        if not re.search(r"\benviad[ao]s?\b", linha, re.I) or re.search(r"n[ãa]o enviad|não enviada", linha, re.I):
            continue
        if "empresa" in cab and "vaga" in cab:
            empresa, vaga = cel[cab.index("empresa")], cel[cab.index("vaga")]
            quando = _data(cel[cab.index("data")], ano) if "data" in cab else None
        else:
            empresa, _, vaga = cel[0].partition(":")
            quando = None
            if not vaga:
                continue
        vaga = re.sub(r"\s*\([^)]*\)\s*$", "", vaga.replace("**", "")).strip()
        empresa = re.sub(r"\s*\([^)]*\)", "", empresa.replace("**", "")).strip()
        if not empresa or not vaga or len(empresa) > 60:
            continue
        ingles = bool(re.search(r"USD|internacional|gring", secao) or EN.search(vaga)) and not PT.search(vaga)
        saida.append({"empresa": empresa, "vaga": vaga, "data": quando or secao_data, "ingles": ingles})
    return saida


def _mensagem(c: dict) -> str:
    quando = c["data"].strftime("%d/%m") if c["data"] else ""
    if c["ingles"]:
        return (f"Hi! I applied for the {c['vaga']} position at {c['empresa']}"
                f"{' on ' + c['data'].strftime('%b %d') if c['data'] else ''} and I'm still very interested. "
                "I bring hands-on experience in customer service operations and AI automation at Itaú Unibanco, "
                "and I'd be glad to share more. Is there any update on the process? Thank you! — Arthur Penedo")
    return (f"Olá! Me candidatei para a vaga de {c['vaga']} na {c['empresa']}{' em ' + quando if quando else ''} e sigo "
            "muito interessado. Tenho experiência em operações de atendimento e automação com IA no Itaú Unibanco e "
            "posso contar mais. Há alguma atualização sobre o processo? Obrigado! — Arthur Penedo")


def followups(raiz: str | Path, hoje: date | None = None, maximo: int = 5, de: int = 7, ate: int = 14) -> list[dict]:
    """Rascunhos de follow-up para candidaturas enviadas há `de`–`ate` dias, sem resposta no radar e sem follow-up feito."""
    raiz, hoje = Path(raiz), hoje or date.today()
    arq = raiz / CANDIDATURAS
    if not arq.exists():
        return []
    radar = (raiz / RADAR).read_text(encoding="utf-8").lower() if (raiz / RADAR).exists() else ""
    arq_feitos = raiz / FEITOS
    feitos = set(json.loads(arq_feitos.read_text(encoding="utf-8"))) if arq_feitos.exists() else set()
    escolhidos, empresas = [], {k.split("|")[0] for k in feitos}  # uma vez por empresa, nunca insistir
    for c in candidaturas_enviadas(arq.read_text(encoding="utf-8"), hoje.year):
        chave = f"{c['empresa']}|{c['vaga']}".lower()
        idade = (hoje - c["data"]).days if c["data"] else -1
        if not de <= idade <= ate or chave in feitos or c["empresa"].lower() in radar or c["empresa"].lower() in empresas:
            continue
        empresas.add(c["empresa"].lower())
        escolhidos.append(c | {"chave": chave, "mensagem": _mensagem(c)})
        if len(escolhidos) >= maximo:
            break
    if escolhidos:
        nota = raiz / FOLLOWUPS
        cab = "" if nota.exists() else ("---\ntipo: followups\n---\n# Follow-ups de candidaturas\n\nGerado por `cerebro followups`. "
                                        "Envie pelo LinkedIn (procure o recrutador no link) e marque [x].\n")
        blocos = [f"\n## {hoje.isoformat()}"]
        for c in escolhidos:
            busca = "https://www.linkedin.com/search/results/people/?keywords=" + quote_plus(f"{c['empresa']} recruiter")
            blocos.append(f"- [ ] **{c['empresa']}** · {c['vaga']} ({(hoje - c['data']).days} dias) · [achar recrutador]({busca})\n"
                          f"  > {c['mensagem']}")
        with nota.open("a", encoding="utf-8") as f:
            f.write(cab + "\n".join(blocos) + "\n")
        arq_feitos.write_text(json.dumps(sorted(feitos | {c["chave"] for c in escolhidos})), encoding="utf-8")
    return escolhidos
