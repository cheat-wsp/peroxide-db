#!/usr/bin/env bash
# Deploy do site estático no GitHub Pages — idempotente.
# Uso: bash scripts/deploy.sh [nome-do-repo] [--private]
#   ou: REPO=nome bash scripts/deploy.sh
set -euo pipefail
cd "$(dirname "$0")/.."

REPO="${1:-${REPO:-peroxide-db}}"
VIS="--public"
[[ "${2:-}" == "--private" ]] && VIS="--private"

echo "== Verificando gh =="
if ! command -v gh >/dev/null; then
  echo "ERRO: GitHub CLI (gh) não instalado."; exit 1
fi
gh auth status || { echo "ERRO: gh não autenticado. Rode: gh auth login"; exit 1; }

OWNER="$(gh api user -q .login)"
echo "== Owner: $OWNER | Repo: $REPO =="

# Garante build atualizado
if [ ! -f docs/index.html ]; then
  echo "== Gerando site =="
  python3 scripts/build.py
fi

# Init git se necessário
if [ ! -d .git ]; then
  git init
  git branch -M main 2>/dev/null || true
fi
git add -A
if git diff --cached --quiet; then
  echo "== Nada novo para commitar =="
else
  git commit -m "Update: Peroxide DB static site ($(date -u +%Y-%m-%d))" || true
fi

# Cria repo se não existe, senão só garante remote + push
if gh repo view "$OWNER/$REPO" >/dev/null 2>&1; then
  echo "== Repo já existe, garantindo remote =="
  git remote remove origin 2>/dev/null || true
  git remote add origin "https://github.com/$OWNER/$REPO.git"
  git branch -M main 2>/dev/null || true
else
  echo "== Criando repo $OWNER/$REPO ($VIS) =="
  gh repo create "$REPO" "$VIS" --source=. --remote=origin --push
fi

git push -u origin main 2>&1 | tail -3 || git push origin main 2>&1 | tail -3

echo "== Ativando GitHub Pages (branch main, pasta /docs) =="
# Tenta criar; se já existe, atualiza
if gh api "repos/$OWNER/$REPO/pages" >/dev/null 2>&1; then
  gh api "repos/$OWNER/$REPO/pages" -X PUT -f "source[branch]=main" -f "source[path]=/docs" --silent || true
else
  gh api "repos/$OWNER/$REPO/pages" -X POST -f "source[branch]=main" -f "source[path]=/docs" --silent || \
  gh api "repos/$OWNER/$REPO/pages" -X PUT -f "source[branch]=main" -f "source[path]=/docs" --silent || true
fi

echo "== Status do Pages =="
sleep 5
gh api "repos/$OWNER/$REPO/pages" -q '"URL: " + .html_url + " | status: " + .status' 2>/dev/null || \
gh api "repos/$OWNER/$REPO/pages"

echo ""
echo "Repo: https://github.com/$OWNER/$REPO"
echo "Site: https://$OWNER.github.io/$REPO/"
