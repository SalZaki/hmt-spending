#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f tsconfig.base.json ]]; then
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
fi

# --- 2) shared config package: @hmt/config ---
mkdir -p packages/config

cat > packages/config/package.json <<'JSON'
{
  "name": "@hmt-spending/config",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "main": "vite.react.ts"
}
JSON

cat > packages/config/tsconfig.react.json <<'JSON'
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": { "types": ["vite/client"] }
}
JSON

cat > packages/config/vite.react.ts <<'TS'
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173 }
})
TS

# --- 3) UI package: @hmt/ui (GOV.UK CSS + Tailwind + shadcn-ready) ---
mkdir -p packages/ui/src/{styles,components,lib,hooks}

cat > packages/ui/package.json <<'JSON'
{
  "name": "@hmt-spending/ui",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "main": "src/index.ts",
  "peerDependencies": {
    "react": ">=18",
    "react-dom": ">=18"
  },
  "dependencies": {
    "govuk-frontend": "^5.7.0"
  }
}
JSON

# styles: import GOV.UK first, then Tailwind v4 (via Vite plugin)
cat > packages/ui/src/styles/globals.css <<'CSS'
/* 1) GOV.UK Frontend CSS (base components/patterns) */
@import "govuk-frontend/govuk/all.css";

/* 2) Tailwind v4 utilities (provided by @tailwindcss/vite) */
@import "tailwindcss";

/* 3) UI design tokens (optional) */
:root {
  --brand-accent: #1d70b8; /* GOV.UK blue */
}
CSS

# basic exports + a utility that shadcn components commonly use
cat > packages/ui/src/lib/utils.ts <<'TS'
export function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ")
}
TS

cat > packages/ui/src/index.ts <<'TS'
import "./styles/globals.css"
export * from "./lib/utils"
// Re-export UI components here as you add them (e.g. from shadcn CLI)
TS

# --- 4) shadcn/ui monorepo setup (components.json in ui + example for apps) ---
cat > packages/ui/components.json <<'JSON'
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "new-york",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "",
    "css": "src/styles/globals.css",
    "baseColor": "zinc",
    "cssVariables": true
  },
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

# If you already have apps/web, you can drop a lightweight components.json there too
if [[ -d apps/web ]]; then
  cat > apps/web/components.json <<'JSON'
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "new-york",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "",
    "css": "../../packages/ui/src/styles/globals.css",
    "baseColor": "zinc",
    "cssVariables": true
  },
  "iconLibrary": "lucide",
  "aliases": {
    "@": "./src",
    "components": "@/components",
    "hooks": "@/hooks",
    "lib": "@/lib",
    "utils": "@hmt-spending/ui/lib/utils",
    "ui": "@hmt/ui/components"
  }
}
JSON
fi

# --- 5) install root dev tooling: vite/react plugin + tailwind v4 vite plugin ---
pnpm add -D vite @vitejs/plugin-react @tailwindcss/vite tailwindcss
