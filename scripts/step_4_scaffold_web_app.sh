#!/usr/bin/env bash
set -euo pipefail

  mkdir -p apps
  cd apps
  pnpm dlx create-vite@latest web -- --template react-ts

cat > apps/web/tsconfig.json <<'JSON'
{
  "extends": "@hmt-spending/config/tsconfig.react.json",
  "include": ["src"]
}
JSON

cat > apps/web/vite.config.ts <<'TS'
import base from "@hmt-spending/config/vite.react"
export default base
TS

pnpm -F @hmt-spending/web add @hmt-spending/ui @hmt-spending/data @hmt-spending/charts

git add apps/web
git commit -m "chore(web): scaffold Vite + React web app in apps/web"
