# tile-puzzle

Claude Code plugin — a Triple Match (Tile Explorer / GD_Test) **level-design toolkit** for the team.

Two skills:
- **`gen-layout`** — create empty layout geometry (shape / icon / bulk), mobile-portrait, symmetric where appropriate.
- **`tile-level-design`** — assign tiles, score difficulty, solve/verify (DFS v3), build trap / easy-layer / difficulty-targeted levels, analyze/modify/normalize, bulk test sets.

Used together for image/shape → playable level.

## Install (team — via the `toolgenlevel` marketplace)

**Automatic (recommended — no commands).** This repo's `.claude/settings.json` declares the
`toolgenlevel` marketplace + `tile-puzzle` plugin via `extraKnownMarketplaces` + `enabledPlugins`.
A teammate just **opens this repo folder** in the Claude Code VS Code extension and **trusts** it —
Claude Code then prompts to add the marketplace and enables the plugin (sparse-clone fetches only
`tile-puzzle/` + `.claude-plugin/`, not the whole repo). `autoUpdate` keeps them on the latest version.

**Manual (any surface).**
```text
/plugin marketplace add thales1020/ToolGenLevel
/plugin install tile-puzzle@toolgenlevel
```
Skills are then namespaced `/toolgenlevel:gen-layout`, `/toolgenlevel:tile-level-design` (or Claude
invokes them automatically). Updates: maintainer bumps `version` in `tile-puzzle/.claude-plugin/plugin.json`.

**Prereqs:** repo is private → teammate needs collaborator access + git/gh auth; Python on PATH (engine).

## Try locally without installing

```bash
claude --plugin-dir ./tile-puzzle
```

## Validate before shipping

```bash
claude plugin validate ./tile-puzzle
python tile-puzzle/tests/check_engine_parity.py      # engine copies byte-identical
# then walk tile-puzzle/tests/TEST_GUIDE.md for live routing/pipeline checks
```
