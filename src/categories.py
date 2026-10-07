"""Regras de categorização por slug/título (comentado em português)."""
import re

# Dicionário de palavras-chave por categoria (tudo minúsculo).
CATEGORY_KEYWORDS = {
    "Hollow": ["hollow", "menos", "adjuchas", "adjucha", "vasto", "vastocar", "vastorage", "arrancar", "resurreccion", "ressurection", "segunda", "hogyoku"],
    "Shinigami": ["shinigami", "shini", "shikai", "bankai", "zanpakuto", "zanpakut", "soul_reaper", "gotei", "konso", "shikai", "shunsui", "rukia", "yamamoto", "kenpachi", "byakuya", "yoruichi"],
    "Quincy": ["quincy", "schrift", "vollstandig", "voltstanding", "yhwach", "wandereich", "wandenreich", "vollständig"],
    "Fullbringer": ["fullbring", "xcution", "xcution"],
    "Guias": ["guide", "starter", "progression", "tutorial"],
    "Itens": ["crystal", "relic", "hogyoku", "weapon", "accessory", "item", "essence", "medallion", "relic", "gourd", "drink", "cake", "milk", "clock", "cellphone", "book_of", "perk_stone", "gems"],
    "Locais": ["location", "map", "karakura", "hueco", "soul_society", "forest", "cave", "sewers", "apartment", "shop", "dojo", "las_noches", "overworld", "afk_world", "heart_cave", "the_cave", "the_sewers", "hospital", "menus_forest", "oasis", "dimension"],
    "Bosses": ["raid", "boss", "prince", "storm", "ulquiorra", "starrk", "aizen", "nnoitra", "yamamoto_raid", "kenpachi_raid", "byakuya_raid", "storm_boss", "hellverse"],
    "Eventos": ["event", "halloween", "easter", "peroxmas", "valentine", "peroximas", "new_year", "wungus", "server_event", "presents_2024"],
    "NPCs": ["npc", "vendor", "shady", "ben", "jim", "kisuke", "urahara", "miguel", "johan", "gunther", "nurse_ari", "yoruichi", "rukia", "characters"],
    "Organizações": ["faction", "guild", "clan", "organization", "gotei_13", "las_noches", "wandenreich", "xcution"],
    "Mecânicas": ["combat", "mechanics", "stats", "skill", "trait", "reputation", "ranking", "combos", "hakuda", "konso", "mode_abilities", "stats_and_perks"],
    "Meta": ["update", "code", "staff", "moderator", "contributor", "wiki", "codes", "top_donators", "staff", "moderators", "contributors"],
}

# Ordem de prioridade: primeira categoria que bater vence.
PRIORITY = ["Guias", "Eventos", "Bosses", "Locais", "NPCs", "Organizações", "Hollow", "Shinigami", "Quincy", "Fullbringer", "Itens", "Mecânicas", "Meta"]


def categorize(slug: str, title: str = "") -> str:
    """Infere categoria pelo slug/título. Retorna 'Outros' como fallback."""
    text = f"{slug} {title}".lower()
    # Normaliza: troca espaços/hífens por underscore para casar com keywords
    norm = re.sub(r"[\s\-]+", "_", text)
    for cat in PRIORITY:
        for kw in CATEGORY_KEYWORDS.get(cat, []):
            if kw.lower() in norm or kw.lower() in text:
                return cat
    # Segunda passada sem prioridade (caso algo fora da lista de prioridade)
    for cat, kws in CATEGORY_KEYWORDS.items():
        if cat in PRIORITY:
            continue
        for kw in kws:
            if kw.lower() in norm or kw.lower() in text:
                return cat
    return "Outros"
