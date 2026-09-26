#!/usr/bin/env python3
"""magpie_jsdom — DOM/browser bindings for Magpie's JavaScript engine.

Wraps ``magpie_dom`` nodes in live JS objects (elements, document, window,
location, events, storage) so page scripts can touch the page Magpie owns.
Network flows through ``magpie_fetch``; timers/promises come from
``magpie_jslib``. No browser engine is borrowed: every binding is ours.
"""
from __future__ import annotations

import asyncio
import time
import urllib.parse

from magpie_dom import Node, Page, collect_styles, compute_style, layout_dom, parse_html
from magpie_fetch import FetchError, resolve_url, url_host_label
from magpie_jslib import EventState, js_array, js_object, native, set_fetcher
from magpie_jsrun import (
    Interpreter, JSOptions, env_get, prop_get, prop_set, to_number, to_string,
)
from magpie_jsval import (
    Environment, FALSE, INTRINSICS, JSArray, JSBoolean, JSFunction, JSNull,
    JSNumber, JSObject, JSString, JSSymbol, JSValue, JSPromise, NULL,
    ReturnExc, ThrowExc, TRUE, UNDEFINED, enum_keys, js_bool, make_error_value,
    to_boolean,
)


ELEMENT_PROTOS: dict[str, JSObject] = {}


def throw_dom(msg: str):
    raise ThrowExc(make_error_value("Error", msg))


class Bindings:
    """Per-page browser state shared by every wrapper on the page."""

    def __init__(self, page: Page, client, *, term_size=(80, 24)) -> None:
        self.page = page
        self.client = client
        self.term_size = term_size
        self.wrappers: dict[int, JSObject] = {}
        self.errors: list[str] = []
        self.alerts: list[str] = []
        self.dom_version = 0
        self.current_script = None
        self.pending_scroll: tuple[str, int] | None = None
        self.nav_request: tuple[str, bool] | None = None
        self.open_request: str | None = None
        self.submit_request = None
        self.media_request = None
        self.copy_text: str | None = None
        self.confirm_default = False
        self.prompt_default = ""
        self.image_info: dict[str, tuple[int, int]] = {}
        self.media_info: dict[str, dict] = {}
        self.storages: dict[str, dict] = {}
        self.history_stack: list[str] = [page.url]
        self.history_index = 0
        self.history_state = None
        self.active_element = None
        self.mutation_watchers: list = []
        self.listeners: dict[int, dict[str, list]] = {}
        self.referrer = ""
        self.ready_state = "loading"
        self.interp_ref = None
        self.module_runner = None
        self.layout_width = 80

    def bump(self) -> None:
        self.dom_version += 1

    def base_url(self) -> str:
        return self.page.url

    def wrap(self, node: Node):
        key = id(node)
        w = self.wrappers.get(key)
        if w is None:
            w = make_node_wrapper(self, node)
            self.wrappers[key] = w
        return w

    def add_listener(self, target_id: int, kind: str, fn: JSFunction) -> None:
        self.listeners.setdefault(target_id, {}).setdefault(kind, []).append(fn)

    def remove_listener(self, target_id: int, kind: str, fn) -> None:
        lst = self.listeners.get(target_id, {}).get(kind, [])
        self.listeners[target_id][kind] = [f for f in lst if f is not fn]


def node_proto(bindings: Bindings, tag: str) -> JSObject:
    key = tag.lower()
    proto = ELEMENT_PROTOS.get(key)
    if proto is None:
        parent_key = {
            "a": "htmlanchorelement", "img": "htmlimageelement",
            "video": "htmlmediaelement", "audio": "htmlmediaelement",
            "input": "htmlinputelement", "textarea": "htmltextareaelement",
            "select": "htmlselectelement", "option": "htmloptionelement",
            "button": "htmlbuttonelement", "form": "htmlformelement",
            "canvas": "htmlcanvaselement", "details": "htmldetailselement",
            "iframe": "htmliframeelement", "script": "htmlscriptelement",
        }.get(key, "htmlelement")
        parent = ELEMENT_PROTOS.get(parent_key)
        if parent is None:
            parent = ELEMENT_PROTOS.get("node")
        proto = JSObject(parent)
        install_element_api(bindings, proto, key)
        ELEMENT_PROTOS[key] = proto
    return proto


def base_protos() -> None:
    if ELEMENT_PROTOS:
        return
    obj = INTRINSICS["Object_prototype"]
    event_target = JSObject(obj)
    node = JSObject(obj)
    element = JSObject(node)
    html_element = JSObject(element)
    for name, proto in (
        ("eventtarget", event_target), ("node", node), ("element", element),
        ("htmlelement", html_element), ("htmlanchorelement", JSObject(html_element)),
        ("htmlimageelement", JSObject(html_element)), ("htmlmediaelement", JSObject(html_element)),
        ("htmlinputelement", JSObject(html_element)), ("htmltextareaelement", JSObject(html_element)),
        ("htmlselectelement", JSObject(html_element)), ("htmloptionelement", JSObject(html_element)),
        ("htmlbuttonelement", JSObject(html_element)), ("htmlformelement", JSObject(html_element)),
        ("htmlcanvaselement", JSObject(html_element)), ("htmldetailselement", JSObject(html_element)),
        ("htmliframeelement", JSObject(html_element)), ("htmlscriptelement", JSObject(html_element)),
        ("document", JSObject(node)), ("characterdata", JSObject(node)),
        ("text", JSObject(ELEMENT_PROTOS.get("characterdata") or node)),
        ("comment", JSObject(ELEMENT_PROTOS.get("characterdata") or node)),
        ("documentfragment", JSObject(node)),
    ):
        ELEMENT_PROTOS[name] = proto
    ELEMENT_PROTOS["text"] = JSObject(ELEMENT_PROTOS["characterdata"])
    ELEMENT_PROTOS["comment"] = JSObject(ELEMENT_PROTOS["characterdata"])


def make_node_wrapper(bindings: Bindings, node: Node) -> JSObject:
    base_protos()
    if node.tag == "#text":
        w = JSObject(ELEMENT_PROTOS["text"])
    elif node.tag == "#comment":
        w = JSObject(ELEMENT_PROTOS["comment"])
    elif node.tag == "#document":
        w = JSObject(ELEMENT_PROTOS["document"])
        install_document_api(bindings, w, node)
    else:
        w = JSObject(node_proto(bindings, node.tag))
    w.define_own("__node__", _NodeRef(node), enumerable=False)
    w.define_own("__bindings__", _BindingsRef(bindings), enumerable=False)
    return w


class _NodeRef:
    __slots__ = ("node",)

    def __init__(self, node: Node) -> None:
        self.node = node


class _BindingsRef:
    __slots__ = ("bindings",)

    def __init__(self, bindings: Bindings) -> None:
        self.bindings = bindings


def node_of(w) -> Node | None:
    ref = w.get_own("__node__") if isinstance(w, JSObject) else None
    return ref.node if isinstance(ref, _NodeRef) else None


def bindings_of(w):
    ref = w.get_own("__bindings__") if isinstance(w, JSObject) else None
    return ref.bindings if isinstance(ref, _BindingsRef) else None


def _acc(proto, name: str, get, set=None) -> None:
    proto.define_accessor(name, native(f"get {name}", get) if get else None,
                          native(f"set {name}", set) if set else None, enumerable=False)


def _m(proto, name: str, handler, *, length: int = 0) -> None:
    proto.define_own(name, native(name, handler, length=length), enumerable=False)


# ── events ───────────────────────────────────────────────────────────────

def make_event(bindings: Bindings, kind: str, *, props: dict | None = None) -> JSObject:
    obj = JSObject(INTRINSICS.get("Event_prototype") or INTRINSICS["Object_prototype"])
    obj.define_own("__event__", _Event(kind, props or {}), enumerable=False)
    return obj


class _Event:
    __slots__ = ("kind", "props", "target", "current", "canceled", "stopped", "immediate")

    def __init__(self, kind: str, props: dict) -> None:
        self.kind = kind
        self.props = props
        self.target = None
        self.current = None
        self.canceled = False
        self.stopped = False
        self.immediate = False


def install_event_proto() -> None:
    if "Event_prototype" in INTRINSICS:
        return
    proto = JSObject(INTRINSICS["Object_prototype"])
    INTRINSICS["Event_prototype"] = proto
    _acc(proto, "type", lambda t, a, i: JSString(_ev_this(t).kind))
    _acc(proto, "target", lambda t, a, i: _ev_this(t).target or NULL)
    _acc(proto, "currentTarget", lambda t, a, i: _ev_this(t).current or NULL)
    _acc(proto, "bubbles", lambda t, a, i: js_bool(_ev_this(t).props.get("bubbles", False)))
    _acc(proto, "cancelable", lambda t, a, i: js_bool(_ev_this(t).props.get("cancelable", False)))
    _acc(proto, "defaultPrevented", lambda t, a, i: js_bool(_ev_this(t).canceled))
    for name in ("preventDefault", "stopPropagation", "stopImmediatePropagation"):
        _m(proto, name, _ev_op(name))
    for name in ("button", "buttons", "clientX", "clientY", "key", "code", "which", "keyCode",
                 "data", "inputType", "deltaX", "deltaY", "detail", "relatedTarget"):
        _acc(proto, name, _ev_prop(name))
    INTRINSICS["Event"] = _event_ctor("Event")
    INTRINSICS["CustomEvent"] = _event_ctor("CustomEvent")
    for sub in ("MouseEvent", "KeyboardEvent", "FocusEvent", "InputEvent", "SubmitEvent", "WheelEvent", "PointerEvent"):
        INTRINSICS[sub] = _event_ctor(sub)


def _ev_this(t) -> _Event:
    if not isinstance(t, JSObject) or not isinstance(t.get_own("__event__"), _Event):
        raise ThrowExc(make_error_value("TypeError", "event member on non-event"))
    return t.get_own("__event__")


def _ev_op(name: str):
    async def handler(t, a, i):
        ev = _ev_this(t)
        if name == "preventDefault" and ev.props.get("cancelable"):
            ev.canceled = True
        elif name == "stopPropagation":
            ev.stopped = True
        else:
            ev.immediate = True
            ev.stopped = True
        return UNDEFINED
    return handler


def _ev_prop(name: str):
    def get(t, a, i):
        v = _ev_this(t).props.get(name, 0 if name in ("button", "which", "keyCode", "detail", "deltaX", "deltaY", "clientX", "clientY") else "")
        if isinstance(v, JSValue):
            return v
        return JSNumber(v) if isinstance(v, (int, float)) else JSString(str(v))
    return get


def _event_ctor(name: str) -> JSFunction:
    async def construct(this, args, interp):
        from magpie_jsrun import to_string as _ts
        kind = await _ts(interp, args[0]) if args else ""
        props = {}
        if len(args) > 1 and isinstance(args[1], JSObject):
            for k in enum_keys(args[1]):
                v = args[1].get(k, recv=args[1])
                v = await _resolve(v, interp)
                props[k] = v.value if isinstance(v, (JSString, JSNumber, JSBoolean)) else to_boolean(v)
        if name == "CustomEvent" and "detail" in props:
            pass
        obj = JSObject(INTRINSICS["Event_prototype"])
        obj.define_own("__event__", _Event(kind, props), enumerable=False)
        if isinstance(props.get("detail"), JSValue):
            obj.define_own("detail", props["detail"])
        return obj
    fn = JSFunction(kind="native", proto=INTRINSICS["Function_prototype"])
    fn.handler = construct
    fn.define_own("name", JSString(name), enumerable=False)
    return fn


async def _resolve(v, interp):
    from magpie_jsrun import resolve_call
    return await resolve_call(v, interp) if isinstance(v, tuple) else v


async def dispatch(bindings: Bindings, interp: Interpreter, target_w, kind: str, *, props: dict | None = None) -> bool:
    """Dispatch an event with capture/bubble; return True if not canceled."""
    install_event_proto()
    ev = make_event(bindings, kind, props=props or {})
    ev_state = ev.get_own("__event__")
    node = node_of(target_w)
    path: list = []
    if node is not None:
        cur: Node | None = node
        while cur is not None:
            path.append(bindings.wrap(cur))
            cur = cur.parent
    else:
        path = [target_w]
    ev_state.target = target_w
    # Capture: window → target parent.
    for w in reversed(path[1:]):
        if ev_state.stopped:
            break
        await _invoke(bindings, interp, w, ev, ev_state, capture=True)
    # Target.
    if not ev_state.stopped:
        await _invoke(bindings, interp, path[0], ev, ev_state, capture=False)
    # Bubble.
    if not ev_state.stopped and ev_state.props.get("bubbles", True):
        for w in path[1:]:
            if ev_state.stopped:
                break
            await _invoke(bindings, interp, w, ev, ev_state, capture=False)
    return not ev_state.canceled


