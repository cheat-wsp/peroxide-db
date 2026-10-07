#!/usr/bin/env python3
"""Scraper do wiki Peroxide Roblox — comentado em português.

Lê /root/links.md, baixa só essas URLs, extrai texto estruturado
e salva JSON por página em data/raw/{slug}.json + índices.
"""
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx
try:
    import lxml  # noqa: F401
    PARSER = "lxml"
except ImportError:
    PARSER = "html.parser"  # fallback quando lxml não tem wheel (ex: Termux/Android)
from bs4 import BeautifulSoup
from slugify import slugify

# Caminhos base (funciona chamado de qualquer cwd)
BASE = Path(__file__).resolve().parent.parent
LINKS_FILE = Path("/root/links.md")
RAW_DIR = BASE / "data" / "raw"
PAGES_JSON = BASE / "data" / "pages.json"
FAILED_JSON = BASE / "data" / "failed.json"

PREFIX = "https://peroxide-roblox.fandom.com/wiki/"
API_BASE = "https://peroxide-roblox.fandom.com/api.php"
UA = "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0"
RATE_LIMIT = 2.0  # segundos entre requisições
MAX_RETRIES = 3
CACHE_DAYS = 7

sys.path.insert(0, str(BASE / "src"))
from categories import categorize  # noqa: E402


def ler_links(path: Path = LINKS_FILE) -> list[str]:
    """Lê links.md: ignora vazias, comentários # e duplicatas, valida prefixo."""
    vistos: set[str] = set()
    urls: list[str] = []
    for linha in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        # Permite linhas tipo "- https://..." ou com espaços
        m = re.search(r"https?://\S+", linha)
        url = m.group(0) if m else linha
        # Remove pontuação final de markdown (ex: "(url)."), mas preserva
        # parênteses balanceados que fazem parte do título (ex: "Xcution_(Faction)")
        url = url.rstrip(".,;:")
        while url.endswith(")") and url.count("(") < url.count(")"):
            url = url[:-1]
        if url in vistos:
            continue
        if not url.startswith(PREFIX):
            print(f"[skip] fora do prefixo: {url}", flush=True)
            continue
        vistos.add(url)
        urls.append(url)
    return urls


def url_para_slug(url: str) -> str:
    """Converte parte após /wiki/ em slug amigável."""
    parte = url.split("/wiki/", 1)[1].split("?")[0].split("#")[0]
    parte = unquote(parte)
    s = slugify(parte, lowercase=True)
    return s or "page"


def url_para_titulo(url: str) -> str:
    """Extrai o título da página (ex: 'Segunda_Etapa') a partir da URL."""
    parte = url.split("/wiki/", 1)[1].split("?")[0].split("#")[0]
    return unquote(parte)


def fetch_via_api(client: httpx.Client, page_title: str) -> dict | None:
    """Busca HTML parseado via MediaWiki API (contorna Cloudflare do HTML).

    O HTML direto do Fandom é protegido por challenge Cloudflare (403),
    mas o api.php responde normalmente. Retorna dict do 'parse' ou None.
    """
    params = {
        "action": "parse",
        "page": page_title,
        "format": "json",
        "prop": "text|displaytitle|pageid",
        "disabletoc": "1",
        "redirects": "1",
    }
    for tentativa in range(1, MAX_RETRIES + 1):
        try:
            r = client.get(API_BASE, params=params, timeout=30.0)
            if r.status_code == 200:
                try:
                    dados = r.json()
                except Exception:
                    time.sleep(2 ** tentativa)
                    continue
                if "parse" in dados:
                    return dados["parse"]
                # página inexistente ou erro da API
                if "error" in dados:
                    print(f"[api-error] {page_title}: {dados['error'].get('info', '')}", flush=True)
                    return None
                print(f"[api-error] resposta sem 'parse' p/ {page_title}", flush=True)
                return None
            if r.status_code in (429, 500, 502, 503, 504):
                espera = 2 ** tentativa
                print(f"[retry {tentativa}/{MAX_RETRIES}] {r.status_code} api:{page_title} -> espera {espera}s", flush=True)
                time.sleep(espera)
                continue
            print(f"[fail] HTTP {r.status_code} api:{page_title}", flush=True)
            return None
        except Exception as e:
            espera = 2 ** tentativa
            print(f"[retry {tentativa}/{MAX_RETRIES}] erro {e} em api:{page_title} -> espera {espera}s", flush=True)
            time.sleep(espera)
    return None


def limpar_conteudo(content: BeautifulSoup) -> None:
    """Remove elementos inúteis in-place: scripts, navbox, toc, imgs etc."""
    for sel in ["script", "style", "figure", "img", "aside",
                ".navbox", ".toc", ".toccolours", ".reference",
                ".mw-editsection", ".printfooter", ".catlinks",
                "#toc", ".mbox", ".ambox", "noscript", "video", "audio", "iframe"]:
        for el in content.select(sel):
            el.decompose()


