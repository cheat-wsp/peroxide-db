#!/usr/bin/env python3
"""Converte /root/guiahollow.md em override JSON (mesmo formato do scraper).

Uso: python3 scripts/convert_guiahollow.py
Saída: data/overrides/hollow-starter-guide.json
"""
import html
import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SRC = Path("/root/guiahollow.md")
OUT = BASE / "data" / "overrides" / "hollow-starter-guide.json"

# Tabelas escritas como texto no md -> definição explícita (colunas + linhas).
# Chave: linha exata do cabeçalho no md.
TABLES = {
    "Option How Result": {
        "headers": ["Option", "How", "Result"],
        "rows": [
            ["Continue to Vasto Lorde", "Don't press G", "Keeps maximum potential"],
            ["Become an Adjucar", "Press G to remove the mask", "Stronger than Menoscar, but weaker than Vastocar"],
        ],
    },
    "Enemy or action Points": {
        "headers": ["Enemy or action", "Points"],
        "rows": "last-token",  # última palavra é a coluna Points
    },
    "Points Dialogue": {
        "headers": ["Points", "Dialogue"],
        "rows": "first-token",  # primeira palavra é a coluna Points
    },
    "Method Amount required": {
        "headers": ["Method", "Amount required"],
        "rows": "amount-2words",  # termina em "N kills" / "N ... consumed"
    },
    "Rank Bar requirement Behavior": {
        "headers": ["Rank", "Bar requirement", "Behavior"],
        "rows": [
            ["Rank C or below", "At least 15% filled", "Must fill the bar to use"],
            ["Rank B or above", "0%", "Infinite Resurrection"],
        ],
    },
    "Mode Rank B or above Rank C or below": {
        "headers": ["Mode", "Rank B or above", "Rank C or below"],
        "rows": [
            ["Resurrection", "Infinite (0% required)", "Requires 15% on the bar"],
            ["Segunda Etapa", "Time-limited (33s to 190s)", "Time-limited (33s to 190s)"],
        ],
    },
}

INTERNAL_LINKS = [
    ("menos", "Menos"), ("menos-forest", "Menos Forest"),
    ("adjuchas", "Adjuchas"), ("vasto-lorde", "Vasto Lorde"),
    ("arrancar", "Arrancar"), ("segunda-etapa", "Segunda Etapa"),
    ("resurreccion", "Resurrección"), ("monolith-quest", "Monolith Quest"),
    ("hollow", "Hollow"), ("hollow-bait", "Hollow Bait"),
    ("hollow-prince", "Hollow Prince"), ("vidente", "Vidente"),
    ("time-gate", "Time Gate"), ("skills", "Skills"),
]


def esc(t: str) -> str:
    return html.escape(t, quote=False)


def negrito_prefixo(line: str) -> str:
    """Destaca prefixos tipo 'Warning:', 'Tip:', 'Notes:' em <strong>."""
    m = re.match(r"^(Warning|Tip|Note|Notes|Important tip|Recommendation|Alternative route|Detailed route|Emergency teleport|Leveling route|Best farming methods|NPC grinding math|How to check progress|Death penalties|Choice:.*|Requirement:.*|Requirements?[^:]*):(.*)$", line)
    if m:
        return f"<strong>{esc(m.group(1))}:</strong>{esc(m.group(2))}"
    return esc(line)