async def _invoke(bindings: Bindings, interp: Interpreter, w, ev, ev_state, *, capture: bool) -> None:
    ev_state.current = w
    node = node_of(w)
    fns: list = []
    if node is not None:
        fns.extend(node.script_state.get("listeners", {}).get(ev_state.kind, []))
        inline = node.get_attribute("on" + ev_state.kind)
        if inline and not node.script_state.get("inline_compiled_" + ev_state.kind):
            node.script_state["inline_compiled_" + ev_state.kind] = True
            try:
                fn = await compile_inline(bindings, interp, node, inline, ev_state.kind)
                if fn is not None:
                    node.script_state.setdefault("listeners", {}).setdefault(ev_state.kind, []).append(fn)
                    fns.append(fn)
            except ThrowExc as e:
                bindings.errors.append(f"on{ev_state.kind}: {await to_string(interp, e.value)}")
    else:
        fns.extend(bindings.listeners.get(id(w), {}).get(ev_state.kind, []))
        prop = w.get("on" + ev_state.kind) if isinstance(w, JSObject) else UNDEFINED
        prop = await _resolve(prop, interp) if isinstance(prop, tuple) else prop
        if isinstance(prop, JSFunction):
            fns.append(prop)
    for fn in fns:
        if ev_state.immediate:
            break
        try:
            this = w
            await interp.call_value(fn, this, [ev])
        except ThrowExc as e:
            try:
                bindings.errors.append(f"{ev_state.kind} listener: {await to_string(interp, e.value)}")
            except ThrowExc:
                pass


async def compile_inline(bindings: Bindings, interp: Interpreter, node: Node, src: str, kind: str):
    from magpie_jsparse import parse_source
    prog = parse_source(f"(function(event){{{src}\n}})", name=f"<on{kind}>")
    fn_node = prog[1][0][1]
    global_env = interp.global_env()
    scope = Environment(global_env, var_scope=False)
    fn = interp.make_function("", fn_node[2], fn_node[3], scope, False, False)
    return fn


# ── elements ─────────────────────────────────────────────────────────────

def install_element_api(bindings: Bindings, proto: JSObject, tag: str) -> None:
    _acc(proto, "nodeType", lambda t, a, i: JSNumber(_node_type(_el_this(t))))
    _acc(proto, "nodeName", lambda t, a, i: JSString(_node_name(_el_this(t))))
    _acc(proto, "tagName", lambda t, a, i: JSString(_el_this(t).tag.upper()))
    _acc(proto, "id", lambda t, a, i: JSString(_el_this(t).get_attribute("id")),
         lambda t, a, i: _set_attr(t, a, i, "id"))
    _acc(proto, "className", lambda t, a, i: JSString(_el_this(t).get_attribute("class")),
         lambda t, a, i: _set_attr(t, a, i, "class"))
    _acc(proto, "classList", lambda t, a, i: make_token_list(bindings, _el_this(t)))
    _acc(proto, "attributes", lambda t, a, i: make_named_map(bindings, _el_this(t)))
    _acc(proto, "dataset", lambda t, a, i: make_dataset(bindings, _el_this(t)))
    _acc(proto, "style", lambda t, a, i: make_style(bindings, _el_this(t)))
    _acc(proto, "parentNode", lambda t, a, i: _wrap_or_null(bindings, _el_this(t).parent))
    _acc(proto, "parentElement", lambda t, a, i: _wrap_or_null(bindings, _el_this(t).parent if _el_this(t).parent and not _el_this(t).parent.tag.startswith("#") else None))
    _acc(proto, "childNodes", lambda t, a, i: make_node_list(bindings, _el_this(t).children, live=lambda n=_el_this(t): list(n.children)))
    _acc(proto, "children", lambda t, a, i: make_collection(bindings, [c for c in _el_this(t).children if not c.tag.startswith("#")], live=lambda n=_el_this(t): [c for c in n.children if not c.tag.startswith("#")]))
    _acc(proto, "firstChild", lambda t, a, i: _wrap_or_null(bindings, _el_this(t).children[0] if _el_this(t).children else None))
    _acc(proto, "lastChild", lambda t, a, i: _wrap_or_null(bindings, _el_this(t).children[-1] if _el_this(t).children else None))
    _acc(proto, "firstElementChild", lambda t, a, i: _wrap_or_null(bindings, next((c for c in _el_this(t).children if not c.tag.startswith("#")), None)))
    _acc(proto, "lastElementChild", lambda t, a, i: _wrap_or_null(bindings, next((c for c in reversed(_el_this(t).children) if not c.tag.startswith("#")), None)))
    _acc(proto, "nextSibling", lambda t, a, i: _sibling(bindings, _el_this(t), 1, False))
    _acc(proto, "previousSibling", lambda t, a, i: _sibling(bindings, _el_this(t), -1, False))
    _acc(proto, "nextElementSibling", lambda t, a, i: _sibling(bindings, _el_this(t), 1, True))
    _acc(proto, "previousElementSibling", lambda t, a, i: _sibling(bindings, _el_this(t), -1, True))
    _acc(proto, "ownerDocument", lambda t, a, i: bindings.wrap(_document_root(_el_this(t))))
    _acc(proto, "textContent", lambda t, a, i: JSString(_el_this(t).text_content()),
         lambda t, a, i: _set_text(t, a, i))
    _acc(proto, "innerText", lambda t, a, i: JSString(_inner_text(_el_this(t))),
         lambda t, a, i: _set_text(t, a, i))
    _acc(proto, "innerHTML", lambda t, a, i: JSString(_el_this(t).inner_html()),
         lambda t, a, i: _set_inner_html(t, a, i))
    _acc(proto, "outerHTML", lambda t, a, i: JSString(_outer_html(_el_this(t))),
         lambda t, a, i: _set_outer_html(t, a, i))
    for name, fn in (
        ("getAttribute", _get_attr), ("setAttribute", _set_attr_m), ("removeAttribute", _remove_attr),
        ("hasAttribute", _has_attr), ("toggleAttribute", _toggle_attr), ("getAttributeNames", _attr_names),
        ("appendChild", _append_child), ("removeChild", _remove_child), ("insertBefore", _insert_before),
        ("replaceChild", _replace_child), ("append", _append), ("prepend", _prepend),
        ("before", _before), ("after", _after), ("replaceWith", _replace_with), ("remove", _remove_self),
        ("replaceChildren", _replace_children), ("cloneNode", _clone_node), ("contains", _contains),
        ("hasChildNodes", _has_children), ("matches", _matches), ("closest", _closest),
        ("querySelector", _query_one), ("querySelectorAll", _query_all),
        ("getElementsByTagName", _by_tag), ("getElementsByClassName", _by_class),
        ("insertAdjacentHTML", _adjacent_html), ("insertAdjacentElement", _adjacent_el),
        ("insertAdjacentText", _adjacent_text), ("addEventListener", _add_listener),
        ("removeEventListener", _remove_listener), ("dispatchEvent", _dispatch_ev),
        ("getBoundingClientRect", _bounding_rect), ("scrollIntoView", _scroll_into_view),
        ("focus", _focus), ("blur", _blur), ("click", _click),
    ):
        _m(proto, name, fn)
    _acc(proto, "scrollTop", lambda t, a, i: JSNumber(0), lambda t, a, i: _scroll_pos(t, a, i))
    _acc(proto, "scrollLeft", lambda t, a, i: JSNumber(0), lambda t, a, i: _scroll_pos(t, a, i))
    if tag == "a":
        _acc(proto, "href", lambda t, a, i: JSString(resolve_url(bindings.base_url(), _el_this(t).get_attribute("href")) if _el_this(t).get_attribute("href") else ""),
             lambda t, a, i: _set_attr(t, a, i, "href"))
        for attr in ("target", "rel", "text", "download", "hreflang", "type"):
            _acc(proto, attr, _attr_getter(attr), _attr_setter(attr))
    if tag in ("img",):
        _acc(proto, "src", lambda t, a, i: JSString(resolve_url(bindings.base_url(), _el_this(t).get_attribute("src")) if _el_this(t).get_attribute("src") else ""),
             lambda t, a, i: _set_attr(t, a, i, "src"))
        _acc(proto, "currentSrc", lambda t, a, i: JSString(resolve_url(bindings.base_url(), _el_this(t).get_attribute("src")) if _el_this(t).get_attribute("src") else ""))
        _acc(proto, "complete", lambda t, a, i: TRUE)
        _acc(proto, "naturalWidth", lambda t, a, i: JSNumber(bindings.image_info.get(resolve_url(bindings.base_url(), _el_this(t).get_attribute("src")), (0, 0))[0]))
        _acc(proto, "naturalHeight", lambda t, a, i: JSNumber(bindings.image_info.get(resolve_url(bindings.base_url(), _el_this(t).get_attribute("src")), (0, 0))[1]))
        for attr in ("alt", "title", "loading", "decoding", "width", "height"):
            _acc(proto, attr, _attr_getter(attr), _attr_setter(attr))
    if tag in ("video", "audio"):
        _acc(proto, "src", lambda t, a, i: JSString(_media_src(bindings, _el_this(t))),
             lambda t, a, i: _set_attr(t, a, i, "src"))
        _acc(proto, "currentSrc", lambda t, a, i: JSString(_media_src(bindings, _el_this(t))))
        _acc(proto, "paused", lambda t, a, i: js_bool(bindings.media_info.get(_media_src(bindings, _el_this(t)), {}).get("paused", True)))
        _acc(proto, "currentTime", lambda t, a, i: JSNumber(bindings.media_info.get(_media_src(bindings, _el_this(t)), {}).get("pos", 0.0)))
        _acc(proto, "duration", lambda t, a, i: JSNumber(bindings.media_info.get(_media_src(bindings, _el_this(t)), {}).get("dur", float("nan"))))
        _acc(proto, "volume", lambda t, a, i: JSNumber(1.0), lambda t, a, i: _media_prop(t, a, i, "volume"))
        _acc(proto, "muted", lambda t, a, i: FALSE, lambda t, a, i: _media_prop(t, a, i, "muted"))
        _acc(proto, "ended", lambda t, a, i: FALSE)
        _acc(proto, "readyState", lambda t, a, i: JSNumber(4))
        for attr in ("poster", "preload", "controls" if False else "title",):
            _acc(proto, attr, _attr_getter(attr), _attr_setter(attr))
        _m(proto, "play", _media_play)
        _m(proto, "pause", _media_pause)
        _m(proto, "load", _media_load)
    if tag == "input":
        for attr in ("type", "name", "value", "placeholder", "alt", "src", "accept", "autocomplete", "pattern", "title"):
            _acc(proto, attr, _attr_getter(attr), _attr_setter(attr))
        _acc(proto, "checked", lambda t, a, i: js_bool(_el_this(t).has_attribute("checked")),
             lambda t, a, i: _toggle_bool_attr(t, a, i, "checked"))
        _acc(proto, "disabled", lambda t, a, i: js_bool(_el_this(t).has_attribute("disabled")),
             lambda t, a, i: _toggle_bool_attr(t, a, i, "disabled"))
        _acc(proto, "required", lambda t, a, i: js_bool(_el_this(t).has_attribute("required")),
             lambda t, a, i: _toggle_bool_attr(t, a, i, "required"))
        _acc(proto, "readOnly", lambda t, a, i: js_bool(_el_this(t).has_attribute("readonly")),
             lambda t, a, i: _toggle_bool_attr(t, a, i, "readonly"))
        _acc(proto, "files", lambda t, a, i: make_collection(bindings, []))
        _acc(proto, "form", lambda t, a, i: _wrap_or_null(bindings, _form_owner(_el_this(t))))
        _m(proto, "select", _noop_undefined)
        _m(proto, "setSelectionRange", _noop_undefined)
    if tag == "textarea":
        for attr in ("name", "placeholder", "rows", "cols"):
            _acc(proto, attr, _attr_getter(attr), _attr_setter(attr))
        _acc(proto, "value", lambda t, a, i: JSString(_el_this(t).text_content()),
             lambda t, a, i: _set_text(t, a, i))
        _acc(proto, "textLength", lambda t, a, i: JSNumber(len(_el_this(t).text_content())))
    if tag == "select":
        _acc(proto, "value", lambda t, a, i: JSString(_select_value(_el_this(t))),
             lambda t, a, i: _set_select_value(t, a, i))
        _acc(proto, "selectedIndex", lambda t, a, i: JSNumber(_selected_index(_el_this(t))),
             lambda t, a, i: _set_selected_index(t, a, i))
        _acc(proto, "options", lambda t, a, i: make_collection(bindings, _el_this(t).get_elements_by_tag("option")))
        _acc(proto, "length", lambda t, a, i: JSNumber(len(_el_this(t).get_elements_by_tag("option"))))
        _acc(proto, "multiple", lambda t, a, i: js_bool(_el_this(t).has_attribute("multiple")),
             lambda t, a, i: _toggle_bool_attr(t, a, i, "multiple"))
        for attr in ("name", "size"):
            _acc(proto, attr, _attr_getter(attr), _attr_setter(attr))
    if tag == "option":
        _acc(proto, "value", lambda t, a, i: JSString(_el_this(t).get_attribute("value") or _el_this(t).text_content()),
             lambda t, a, i: _set_attr(t, a, i, "value"))
        _acc(proto, "text", lambda t, a, i: JSString(_el_this(t).text_content()),
             lambda t, a, i: _set_text(t, a, i))
        _acc(proto, "selected", lambda t, a, i: js_bool(_el_this(t).has_attribute("selected")),
             lambda t, a, i: _toggle_bool_attr(t, a, i, "selected"))
        _acc(proto, "index", lambda t, a, i: JSNumber(_option_index(_el_this(t))))
    if tag == "button":
        for attr in ("type", "name", "value"):
            _acc(proto, attr, _attr_getter(attr), _attr_setter(attr))
        _acc(proto, "disabled", lambda t, a, i: js_bool(_el_this(t).has_attribute("disabled")),
             lambda t, a, i: _toggle_bool_attr(t, a, i, "disabled"))
    if tag == "form":
        for attr in ("action", "method", "enctype", "name", "target"):
            _acc(proto, attr, _attr_getter(attr), _attr_setter(attr))
        _acc(proto, "elements", lambda t, a, i: make_collection(bindings, [c for c in _el_this(t).iter() if c.tag in ("input", "select", "textarea", "button")]))
        _acc(proto, "length", lambda t, a, i: JSNumber(len([c for c in _el_this(t).iter() if c.tag in ("input", "select", "textarea", "button")])))
        _m(proto, "submit", _form_submit)
        _m(proto, "reset", _form_reset)
        _m(proto, "reportValidity", _form_validity)
        _m(proto, "checkValidity", _form_validity)
    if tag == "canvas":
        _acc(proto, "width", lambda t, a, i: JSNumber(int(_el_this(t).get_attribute("width") or 300)),
             lambda t, a, i: _set_attr(t, a, i, "width"))
        _acc(proto, "height", lambda t, a, i: JSNumber(int(_el_this(t).get_attribute("height") or 150)),
             lambda t, a, i: _set_attr(t, a, i, "height"))
        _m(proto, "getContext", _canvas_context)
    if tag == "details":
        _acc(proto, "open", lambda t, a, i: js_bool(_el_this(t).has_attribute("open") or bool(_el_this(t).script_state.get("open"))),
             lambda t, a, i: _set_details_open(t, a, i))
    if tag == "iframe":
        _acc(proto, "src", lambda t, a, i: JSString(resolve_url(bindings.base_url(), _el_this(t).get_attribute("src")) if _el_this(t).get_attribute("src") else ""),
             lambda t, a, i: _set_attr(t, a, i, "src"))
        _acc(proto, "contentDocument", lambda t, a, i: NULL)
        _acc(proto, "contentWindow", lambda t, a, i: NULL)
    if tag == "script":
        _acc(proto, "src", lambda t, a, i: JSString(_el_this(t).get_attribute("src")),
             lambda t, a, i: _set_attr(t, a, i, "src"))
        _acc(proto, "text", lambda t, a, i: JSString(_el_this(t).text_content()),
             lambda t, a, i: _set_text(t, a, i))


