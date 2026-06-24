# harvex

[English](README.md) · [简体中文](README.zh-CN.md) · **日本語**

**AI 時代のデータ収集基盤** —— AI エージェントと vibecoding のためのゼロボイラープレートなデータ収集フレームワーク。

AI（またはあなた自身の vibecoding）には得意なこと —— *どう取得し、どう解析するか* —— だけを書かせ、残りはすべてフレームワークに任せます：並行スケジューリング、フィールド集約、重複排除書き込み、実行メタデータ、HTTP リトライ、ロギング、アラート、データ健全性チェック、定時スケジューリング、Web 閲覧 UI、LLM 翻訳・補強、TUI コントロールパネル。

```bash
pip install harvex                              # コア、重い依存ゼロ
pip install "harvex[web,llm,browser,tui]"       # 必要に応じて拡張を追加
```

## なぜ「AI 時代の収集基盤」なのか

LLM にスクレイパーを書かせると、モデルは *「このページ/API をどう構造化データに変換するか」* は得意ですが、周辺のエンジニアリング —— リトライ/バックオフ、並行分離、増分重複排除、スキーマのdrift、スケジューリング、可観測性 —— は不得意で、最も間違えやすい部分です。harvex はそれらをすべて安定した基盤に落とし込み、AI には**狭く、極めて堅牢な契約面**だけを残します：

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

AI はこのようなクラスを生成するだけで、`harvex run` が 取得 → 検証 → 重複排除 → 保存 → メタデータ → 健全性チェック の全工程を駆動します。新しいフィールドがメインテーブルを肥大化させることはなく（自動的に `extra` 列に折り畳まれます）、1 つのソースが失敗してもラウンド全体は壊れず、不正なデータは DB に書き込まれる前に拒否されます。

## 設計原則

- **コアは重い依存ゼロ**：コアは `pydantic` / `httpx` / `tenacity` のみに依存。`playwright`、`openai`、Web、TUI はすべてオンデマンドでインストールする `extras`。
- **フィールド集約は契約**：`HarvestRecord`（pydantic v2）が「メインテーブルを疎行列にしない」規律を守り、未宣言フィールドは自動的に折り畳まれ、不正データは書き込み前に捕捉されます。
- **障害分離**：1 つのソースの失敗がラウンド全体を壊しません。
- **まず SQLite、Sink 抽象を予約**：すぐ使えて、きれいな拡張ポイントも確保。
- **スケジューリングと Web の分離**：CLI + システムの launchd/cron。Web プロセス内のタイマースレッドに寄生させません。

## レイヤー

```
sources/*.py (あなた/AI が記述)   BaseSource サブクラス：fetch() + parse()
     ↓ raw → list[dict]
core/pipeline                     検証(pydantic) → 集約(extra 折込) → 保存 → メタデータ → 健全性
     ↓
storage/sqlite_sink               テーブル作成/列追加 + upsert 重複排除 + ラウンド単位バックアップ
     ↓
SQLite 業務 DB + メタデータ DB
     ↓ (extras)
extras/web  閲覧    extras/llm  翻訳    extras/tui  コントロールパネル
統括：core/runner（並行） + cli（harvex run / health / gen-launchd）
```

## 新規プロジェクトの雛形

```
my_project/
├── config.toml         # ソースの有効/無効・スケジュール・フィルタ・通知
├── .env.local          # シークレット（openai key、webhook url）
├── fields.py           # あなたの HarvestRecord サブクラス —— 標準フィールド
├── sources/            # 1 ソース 1 ファイル、fetch/parse だけ
└── database/  logs/
```

すぐ動く完全なテンプレートは [`templates/project/`](templates/project) にあります。

## CLI

```bash
harvex list                 # 発見されたソースを一覧表示
harvex run --all            # 全ソースを 1 ラウンド実行
harvex run gh_trending      # 指定ソースを実行
harvex health               # データ健全性チェック（ゼロ化/急減）
harvex gen-launchd          # macOS launchd スケジュールを生成
harvex gen-cron             # crontab 行を生成
harvex web                  # 読み取り専用の閲覧 UI を起動（[web] が必要）
harvex tui                  # ローカルコントロールパネルを起動（[tui] が必要）
```

## 開発

```bash
uv venv && uv pip install -e ".[dev]"
uv run pytest
```

## ライセンス

MIT
