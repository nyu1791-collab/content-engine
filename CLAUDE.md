# content-engine
- 実行: `python -m engine <cmd>`。エントリ `engine/__main__.py`
- ソース追加: `engine/sources.py` に関数を足し `TYPES` に登録 → `config.yaml` の `sources` に書く
- 公開先追加: `engine/publishers/<name>.py` に `publish(post, cfg) -> url` → `__main__.publish()` に分岐1つ
- 文体・構成は `prompts/*.md`。post は `{title, slug, description, tags, body(markdown), source_url}`
- 状態は `data/state.json`（Actions がコミット）。手で消せば再収集される