def _el_this(t) -> Node:
    node = node_of(t)
    if node is None or node.tag.startswith("#"):
        throw_dom("element member on non-element")
    return node


def _node_type(node: Node) -> int:
    return {"#document": 9, "#text": 3, "#comment": 8}.get(node.tag, 1)


def _node_name(node: Node) -> str:
    if node.tag == "#text":
        return "#text"
    if node.tag == "#comment":
        return "#comment"
    if node.tag == "#document":
        return "#document"
    return node.tag.upper()


def _document_root(node: Node) -> Node:
    cur = node
    while cur.parent is not None:
        cur = cur.parent
    return cur


def _wrap_or_null(bindings: Bindings, node: Node | None):
    return bindings.wrap(node) if node is not None else NULL


def _sibling(bindings: Bindings, node: Node, step: int, elements_only: bool):
    if node.parent is None:
        return NULL
    sibs = node.parent.children
    idx = sibs.index(node) + step
    while 0 <= idx < len(sibs):
        if not elements_only or not sibs[idx].tag.startswith("#"):
            return bindings.wrap(sibs[idx])
        idx += step
    return NULL


def _tag_bindings(obj: JSObject, bindings: Bindings) -> JSObject:
    obj.define_own("__bindings__", _BindingsRef(bindings), enumerable=False)
    return obj


def _inner_text(node: Node) -> str:
    if node.tag in ("script", "style"):
        return ""
    if node.tag == "#text":
        return node.text
    if node.tag == "#comment":
        return ""
    parts = []
    for c in node.children:
        if c.tag == "br":
            parts.append("\n")
        elif c.tag in ("p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6",
                        "section", "article", "tr", "blockquote", "pre", "ul", "ol"):
            parts.append(_inner_text(c) + "\n")
        else:
            parts.append(_inner_text(c))
    return "".join(parts)


def _outer_html(node: Node) -> str:
    from magpie_dom import serialize_node
    return serialize_node(node)


async def _set_attr(t, a, i, name: str):
    from magpie_jsrun import to_string as _ts
    _el_this(t).set_attribute(name, await _ts(i, a[0]) if a else "")
    bindings_of(t).bump()
    return UNDEFINED


def _attr_getter(name: str):
    def get(t, a, i):
        return JSString(_el_this(t).get_attribute(name))
    return get


def _attr_setter(name: str):
    async def setv(t, a, i):
        return await _set_attr(t, a, i, name)
    return setv


async def _set_text(t, a, i):
    from magpie_jsrun import to_string as _ts
    node = _el_this(t)
    node.set_text_content(await _ts(i, a[0]) if a else "")
    bindings_of(t).bump()
    return UNDEFINED


async def _set_inner_html(t, a, i):
    from magpie_jsrun import to_string as _ts
    node = _el_this(t)
    node.set_inner_html(await _ts(i, a[0]) if a else "")
    bindings_of(t).bump()
    return UNDEFINED


async def _set_outer_html(t, a, i):
    from magpie_jsrun import to_string as _ts
    node = _el_this(t)
    if node.parent is None:
        throw_dom("no parent for outerHTML")
    frag = parse_html(f"<div>{await _ts(i, a[0]) if a else ''}</div>").query_selector("div")
    idx = node.parent.children.index(node)
    node.parent.remove(node)
    for k, c in enumerate(frag.children if frag else []):
        node.parent.insert(idx + k, c)
    bindings_of(t).bump()
    return UNDEFINED


async def _get_attr(t, a, i):
    from magpie_jsrun import to_string as _ts
    name = (await _ts(i, a[0])).lower() if a else ""
    node = _el_this(t)
    return JSString(node.attrs[name]) if name in node.attrs else NULL


async def _set_attr_m(t, a, i):
    from magpie_jsrun import to_string as _ts
    node = _el_this(t)
    node.set_attribute((await _ts(i, a[0])).lower() if a else "", await _ts(i, a[1]) if len(a) > 1 else "")
    bindings_of(t).bump()
    return UNDEFINED


async def _remove_attr(t, a, i):
    from magpie_jsrun import to_string as _ts
    _el_this(t).remove_attribute((await _ts(i, a[0])).lower() if a else "")
    bindings_of(t).bump()
    return UNDEFINED


async def _has_attr(t, a, i):
    from magpie_jsrun import to_string as _ts
    return js_bool(_el_this(t).has_attribute((await _ts(i, a[0])).lower() if a else ""))


async def _toggle_attr(t, a, i):
    from magpie_jsrun import to_string as _ts
    node = _el_this(t)
    name = (await _ts(i, a[0])).lower() if a else ""
    force = a[1] if len(a) > 1 else UNDEFINED
    has = node.has_attribute(name)
    if force is UNDEFINED:
        should = not has
    else:
        should = to_boolean(force)
    if should:
        node.set_attribute(name, "")
    else:
        node.remove_attribute(name)
    bindings_of(t).bump()
    return js_bool(should)


async def _attr_names(t, a, i):
    return js_array(i, [JSString(k) for k in _el_this(t).attrs])


async def _toggle_bool_attr(t, a, i, name: str):
    node = _el_this(t)
    if to_boolean(a[0] if a else UNDEFINED):
        node.set_attribute(name, "")
    else:
        node.remove_attribute(name)
    bindings_of(t).bump()
    return UNDEFINED


def _as_node(v, interp) -> Node | None:
    if isinstance(v, JSObject):
        n = node_of(v)
        if n is not None and (not n.tag.startswith("#") or n.tag in ("#text", "#comment", "#fragment")):
            return n
    return None


async def _append_child(t, a, i):
    parent = _el_this(t)
    child = _as_node(a[0] if a else UNDEFINED, i)
    if child is None:
        throw_dom("appendChild needs a node")
    if child.parent is not None:
        child.parent.remove(child)
    parent.append(child)
    bindings_of(t).bump()
    return bindings_of(t).wrap(child)


async def _remove_child(t, a, i):
    parent = _el_this(t)
    child = _as_node(a[0] if a else UNDEFINED, i)
    if child is None or child.parent is not parent:
        throw_dom("not a child")
    parent.remove(child)
    bindings_of(t).bump()
    return bindings_of(t).wrap(child)


async def _insert_before(t, a, i):
    parent = _el_this(t)
    child = _as_node(a[0] if a else UNDEFINED, i)
    ref = _as_node(a[1] if len(a) > 1 else UNDEFINED, i)
    if child is None:
        throw_dom("insertBefore needs a node")
    if child.parent is not None:
        child.parent.remove(child)
    if ref is None or ref is UNDEFINED:
        parent.append(child)
    else:
        if ref.parent is not parent:
            throw_dom("reference is not a child")
        parent.insert(parent.children.index(ref), child)
    bindings_of(t).bump()
    return bindings_of(t).wrap(child)


async def _replace_child(t, a, i):
    parent = _el_this(t)
    new = _as_node(a[0] if a else UNDEFINED, i)
    old = _as_node(a[1] if len(a) > 1 else UNDEFINED, i)
    if new is None or old is None or old.parent is not parent:
        throw_dom("bad replaceChild")
    if new.parent is not None:
        new.parent.remove(new)
    parent.insert(parent.children.index(old), new)
    parent.remove(old)
    bindings_of(t).bump()
    return bindings_of(t).wrap(old)


async def _insert_nodes(parent: Node, idx: int | None, args, i, bindings: Bindings) -> None:
    from magpie_jsrun import to_string as _ts
    items = []
    for v in args:
        n = _as_node(v, i)
        if n is not None:
            items.append(n)
        elif isinstance(v, JSObject) and node_of(v) is None:
            frag = parse_html(f"<div>{await _ts(i, v)}</div>").query_selector("div")
            items.extend(frag.children if frag else [])
        else:
            items.append(Node("#text", text=await _ts(i, v)))
    for n in items:
        if n.parent is not None:
            n.parent.remove(n)
    if idx is None:
        for n in items:
            parent.append(n)
    else:
        for k, n in enumerate(items):
            parent.insert(idx + k, n)
    bindings.bump()


async def _append(t, a, i):
    b = bindings_of(t)
    await _insert_nodes(_el_this(t), None, a, i, b)
    return UNDEFINED


async def _prepend(t, a, i):
    b = bindings_of(t)
    await _insert_nodes(_el_this(t), 0, a, i, b)
    return UNDEFINED


async def _before(t, a, i):
    node = _el_this(t)
    if node.parent is None:
        return UNDEFINED
    await _insert_nodes(node.parent, node.parent.children.index(node), a, i, bindings_of(t))
    return UNDEFINED