def tabela_para_json(table) -> dict:
    """Converte <table> em {headers, rows}."""
    headers: list[str] = []
    rows: list[list[str]] = []
    # Headers: th da primeira linha ou thead
    thead = table.find("thead")
    first_tr = (thead.find("tr") if thead else None) or table.find("tr")
    if first_tr:
        for th in first_tr.find_all(["th", "td"]):
            headers.append(th.get_text(" ", strip=True)[:300])
    for tr in table.find_all("tr"):
        if tr is first_tr and headers and tr.find("th"):
            continue
        cells = [c.get_text(" ", strip=True)[:500] for c in tr.find_all(["td", "th"])]
        if cells and any(cells):
            rows.append(cells)
    return {"headers": headers, "rows": rows}


def extrair_infobox(content) -> dict | None:
    """Extrai o infobox (Fandom usa <aside class=portable-infobox>, não <table>).

    Deve ser chamado ANTES de limpar_conteudo (que remove <aside>).
    Retorna {headers, rows} e remove o infobox do conteúdo.
    """
    ib = content.select_one("aside.portable-infobox, table.infobox, table.portable-infobox")
    if ib is None:
        return None
    rows: list[list[str]] = []
    if ib.name == "aside":
        titulo = ib.select_one(".pi-title")
        if titulo and titulo.get_text(strip=True):
            rows.append([titulo.get_text(" ", strip=True)[:200]])
        for item in ib.select(".pi-data"):
            lab = item.select_one(".pi-data-label")
            val = item.select_one(".pi-data-value")
            label = lab.get_text(" ", strip=True)[:200] if lab else ""
            value = val.get_text(" ", strip=True)[:500] if val else item.get_text(" ", strip=True)[:500]
            if label or value:
                rows.append([label, value])
        # Navegação/links extras do infobox viram última fileira? Não — só dados.
        resultado = {"headers": ["Campo", "Valor"], "rows": rows} if rows else None
    else:
        resultado = tabela_para_json(ib)
        if not resultado.get("rows"):
            resultado = None
    ib.decompose()  # não duplicar nas seções
    return resultado


def extrair(url: str, html: str, slug: str, titulo_api: str | None = None) -> dict:
    """Extrai título, seções, tabelas, infobox e links internos."""
    soup = BeautifulSoup(html, PARSER)

    # Título: prefere displaytitle da API
    titulo = None
    if titulo_api:
        titulo = BeautifulSoup(titulo_api, PARSER).get_text(strip=True)
    if not titulo:
        for sel in ["h1#firstHeading", ".page-header__title", "h1"]:
            el = soup.select_one(sel)
            if el and el.get_text(strip=True):
                titulo = el.get_text(strip=True)
                break
    if not titulo:
        # fallback: usa slug humanizado
        titulo = slug.replace("-", " ").title()

    content = soup.select_one("div.mw-parser-output") or soup.select_one("div.mw-content-ltr") or soup.body or soup
    if content is None:
        return {"url": url, "slug": slug, "title": titulo, "category": categorize(slug, titulo),
                "scraped_at": datetime.now(timezone.utc).isoformat(),
                "sections": [], "infobox": None, "tables": [], "internal_links": [], "summary": ""}

    # Infobox primeiro (Fandom usa <aside>, removido pela limpeza)
    infobox = extrair_infobox(content)

    limpar_conteudo(content)

    # Seções: percorre filhos diretos; h2/h3/h4 abrem nova seção
    sections: list[dict] = []
    atual = {"level": 2, "heading": "Visão Geral", "html": ""}
    buf: list[str] = []

    def flush():
        nonlocal buf, atual
        html_seg = "".join(buf).strip()
        if html_seg or atual["heading"] != "Visão Geral":
            # mantém só html seguro/útil
            atual["html"] = html_seg[:200_000]
            # só adiciona se tem conteúdo ou heading real
            if html_seg or sections or atual["heading"] != "Visão Geral":
                sections.append({"level": atual["level"], "heading": atual["heading"], "html": html_seg[:200_000]})
        buf = []

    for child in list(content.children):
        nome = getattr(child, "name", None)
        if nome in ("h2", "h3", "h4"):
            flush()
            nivel = int(nome[1])
            heading = child.get_text(" ", strip=True)[:200]
            atual = {"level": nivel, "heading": heading, "html": ""}
        elif nome is None:
            txt = str(child).strip()
            if txt:
                buf.append(f"<p>{BeautifulSoup(txt, PARSER).get_text(' ', strip=True)[:2000]}</p>")
        else:
            if nome in ("script", "style"):
                continue
            # guarda html limpo do bloco
            for a in child.select("a[href]"):
                href = a.get("href", "")
                # normaliza links internos depois no build; aqui só marca
                if href.startswith("/wiki/"):
                    a["data-wiki"] = href.split("/wiki/", 1)[1].split("?")[0].split("#")[0]
            buf.append(str(child))
    flush()

    # Remove seções vazias
    sections = [s for s in sections if s["html"].strip() or s["heading"] != "Visão Geral"][:60]

    # Tabelas restantes (fora infobox)
    tables = []
    for t in content.select("table.wikitable, table.article-table"):
        try:
            tables.append(tabela_para_json(t))
        except Exception:
            continue
        if len(tables) >= 20:
            break

    # Links internos
    links = []
    vistos = set()
    for a in content.select('a[href^="/wiki/"]'):
        href = a.get("href", "")
        parte = href.split("/wiki/", 1)[1].split("?")[0].split("#")[0]
        parte = unquote(parte)
        if ":" in parte:  # File:, Category: etc — ignora
            continue
        ls = slugify(parte, lowercase=True)
        if not ls or ls in vistos:
            continue
        vistos.add(ls)
        links.append({"slug": ls, "label": a.get_text(" ", strip=True)[:120] or parte})
        if len(links) >= 100:
            break

    # Summary: primeiro parágrafo com texto
    summary = ""
    for s in sections:
        txt = BeautifulSoup(s["html"], PARSER).get_text(" ", strip=True)
        if len(txt) > 40:
            summary = txt[:300]
            break

    return {
        "url": url,
        "slug": slug,
        "title": titulo,
        "category": categorize(slug, titulo),
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "sections": sections,
        "infobox": infobox,
        "tables": tables,
        "internal_links": links,
        "summary": summary,
    }


