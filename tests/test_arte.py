from cerebro.arte import gerar_html, ler_post

POST = """---
projeto: x
link: https://arthurpenedo.github.io/x/
arte_titulo: Um titulo bem grande aqui
arte_exemplo: antes <b> → depois
arte_num1: 94% | protegidos
arte_num2: 0 de 26 | alarmes
---
texto
"""


def test_html_da_arte_usa_campos_e_escapa(tmp_path):
    post = tmp_path / "Post - x.md"
    post.write_text(POST, encoding="utf-8")
    pagina = gerar_html(ler_post(post))
    assert "<span>bem grande aqui</span>" in pagina and "antes &lt;b&gt;" in pagina
    assert "<b>94%</b><span>protegidos</span>" in pagina and "/x</b>" in pagina
