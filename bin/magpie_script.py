#!/usr/bin/env python3
"""magpie_script — page-script runner for Magpie browse.

Fetches external scripts through Magpie's own fetch layer, executes classic
and module scripts with the DOM bindings, fires DOMContentLoaded/load, drains
timers, and reports per-script errors without ever killing the page.
"""
from __future__ import annotations

import asyncio
import time
import urllib.parse

from magpie_dom import layout_dom
from magpie_fetch import FetchError, resolve_url
from magpie_jsdom import Bindings, dispatch, install_browser
from magpie_jslib import EventState, create_sandbox, drain_timers, set_fetcher
from magpie_jsparse import ParseError, parse_source
from magpie_jsrun import JSOptions, to_string
from magpie_jsval import Environment, ThrowExc, UNDEFINED
from magpie_jslex import LexError


class ScriptResult:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.ran = 0
        self.skipped = 0


def _script_type(node) -> str:
    return (node.get_attribute("type") or "").strip().lower()


def classic_type(typ: str) -> bool:
    return typ in ("", "text/javascript", "application/javascript", "text/ecmascript", "application/ecmascript")


async def run_page_scripts(bindings: Bindings, *, js_enabled: bool, budget_ms: float = 4000.0, width: int = 80) -> ScriptResult:
    """Execute a page's scripts; always returns (never raises into the TUI)."""
    from magpie_jsval import JSObject, INTRINSICS
    result = ScriptResult()
    if not js_enabled:
        return result
    page = bindings.page
    scripts = [s for s in page.scripts if s.tag == "script"]
    if not scripts:
        return result
    opts = JSOptions(budget_ms=budget_ms, budget_ops=4_000_000, module_loader=_module_loader(bindings))
    interp, g, env = create_sandbox(opts)
    interp.events = EventState()
    bindings.interp_ref = interp
    bindings.layout_width = width
    install_browser(g, bindings, interp)
    set_fetcher(_fetch_hook(bindings))
    bindings.ready_state = "loading"

    async def run_module_prog(prog):
        exports: dict = {}
        await interp.run_program(prog, env, module_exports=exports)
        return exports

    bindings.module_runner = run_module_prog

    async def guard(coro, label: str):
        try:
            await coro
        except ThrowExc as e:
            try:
                result.errors.append(f"{label}: {await to_string(interp, e.value)}")
            except ThrowExc:
                result.errors.append(f"{label}: script error")
        except (LexError, ParseError) as e:
            result.errors.append(f"{label}: syntax error: {e}")
        except Exception as e:
            result.errors.append(f"{label}: engine bug: {e}")

    deferred: list = []
    for node in scripts:
        typ = _script_type(node)
        if typ == "module":
            deferred.append(node)
            continue
        if not classic_type(typ):
            result.skipped += 1
            continue
        if node.has_attribute("defer"):
            deferred.append(node)
            continue
        src = await _script_source(bindings, node, result)
        if src is None:
            continue
        bindings.current_script = node
        prog = _parse_guarded(src, result, node)
        if prog is None:
            bindings.current_script = None
            continue
        result.ran += 1
        await guard(_run_program(interp, prog, env), _label(node))
        bindings.current_script = None
        if bindings.nav_request is not None:
            break
    for node in deferred:
        if bindings.nav_request is not None:
            break
        typ = _script_type(node)
        src = await _script_source(bindings, node, result)
        if src is None:
            continue
        bindings.current_script = node
        if typ == "module":
            prog = _parse_guarded(src, result, node, module=True)
            if prog is None:
                bindings.current_script = None
                continue
            result.ran += 1
            await guard(_run_module(interp, prog, env), _label(node))
        else:
            prog = _parse_guarded(src, result, node)
            if prog is None:
                bindings.current_script = None
                continue
            result.ran += 1
            await guard(_run_program(interp, prog, env), _label(node))
        bindings.current_script = None
    bindings.ready_state = "interactive"
    await guard(dispatch(bindings, interp, bindings.wrap(page.root), "DOMContentLoaded", props={"bubbles": False}), "DOMContentLoaded")
    await guard(drain_timers(interp, budget_ms=min(2000.0, budget_ms / 2)), "timers")
    await _fire_mutations(bindings, interp)
    bindings.ready_state = "complete"
    await guard(dispatch(bindings, interp, bindings.wrap(page.root), "load", props={"bubbles": False}), "load")
    # Re-layout the (possibly mutated) tree so the TUI shows script output.
    try:
        bindings.page = layout_dom(page.root, page.url, bindings.layout_width, js_enabled=True, title_override=page.title)
    except (ValueError, MemoryError, RecursionError):
        pass
    return result


async def _run_program(interp, prog, env) -> None:
    await interp.run_program(prog, env)


async def _run_module(interp, prog, env) -> None:
    await interp.run_program(prog, env, module_exports={})


