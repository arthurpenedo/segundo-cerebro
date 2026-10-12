"""Arte vertical (1080x1350) para post de LinkedIn, a partir do frontmatter do rascunho.

Campos usados: projeto, link, arte_titulo, arte_exemplo, arte_num1 e arte_num2 ("número | legenda").
O HTML é renderizado com o Edge/Chrome headless que já existe na máquina: nada para instalar.
"""

from __future__ import annotations

import hashlib
import html
import re
import shutil
import subprocess
from pathlib import Path

import yaml

# (fundo 1, fundo 2, destaque) — a cor é escolhida pelo nome do projeto, então cada projeto tem a sua
PALETAS = [("#2b3a8c", "#0b0d1f", "#7db4ff"), ("#0f5c4a", "#081515", "#5eead4"), ("#6b2a8c", "#140b1f", "#d8b4fe"),
           ("#8c4a2b", "#1f120b", "#fdba74"), ("#2b6b8c", "#0b161f", "#7dd3fc"), ("#8c2b4a", "#1f0b12", "#fda4af")]

NAVEGADORES = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
               r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
               r"C:\Program Files\Google\Chrome\Application\chrome.exe", "msedge", "google-chrome", "chromium"]


def ler_post(arquivo: Path) -> dict:
    texto = arquivo.read_text(encoding="utf-8")
    m = re.match(r"---\r?\n(.*?)\r?\n---", texto, re.S)
    if not m:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        # rascunho escrito à mão com aspas no meio do valor: lê "chave: valor" linha a linha
        return {k.strip(): v.strip() for k, _, v in (l.partition(":") for l in m.group(1).splitlines()) if v}


def _num(campo: str | None) -> tuple[str, str]:
    numero, _, legenda = str(campo or "").partition("|")
    return html.escape(numero.strip()), html.escape(legenda.strip())


def gerar_html(meta: dict) -> str:
    projeto = str(meta.get("projeto", "projeto"))
    c1, c2, destaque = PALETAS[int(hashlib.md5(projeto.encode()).hexdigest(), 16) % len(PALETAS)]
    titulo = html.escape(str(meta.get("arte_titulo", projeto)))
    palavras = titulo.split()
    if len(palavras) > 3:  # destaca as últimas palavras do título
        titulo = " ".join(palavras[:-3]) + f' <span>{" ".join(palavras[-3:])}</span>'
    exemplo = html.escape(str(meta.get("arte_exemplo", ""))).replace("→", "<br><b class='seta'>↓</b><br>")
    (n1, l1), (n2, l2) = _num(meta.get("arte_num1")), _num(meta.get("arte_num2"))
    link = str(meta.get("link", f"https://github.com/arthurpenedo/{projeto}")).replace("https://", "").rstrip("/")
    dominio, _, caminho = link.partition("/")
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0}}
body{{width:1080px;height:1350px;background:radial-gradient(circle at 20% 0%,{c1} 0%,{c2} 70%);font-family:Inter,Segoe UI,sans-serif;
color:#fff;padding:84px 72px;display:flex;flex-direction:column}}
.tag{{align-self:flex-start;background:#ffffff1a;border:1px solid #ffffff33;border-radius:999px;padding:10px 22px;font-size:26px;font-weight:600}}
h1{{font-size:86px;line-height:1.06;font-weight:800;margin-top:64px;letter-spacing:-1.5px}}
h1 span{{color:{destaque}}}
.ex{{margin-top:72px;background:#fff;color:#1d1d22;border-radius:26px;padding:42px 44px;font-size:37px;line-height:1.45;
box-shadow:0 30px 80px #0008}}
.ex .seta{{color:{c1};font-size:34px}}
.nums{{display:flex;gap:24px;margin-top:64px}}
.n{{flex:1;background:#ffffff12;border:1px solid #ffffff26;border-radius:22px;padding:30px 30px}}
.n b{{display:block;font-size:76px;font-weight:800;color:{destaque};letter-spacing:-1px}}
.n span{{font-size:27px;color:#d6dbf5;line-height:1.35}}
.rodape{{margin-top:auto;display:flex;justify-content:space-between;align-items:flex-end;font-size:26px;color:#d6dbf5}}
.rodape b{{color:#fff;font-size:30px}}
</style></head><body>
<div class="tag">{html.escape(projeto)} · projeto open source</div>
<h1>{titulo}</h1>
<div class="ex">{exemplo}</div>
<div class="nums"><div class="n"><b>{n1}</b><span>{l1}</span></div><div class="n"><b>{n2}</b><span>{l2}</span></div></div>
<div class="rodape"><div><b>Grátis e de código aberto</b><br>feito por Arthur Penedo</div>
<div style="text-align:right">{html.escape(dominio)}<br><b>/{html.escape(caminho)}</b></div></div>
</body></html>"""


def renderizar(html_arquivo: Path, png: Path) -> Path:
    navegador = next((n for n in NAVEGADORES if Path(n).exists() or shutil.which(n)), None)
    if navegador is None:
        raise RuntimeError("nenhum Edge/Chrome encontrado para gerar a imagem")
    subprocess.run([navegador, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--window-size=1080,1350",
                    "--force-device-scale-factor=1", "--virtual-time-budget=6000", f"--screenshot={png.resolve()}",
                    html_arquivo.resolve().as_uri()], capture_output=True, timeout=120)
    if not png.exists():
        raise RuntimeError("o navegador não gerou a imagem")
    return png


def gerar_arte(post: str | Path, destino: str | Path | None = None) -> Path:
    post = Path(post)
    meta = ler_post(post)
    projeto = meta.get("projeto", post.stem.replace("Post - ", ""))
    destino = Path(destino) if destino else post.with_name(f"Imagem - {projeto}.png")
    html_arquivo = destino.with_suffix(".html")
    html_arquivo.write_text(gerar_html(meta), encoding="utf-8")
    renderizar(html_arquivo, destino)
    html_arquivo.unlink(missing_ok=True)
    return destino
