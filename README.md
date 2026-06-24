# harvex

**English** · [简体中文](README.zh-CN.md) · [日本語](README.ja.md)

**The data-harvesting foundation for the AI era** — a zero-boilerplate framework for AI agents and vibecoding.

Let the AI (or your own vibecoding) write only the one thing it's good at — *how to fetch, how to parse* — and leave everything else to the framework: concurrent scheduling, field consolidation, deduplicated writes, run metadata, HTTP retries, logging, alerting, data-health checks, scheduling, a web browser UI, LLM translation/enrichment, and a TUI control panel.

```bash
pip install harvex                              # core, zero heavy deps
pip install "harvex[web,llm,browser,tui]"       # opt into extras as needed
```

## Why "a harvesting foundation for the AI era"

When an LLM writes a scraper, the model is great at *"how do I turn this page/endpoint into structured data"* and bad at — and most likely to get wrong — the surrounding engineering: retry/backoff, concurrency isolation, incremental dedup, schema drift, scheduling, observability. harvex turns all of that into a stable foundation and gives the AI a **narrow, rock-solid contract surface**:

```python
from harvex import BaseSource, SourceProfile

class GithubTrending(BaseSource):
    profile = SourceProfile(slug="gh_trending", name="GitHub Trending")

    def fetch(self):
        return self.ctx.http.get_json("https://api.example.com/trending")

    def parse(self, raw):
        for item in raw["items"]:
            yield {"title": item["name"], "stars": item["stars"]}
```

The AI only needs to produce a class like this, and `harvex run` drives the whole chain: fetch → validate → dedup → store → run metadata → health check. New fields won't blow up your main table (they fold into an `extra` column automatically), one failing source won't take down the round, and dirty data is rejected before it hits the database.

## Design principles

- **Zero heavy core deps**: the core depends only on `pydantic` / `httpx` / `tenacity`. `playwright`, `openai`, web, and TUI are all `extras` installed on demand.
- **Field consolidation as a contract**: `HarvestRecord` (pydantic v2) enforces the "don't let the main table become a sparse matrix" discipline — undeclared fields fold automatically, dirty data is caught before writing.
- **Fault isolation**: one failing source never breaks the whole round.
- **SQLite first, Sink abstraction reserved**: works out of the box, with a clean extension point.
- **Scheduling decoupled from the web**: CLI + system launchd/cron, instead of parasitizing a timer thread inside the web process.

## Layers

```
sources/*.py (you / AI write)   BaseSource subclass: fetch() + parse()
     ↓ raw → list[dict]
core/pipeline                   validate(pydantic) → consolidate(extra fold) → store → metadata → health
     ↓
storage/sqlite_sink             create/alter table + upsert dedup + per-round backup
     ↓
SQLite business DB + metadata DB
     ↓ (extras)
extras/web  browse    extras/llm  translate    extras/tui  control panel
orchestration: core/runner (concurrency) + cli (harvex run / health / gen-launchd)
```

## New project skeleton

```
my_project/
├── config.toml         # source toggles / schedule / filters / notifications
├── .env.local          # secrets (openai key, webhook url)
├── fields.py           # your HarvestRecord subclass — standard fields
├── sources/            # one file per source, just fetch/parse
└── database/  logs/
```

A complete runnable template lives in [`templates/project/`](templates/project).

## CLI

```bash
harvex list                 # list discovered sources
harvex run --all            # run one round over all sources
harvex run gh_trending      # run specific sources
harvex health               # data-health check (zeroed-out / sharp drop)
harvex gen-launchd          # generate a macOS launchd schedule
harvex gen-cron             # generate a crontab line
harvex web                  # start the read-only browse UI (needs [web])
harvex tui                  # start the local control panel (needs [tui])
```

## Development

```bash
uv venv && uv pip install -e ".[dev]"
uv run pytest
```

## License

MIT