async def _after(t, a, i):
    node = _el_this(t)
    if node.parent is None:
        return UNDEFINED
    await _insert_nodes(node.parent, node.parent.children.index(node) + 1, a, i, bindings_of(t))
    return UNDEFINED


async def _replace_with(t, a, i):
    node = _el_this(t)
    if node.parent is None:
        return UNDEFINED
    b = bindings_of(t)
    await _insert_nodes(node.parent, node.parent.children.index(node), a, i, b)
    node.parent.remove(node)
    b.bump()
    return UNDEFINED


async def _remove_self(t, a, i):
    node = _el_this(t)
    if node.parent is not None:
        node.parent.remove(node)
        bindings_of(t).bump()
    return UNDEFINED


async def _replace_children(t, a, i):
    node = _el_this(t)
    node.children = []
    await _insert_nodes(node, None, a, i, bindings_of(t))
    return UNDEFINED


async def _clone_node(t, a, i):
    node = _el_this(t)
    deep = to_boolean(a[0]) if a else False
    return bindings_of(t).wrap(node.clone(deep=bool(deep)))


async def _contains(t, a, i):
    node = _el_this(t)
    other = _as_node(a[0] if a else UNDEFINED, i)
    if other is None:
        return FALSE
    cur: Node | None = other
    while cur is not None:
        if cur is node:
            return TRUE
        cur = cur.parent
    return FALSE


async def _has_children(t, a, i):
    return js_bool(bool(_el_this(t).children))


async def _matches(t, a, i):
    from magpie_jsrun import to_string as _ts
    from magpie_dom import parse_selector, matches_selector
    sel = await _ts(i, a[0]) if a else ""
    try:
        seq = parse_selector(sel)
    except (ValueError, IndexError):
        throw_dom("bad selector")
    return js_bool(matches_selector(_el_this(t), seq))


async def _closest(t, a, i):
    from magpie_jsrun import to_string as _ts
    from magpie_dom import parse_selector, matches_selector, split_selector_groups
    sel = await _ts(i, a[0]) if a else ""
    b = bindings_of(t)
    for group in split_selector_groups(sel):
        seq = parse_selector(group)
        cur: Node | None = _el_this(t)
        while cur is not None:
            if matches_selector(cur, seq):
                return b.wrap(cur)
            cur = cur.parent
    return NULL


async def _query_all_on(node: Node, sel: str, bindings: Bindings):
    from magpie_dom import split_selector_groups, parse_selector, matches_selector
    out = []
    for group in split_selector_groups(sel):
        seq = parse_selector(group)
        out.extend(n for n in node.elements() if matches_selector(n, seq))
    seen: set[int] = set()
    uniq = []
    for n in out:
        if id(n) not in seen:
            seen.add(id(n))
            uniq.append(n)
    return make_collection(bindings, uniq)


async def _query_one(t, a, i):
    from magpie_jsrun import to_string as _ts
    node = _el_this(t)
    sel = await _ts(i, a[0]) if a else ""
    col = await _query_all_on(node, sel, bindings_of(t))
    items = col.get_own("__items__")
    return bindings_of(t).wrap(items[0]) if items else NULL


async def _query_all(t, a, i):
    from magpie_jsrun import to_string as _ts
    node = _el_this(t)
    return await _query_all_on(node, await _ts(i, a[0]) if a else "", bindings_of(t))


async def _by_tag(t, a, i):
    from magpie_jsrun import to_string as _ts
    node = _el_this(t)
    name = (await _ts(i, a[0])).lower() if a else ""
    kids = node.get_elements_by_tag(name) if name != "*" else [n for n in node.elements()]
    return make_collection(bindings_of(t), kids)


async def _by_class(t, a, i):
    from magpie_jsrun import to_string as _ts
    node = _el_this(t)
    return make_collection(bindings_of(t), node.get_elements_by_class(await _ts(i, a[0]) if a else ""))


async def _adjacent_html(t, a, i):
    from magpie_jsrun import to_string as _ts
    node = _el_this(t)
    pos = (await _ts(i, a[0])).lower() if a else ""
    markup = await _ts(i, a[1]) if len(a) > 1 else ""
    frag = parse_html(f"<div>{markup}</div>").query_selector("div")
    kids = list(frag.children) if frag else []
    b = bindings_of(t)
    if pos == "beforebegin":
        if node.parent is None:
            throw_dom("no parent")
        for k, c in enumerate(kids):
            node.parent.insert(node.parent.children.index(node) + k, c)
    elif pos == "afterbegin":
        for k, c in enumerate(kids):
            node.insert(k, c)
    elif pos == "beforeend":
        for c in kids:
            node.append(c)
    elif pos == "afterend":
        if node.parent is None:
            throw_dom("no parent")
        for k, c in enumerate(kids):
            node.parent.insert(node.parent.children.index(node) + 1 + k, c)
    else:
        throw_dom("bad adjacent position")
    b.bump()
    return UNDEFINED


async def _adjacent_el(t, a, i):
    from magpie_jsrun import to_string as _ts
    pos = (await _ts(i, a[0])).lower() if a else ""
    el = _as_node(a[1] if len(a) > 1 else UNDEFINED, i)
    if el is None:
        return NULL
    node = _el_this(t)
    b = bindings_of(t)
    if el.parent is not None:
        el.parent.remove(el)
    if pos == "beforebegin" and node.parent is not None:
        node.parent.insert(node.parent.children.index(node), el)
    elif pos == "afterbegin":
        node.insert(0, el)
    elif pos == "beforeend":
        node.append(el)
    elif pos == "afterend" and node.parent is not None:
        node.parent.insert(node.parent.children.index(node) + 1, el)
    else:
        throw_dom("bad adjacent position")
    b.bump()
    return b.wrap(el)


async def _adjacent_text(t, a, i):
    from magpie_jsrun import to_string as _ts
    pos = (await _ts(i, a[0])).lower() if a else ""
    text = await _ts(i, a[1]) if len(a) > 1 else ""
    node = _el_this(t)
    kid = Node("#text", text=text)
    if pos == "beforebegin" and node.parent is not None:
        node.parent.insert(node.parent.children.index(node), kid)
    elif pos == "afterbegin":
        node.insert(0, kid)
    elif pos == "beforeend":
        node.append(kid)
    elif pos == "afterend" and node.parent is not None:
        node.parent.insert(node.parent.children.index(node) + 1, kid)
    else:
        throw_dom("bad adjacent position")
    bindings_of(t).bump()
    return UNDEFINED


async def _add_listener(t, a, i):
    from magpie_jsrun import to_string as _ts
    kind = await _ts(i, a[0]) if a else ""
    fn = a[1] if len(a) > 1 else UNDEFINED
    if not isinstance(fn, JSFunction):
        return UNDEFINED
    node = node_of(t)
    b = bindings_of(t)
    if node is not None:
        node.script_state.setdefault("listeners", {}).setdefault(kind, []).append(fn)
    elif b is not None:
        b.add_listener(id(t), kind, fn)
    return UNDEFINED


async def _remove_listener(t, a, i):
    from magpie_jsrun import to_string as _ts
    kind = await _ts(i, a[0]) if a else ""
    fn = a[1] if len(a) > 1 else UNDEFINED
    node = node_of(t)
    b = bindings_of(t)
    if node is not None:
        lst = node.script_state.get("listeners", {}).get(kind, [])
        node.script_state["listeners"][kind] = [f for f in lst if f is not fn]
    elif b is not None:
        b.remove_listener(id(t), kind, fn)
    return UNDEFINED


async def _dispatch_ev(t, a, i):
    v = a[0] if a else UNDEFINED
    if not isinstance(v, JSObject) or not isinstance(v.get_own("__event__"), _Event):
        throw_dom("dispatchEvent needs an event")
    b = bindings_of(t)
    ok = await dispatch(b, i, t, v.get_own("__event__").kind, props=v.get_own("__event__").props)
    return js_bool(ok)


async def _bounding_rect(t, a, i):
    node = _el_this(t)
    b = bindings_of(t)
    row = b.page.anchors.get(node.get_attribute("id"), 0) if node.get_attribute("id") else 0
    w = 0
    try:
        w = int(node.get_attribute("width") or 0)
    except ValueError:
        w = 0
    return js_object(i, {"x": JSNumber(0), "y": JSNumber(row), "width": JSNumber(w),
                         "height": JSNumber(1), "top": JSNumber(row), "left": JSNumber(0),
                         "bottom": JSNumber(row + 1), "right": JSNumber(w)})


async def _scroll_into_view(t, a, i):
    node = _el_this(t)
    b = bindings_of(t)
    anchor = node.get_attribute("id")
    b.pending_scroll = ("anchor", anchor) if anchor else ("node", id(node))
    return UNDEFINED


async def _scroll_pos(t, a, i):
    b = bindings_of(t)
    b.pending_scroll = ("top", 0)
    return UNDEFINED


async def _focus(t, a, i):
    b = bindings_of(t)
    b.active_element = _el_this(t)
    await dispatch(b, i, t, "focus", props={"bubbles": False})
    return UNDEFINED


async def _blur(t, a, i):
    b = bindings_of(t)
    if b.active_element is _el_this(t):
        b.active_element = None
    await dispatch(b, i, t, "blur", props={"bubbles": False})
    return UNDEFINED


async def _click(t, a, i):
    node = _el_this(t)
    b = bindings_of(t)
    ok = await dispatch(b, i, t, "click", props={"bubbles": True, "cancelable": True})
    if ok:
        await default_click_action(b, i, node)
    return UNDEFINED


async def default_click_action(b: Bindings, interp: Interpreter, node: Node) -> None:
    if node.tag == "a" and node.get_attribute("href"):
        b.nav_request = (resolve_url(b.base_url(), node.get_attribute("href")), False)
    elif node.tag == "input" and (node.get_attribute("type") or "text").lower() in ("checkbox", "radio"):
        if node.has_attribute("checked"):
            node.remove_attribute("checked")
        else:
            node.set_attribute("checked", "")
            if (node.get_attribute("type") or "").lower() == "radio" and node.get_attribute("name"):
                root = _document_root(node)
                for other in root.elements():
                    if other is not node and other.tag == "input" and other.get_attribute("name") == node.get_attribute("name"):
                        other.remove_attribute("checked")
        b.bump()
    elif node.tag == "input" and (node.get_attribute("type") or "").lower() in ("submit", "image"):
        form = _form_owner(node) or _ancestor(node, "form")
        if form is not None:
            b.submit_request = form
    elif node.tag == "button" and (node.get_attribute("type") or "submit").lower() == "submit":
        form = _form_owner(node) or _ancestor(node, "form")
        if form is not None:
            b.submit_request = form
    elif node.tag == "button" and node.get_attribute("type").lower() == "reset":
        form = _form_owner(node) or _ancestor(node, "form")
        if form is not None:
            _reset_form(form)
            b.bump()
    elif node.tag == "summary":
        details = _ancestor(node, "details")
        if details is not None:
            details.script_state["open"] = not details.script_state.get("open", details.has_attribute("open"))
            b.bump()
    elif node.tag == "option":
        select = _ancestor(node, "select")
        if select is not None:
            if not select.has_attribute("multiple"):
                for opt in select.get_elements_by_tag("option"):
                    opt.remove_attribute("selected")
            node.set_attribute("selected", "")
            b.bump()


def _ancestor(node: Node, tag: str) -> Node | None:
    cur = node.parent
    while cur is not None:
        if cur.tag == tag:
            return cur
        cur = cur.parent
    return None


def _form_owner(node: Node) -> Node | None:
    fid = node.get_attribute("form")
    if fid:
        root = _document_root(node)
        found = root.get_element_by_id(fid)
        if found is not None and found.tag == "form":
            return found
    return None


def _reset_form(form: Node) -> None:
    for c in form.iter():
        if c.tag == "input":
            if c.has_attribute("value"):
                pass
            if c.has_attribute("checked") and not c.script_state.get("default_checked"):
                c.remove_attribute("checked")
        elif c.tag == "textarea":
            c.set_text_content(c.script_state.get("default_text", ""))
        elif c.tag == "option":
            if c.has_attribute("selected") and not c.script_state.get("default_selected"):
                c.remove_attribute("selected")


async def _noop_undefined(t, a, i):
    return UNDEFINED


# ── media / forms / misc element helpers ─────────────────────────────────

