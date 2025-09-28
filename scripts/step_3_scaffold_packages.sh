#!/usr/bin/env bash
set -euo pipefail

# UI
mkdir -p packages/ui/src/{layouts,components}
cat > packages/ui/package.json <<'JSON'
{
  "name": "@hmt-spending/ui",
  "version": "0.1.0",
  "type": "module",
  "main": "src/index.ts",
  "private": true
}
JSON
cat > packages/ui/src/index.ts <<'TS'
export const Placeholder = () => null
TS

# Data
mkdir -p packages/data/src
cat > packages/data/package.json <<'JSON'
{
  "name": "@hmt-spending/data",
  "version": "0.1.0",
  "type": "module",
  "main": "src/index.ts",
  "private": true
}
JSON
cat > packages/data/src/index.ts <<'TS'
export const helloData = () => "ok"
TS

# Charts
mkdir -p packages/charts/src
cat > packages/charts/package.json <<'JSON'
{
  "name": "@hmt-spending/charts",
  "version": "0.1.0",
  "type": "module",
  "main": "src/index.ts",
  "private": true,
  "peerDependencies": { "react": ">=18", "react-dom": ">=18" }
}
JSON
cat > packages/charts/src/index.ts <<'TS'
export const helloCharts = () => "ok"
TS

pnpm install

git add packages/ui packages/data packages/charts
git commit -m "chore(packages): scaffold UI, Data, and Charts packages"
