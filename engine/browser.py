"""browser-use（vendor/browser-use）で note / X に「人間と同じ画面操作」で投稿する。API不要・ログイン状態を使い回す。
- ログイン: python -m engine login note|x  （data/browser_profile に保存。一度だけ）
- 長文は LLM に打たせず、カスタムアクション insert_prepared_text で CDP 経由で一括挿入（速い・トークン節約）
  （browser-use 公式 examples/custom-functions と integrations/*/browser_use.py の Input.insertText パターンを流用）"""
import asyncio
import os
from pathlib import Path

from pydantic import BaseModel

from browser_use import ActionResult, Agent, Browser, BrowserSession, ChatGoogle, Tools

PROFILE = Path(os.getenv("BROWSER_PROFILE_DIR", "data/browser_profile")).resolve()
LOGIN_URLS = {"note": "https://note.com/login", "x": "https://x.com/login"}


class PostResult(BaseModel):
    ok: bool
    url: str
    note: str


def _llm():
    return ChatGoogle(model=os.getenv("BROWSER_USE_MODEL") or os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
                      api_key=os.getenv("GEMINI_API_KEY"), temperature=0)


def _tools(texts: dict[str, str]):
    tools = Tools(exclude_actions=["search"])

    @tools.registry.action(
        "Insert a prepared text block into the currently focused input/editor. "
        f"Click the target field first. Available keys: {', '.join(texts)}")
    async def insert_prepared_text(key: str, browser_session: BrowserSession):
        text = texts.get(key)
        if text is None:
            return ActionResult(error=f"unknown key '{key}'. available: {list(texts)}")
        cdp = await browser_session.get_or_create_cdp_session()
        await cdp.cdp_client.send.Input.insertText(params={"text": text}, session_id=cdp.session_id)
        return ActionResult(extracted_content=f"inserted '{key}' ({len(text)} chars)", include_in_memory=True)

    return tools


async def _run(task, texts, domains, headless):
    browser = Browser(headless=headless, user_data_dir=str(PROFILE), allowed_domains=domains)
    agent = Agent(task=task, llm=_llm(), browser=browser, tools=_tools(texts), output_model_schema=PostResult)
    try:
        hist = await agent.run(max_steps=int(os.getenv("AGENT_MAX_STEPS", "30")))
        raw = hist.final_result()
        res = PostResult.model_validate_json(raw) if raw else PostResult(ok=False, url="", note="結果なし")
    finally:
        await browser.kill()
    if not res.ok:
        raise RuntimeError(res.note or "投稿失敗")
    return res.url


def login(site: str):
    """普通のブラウザを開くので手動でログイン → Enter。以後このプロファイルで投稿される。"""
    from playwright.sync_api import sync_playwright
    PROFILE.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(PROFILE), headless=False,
                                                   executable_path=os.getenv("CHROME_PATH") or None)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(LOGIN_URLS[site])
        input(f"{site} にログインしたら Enter: ")
        ctx.close()
    print(f"保存: {PROFILE}")


def note_draft(post: dict, publish=False, headless=True) -> str:
    texts = {"title": post["title"], "body": post["body"]}
    final = "『公開に進む』→『投稿する』まで行い公開する" if publish else "『下書き保存』を押す（公開はしない）"
    task = f"""note に記事を作成してください（ログイン済み）。
1. https://note.com/notes/new を開く（エディタに遷移するまで待つ）
2. 記事タイトル欄をクリックし insert_prepared_text(key="title")
3. 本文エディタ（本文の入力欄）をクリックし insert_prepared_text(key="body")
4. {final}
5. 完了後のページURLを url に入れて ok=true で終了。ログイン画面が出たら ok=false, note="要ログイン" で終了"""
    return asyncio.run(_run(task, texts, ["note.com", "*.note.com"], headless))


def x_thread(tweets: list[str], headless=True) -> str:
    texts = {f"tweet_{i}": t for i, t in enumerate(tweets)}
    steps = "\n".join(
        (f"- 投稿欄をクリックし insert_prepared_text(key=\"tweet_0\")" if i == 0 else
         f"- 『ポストを追加』（+ボタン）を押し、新しく出た欄をクリックして insert_prepared_text(key=\"tweet_{i}\")")
        for i in range(len(tweets)))
    task = f"""X（旧Twitter）でスレッド投稿してください（ログイン済み）。
1. https://x.com/compose/post を開く
{steps}
2. 『すべてポスト』（Post all）を押す。1件だけなら『ポストする』
3. 自分のプロフィールで最新ポストのURLを開き、url に入れて ok=true で終了。ログイン画面なら ok=false, note="要ログイン\""""
    return asyncio.run(_run(task, texts, ["x.com", "*.x.com", "twitter.com", "*.twitter.com"], headless))