def _media_src(bindings: Bindings, node: Node) -> str:
    src = node.get_attribute("src")
    if src:
        return resolve_url(bindings.base_url(), src)
    for s in node.get_elements_by_tag("source"):
        if s.get_attribute("src"):
            return resolve_url(bindings.base_url(), s.get_attribute("src"))
    return ""


async def _media_prop(t, a, i, name: str):
    b = bindings_of(t)
    src = _media_src(b, _el_this(t))
    info = b.media_info.setdefault(src, {})
    info[name] = to_boolean(a[0] if a else UNDEFINED) if name == "muted" else 1.0
    return UNDEFINED


async def _media_play(t, a, i):
    b = bindings_of(t)
    src = _media_src(b, _el_this(t))
    if src:
        b.media_request = ("play", src)
        b.media_info.setdefault(src, {})["paused"] = False
    p = JSPromise(i)
    p.resolve(UNDEFINED)
    return p


async def _media_pause(t, a, i):
    b = bindings_of(t)
    src = _media_src(b, _el_this(t))
    if src:
        b.media_request = ("pause", src)
        b.media_info.setdefault(src, {})["paused"] = True
    return UNDEFINED


async def _media_load(t, a, i):
    return UNDEFINED


def _select_value(node: Node) -> str:
    for opt in node.get_elements_by_tag("option"):
        if opt.has_attribute("selected"):
            return opt.get_attribute("value") or opt.text_content()
    opts = node.get_elements_by_tag("option")
    if opts:
        return opts[0].get_attribute("value") or opts[0].text_content()
    return ""


async def _set_select_value(t, a, i):
    from magpie_jsrun import to_string as _ts
    node = _el_this(t)
    want = await _ts(i, a[0]) if a else ""
    for opt in node.get_elements_by_tag("option"):
        if (opt.get_attribute("value") or opt.text_content()) == want:
            opt.set_attribute("selected", "")
        else:
            opt.remove_attribute("selected")
    bindings_of(t).bump()
    return UNDEFINED


def _selected_index(node: Node) -> int:
    opts = node.get_elements_by_tag("option")
    for k, opt in enumerate(opts):
        if opt.has_attribute("selected"):
            return k
    return -1


async def _set_selected_index(t, a, i):
    from magpie_jsrun import to_number as _tn
    node = _el_this(t)
    idx = int(await _tn(i, a[0])) if a else -1
    opts = node.get_elements_by_tag("option")
    for k, opt in enumerate(opts):
        if k == idx:
            opt.set_attribute("selected", "")
        else:
            opt.remove_attribute("selected")
    bindings_of(t).bump()
    return UNDEFINED


def _option_index(node: Node) -> int:
    select = _ancestor(node, "select")
    if select is None:
        return -1
    try:
        return select.get_elements_by_tag("option").index(node)
    except ValueError:
        return -1


async def _form_submit(t, a, i):
    bindings_of(t).submit_request = _el_this(t)
    return UNDEFINED


async def _form_reset(t, a, i):
    _reset_form(_el_this(t))
    bindings_of(t).bump()
    return UNDEFINED


async def _form_validity(t, a, i):
    node = _el_this(t)
    for c in node.iter():
        if c.tag in ("input", "select", "textarea") and c.has_attribute("required"):
            val = c.get_attribute("value") if c.tag == "input" else c.text_content()
            if not val.strip():
                return FALSE
    return TRUE


async def _canvas_context(t, a, i):
    from magpie_jsrun import to_string as _ts
    kind = (await _ts(i, a[0])).lower() if a else "2d"
    if kind != "2d":
        return NULL
    ctx = JSObject(INTRINSICS["Object_prototype"])
    ctx.define_own("__canvas__", _el_this(t), enumerable=False)
    for name in ("fillRect", "clearRect", "strokeRect", "beginPath", "closePath", "moveTo",
                 "lineTo", "stroke", "fill", "arc", "rect", "fillText", "strokeText",
                 "drawImage", "save", "restore", "translate", "scale", "rotate",
                 "setTransform", "resetTransform", "clip", "createLinearGradient",
                 "createRadialGradient", "createPattern", "putImageData", "setLineDash"):
        ctx.define_own(name, native(name, _canvas_noop), enumerable=False)
    ctx.define_own("measureText", native("measureText", _canvas_measure), enumerable=False)
    ctx.define_own("getImageData", native("getImageData", _canvas_noop), enumerable=False)
    for prop in ("fillStyle", "strokeStyle", "font", "lineWidth", "globalAlpha"):
        ctx.define_own(prop, JSString(""), writable=True)
    return ctx


async def _canvas_noop(t, a, i):
    return UNDEFINED


async def _canvas_measure(t, a, i):
    from magpie_jsrun import to_string as _ts
    s = await _ts(i, a[0]) if a else ""
    return js_object(i, {"width": JSNumber(len(s) * 6.0)})


async def _set_details_open(t, a, i):
    node = _el_this(t)
    node.script_state["open"] = to_boolean(a[0] if a else UNDEFINED)
    bindings_of(t).bump()
    return UNDEFINED


# ── live collections ─────────────────────────────────────────────────────

def make_node_list(bindings: Bindings, nodes, *, live=None) -> JSObject:
    obj = JSObject(INTRINSICS["Object_prototype"])
    _tag_bindings(obj, bindings)
    snapshot = list(nodes() if callable(nodes) else nodes)
    obj.define_own("__items__", snapshot, enumerable=False)
    _collection_api(bindings, obj, live or (lambda: snapshot))
    return obj


def make_collection(bindings: Bindings, nodes, *, live=None) -> JSObject:
    nodelist = make_node_list(bindings, nodes, live=live)
    _m(nodelist, "namedItem", _collection_named_item)
    return nodelist


def _collection_api(bindings: Bindings, obj: JSObject, live) -> None:
    def length(t, a, i):
        return JSNumber(len(live()))

    async def item(t, a, i):
        from magpie_jsrun import to_number as _tn
        items = live()
        idx = int(await _tn(i, a[0])) if a else 0
        return bindings.wrap(items[idx]) if 0 <= idx < len(items) else NULL

    obj.define_own("length", JSNumber(0), enumerable=False)
    obj.define_accessor("length", native("get length", length), None, enumerable=False)
    obj.define_own("item", native("item", item), enumerable=False)
    for k, n in enumerate(live()):
        obj.define_own(str(k), bindings.wrap(n), enumerable=False)
    obj.define_own("@@iterator", native("@@iterator", _collection_iterator(bindings, live)), enumerable=False)


def _collection_iterator(bindings: Bindings, live):
    def handler(t, a, i):
        from magpie_jslib import _make_iterator
        return _make_iterator(i, [bindings.wrap(n) for n in live()])
    return handler


async def _collection_named_item(t, a, i):
    from magpie_jsrun import to_string as _ts
    name = await _ts(i, a[0]) if a else ""
    items = t.get_own("__items__")
    for n in items if isinstance(items, list) else []:
        if n.get_attribute("id") == name or n.get_attribute("name") == name:
            return bindings_of(t).wrap(n)
    return NULL


def make_token_list(bindings: Bindings, node: Node) -> JSObject:
    obj = JSObject(INTRINSICS["Object_prototype"])
    _tag_bindings(obj, bindings)
    obj.define_own("__token_node__", _NodeRef(node), enumerable=False)
    _m(obj, "add", _tokens_add)
    _m(obj, "remove", _tokens_remove)
    _m(obj, "toggle", _tokens_toggle)
    _m(obj, "contains", _tokens_contains)
    _m(obj, "replace", _tokens_replace)
    _acc(obj, "value", lambda t, a, i: JSString(_token_node(t).get_attribute("class")),
         lambda t, a, i: _tokens_set(t, a, i))
    _acc(obj, "length", lambda t, a, i: JSNumber(len(_token_node(t).get_attribute("class").split())))
    obj.define_own("@@iterator", native("@@iterator", _tokens_iter), enumerable=False)
    return obj


def _token_node(t) -> Node:
    ref = t.get_own("__token_node__")
    if not isinstance(ref, _NodeRef):
        throw_dom("token list on non-element")
    return ref.node


def _tokens_set(t, a, i):
    from magpie_jsrun import to_string as _ts
    node = _token_node(t)

    async def run():
        node.set_attribute("class", await _ts(i, a[0]) if a else "")
        bindings_of(t).bump()
    return run()


async def _tokens_add(t, a, i):
    from magpie_jsrun import to_string as _ts
    node = _token_node(t)
    classes = node.get_attribute("class").split()
    for v in a:
        c = await _ts(i, v)
        if c and c not in classes:
            classes.append(c)
    node.set_attribute("class", " ".join(classes))
    bindings_of(t).bump()
    return UNDEFINED


async def _tokens_remove(t, a, i):
    from magpie_jsrun import to_string as _ts
    node = _token_node(t)
    drop = {await _ts(i, v) for v in a}
    node.set_attribute("class", " ".join(c for c in node.get_attribute("class").split() if c not in drop))
    bindings_of(t).bump()
    return UNDEFINED


async def _tokens_toggle(t, a, i):
    from magpie_jsrun import to_string as _ts
    node = _token_node(t)
    c = await _ts(i, a[0]) if a else ""
    force = a[1] if len(a) > 1 else UNDEFINED
    classes = node.get_attribute("class").split()
    if force is UNDEFINED:
        should = c not in classes
    else:
        should = to_boolean(force)
    if should and c not in classes:
        classes.append(c)
    if not should and c in classes:
        classes.remove(c)
    node.set_attribute("class", " ".join(classes))
    bindings_of(t).bump()
    return js_bool(should)


async def _tokens_contains(t, a, i):
    from magpie_jsrun import to_string as _ts
    return js_bool((await _ts(i, a[0]) if a else "") in _token_node(t).get_attribute("class").split())


async def _tokens_replace(t, a, i):
    from magpie_jsrun import to_string as _ts
    node = _token_node(t)
    old = await _ts(i, a[0]) if a else ""
    new = await _ts(i, a[1]) if len(a) > 1 else ""
    classes = node.get_attribute("class").split()
    if old not in classes:
        return FALSE
    node.set_attribute("class", " ".join(new if c == old else c for c in classes))
    bindings_of(t).bump()
    return TRUE


def _tokens_iter(t, a, i):
    from magpie_jslib import _make_iterator
    return _make_iterator(i, [JSString(c) for c in _token_node(t).get_attribute("class").split()])


# ── document ─────────────────────────────────────────────────────────────

def install_document_api(bindings: Bindings, w: JSObject, node: Node) -> None:
    _acc(w, "readyState", lambda t, a, i: JSString(bindings_of(t).ready_state))
    _acc(w, "title", lambda t, a, i: JSString(bindings.page.title),
         lambda t, a, i: _set_doc_title(t, a, i))
    _acc(w, "URL", lambda t, a, i: JSString(bindings.base_url()))
    _acc(w, "documentURI", lambda t, a, i: JSString(bindings.base_url()))
    _acc(w, "domain", lambda t, a, i: JSString(url_host_label(bindings.base_url())))
    _acc(w, "referrer", lambda t, a, i: JSString(bindings.referrer))
    _acc(w, "cookie", lambda t, a, i: JSString(_cookie_get(bindings)),
         lambda t, a, i: _cookie_set(t, a, i))
    _acc(w, "documentElement", lambda t, a, i: _doc_el(bindings, "html"))
    _acc(w, "head", lambda t, a, i: _doc_el(bindings, "head"))
    _acc(w, "body", lambda t, a, i: _doc_el(bindings, "body"))
    _acc(w, "activeElement", lambda t, a, i: bindings.wrap(bindings.active_element) if bindings.active_element else NULL)
    _acc(w, "currentScript", lambda t, a, i: bindings.wrap(bindings.current_script) if bindings.current_script else NULL)
    _acc(w, "visibilityState", lambda t, a, i: JSString("visible"))
    _acc(w, "hidden", lambda t, a, i: FALSE)
    _acc(w, "characterSet", lambda t, a, i: JSString("UTF-8"))
    _acc(w, "contentType", lambda t, a, i: JSString("text/html"))
    _acc(w, "forms", lambda t, a, i: make_collection(bindings, _root_el(bindings).get_elements_by_tag("form")))
    _acc(w, "images", lambda t, a, i: make_collection(bindings, _root_el(bindings).get_elements_by_tag("img")))
    _acc(w, "links", lambda t, a, i: make_collection(bindings, [n for n in _root_el(bindings).get_elements_by_tag("a") if n.get_attribute("href")]))
    _acc(w, "scripts", lambda t, a, i: make_collection(bindings, _root_el(bindings).get_elements_by_tag("script")))
    _acc(w, "anchors", lambda t, a, i: make_collection(bindings, [n for n in _root_el(bindings).get_elements_by_tag("a") if n.get_attribute("name")]))
    for name, fn in (
        ("getElementById", _doc_by_id), ("getElementsByTagName", _doc_by_tag),
        ("getElementsByClassName", _doc_by_class), ("getElementsByName", _doc_by_name),
        ("querySelector", _doc_query_one), ("querySelectorAll", _doc_query_all),
        ("createElement", _doc_create), ("createElementNS", _doc_create_ns),
        ("createTextNode", _doc_create_text), ("createComment", _doc_create_comment),
        ("createDocumentFragment", _doc_create_frag), ("createEvent", _doc_create_event),
        ("createAttribute", _doc_create_attr), ("importNode", _doc_import),
        ("adoptNode", _doc_adopt), ("write", _doc_write), ("writeln", _doc_writeln),
        ("open", _doc_open), ("close", _doc_close), ("hasFocus", _doc_has_focus),
        ("execCommand", _doc_exec), ("queryCommandSupported", _doc_exec),
        ("addEventListener", _doc_add_listener), ("removeEventListener", _doc_remove_listener),
        ("dispatchEvent", _doc_dispatch), ("hasStorageAccess", _doc_false),
        ("elementFromPoint", _doc_null), ("elementsFromPoint", _doc_empty_array),
        ("getSelection", _doc_selection),
    ):
        _m(w, name, fn)