def consumir_tabela(lines: list[str], i: int, spec) -> tuple[str, int]:
    """Consome linhas da tabela a partir de i. Retorna (html, novo_i)."""
    headers = spec["headers"]
    out = ["<table class=\"wikitable\"><thead><tr>"]
    out += [f"<th>{esc(h)}</th>" for h in headers]
    out.append("</tr></thead><tbody>")
    j = i
    if isinstance(spec["rows"], list):
        for row in spec["rows"]:
            # pula as linhas-fonte correspondentes
            while j < len(lines) and not lines[j].strip():
                j += 1
            j += 1  # consome a linha-fonte
            out.append("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in row) + "</tr>")
    else:
        while j < len(lines):
            raw = lines[j].strip()
            if not raw or raw.startswith("```"):
                break
            parts = raw.split()
            if spec["rows"] == "last-token":
                row = [" ".join(parts[:-1]), parts[-1]]
            elif spec["rows"] == "first-token":
                row = [parts[0], " ".join(parts[1:])]
            elif spec["rows"] == "amount-2words":
                if len(parts) >= 3 and parts[-1] in ("kills", "consumed"):
                    row = [" ".join(parts[:-2]), " ".join(parts[-2:])]
                else:
                    row = [" ".join(parts[:-1]), parts[-1]]
            else:
                row = [raw]
            out.append("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in row) + "</tr>")
            j += 1
    out.append("</tbody></table>")
    return "".join(out), j


def corpo_para_html(lines: list[str]) -> str:
    """Converte linhas do corpo em HTML (parágrafos, listas, tabelas, código)."""
    parts: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].rstrip()
        s = line.strip()
        if not s:
            i += 1
            continue
        if s in TABLES:
            tbl, i = consumir_tabela(lines, i + 1, TABLES[s])
            parts.append(tbl)
            continue
        if s.startswith("```"):
            buf = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i].rstrip())
                i += 1
            i += 1  # fecha o fence
            parts.append("<pre><code>" + esc("\n".join(buf)) + "</code></pre>")
            continue
        if s.startswith("·"):
            items = []
            while i < n and lines[i].strip().startswith("·"):
                items.append(lines[i].strip()[1:].strip())
                i += 1
            parts.append("<ul>" + "".join(f"<li>{negrito_prefixo(x)}</li>" for x in items) + "</ul>")
            continue
        m = re.match(r"^(\d+)\.\s+(.*)$", s)
        if m:
            items = []
            while i < n:
                mm = re.match(r"^(\d+)\.\s+(.*)$", lines[i].strip())
                if not mm:
                    break
                items.append(mm.group(2).strip())
                i += 1
            parts.append("<ol>" + "".join(f"<li>{negrito_prefixo(x)}</li>" for x in items) + "</ol>")
            continue
        parts.append(f"<p>{negrito_prefixo(s)}</p>")
        i += 1
    return "".join(parts)


def main():
    texto = SRC.read_text(encoding="utf-8")
    blocos = [b.strip("\n") for b in re.split(r"(?m)^---\s*$", texto)]
    blocos = [b for b in blocos if b.strip()]

    # Bloco 0: título + intro
    l0 = blocos[0].splitlines()
    titulo = l0[0].strip()
    intro = [l for l in l0[1:] if l.strip()]

    sections = [{"level": 2, "heading": "Visão Geral", "html": corpo_para_html(intro)}]
    for b in blocos[1:]:
        linhas = b.splitlines()
        # cabeçalho = primeira linha não-vazia
        h_idx = next(k for k, l in enumerate(linhas) if l.strip())
        heading = linhas[h_idx].strip()
        # nível: seções numeradas "N. ..." -> h2, resto -> h3
        level = 2 if re.match(r"^\d+\.\s+", heading) else 3
        sections.append({"level": level, "heading": heading,
                         "html": corpo_para_html(linhas[h_idx + 1:])})

    # Summary: primeiro parágrafo longo
    summary = ""
    for sec in sections:
        txt = re.sub(r"<[^>]+>", " ", sec["html"])
        txt = re.sub(r"\s+", " ", txt).strip()
        if len(txt) > 40:
            summary = txt[:300]
            break

    pagina = {
        "slug": "hollow-starter-guide",
        "title": titulo,
        "category": "Guias",
        "summary": summary,
        "sections": sections,
        "infobox": None,
        "tables": [],
        "internal_links": [{"slug": s, "label": l} for s, l in INTERNAL_LINKS],
        "override": True,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(pagina, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK: {OUT} ({len(sections)} seções)")


if __name__ == "__main__":
    main()
