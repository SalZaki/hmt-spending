#!/usr/bin/env bash
set -euo pipefail

mkdir -p apps packages
[[ -f pnpm-workspace.yaml ]] || cat > pnpm-workspace.yaml <<'YAML'
packages:
  - "apps/*"
  - "packages/*"
YAML

[[ -f tsconfig.base.json ]] || cat > tsconfig.base.json <<'JSON'
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

mkdir -p packages/config
cat > packages/config/package.json <<'JSON'
{ "name": "@hmt-spending/config", "version": "0.1.0", "private": true, "type": "module", "main": "vite.react.ts" }
JSON
cat > packages/config/tsconfig.react.json <<'JSON'
{ "extends": "../../tsconfig.base.json", "compilerOptions": { "types": ["vite/client"] } }
JSON
cat > packages/config/vite.react.ts <<'TS'
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
export default defineConfig({ plugins: [react(), tailwindcss()], server: { port: 5173 } })
TS

mkdir -p packages/ui/src/{styles,components,lib,hooks}
cat > packages/ui/package.json <<'JSON'
{
  "name": "@hmt-spending/ui",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "main": "src/index.ts",
  "peerDependencies": { "react": ">=18", "react-dom": ">=18" }
}
JSON
cat > packages/ui/src/styles/globals.css <<'CSS'
@import "govuk-frontend/govuk/all.css";
@import "tailwindcss";
:root { --brand-accent: #1d70b8; }
CSS
cat > packages/ui/src/lib/utils.ts <<'TS'
export function cn(...c:(string|false|null|undefined)[]){return c.filter(Boolean).join(" ")}
TS
cat > packages/ui/src/index.ts <<'TS'
import "./styles/globals.css"
export * from "./lib/utils"
TS
cat > packages/ui/components.json <<'JSON'
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "new-york",
  "rsc": false,
  "tsx": true,
  "tailwind": { "config": "", "css": "src/styles/globals.css", "baseColor": "zinc", "cssVariables": true },
  "iconLibrary": "lucide",
  "aliases": {
    "components": "@hmt-spending/ui/components",
    "hooks": "@hmt-spending/ui/hooks",
    "lib": "@hmt-spending/ui/lib",
    "utils": "@hmt-spending/ui/lib/utils",
    "ui": "@hmt-spending/ui/components"
  }
}
JSON

pnpm add -w -D vite @vitejs/plugin-react tailwindcss @tailwindcss/vite
pnpm -F @hmt-spending/ui add govuk-frontend

if [[ -d apps/web ]]; then
  cat > apps/web/components.json <<'JSON'
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "new-york",
  "rsc": false,
  "tsx": true,
  "tailwind": { "config": "", "css": "../../packages/ui/src/styles/globals.css", "baseColor": "zinc", "cssVariables": true },
  "iconLibrary": "lucide",
  "aliases": { "@": "./src", "components": "@/components", "hooks": "@/hooks", "lib": "@/lib", "utils": "@hmt-spending/ui/lib/utils", "ui": "@hmt-spending/ui/components" }
}
JSON
fi

git add pnpm-workspace.yaml tsconfig.base.json packages/config packages/ui
git commit -m "chore(config,ui): add shared Vite/TS config and UI pkg (GOV.UK CSS + Tailwind v4 + shadcn-ready)"
