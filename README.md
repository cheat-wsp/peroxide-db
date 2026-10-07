# Peroxide DB — Database estática do Peroxide (Roblox)

Site estático (HTML/CSS/JS puro) com o conteúdo textual do wiki oficial do
Peroxide no Fandom, publicado no **GitHub Pages**. Sem backend: os dados são
arquivos JSON gerados no build + páginas HTML pré-renderizadas.

## O que é

- **Scraper:** lê `/root/links.md` (só essas URLs) via **MediaWiki API**
  (`api.php?action=parse` — o HTML direto é bloqueado por challenge Cloudflare,
  a API responde normalmente). Extrai título, seções, tabelas, infobox e links
  internos. Nada de imagens/CSS/JS do Fandom.
- **Gerador:** Python + Jinja2 gera `docs/` (pronto pro Pages).
- **Busca:** Fuse.js via CDN na página `search.html`.

> Nota de ambiente: `requirements.txt` mantém `lxml==5.3.0` como pede a spec,
> mas o código usa `lxml` se disponível e cai para `html.parser` quando não há
> wheel (ex: Termux/Android). O comportamento é idêntico para este uso.

## Como instalar

```bash
pip install -r requirements.txt
```

## Como rodar o scraping

```bash
python scripts/scrape.py                 # todas as URLs de /root/links.md
python scripts/scrape.py --limit 5        # só as 5 primeiras (teste)
python scripts/scrape.py <URL1> <URL2>    # URLs específicas
```

- Rate limit: 2 s entre requisições + retry com backoff em 429/5xx (máx 3).
- Idempotente: `data/raw/{slug}.json` com menos de 7 dias é pulado.
- Saídas: `data/raw/*.json`, `data/pages.json` (índice), `data/failed.json`.

## Como gerar o site

```bash
python scripts/build.py
```

Gera `docs/` com `index.html`, `search.html`, `categorias/*.html`,
`pagina/*.html`, `assets/data/{pages,search-index}.json` e `.nojekyll`.

## Como publicar

```bash
bash scripts/deploy.sh [nome-do-repo]
# ex: bash scripts/deploy.sh peroxide-db
```

O script verifica `gh auth`, cria o repo público (ou usa o existente),
faz push e ativa o Pages em `main` + `/docs`. URL final:
`https://SEU_USUARIO.github.io/peroxide-db/`.

## Estrutura dos dados

Por página (`data/raw/{slug}.json`):

```json
{
  "url": "https://peroxide-roblox.fandom.com/wiki/Hollow",
  "slug": "hollow",
  "title": "Hollow",
  "category": "Hollow",
  "scraped_at": "2025-01-15T10:30:00Z",
  "sections": [{"level": 2, "heading": "...", "html": "<p>...</p>"}],
  "infobox": {"headers": [], "rows": [[...]]},
  "tables": [],
  "internal_links": [{"slug": "menos", "label": "Menos"}]
}
```

Categorias em `src/categories.py` (fallback: `Outros`).
Atualização automática: `.github/workflows/update.yml` (domingo 03:00 UTC).