def _parse_guarded(src: str, result: ScriptResult, node, *, module: bool = False):
    try:
        return parse_source(src, name=_label(node), module=module)
    except (LexError, ParseError) as e:
        result.errors.append(f"{_label(node)}: syntax error: {e}")
        return None


def _label(node) -> str:
    src = node.get_attribute("src")
    return f"<script src={src}>" if src else "<script>"


async def _script_source(bindings: Bindings, node, result: ScriptResult) -> str | None:
    src = node.get_attribute("src")
    if src:
        url = resolve_url(bindings.base_url(), src)
        try:
            resp = bindings.client.request(url, top_level=False)
        except FetchError as e:
            result.errors.append(f"<script src={src}>: {e}")
            return None
        if resp.status >= 400:
            result.errors.append(f"<script src={src}>: HTTP {resp.status}")
            return None
        try:
            return resp.data.decode("utf-8")
        except UnicodeDecodeError:
            return resp.data.decode("latin-1", "replace")
    parts = []
    for child in node.children:
        if child.tag == "#text":
            parts.append(child.text)
    text = "".join(parts)
    if len(text) > 1_000_000:
        result.errors.append("<script>: inline script over size cap, skipped")
        return None
    return text


def _module_loader(bindings: Bindings):
    seen: dict[str, dict] = {}
    active: set[str] = set()

    async def load(spec: str):
        url = resolve_url(bindings.base_url(), spec)
        if url in seen:
            return seen[url]
        if url in active:
            raise ThrowExc(__import__("magpie_jsval").make_error_value("Error", f"circular import {spec}"))
        active.add(url)
        try:
            resp = bindings.client.request(url, top_level=False)
        except FetchError as e:
            from magpie_jsval import ThrowExc as _TE, make_error_value as _me
            raise _TE(_me("Error", f"module {spec}: {e}"))
        if resp.status >= 400:
            from magpie_jsval import ThrowExc as _TE, make_error_value as _me
            raise _TE(_me("Error", f"module {spec}: HTTP {resp.status}"))
        try:
            text = resp.data.decode("utf-8")
        except UnicodeDecodeError:
            text = resp.data.decode("latin-1", "replace")
        from magpie_jsparse import parse_source as _parse
        from magpie_jslex import LexError as _LE
        from magpie_jsparse import ParseError as _PE
        try:
            prog = _parse(text, name=url, module=True)
        except (_LE, _PE) as e:
            from magpie_jsval import ThrowExc as _TE, make_error_value as _me
            raise _TE(_me("SyntaxError", f"module {spec}: {e}"))
        # Modules evaluate in the page interpreter; stash via bindings hook.
        runner = bindings.module_runner
        exports = await runner(prog)
        seen[url] = exports
        active.discard(url)
        return exports

    return load


async def _fire_mutations(bindings: Bindings, interp) -> None:
    for watcher in list(bindings.mutation_watchers):
        if not watcher.active or watcher.seen >= bindings.dom_version:
            continue
        watcher.seen = bindings.dom_version
        try:
            await interp.call_value(watcher.callback, UNDEFINED, [[]])
        except ThrowExc:
            pass


def _fetch_hook(bindings: Bindings):
    async def fetch_fn(method: str, url: str, headers: list, body: bytes):
        full = resolve_url(bindings.base_url(), url)
        scheme = urllib.parse.urlparse(full).scheme.lower()
        if scheme not in ("http", "https"):
            from magpie_jsval import ThrowExc as _TE, make_error_value as _me
            raise _TE(_me("TypeError", f"fetch blocked: {scheme or '(no scheme)'}"))
        same = _same_origin(full, bindings.base_url())
        try:
            resp = await asyncio.to_thread(
                bindings.client.request, full, method=method, body=body or None,
                content_type=dict(headers).get("content-type", ""), top_level=False,
            )
        except FetchError as e:
            from magpie_jsval import ThrowExc as _TE, make_error_value as _me
            raise _TE(_me("TypeError", f"fetch failed: {e}"))
        if not same:
            allowed = "*"
            for k, v in resp.headers:
                if k.lower() == "access-control-allow-origin":
                    allowed = v.strip()
                    break
            origin = f"{urllib.parse.urlparse(bindings.base_url()).scheme}://{urllib.parse.urlparse(bindings.base_url()).netloc}"
            if allowed != "*" and allowed != origin:
                from magpie_jsval import ThrowExc as _TE, make_error_value as _me
                raise _TE(_me("TypeError", "cross-origin fetch blocked by CORS"))
        return {
            "status": resp.status, "status_text": "", "url": resp.url,
            "headers": [(k.lower(), v) for k, v in resp.headers], "body": resp.data,
        }

    return fetch_fn


def _same_origin(a: str, b: str) -> bool:
    pa, pb = urllib.parse.urlparse(a), urllib.parse.urlparse(b)
    return (pa.scheme, pa.hostname, pa.port) == (pb.scheme, pb.hostname, pb.port)