def cache_valido(path: Path) -> bool:
    """Verifica se cache tem menos de CACHE_DAYS dias."""
    if not path.exists():
        return False
    try:
        dados = json.loads(path.read_text(encoding="utf-8"))
        ts = dados.get("scraped_at", "")
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).days < CACHE_DAYS
    except Exception:
        return False


def main(limit: int | None = None, only: list[str] | None = None):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    urls = ler_links()
    if only:
        urls = [u for u in urls if u in only]
    if limit:
        urls = urls[:limit]
    print(f"Total de URLs a processar: {len(urls)}", flush=True)

    ok: list[dict] = []
    falhas: list[dict] = []

    with httpx.Client(headers={"User-Agent": UA}, timeout=30.0) as client:
        for i, url in enumerate(urls, 1):
            slug = url_para_slug(url)
            titulo_pagina = url_para_titulo(url)
            destino = RAW_DIR / f"{slug}.json"
            if cache_valido(destino):
                print(f"[{i}/{len(urls)}] cache OK: {slug}", flush=True)
                try:
                    d = json.loads(destino.read_text(encoding="utf-8"))
                    ok.append({"slug": d["slug"], "title": d["title"], "category": d.get("category", "Outros"), "summary": d.get("summary", "")})
                    continue
                except Exception:
                    pass
            print(f"[{i}/{len(urls)}] baixando (API): {titulo_pagina}", flush=True)
            parse = fetch_via_api(client, titulo_pagina)
            if parse is None:
                falhas.append({"url": url, "slug": slug, "error": "fetch-failed"})
                time.sleep(RATE_LIMIT)
                continue
            try:
                html_frag = parse.get("text", {}).get("*", "")
                disp = parse.get("displaytitle", "")
                dados = extrair(url, html_frag, slug, titulo_api=disp)
            except Exception as e:
                falhas.append({"url": url, "slug": slug, "error": f"parse: {e}"})
                time.sleep(RATE_LIMIT)
                continue
            destino.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
            ok.append({"slug": dados["slug"], "title": dados["title"], "category": dados["category"], "summary": dados.get("summary", "")})
            time.sleep(RATE_LIMIT)

    # Mescla com índice anterior para não perder páginas já baixadas (idempotente)
    try:
        anteriores = json.loads(PAGES_JSON.read_text(encoding="utf-8")) if PAGES_JSON.exists() else []
    except Exception:
        anteriores = []
    por_slug = {p["slug"]: p for p in anteriores}
    for p in ok:
        por_slug[p["slug"]] = p
    final = sorted(por_slug.values(), key=lambda x: x["slug"])
    PAGES_JSON.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")

    # Falhas: mescla também
    try:
        f_ant = json.loads(FAILED_JSON.read_text(encoding="utf-8")) if FAILED_JSON.exists() else []
    except Exception:
        f_ant = []
    FAILED_JSON.write_text(json.dumps(falhas + [f for f in f_ant if f.get("url") not in {x["url"] for x in falhas}], ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"OK nesta rodada: {len(ok)} | Falhas nesta rodada: {len(falhas)} | Total no índice: {len(final)}")


if __name__ == "__main__":
    # Uso: python scripts/scrape.py [--limit N] [URL ...]
    lim = None
    only_list = None
    args = sys.argv[1:]
    if "--limit" in args:
        idx = args.index("--limit")
        lim = int(args[idx + 1])
        args = args[:idx] + args[idx + 2:]
    if args:
        only_list = args
    main(limit=lim, only=only_list)