def _root_el(bindings: Bindings) -> Node:
    return bindings.page.root


def _doc_el(bindings: Bindings, tag: str):
    found = _root_el(bindings).query_selector(tag)
    return bindings.wrap(found) if found else NULL


async def _set_doc_title(t, a, i):
    from magpie_jsrun import to_string as _ts
    b = bindings_of(t)
    title = await _ts(i, a[0]) if a else ""
    head = _root_el(b).query_selector("head")
    title_el = _root_el(b).query_selector("title")
    if title_el is None:
        if head is None:
            return UNDEFINED
        title_el = Node("title")
        head.append(title_el)
    title_el.set_text_content(title)
    b.page.title = title
    b.bump()
    return UNDEFINED


def _cookie_get(bindings: Bindings) -> str:
    jar = bindings.client.cookies if hasattr(bindings.client, "cookies") else None
    if jar is None:
        return ""
    header = jar.header_for(bindings.base_url(), method="GET", top_level=True)
    return header


async def _cookie_set(t, a, i):
    from magpie_jsrun import to_string as _ts
    b = bindings_of(t)
    raw = await _ts(i, a[0]) if a else ""
    jar = b.client.cookies if hasattr(b.client, "cookies") else None
    if jar is None or not raw.strip():
        return UNDEFINED
    # Only the first name=value pair; attributes honored by the jar parser.
    first = raw.split(";")[0]
    if "=" in first:
        from magpie_fetch import parse_set_cookie
        import time as _time
        host = url_host_label(b.base_url())
        cookie = parse_set_cookie(raw, host, "/", _time.time())
        if cookie is not None and (cookie.host == host or host.endswith("." + cookie.host)):
            jar.set_from_headers(b.base_url(), [("Set-Cookie", raw)])
    return UNDEFINED


async def _doc_by_id(t, a, i):
    from magpie_jsrun import to_string as _ts
    b = bindings_of(t)
    found = _root_el(b).get_element_by_id(await _ts(i, a[0]) if a else "")
    return b.wrap(found) if found else NULL


async def _doc_by_tag(t, a, i):
    from magpie_jsrun import to_string as _ts
    b = bindings_of(t)
    name = (await _ts(i, a[0])).lower() if a else ""
    kids = _root_el(b).get_elements_by_tag(name) if name != "*" else [n for n in _root_el(b).elements()]
    return make_collection(b, kids)


async def _doc_by_class(t, a, i):
    from magpie_jsrun import to_string as _ts
    b = bindings_of(t)
    return make_collection(b, _root_el(b).get_elements_by_class(await _ts(i, a[0]) if a else ""))


async def _doc_by_name(t, a, i):
    from magpie_jsrun import to_string as _ts
    b = bindings_of(t)
    name = await _ts(i, a[0]) if a else ""
    return make_collection(b, [n for n in _root_el(b).elements() if n.get_attribute("name") == name])


async def _doc_query_one(t, a, i):
    from magpie_jsrun import to_string as _ts
    b = bindings_of(t)
    found = _root_el(b).query_selector(await _ts(i, a[0]) if a else "")
    return b.wrap(found) if found else NULL


async def _doc_query_all(t, a, i):
    from magpie_jsrun import to_string as _ts
    b = bindings_of(t)
    return make_collection(b, _root_el(b).query_selector_all(await _ts(i, a[0]) if a else ""))


async def _doc_create(t, a, i):
    from magpie_jsrun import to_string as _ts
    b = bindings_of(t)
    tag = (await _ts(i, a[0])).lower() if a else "div"
    if not tag or " " in tag:
        throw_dom("bad tag name")
    return b.wrap(Node(tag))


async def _doc_create_ns(t, a, i):
    return await _doc_create(t, [a[1]] if len(a) > 1 else [], i)


async def _doc_create_text(t, a, i):
    from magpie_jsrun import to_string as _ts
    return bindings_of(t).wrap(Node("#text", text=await _ts(i, a[0]) if a else ""))


async def _doc_create_comment(t, a, i):
    from magpie_jsrun import to_string as _ts
    return bindings_of(t).wrap(Node("#comment", text=await _ts(i, a[0]) if a else ""))


async def _doc_create_frag(t, a, i):
    return bindings_of(t).wrap(Node("#fragment"))


async def _doc_create_event(t, a, i):
    from magpie_jsrun import to_string as _ts
    install_event_proto()
    return make_event(bindings_of(t), await _ts(i, a[0]) if a else "Event")


async def _doc_create_attr(t, a, i):
    from magpie_jsrun import to_string as _ts
    b = bindings_of(t)
    name = (await _ts(i, a[0])).lower() if a else ""
    obj = JSObject(INTRINSICS["Object_prototype"])
    obj.define_own("name", JSString(name), enumerable=False)
    obj.define_own("value", JSString(""))
    return obj


async def _doc_import(t, a, i):
    v = a[0] if a else UNDEFINED
    node = node_of(v) if isinstance(v, JSObject) else None
    if node is None:
        throw_dom("importNode needs a node")
    deep = to_boolean(a[1]) if len(a) > 1 else TRUE
    return bindings_of(t).wrap(node.clone(deep=bool(deep)))


async def _doc_adopt(t, a, i):
    v = a[0] if a else UNDEFINED
    node = node_of(v) if isinstance(v, JSObject) else None
    if node is None:
        throw_dom("adoptNode needs a node")
    if node.parent is not None:
        node.parent.remove(node)
    bindings_of(t).bump()
    return bindings_of(t).wrap(node)


async def _doc_write(t, a, i):
    from magpie_jsrun import to_string as _ts
    b = bindings_of(t)
    markup = "".join(await _ts(i, v) for v in a)
    body = _root_el(b).query_selector("body") or _root_el(b)
    frag = parse_html(f"<div>{markup}</div>").query_selector("div")
    for c in list(frag.children) if frag else []:
        body.append(c)
    b.bump()
    return UNDEFINED


async def _doc_writeln(t, a, i):
    from magpie_jsrun import to_string as _ts
    return await _doc_write(t, [*a, JSString("\n")], i)


async def _doc_open(t, a, i):
    return UNDEFINED


async def _doc_close(t, a, i):
    return UNDEFINED


async def _doc_has_focus(t, a, i):
    return TRUE


async def _doc_exec(t, a, i):
    return FALSE


async def _doc_add_listener(t, a, i):
    return await _add_listener(t, a, i)


async def _doc_remove_listener(t, a, i):
    return await _remove_listener(t, a, i)


async def _doc_dispatch(t, a, i):
    return await _dispatch_ev(t, a, i)


async def _doc_false(t, a, i):
    return FALSE


async def _doc_null(t, a, i):
    return NULL


async def _doc_empty_array(t, a, i):
    return js_array(i, [])


async def _doc_selection(t, a, i):
    return js_object(i, {"toString": native("toString", lambda tt, aa, ii: JSString(""))})


# ── window ───────────────────────────────────────────────────────────────

def install_browser(g: JSObject, bindings: Bindings, interp: Interpreter) -> None:
    from magpie_jslib import EventState
    install_event_proto()
    doc = bindings.wrap(bindings.page.root)
    _tag_bindings(g, bindings)
    g.define_own("document", doc)
    g.define_own("window", g)
    g.define_own("self", g)
    g.define_own("top", g)
    g.define_own("parent", g)
    g.define_own("frames", js_array(interp, []))
    g.define_own("length", JSNumber(0), enumerable=False)
    g.define_own("location", make_location(bindings))
    g.define_own("history", make_history(bindings))
    g.define_own("navigator", make_navigator(bindings))
    g.define_own("screen", make_screen(bindings))
    g.define_own("localStorage", make_storage(bindings, "local"))
    g.define_own("sessionStorage", make_storage(bindings, "session"))
    g.define_own("customElements", js_object(interp, {
        "define": native("define", _ce_define), "get": native("get", _ce_get),
        "whenDefined": native("whenDefined", _ce_when_defined), "upgrade": native("upgrade", _ce_noop),
    }))
    g.define_own("DOMParser", make_dom_parser(bindings))
    g.define_own("MutationObserver", make_mutation_observer(bindings))
    g.define_own("ResizeObserver", make_noop_observer("ResizeObserver"))
    g.define_own("IntersectionObserver", make_noop_observer("IntersectionObserver"))
    g.define_own("Node", _node_ctor_fn())
    for const, val in (("ELEMENT_NODE", 1), ("TEXT_NODE", 3), ("COMMENT_NODE", 8), ("DOCUMENT_NODE", 9)):
        INTRINSICS["Node"].define_own(const, JSNumber(val), enumerable=False)
    for name, fn in (
        ("getComputedStyle", _get_computed_style), ("matchMedia", _match_media),
        ("requestAnimationFrame", _raf), ("cancelAnimationFrame", _cancel_raf),
        ("open", _window_open), ("close", _window_close), ("print", _noop_undefined),
        ("focus", _noop_undefined), ("blur", _noop_undefined),
        ("scrollTo", _window_scroll), ("scrollBy", _window_scroll), ("scroll", _window_scroll),
        ("moveTo", _noop_undefined), ("moveBy", _noop_undefined), ("resizeTo", _noop_undefined),
        ("alert", _window_alert), ("confirm", _window_confirm), ("prompt", _window_prompt),
        ("getSelection", _doc_selection), ("find", _doc_false), ("stop", _noop_undefined),
        ("addEventListener", _window_add_listener), ("removeEventListener", _window_remove_listener),
        ("dispatchEvent", _window_dispatch),
        ("WebSocket", _unsupported("WebSocket")), ("EventSource", _unsupported("EventSource")),
        ("Worker", _unsupported("Worker")), ("SharedWorker", _unsupported("SharedWorker")),
        ("Proxy", _unsupported("Proxy")),
    ):
        if isinstance(fn, JSFunction):
            g.define_own(name, fn)
        else:
            g.define_own(name, native(name, fn), enumerable=False)
    for name in ("onload", "onerror", "onpopstate", "onhashchange", "onbeforeunload", "onunload"):
        g.define_own(name, NULL, writable=True)


def _unsupported(name: str):
    async def construct(this, args, interp):
        throw_dom(f"{name} is not supported in Magpie")
    return native(name, construct)


async def _noop_undefined(t, a, i):
    return UNDEFINED


async def _ce_define(t, a, i):
    return UNDEFINED


async def _ce_get(t, a, i):
    return UNDEFINED


async def _ce_when_defined(t, a, i):
    p = JSPromise(i)
    p.resolve(UNDEFINED)
    return p


async def _ce_noop(t, a, i):
    return UNDEFINED


def _node_ctor_fn() -> JSFunction:
    fn = native("Node", _node_ctor)
    INTRINSICS["Node"] = fn
    return fn


async def _node_ctor(this, args, interp):
    throw_dom("Node cannot be constructed")


# ── location / history ───────────────────────────────────────────────────

