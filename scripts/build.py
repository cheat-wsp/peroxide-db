#!/usr/bin/env python3
"""Gerador estático: lê data/raw/*.json e gera docs/ com Jinja2."""
import json
import re
import shutil
from pathlib import Path
from urllib.parse import unquote

from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader
from slugify import slugify

try:
    import lxml  # noqa
    PARSER = "lxml"
except ImportError:
    PARSER = "html.parser"

BASE = Path(__file__).resolve().parent.parent
RAW_DIR = BASE / "data" / "raw"
PAGES_JSON = BASE / "data" / "pages.json"
TEMPLATES = BASE / "src" / "templates"
STATIC = BASE / "src" / "static"
OUT = BASE / "docs"


def texto_puro(html: str) -> str:
    """Extrai texto puro de um HTML para o índice de busca."""
    try:
        return BeautifulSoup(html or "", PARSER).get_text(" ", strip=True)[:3000]
    except Exception:
        return ""


def reescrever_links_internos(html: str, slugs_validos: set[str]) -> str:
    """Converte <a href=/wiki/X> em links relativos pagina/x.html (só se slug existe)."""
    if not html:
        return ""
    soup = BeautifulSoup(html, PARSER)
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if href.startswith("/wiki/"):
            parte = unquote(href.split("/wiki/", 1)[1].split("?")[0].split("#")[0])
            if ":" in parte:
                # File:/Category: -> aponta pra fonte externa, remove link mas mantém texto
                a.unwrap() if False else None
                continue
            s = slugify(parte, lowercase=True)
            if s in slugs_validos:
                a["href"] = f"{s}.html"
            else:
                # mantém texto, remove link quebrado
                a["href"] = a.get("href", "#")
                a["rel"] = "nofollow"
        elif href.startswith("http"):
            a["rel"] = "nofollow"
    # remove imgs/scripts que sobraram
    for tag in soup.select("script, style, img, figure, aside, iframe, video, audio"):
        tag.decompose()
    return str(soup)


def carregar_paginas() -> list[dict]:
    """Carrega todas as páginas de data/raw/*.json (fallback p/ pages.json)."""
    paginas = []
    if RAW_DIR.exists():
        for f in sorted(RAW_DIR.glob("*.json")):
            try:
                paginas.append(json.loads(f.read_text(encoding="utf-8")))
            except Exception as e:
                print(f"[warn] {f.name}: {e}")
    if not paginas and PAGES_JSON.exists():
        print("[warn] sem raw/, usando só índice (sem seções).")
    return sorted(paginas, key=lambda p: p.get("slug", ""))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pagina").mkdir(exist_ok=True)
    (OUT / "categorias").mkdir(exist_ok=True)
    (OUT / "assets" / "data").mkdir(parents=True, exist_ok=True)

    paginas = carregar_paginas()
    print(f"Páginas carregadas: {len(paginas)}")
    if not paginas:
        print("Nada para gerar. Rode scripts/scrape.py primeiro.")
        return

    slugs = {p["slug"] for p in paginas}
    # Reescreve links internos + limpa html
    for p in paginas:
        for sec in p.get("sections", []):
            sec["html"] = reescrever_links_internos(sec.get("html", ""), slugs)

    # Agrupa por categoria
    por_cat: dict[str, list[dict]] = {}
    for p in paginas:
        por_cat.setdefault(p.get("category", "Outros"), []).append(p)
    categorias = sorted(por_cat.keys())
    cat_counts = {c: len(por_cat[c]) for c in categorias}

    def cat_slug(c: str) -> str:
        return slugify(c, lowercase=True) or "outros"

    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=True)

    # Contextos compartilhados por nível de profundidade (paths relativos)
    ctx_root = dict(categories=categorias, cat_counts=cat_counts, total=len(paginas),
                    asset="assets/", home="index.html", search_page="search.html",
                    cat_url={c: f"categorias/{cat_slug(c)}.html" for c in categorias},
                    page_url={p["slug"]: f"pagina/{p['slug']}.html" for p in paginas})
    ctx_sub = dict(categories=categorias, cat_counts=cat_counts, total=len(paginas),
                   asset="../assets/", home="../index.html", search_page="../search.html",
                   cat_url={c: f"../categorias/{cat_slug(c)}.html" for c in categorias},
                   page_url={p["slug"]: f"../pagina/{p['slug']}.html" for p in paginas})

    # index.html
    recent = sorted(paginas, key=lambda p: p.get("title", ""))[:24]
    (OUT / "index.html").write_text(
        env.get_template("index.html").render(**ctx_root, recent=[{"slug": p["slug"], "title": p["title"], "category": p.get("category", "Outros"), "summary": p.get("summary", "")} for p in recent]),
        encoding="utf-8")

    # search.html
    (OUT / "search.html").write_text(env.get_template("search.html").render(**ctx_root), encoding="utf-8")

    # categorias/*.html
    for cat in categorias:
        items = sorted(por_cat[cat], key=lambda p: p.get("title", ""))
        ctx = {k: v for k, v in ctx_sub.items() if k != "page_url"}
        html = env.get_template("category.html").render(
            **ctx, category=cat, pages=[{"slug": p["slug"], "title": p["title"], "summary": p.get("summary", "")} for p in items],
            page_url={p["slug"]: f"../pagina/{p['slug']}.html" for p in items})
        (OUT / "categorias" / f"{cat_slug(cat)}.html").write_text(html, encoding="utf-8")

    # pagina/*.html
    for p in paginas:
        rel = [l for l in p.get("internal_links", []) if l.get("slug") in slugs][:12]
        relacionados = []
        for l in rel:
            # título bonito: busca página real
            t = next((q["title"] for q in paginas if q["slug"] == l["slug"]), l.get("label") or l["slug"])
            relacionados.append({"slug": l["slug"], "title": t})
        html = env.get_template("page.html").render(
            **ctx_sub, page=p, related=relacionados,
            category_url=f"../categorias/{cat_slug(p.get('category', 'Outros'))}.html")
        (OUT / "pagina" / f"{p['slug']}.html").write_text(html, encoding="utf-8")

    # assets/data/*.json
    indice = [{"slug": p["slug"], "title": p["title"], "category": p.get("category", "Outros"), "summary": p.get("summary", "")} for p in paginas]
    (OUT / "assets" / "data" / "pages.json").write_text(json.dumps(indice, ensure_ascii=False, indent=2), encoding="utf-8")
    busca = [{"slug": p["slug"], "title": p["title"], "category": p.get("category", "Outros"),
              "content": texto_puro(" ".join(s.get("html", "") for s in p.get("sections", [])))} for p in paginas]
    (OUT / "assets" / "data" / "search-index.json").write_text(json.dumps(busca, ensure_ascii=False, indent=2), encoding="utf-8")

    # Estáticos + .nojekyll + CNAME-less
    for nome in ["style.css", "app.js", "favicon.svg"]:
        src = STATIC / nome
        if src.exists():
            shutil.copy(src, OUT / "assets" / nome)
    (OUT / ".nojekyll").write_text("", encoding="utf-8")

    print(f"Build OK: {len(paginas)} páginas, {len(categorias)} categorias -> {OUT}")


if __name__ == "__main__":
    main()
