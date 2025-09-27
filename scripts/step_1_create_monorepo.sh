#!/usr/bin/env bash
set -euo pipefail

# 1) root package.json
if [[ ! -f package.json ]]; then
  cat > package.json <<'JSON'
{
  "name": "hmt-spending",
  "private": true,
  "packageManager": "pnpm@9",
  "scripts": {
    "dev": "turbo dev",
    "build": "turbo build",
    "lint": "turbo lint",
    "preview": "pnpm --filter hmt-spending/web preview"
  },
  "devDependencies": {
    "turbo": "^2.0.0",
    "typescript": "^5.5.0",
    "eslint": "^9.0.0",
    "prettier": "^3.3.0"
  }
}
JSON
fi

# 2) pnpm workspace file (defines monorepo root & package globs)
mkdir -p apps packages
cat > pnpm-workspace.yaml <<'YAML'
packages:
  - "apps/*"
  - "packages/*"
YAML

# 3) base tsconfig for the repo
cat > tsconfig.base.json <<'JSON'
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022","DOM"],
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "jsx": "react-jsx",
    "strict": true,
    "baseUrl": ".",
    "paths": {
      "@hmt-spending/ui/*": ["packages/ui/src/*"],
      "@hmt-spending/data/*": ["packages/data/src/*"],
      "@hmt-spending/charts/*": ["packages/charts/src/*"],
      "@hmt-spending/config/*": ["packages/config/*"]
    }
  }
}
JSON

# 4) turbo.json – task pipeline config
cat > turbo.json <<'JSON'
{
  "pipeline": {
    "build": { "dependsOn": ["^build"], "outputs": ["dist/**"] },
    "dev":   { "cache": false, "persistent": true },
    "lint":  {}
  }
}
JSON

git add -A
export GPG_TTY="$(tty)" || true
git commit -m "chore: initialize monorepo (pnpm workspace + turbo)" || true

echo "✅ Monorepo initialized (pnpm workspace + turbo)."