def make_location(bindings: Bindings) -> JSObject:
    obj = JSObject(INTRINSICS["Object_prototype"])
    _tag_bindings(obj, bindings)
    _acc(obj, "href", lambda t, a, i: JSString(bindings.base_url()),
         lambda t, a, i: _loc_set_href(t, a, i))
    for name in ("protocol", "host", "hostname", "port", "pathname", "search", "hash", "origin"):
        _acc(obj, name, _loc_getter(name), _loc_setter(name))
    _m(obj, "assign", _loc_assign)
    _m(obj, "replace", _loc_replace)
    _m(obj, "reload", _loc_reload)
    _m(obj, "toString", _loc_to_string)
    _m(obj, "toJSON", _loc_to_string)
    return obj


def _loc_parts(bindings: Bindings):
    return urllib.parse.urlparse(bindings.base_url())


def _loc_getter(name: str):
    def get(t, a, i):
        b = bindings_of(t)
        p = _loc_parts(b)
        table = {
            "protocol": p.scheme + ":", "host": p.netloc, "hostname": p.hostname or "",
            "port": str(p.port) if p.port else "", "pathname": p.path or "/",
            "search": ("?" + p.query) if p.query else "", "hash": ("#" + p.fragment) if p.fragment else "",
            "origin": f"{p.scheme}://{p.netloc}" if p.scheme in ("http", "https") else "null",
        }
        return JSString(table[name])
    return get


def _loc_setter(name: str):
    async def setv(t, a, i):
        from magpie_jsrun import to_string as _ts
        b = bindings_of(t)
        v = await _ts(i, a[0]) if a else ""
        p = _loc_parts(b)
        try:
            if name == "protocol":
                np = p._replace(scheme=v.rstrip(":").lower())
            elif name == "host":
                np = p._replace(netloc=v)
            elif name == "hostname":
                np = p._replace(netloc=v + (f":{p.port}" if p.port else ""))
            elif name == "port":
                np = p._replace(netloc=p.hostname + (f":{v}" if v else ""))
            elif name == "pathname":
                np = p._replace(path=v if v.startswith("/") else "/" + v)
            elif name == "search":
                np = p._replace(query=v[1:] if v.startswith("?") else v)
            elif name == "hash":
                np = p._replace(fragment=v[1:] if v.startswith("#") else v)
            else:
                return UNDEFINED
            b.nav_request = (np.geturl(), False)
        except ValueError:
            pass
        return UNDEFINED
    return setv


async def _loc_set_href(t, a, i):
    from magpie_jsrun import to_string as _ts
    b = bindings_of(t)
    b.nav_request = (resolve_url(b.base_url(), await _ts(i, a[0]) if a else ""), False)
    return UNDEFINED


async def _loc_assign(t, a, i):
    return await _loc_set_href(t, a, i)


async def _loc_replace(t, a, i):
    from magpie_jsrun import to_string as _ts
    b = bindings_of(t)
    b.nav_request = (resolve_url(b.base_url(), await _ts(i, a[0]) if a else ""), True)
    return UNDEFINED


async def _loc_reload(t, a, i):
    b = bindings_of(t)
    b.nav_request = (b.base_url(), True)
    return UNDEFINED


async def _loc_to_string(t, a, i):
    return JSString(bindings_of(t).base_url())


def make_history(bindings: Bindings) -> JSObject:
    obj = JSObject(INTRINSICS["Object_prototype"])
    _tag_bindings(obj, bindings)
    _acc(obj, "length", lambda t, a, i: JSNumber(len(bindings.history_stack)))
    _acc(obj, "state", lambda t, a, i: bindings.history_state or NULL)
    _acc(obj, "scrollRestoration", lambda t, a, i: JSString("auto"),
         lambda t, a, i: _history_scroll(t, a, i))
    _m(obj, "back", _history_back)
    _m(obj, "forward", _history_forward)
    _m(obj, "go", _history_go)
    _m(obj, "pushState", _history_push)
    _m(obj, "replaceState", _history_replace)
    return obj


async def _history_scroll(t, a, i):
    return UNDEFINED


async def _history_back(t, a, i):
    b = bindings_of(t)
    if b.history_index > 0:
        b.history_index -= 1
        b.nav_request = (b.history_stack[b.history_index], True)
    return UNDEFINED


async def _history_forward(t, a, i):
    b = bindings_of(t)
    if b.history_index < len(b.history_stack) - 1:
        b.history_index += 1
        b.nav_request = (b.history_stack[b.history_index], True)
    return UNDEFINED


async def _history_go(t, a, i):
    from magpie_jsrun import to_number as _tn
    b = bindings_of(t)
    delta = int(await _tn(i, a[0])) if a else 0
    idx = max(0, min(len(b.history_stack) - 1, b.history_index + delta))
    if idx != b.history_index:
        b.history_index = idx
        b.nav_request = (b.history_stack[idx], True)
    return UNDEFINED


def _same_origin(a: str, b: str) -> bool:
    pa, pb = urllib.parse.urlparse(a), urllib.parse.urlparse(b)
    return (pa.scheme, pa.hostname, pa.port) == (pb.scheme, pb.hostname, pb.port)


async def _history_push(t, a, i):
    from magpie_jsrun import to_string as _ts
    b = bindings_of(t)
    state = a[0] if a else UNDEFINED
    url = resolve_url(b.base_url(), await _ts(i, a[2]) if len(a) > 2 and a[2] is not UNDEFINED else b.base_url())
    if not _same_origin(url, b.base_url()):
        throw_dom("pushState across origins is blocked")
    b.history_stack = b.history_stack[:b.history_index + 1] + [url]
    b.history_index += 1
    b.history_state = state
    b.page.url = url
    return UNDEFINED


async def _history_replace(t, a, i):
    from magpie_jsrun import to_string as _ts
    b = bindings_of(t)
    state = a[0] if a else UNDEFINED
    url = resolve_url(b.base_url(), await _ts(i, a[2]) if len(a) > 2 and a[2] is not UNDEFINED else b.base_url())
    if not _same_origin(url, b.base_url()):
        throw_dom("replaceState across origins is blocked")
    b.history_stack[b.history_index] = url
    b.history_state = state
    b.page.url = url
    return UNDEFINED


# ── navigator / screen / storage ─────────────────────────────────────────

def make_navigator(bindings: Bindings) -> JSObject:
    import os as _os
    obj = JSObject(INTRINSICS["Object_prototype"])
    obj.define_own("userAgent", JSString("magpie-tui/0.1 (faeOS private browser)"))
    obj.define_own("language", JSString("en-US"))
    obj.define_own("languages", js_array(_interp_of(bindings), [JSString("en-US"), JSString("en")]))
    obj.define_own("onLine", TRUE)
    obj.define_own("cookieEnabled", TRUE)
    obj.define_own("hardwareConcurrency", JSNumber(_os.cpu_count() or 4))
    obj.define_own("platform", JSString("Linux x86_64"))
    obj.define_own("vendor", JSString(""))
    obj.define_own("webdriver", FALSE)
    obj.define_own("clipboard", js_object(_interp_of(bindings), {
        "writeText": native("writeText", _clip_write),
        "readText": native("readText", _clip_read),
    }))
    obj.define_own("geolocation", js_object(_interp_of(bindings), {
        "getCurrentPosition": native("getCurrentPosition", _geo_denied),
        "watchPosition": native("watchPosition", _geo_denied),
    }))
    obj.define_own("mediaDevices", js_object(_interp_of(bindings), {
        "getUserMedia": native("getUserMedia", _media_denied),
        "enumerateDevices": native("enumerateDevices", _media_empty),
    }))
    obj.define_own("permissions", js_object(_interp_of(bindings), {
        "query": native("query", _perm_query),
    }))
    return obj


def _interp_of(bindings: Bindings):
    return bindings.interp_ref


async def _clip_write(t, a, i):
    from magpie_jsrun import to_string as _ts
    # Clipboard writes route through the TUI (OSC52); here we stash the text.
    text = await _ts(i, a[0]) if a else ""
    p = JSPromise(i)
    p.resolve(UNDEFINED)
    # The TUI picks this up via bindings.copy_text set by the caller wrapper.
    i.console_lines.append(f"[clipboard] {text[:80]}")
    return p


async def _clip_read(t, a, i):
    p = JSPromise(i)
    p.reject(make_error_value("Error", "clipboard read is not permitted"))
    return p


async def _geo_denied(t, a, i):
    if len(a) > 1 and isinstance(a[1], JSFunction):
        await i.call_value(a[1], UNDEFINED, [js_object(i, {"code": JSNumber(1), "message": JSString("denied")})])
    return UNDEFINED


async def _media_denied(t, a, i):
    p = JSPromise(i)
    p.reject(make_error_value("Error", "media devices are unavailable"))
    return p


async def _media_empty(t, a, i):
    p = JSPromise(i)
    p.resolve(js_array(i, []))
    return p


async def _perm_query(t, a, i):
    return js_object(i, {"state": JSString("denied")})


def make_screen(bindings: Bindings) -> JSObject:
    cols, rows = bindings.term_size
    obj = JSObject(INTRINSICS["Object_prototype"])
    for name, val in (("width", cols), ("height", rows), ("availWidth", cols),
                      ("availHeight", rows), ("colorDepth", 24), ("pixelDepth", 24)):
        obj.define_own(name, JSNumber(val))
    obj.define_own("orientation", js_object(_interp_of(bindings), {"type": JSString("landscape-primary")}))
    return obj


def make_storage(bindings: Bindings, which: str) -> JSObject:
    key = ("storage", which, url_host_label(bindings.base_url()))
    store = bindings.storages.setdefault(key, {})
    obj = JSObject(INTRINSICS["Object_prototype"])
    _tag_bindings(obj, bindings)
    obj.define_own("__store__", _Store(store), enumerable=False)
    _m(obj, "getItem", _store_get)
    _m(obj, "setItem", _store_set)
    _m(obj, "removeItem", _store_remove)
    _m(obj, "clear", _store_clear)
    _m(obj, "key", _store_key)
    _acc(obj, "length", lambda t, a, i: JSNumber(len(_store_this(t))))
    return obj


class _Store:
    __slots__ = ("data",)

    def __init__(self, data: dict) -> None:
        self.data = data


def _store_this(t) -> dict:
    raw = t.get_own("__store__") if isinstance(t, JSObject) else None
    if not isinstance(raw, _Store):
        throw_dom("storage member on non-storage")
    return raw.data


async def _store_get(t, a, i):
    from magpie_jsrun import to_string as _ts
    return JSString(_store_this(t).get(await _ts(i, a[0]) if a else "", "")) if (await _ts(i, a[0]) if a else "") in _store_this(t) else NULL


async def _store_set(t, a, i):
    from magpie_jsrun import to_string as _ts
    store = _store_this(t)
    store[await _ts(i, a[0]) if a else ""] = await _ts(i, a[1]) if len(a) > 1 else ""
    return UNDEFINED


async def _store_remove(t, a, i):
    from magpie_jsrun import to_string as _ts
    _store_this(t).pop(await _ts(i, a[0]) if a else "", None)
    return UNDEFINED


async def _store_clear(t, a, i):
    _store_this(t).clear()
    return UNDEFINED


async def _store_key(t, a, i):
    from magpie_jsrun import to_number as _tn
    keys = sorted(_store_this(t).keys())
    idx = int(await _tn(i, a[0])) if a else 0
    return JSString(keys[idx]) if 0 <= idx < len(keys) else NULL


def make_dom_parser(bindings: Bindings) -> JSFunction:
    async def parse_from_string(t, a, i):
        from magpie_jsrun import to_string as _ts
        text = await _ts(i, a[0]) if a else ""
        mime = (await _ts(i, a[1])).lower() if len(a) > 1 else "text/html"
        if mime not in ("text/html", "text/xml", "application/xml"):
            throw_dom("only text/html parsing is supported")
        root = parse_html(text, js_enabled=True)
        sub = Bindings.__new__(Bindings)
        sub.__dict__.update(bindings.__dict__)
        sub.page = Page(url=bindings.base_url(), title="", root=root, rules=collect_styles(root))
        sub.wrappers = {}
        return sub.wrap(root)
    obj = JSObject(INTRINSICS["Object_prototype"])
    obj.define_own("parseFromString", native("parseFromString", parse_from_string))

    async def construct(this, args, interp):
        return obj
    fn = JSFunction(kind="native", proto=INTRINSICS["Function_prototype"])
    fn.handler = construct
    fn.define_own("name", JSString("DOMParser"), enumerable=False)
    fn.define_own("prototype", obj, enumerable=False)
    return fn


def make_mutation_observer(bindings: Bindings) -> JSFunction:
    async def construct(this, args, interp):
        cb = args[0] if args and isinstance(args[0], JSFunction) else None
        if cb is None:
            throw_dom("MutationObserver needs a callback")
        obj = JSObject(INTRINSICS["Object_prototype"])
        _tag_bindings(obj, bindings)
        obj.define_own("__observer__", _Observer(cb, bindings.dom_version), enumerable=False)
        obj.define_own("observe", native("observe", _mo_observe))
        obj.define_own("disconnect", native("disconnect", _mo_disconnect))
        obj.define_own("takeRecords", native("takeRecords", _mo_take))
        return obj
    fn = JSFunction(kind="native", proto=INTRINSICS["Function_prototype"])
    fn.handler = construct
    fn.define_own("name", JSString("MutationObserver"), enumerable=False)
    return fn


class _Observer:
    __slots__ = ("callback", "seen", "active")

    def __init__(self, callback, seen: int) -> None:
        self.callback = callback
        self.seen = seen
        self.active = False


async def _mo_observe(t, a, i):
    raw = t.get_own("__observer__") if isinstance(t, JSObject) else None
    if not isinstance(raw, _Observer):
        throw_dom("observe on non-observer")
    raw.active = True
    b = bindings_of(t)
    if b is not None and raw not in b.mutation_watchers:
        b.mutation_watchers.append(raw)
    return UNDEFINED


async def _mo_disconnect(t, a, i):
    raw = t.get_own("__observer__") if isinstance(t, JSObject) else None
    if isinstance(raw, _Observer):
        raw.active = False
    return UNDEFINED


async def _mo_take(t, a, i):
    return js_array(i, [])


def make_noop_observer(name: str) -> JSFunction:
    async def construct(this, args, interp):
        obj = JSObject(INTRINSICS["Object_prototype"])
        obj.define_own("observe", native("observe", _ce_noop))
        obj.define_own("disconnect", native("disconnect", _ce_noop))
        obj.define_own("unobserve", native("unobserve", _ce_noop))
        return obj
    fn = JSFunction(kind="native", proto=INTRINSICS["Function_prototype"])
    fn.handler = construct
    fn.define_own("name", JSString(name), enumerable=False)
    return fn


async def _get_computed_style(t, a, i):
    from magpie_dom import compute_style as _cs, ComputedStyle
    v = a[0] if a else UNDEFINED
    node = node_of(v) if isinstance(v, JSObject) else None
    if node is None:
        throw_dom("getComputedStyle needs an element")
    b = bindings_of(t)
    style = _cs(node, b.page.rules, None)
    obj = JSObject(INTRINSICS["Object_prototype"])
    from magpie_dom import color_ansi
    if style.color is not None:
        r, g, bl = style.color.rgb()
        obj.define_own("color", JSString(f"rgb({r}, {g}, {bl})"))
    if style.background is not None:
        r, g, bl = style.background.rgb()
        obj.define_own("backgroundColor", JSString(f"rgb({r}, {g}, {bl})"))
    obj.define_own("display", JSString(style.display))
    obj.define_own("fontWeight", JSString("bold" if style.bold else "normal"))
    obj.define_own("fontStyle", JSString("italic" if style.italic else "normal"))
    obj.define_own("textAlign", JSString(style.align))
    obj.define_own("getPropertyValue", native("getPropertyValue", _computed_get))
    return obj


async def _computed_get(t, a, i):
    return JSString("")


async def _match_media(t, a, i):
    from magpie_jsrun import to_string as _ts
    query = await _ts(i, a[0]) if a else ""
    obj = js_object(i, {"matches": FALSE, "media": JSString(query)})
    obj.define_own("addListener", native("addListener", _ce_noop))
    obj.define_own("removeListener", native("removeListener", _ce_noop))
    return obj


async def _raf(t, a, i):
    fn = a[0] if a and isinstance(a[0], JSFunction) else None
    if fn is None:
        throw_dom("rAF needs a function")
    ev = i.events if i.events is not None else EventState()
    i.events = ev

    async def cb() -> None:
        try:
            await i.call_value(fn, i.global_obj, [JSNumber(time.monotonic() * 1000.0)])
        except ThrowExc:
            pass

    return JSNumber(ev.add_timer(time.monotonic() + 0.016, cb))


async def _cancel_raf(t, a, i):
    from magpie_jsrun import to_number as _tn
    if a and a[0] is not UNDEFINED and i.events is not None:
        i.events.cancel(int(await _tn(i, a[0])))
    return UNDEFINED


async def _window_open(t, a, i):
    from magpie_jsrun import to_string as _ts
    b = bindings_of(t)
    url = await _ts(i, a[0]) if a and a[0] is not UNDEFINED and a[0] is not NULL else "about:blank"
    b.open_request = resolve_url(b.base_url(), url)
    return NULL


async def _window_close(t, a, i):
    return UNDEFINED


async def _window_scroll(t, a, i):
    b = bindings_of(t)
    b.pending_scroll = ("top", 0)
    return UNDEFINED


async def _window_alert(t, a, i):
    from magpie_jsrun import to_string as _ts
    b = bindings_of(t)
    msg = await _ts(i, a[0]) if a else ""
    b.alerts.append(msg)
    if callable(i.options.on_alert):
        i.options.on_alert(msg)
    return UNDEFINED


async def _window_confirm(t, a, i):
    from magpie_jsrun import to_string as _ts
    b = bindings_of(t)
    b.alerts.append("[confirm] " + (await _ts(i, a[0]) if a else ""))
    return js_bool(b.confirm_default)


async def _window_prompt(t, a, i):
    from magpie_jsrun import to_string as _ts
    b = bindings_of(t)
    b.alerts.append("[prompt] " + (await _ts(i, a[0]) if a else ""))
    return JSString(b.prompt_default)


async def _window_add_listener(t, a, i):
    from magpie_jsrun import to_string as _ts
    kind = await _ts(i, a[0]) if a else ""
    fn = a[1] if len(a) > 1 else UNDEFINED
    if isinstance(fn, JSFunction):
        bindings_of(t).add_listener(id(t), kind, fn)
    return UNDEFINED


async def _window_remove_listener(t, a, i):
    from magpie_jsrun import to_string as _ts
    kind = await _ts(i, a[0]) if a else ""
    bindings_of(t).remove_listener(id(t), kind, a[1] if len(a) > 1 else UNDEFINED)
    return UNDEFINED


async def _window_dispatch(t, a, i):
    v = a[0] if a else UNDEFINED
    if not isinstance(v, JSObject) or not isinstance(v.get_own("__event__"), _Event):
        throw_dom("dispatchEvent needs an event")
    b = bindings_of(t)
    ok = await dispatch(b, i, t, v.get_own("__event__").kind, props=v.get_own("__event__").props)
    return js_bool(ok)


def make_named_map(bindings: Bindings, node: Node) -> JSObject:
    obj = JSObject(INTRINSICS["Object_prototype"])
    _tag_bindings(obj, bindings)
    obj.define_own("__attr_node__", _NodeRef(node), enumerable=False)
    _m(obj, "getNamedItem", _attr_item_get)
    _m(obj, "setNamedItem", _attr_item_set)
    _m(obj, "removeNamedItem", _attr_item_remove)
    _acc(obj, "length", lambda t, a, i: JSNumber(len(_attr_node(t).attrs)))
    obj.define_own("@@iterator", native("@@iterator", _attr_iter), enumerable=False)
    for k, name in enumerate(node.attrs):
        obj.define_own(str(k), make_attr(bindings, node, name), enumerable=False)
    return obj


def _attr_node(t) -> Node:
    ref = t.get_own("__attr_node__")
    if not isinstance(ref, _NodeRef):
        throw_dom("attributes on non-element")
    return ref.node


def make_attr(bindings: Bindings, node: Node, name: str) -> JSObject:
    obj = JSObject(INTRINSICS["Object_prototype"])
    obj.define_own("name", JSString(name), enumerable=False)
    obj.define_own("value", JSString(node.get_attribute(name)))
    return obj


async def _attr_item_get(t, a, i):
    from magpie_jsrun import to_string as _ts
    name = (await _ts(i, a[0])).lower() if a else ""
    node = _attr_node(t)
    if name not in node.attrs:
        return NULL
    return make_attr(bindings_of(t), node, name)


async def _attr_item_set(t, a, i):
    node = _attr_node(t)
    attr = a[0] if a else UNDEFINED
    if not isinstance(attr, JSObject):
        throw_dom("setNamedItem needs an Attr")
    name = attr.get("name")
    name = name.value if isinstance(name, JSString) else ""
    value = attr.get("value")
    value = value.value if isinstance(value, JSString) else ""
    node.set_attribute(name.lower(), value)
    bindings_of(t).bump()
    return attr


async def _attr_item_remove(t, a, i):
    from magpie_jsrun import to_string as _ts
    node = _attr_node(t)
    name = (await _ts(i, a[0])).lower() if a else ""
    if name not in node.attrs:
        throw_dom("no such attribute")
    old = make_attr(bindings_of(t), node, name)
    node.remove_attribute(name)
    bindings_of(t).bump()
    return old


def _attr_iter(t, a, i):
    from magpie_jslib import _make_iterator
    node = _attr_node(t)
    return _make_iterator(i, [make_attr(bindings_of(t), node, name) for name in node.attrs])


def make_dataset(bindings: Bindings, node: Node) -> JSObject:
    obj = JSObject(INTRINSICS["Object_prototype"])
    _tag_bindings(obj, bindings)
    obj.define_own("__data_node__", _NodeRef(node), enumerable=False)
    for attr, val in node.attrs.items():
        if attr.startswith("data-"):
            key = attr[5:].replace("-", "_")
            obj.define_own(key, JSString(val))
    return obj


def make_style(bindings: Bindings, node: Node) -> JSObject:
    from magpie_dom import parse_declarations
    obj = JSObject(INTRINSICS["Object_prototype"])
    _tag_bindings(obj, bindings)
    obj.define_own("__style_node__", _NodeRef(node), enumerable=False)
    for prop, val in parse_declarations(node.get_attribute("style")).items():
        obj.define_own(_css_camel(prop), JSString(val))
    _acc(obj, "cssText", lambda t, a, i: JSString(_style_node(t).get_attribute("style")),
         lambda t, a, i: _style_set_text(t, a, i))
    _m(obj, "getPropertyValue", _style_get)
    _m(obj, "setProperty", _style_set)
    _m(obj, "removeProperty", _style_remove)
    return obj


def _style_node(t) -> Node:
    ref = t.get_own("__style_node__")
    if not isinstance(ref, _NodeRef):
        throw_dom("style on non-element")
    return ref.node


def _css_camel(prop: str) -> str:
    bits = prop.split("-")
    return bits[0] + "".join(b.capitalize() for b in bits[1:])


def _css_kebab(name: str) -> str:
    out = []
    for ch in name:
        if ch.isupper():
            out.append("-" + ch.lower())
        else:
            out.append(ch)
    return "".join(out)


async def _style_set_text(t, a, i):
    from magpie_jsrun import to_string as _ts
    node = _style_node(t)
    node.set_attribute("style", await _ts(i, a[0]) if a else "")
    bindings_of(t).bump()
    return UNDEFINED


async def _style_get(t, a, i):
    from magpie_jsrun import to_string as _ts
    from magpie_dom import parse_declarations
    name = _css_kebab(await _ts(i, a[0])) if a else ""
    return JSString(parse_declarations(_style_node(t).get_attribute("style")).get(name, ""))


async def _style_set(t, a, i):
    from magpie_jsrun import to_string as _ts
    from magpie_dom import parse_declarations
    node = _style_node(t)
    name = _css_kebab(await _ts(i, a[0])) if a else ""
    value = await _ts(i, a[1]) if len(a) > 1 else ""
    decls = parse_declarations(node.get_attribute("style"))
    if value:
        decls[name] = value
    elif name in decls:
        del decls[name]
    node.set_attribute("style", "; ".join(f"{k}: {v}" for k, v in decls.items()))
    node.set_attribute("style", node.get_attribute("style"))
    bindings_of(t).bump()
    return UNDEFINED


async def _style_remove(t, a, i):
    from magpie_jsrun import to_string as _ts
    from magpie_dom import parse_declarations
    node = _style_node(t)
    name = _css_kebab(await _ts(i, a[0])) if a else ""
    decls = parse_declarations(node.get_attribute("style"))
    old = decls.pop(name, "")
    node.set_attribute("style", "; ".join(f"{k}: {v}" for k, v in decls.items()))
    bindings_of(t).bump()
    return JSString(old)
