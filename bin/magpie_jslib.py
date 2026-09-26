#!/usr/bin/env python3
"""magpie_jslib — JavaScript builtins, RegExp/Date, timers, and run helpers."""
from __future__ import annotations

import asyncio
import base64
import binascii
import datetime
import heapq
import json
import math
import random
import re
import struct
import time
import unicodedata
import urllib.parse
import uuid

from magpie_jsparse import parse_source
from magpie_jsrun import Interpreter, JSOptions, prop_key
from magpie_jsval import (
    BreakExc, ContinueExc, Environment, FALSE, INTRINSICS, JSArray, JSBigInt,
    JSBoolean, JSFunction, JSNull, JSNumber, JSObject, JSString, JSSymbol,
    JSUndefined, JSValue, JSPromise, NULL, ReturnExc, ThrowExc, TRUE,
    UNDEFINED, enum_keys, js_bool, make_error_value, number_to_string,
    prop_exists, same_value_zero, strict_equal, str_to_number, to_boolean,
    to_length_primitive, to_number_primitive, to_string_primitive,
)


def throw_type(msg: str):
    raise ThrowExc(make_error_value("TypeError", msg))


def throw_range(msg: str):
    raise ThrowExc(make_error_value("RangeError", msg))


def call_native_method(fn: JSFunction, this: JSValue, args: list):
    out = fn.handler(this, args, None)
    if asyncio.iscoroutine(out):
        raise ThrowExc(make_error_value("TypeError", "async value in sync conversion"))
    return out


def native(name: str, handler, *, length: int = 0) -> JSFunction:
    fn = JSFunction(kind="native", proto=INTRINSICS["Function_prototype"])
    fn.handler = handler
    fn.name = name
    fn.length = length
    fn.define_own("name", JSString(name), enumerable=False)
    fn.define_own("length", JSNumber(length), enumerable=False)
    return fn


def get_arg(args: list, i: int, default=None):
    av = args[i] if i < len(args) else UNDEFINED
    return default if av is UNDEFINED and default is not None else av


async def to_number_i(interp, v: JSValue) -> float:
    from magpie_jsrun import to_number
    return await to_number(interp, v)


async def to_string_i(interp, v: JSValue) -> str:
    from magpie_jsrun import to_string
    return await to_string(interp, v)


async def to_int32_i(interp, v: JSValue) -> int:
    from magpie_jsrun import to_int32
    return await to_int32(interp, v)


def js_array(interp, items: list) -> JSArray:
    arr = JSArray(INTRINSICS["Array_prototype"])
    for item in items:
        arr.set(str(arr.length()), item)
        arr.set_length(arr.length() + 1)
    return arr


def js_object(interp, pairs: dict) -> JSObject:
    obj = JSObject(INTRINSICS["Object_prototype"])
    for k, v in pairs.items():
        obj.define_own(k, v)
    return obj


# ── RegExp ───────────────────────────────────────────────────────────────

def translate_regex(pattern: str, flags: str) -> str:
    out: list[str] = []
    i, n = 0, len(pattern)
    in_class = False
    while i < n:
        c = pattern[i]
        if c == "\\" and i + 1 < n:
            nxt = pattern[i + 1]
            if nxt == "c" and i + 2 < n and pattern[i + 2].isalpha():
                out.append(chr(ord(pattern[i + 2].upper()) & 31))
                i += 3
                continue
            if nxt == "0" and (i + 2 >= n or not pattern[i + 2].isdigit()):
                out.append("\x00")
                i += 2
                continue
            if nxt.isdigit():
                # Octal/backreference: keep backrefs 1-9 as-is; translate octal.
                j = i + 1
                while j < n and j < i + 4 and pattern[j].isdigit():
                    j += 1
                digits = pattern[i + 1:j]
                if len(digits) == 1 and digits in "123456789":
                    out.append("\\" + digits)
                else:
                    try:
                        out.append(chr(int(digits, 8) % 256))
                    except ValueError:
                        out.append("\\" + digits)
                i = j
                continue
            out.append(c)
            out.append(nxt)
            i += 2
            continue
        if c == "[" and not in_class:
            if pattern[i:i + 2] == "[^]":
                out.append(r"[\s\S]")
                i += 3
                continue
            in_class = True
        elif c == "]":
            in_class = False
        out.append(c)
        i += 1
    return "".join(out)


def make_regexp(pattern: str, flags: str = "") -> JSObject:
    for ch in flags:
        if ch not in "dgimsuvy":
            raise ThrowExc(make_error_value("SyntaxError", f"bad regex flag {ch}"))
    if len(set(flags)) != len(flags):
        raise ThrowExc(make_error_value("SyntaxError", "duplicate regex flag"))
    py_flags = 0
    if "i" in flags:
        py_flags |= re.IGNORECASE
    if "m" in flags:
        py_flags |= re.MULTILINE
    if "s" in flags:
        py_flags |= re.DOTALL
    try:
        compiled = re.compile(translate_regex(pattern, flags), py_flags)
    except re.error as e:
        raise ThrowExc(make_error_value("SyntaxError", f"bad regex: {e}")) from e
    obj = JSObject(INTRINSICS["RegExp_prototype"])
    obj.define_own("__regexp__", JSString(pattern), enumerable=False)
    obj.define_own("__regexp_flags__", JSString(flags), enumerable=False)
    obj.define_own("__regexp_py__", _PyRegex(compiled), enumerable=False)
    obj.define_own("lastIndex", JSNumber(0), writable=True, enumerable=False)
    return obj


class _PyRegex:
    __slots__ = ("rx",)

    def __init__(self, rx) -> None:
        self.rx = rx


def regexp_state(obj: JSObject):
    raw = obj.get_own("__regexp_py__")
    flags = obj.get_own("__regexp_flags__")
    last = obj.get_own("lastIndex")
    if not isinstance(raw, _PyRegex) or not isinstance(flags, JSString) or not isinstance(last, JSNumber):
        throw_type("not a regexp")
    return raw.rx, flags.value, int(last.value)


def regexp_exec(obj: JSObject, text: str):
    rx, flags, last = regexp_state(obj)
    start = last if ("g" in flags or "y" in flags) else 0
    if start > len(text):
        if "g" in flags or "y" in flags:
            obj.define_own("lastIndex", JSNumber(0))
        return None
    m = rx.match(text, start) if "y" in flags else rx.search(text, start)
    if m is None:
        if "g" in flags or "y" in flags:
            obj.define_own("lastIndex", JSNumber(0))
        return None
    if "g" in flags or "y" in flags:
        obj.define_own("lastIndex", JSNumber(m.end()))
    arr = JSArray(INTRINSICS["Array_prototype"])
    for g in m.groups(default=None):
        arr.set(str(arr.length()), JSString(g) if g is not None else UNDEFINED)
        arr.set_length(arr.length() + 1)
    arr.set("0", JSString(m.group(0)))
    arr.define_own("index", JSNumber(m.start()))
    arr.define_own("input", JSString(text))
    groups = getattr(m, "groupdict", lambda: {})()
    if groups and any(v is not None for v in groups.values()):
        gobj = JSObject(INTRINSICS["Object_prototype"])
        for k, v in groups.items():
            gobj.define_own(k, JSString(v) if v is not None else UNDEFINED)
        arr.define_own("groups", gobj)
    else:
        arr.define_own("groups", UNDEFINED)
    return arr


# ── Dates ────────────────────────────────────────────────────────────────

def date_ms(obj: JSObject) -> float:
    raw = obj.get_own("__date__")
    if not isinstance(raw, JSNumber):
        throw_type("not a date")
    return raw.value


def parse_date_string(s: str) -> float:
    t = s.strip()
    if not t:
        return math.nan
    try:
        iso = t.replace("Z", "+00:00") if t.endswith(("Z", "z")) else t
        dt = datetime.datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.timestamp() * 1000.0
    except ValueError:
        pass
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%A, %d-%b-%y %H:%M:%S %Z", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            dt = datetime.datetime.strptime(t, fmt).replace(tzinfo=datetime.timezone.utc)
            return dt.timestamp() * 1000.0
        except ValueError:
            continue
    return math.nan


def date_parts(ms: float, *, utc: bool = False):
    if ms != ms:
        return None
    dt = datetime.datetime.fromtimestamp(ms / 1000.0, tz=datetime.timezone.utc)
    if not utc:
        dt = dt.astimezone()
    return dt


# ── install ──────────────────────────────────────────────────────────────

_FETCHER = None


def set_fetcher(fn) -> None:
    global _FETCHER
    _FETCHER = fn


class EventState:
    def __init__(self) -> None:
        import heapq as _h
        self.timers: list = []
        self.next_id = 1
        self.cancelled: set[int] = set()
        self._h = _h

    def add_timer(self, when: float, callback, *, args=(), repeat: float = 0.0) -> int:
        ident = self.next_id
        self.next_id += 1
        self._h.heappush(self.timers, (when, ident, callback, args, repeat))
        return ident

    def cancel(self, ident: int) -> None:
        self.cancelled.add(ident)


def install_builtins(g: JSObject) -> None:
    object_proto = JSObject(None)
    INTRINSICS["Object_prototype"] = object_proto
    func_proto = JSObject(object_proto)
    INTRINSICS["Function_prototype"] = func_proto

    def ctor(name: str, handler, *, length: int = 1, proto=None, parent_proto=None):
        fn = JSFunction(kind="native", proto=INTRINSICS["Function_prototype"])
        fn.handler = handler
        fn.name = name
        fn.length = length
        fn.define_own("name", JSString(name), enumerable=False)
        fn.define_own("length", JSNumber(length), enumerable=False)
        p = JSObject(parent_proto or object_proto)
        p.define_own("constructor", fn, enumerable=False)
        if name != "Object":
            p.define_own("@@toStringTag", JSString(name), enumerable=False)
        fn.define_own("prototype", p, enumerable=False)
        INTRINSICS[name] = fn
        INTRINSICS[name + "_prototype"] = p
        g.define_own(name, fn)
        return fn, p

    # Object.prototype basics (methods added after all prototypes exist).
    # Function.prototype
    Object, Object_p = ctor("Object", object_construct, length=1)
    Function, Function_p = ctor("Function", function_construct)
    Function_p.define_own("constructor", Function, enumerable=False)
    Array, Array_p = ctor("Array", array_construct)
    String, String_p = ctor("String", string_construct)
    Number, Number_p = ctor("Number", number_construct)
    Boolean, Boolean_p = ctor("Boolean", boolean_construct)
    BigIntF, BigInt_p = ctor("BigInt", bigint_construct)
    SymbolF, Symbol_p = ctor("Symbol", symbol_construct)
    ErrorF, Error_p = ctor("Error", error_construct)
    for sub in ("EvalError", "RangeError", "ReferenceError", "SyntaxError", "TypeError", "URIError"):
        fn, p = ctor(sub, error_construct)
        p.proto = Error_p
        INTRINSICS[sub + "_prototype"] = p
    AggError, AggError_p = ctor("AggregateError", aggregate_construct)
    AggError_p.proto = Error_p
    PromiseF, Promise_p = ctor("Promise", promise_construct)
    RegExpF, RegExp_p = ctor("RegExp", regexp_construct)
    DateF, Date_p = ctor("Date", date_construct)
    MapF, Map_p = ctor("Map", map_construct)
    SetF, Set_p = ctor("Set", set_construct)
    WeakMapF, WeakMap_p = ctor("WeakMap", weakmap_construct)
    WeakSetF, WeakSet_p = ctor("WeakSet", weakset_construct)
    ArrayBufferF, ArrayBuffer_p = ctor("ArrayBuffer", arraybuffer_construct)
    DataViewF, DataView_p = ctor("DataView", dataview_construct)
    TextEncoderF, TextEncoder_p = ctor("TextEncoder", textencoder_construct)
    TextDecoderF, TextDecoder_p = ctor("TextDecoder", textdecoder_construct)
    URLF, URL_p = ctor("URL", url_construct)
    URLSearchParamsF, URLSearchParams_p = ctor("URLSearchParams", urlsp_construct)
    HeadersF, Headers_p = ctor("Headers", headers_construct)
    BlobF, Blob_p = ctor("Blob", blob_construct)
    FormDataF, FormData_p = ctor("FormData", formdata_construct)
    AbortControllerF, AbortController_p = ctor("AbortController", abort_construct)
    XMLHttpRequestF, XMLHttpRequest_p = ctor("XMLHttpRequest", xhr_construct)

    for tname, size, kind in (
        ("Int8Array", 1, "int"), ("Uint8Array", 1, "uint"), ("Uint8ClampedArray", 1, "clamp"),
        ("Int16Array", 2, "int"), ("Uint16Array", 2, "uint"), ("Int32Array", 4, "int"),
        ("Uint32Array", 4, "uint"), ("Float32Array", 4, "float"), ("Float64Array", 8, "float"),
        ("BigInt64Array", 8, "bigint"), ("BigUint64Array", 8, "biguint"),
    ):
        fn, p = ctor(tname, lambda this, a, i, _t=tname, _s=size, _k=kind: typed_construct(_t, _s, _k, a, i))
        p.define_own("BYTES_PER_ELEMENT", JSNumber(size), enumerable=False)
        fn.define_own("BYTES_PER_ELEMENT", JSNumber(size), enumerable=False)
        INTRINSICS[tname] = fn

    # Well-known symbols
    SymbolF.define_own("iterator", JSSymbol("Symbol.iterator", key="@@iterator"), enumerable=False)
    SymbolF.define_own("asyncIterator", JSSymbol("Symbol.asyncIterator", key="@@asyncIterator"), enumerable=False)
    SymbolF.define_own("hasInstance", JSSymbol("Symbol.hasInstance", key="@@hasInstance"), enumerable=False)
    SymbolF.define_own("species", JSSymbol("Symbol.species", key="@@species"), enumerable=False)
    SymbolF.define_own("toStringTag", JSSymbol("Symbol.toStringTag", key="@@toStringTag"), enumerable=False)

    install_object(Object, Object_p)
    install_function(Function, Function_p)
    install_array(Array, Array_p)
    install_string(String, String_p)
    install_number(Number, Number_p)
    install_boolean(Boolean, Boolean_p)
    install_bigint(BigIntF, BigInt_p)
    install_symbol(SymbolF, Symbol_p)
    install_error(ErrorF, Error_p)
    install_promise(PromiseF, Promise_p)
    install_regexp(RegExpF, RegExp_p)
    install_date(DateF, Date_p)
    install_map(MapF, Map_p)
    install_set(SetF, Set_p)
    install_weak(WeakMapF, WeakMap_p, WeakSetF, WeakSet_p)
    install_buffer(ArrayBufferF, ArrayBuffer_p, DataViewF, DataView_p)
    install_typed_protos()
    install_text(TextEncoderF, TextEncoder_p, TextDecoderF, TextDecoder_p)
    install_url(URLF, URL_p, URLSearchParamsF, URLSearchParams_p)
    install_fetchables(HeadersF, Headers_p, BlobF, Blob_p, FormDataF, FormData_p, AbortControllerF, AbortController_p, XMLHttpRequestF, XMLHttpRequest_p)
    install_json_math(g)
    install_globals(g)


# ── constructors ─────────────────────────────────────────────────────────

def object_construct(this, args, interp):
    if args and isinstance(args[0], JSObject):
        return args[0]
    if args and (isinstance(args[0], (JSString, JSNumber, JSBoolean))):
        from magpie_jsrun import box_primitive
        return box_primitive(args[0])
    return JSObject(INTRINSICS["Object_prototype"])


async def function_construct(this, args, interp):
    from magpie_jsrun import to_string as _ts
    from magpie_jsparse import parse_source as _parse
    body = await _ts(interp, args[-1]) if args else ""
    params = ",".join(await _ts(interp, a) for a in args[:-1]) if len(args) > 1 else ""
    prog = _parse(f"function anonymous({params}){{{body}}}", name="<Function>")
    fn_node = prog[1][0]
    return interp.make_function("anonymous", fn_node[2], fn_node[3], interp.global_env(), False, False)


def array_construct(this, args, interp):
    arr = JSArray(INTRINSICS["Array_prototype"])
    if len(args) == 1 and isinstance(args[0], JSNumber):
        arr.set_length(max(0, int(args[0].value)))
        return arr
    for a in args:
        arr.set(str(arr.length()), a)
        arr.set_length(arr.length() + 1)
    return arr


async def string_construct(this, args, interp):
    from magpie_jsrun import to_string as _ts
    s = await _ts(interp, args[0]) if args else ""
    if isinstance(this, JSFunction):
        obj = JSObject(INTRINSICS["String_prototype"])
        obj.define_own("__boxed__", JSString(s), enumerable=False)
        return obj
    return JSString(s)


async def number_construct(this, args, interp):
    from magpie_jsrun import to_number as _tn
    v = await _tn(interp, args[0]) if args else 0.0
    if isinstance(this, JSFunction):
        obj = JSObject(INTRINSICS["Number_prototype"])
        obj.define_own("__boxed__", JSNumber(v), enumerable=False)
        return obj
    return JSNumber(v)


def boolean_construct(this, args, interp):
    v = js_bool(to_boolean(args[0]) if args else False)
    if isinstance(this, JSFunction):
        obj = JSObject(INTRINSICS["Boolean_prototype"])
        obj.define_own("__boxed__", v, enumerable=False)
        return obj
    return v


async def bigint_construct(this, args, interp):
    from magpie_jsrun import to_number as _tn, to_primitive as _tp, to_string as _ts
    if isinstance(this, JSFunction):
        throw_type("BigInt is not a constructor")
    if not args or args[0] is UNDEFINED:
        throw_type("BigInt needs a value")
    v = args[0]
    if isinstance(v, JSBigInt):
        return JSBigInt(v.value)
    if isinstance(v, JSBoolean):
        return JSBigInt(1 if v.value else 0)
    if isinstance(v, JSNumber):
        if v.value != v.value or v.value in (math.inf, -math.inf) or not v.value.is_integer():
            throw_type("cannot convert to BigInt")
        return JSBigInt(int(v.value))
    if isinstance(v, JSString):
        t = v.value.strip()
        try:
            if t[:2].lower() == "0x":
                return JSBigInt(int(t, 16))
            if t[:2].lower() == "0b":
                return JSBigInt(int(t, 2))
            if t[:2].lower() == "0o":
                return JSBigInt(int(t, 8))
            return JSBigInt(int(t, 10))
        except ValueError:
            throw_type("cannot convert to BigInt")
    prim = await _tp(interp, v)
    return await bigint_construct(UNDEFINED, [prim], interp)


async def symbol_construct(this, args, interp):
    if isinstance(this, JSFunction):
        throw_type("Symbol is not a constructor")
    from magpie_jsrun import to_string as _ts
    desc = await _ts(interp, args[0]) if args and args[0] is not UNDEFINED else ""
    return JSSymbol(desc)


async def error_construct(this, args, interp):
    from magpie_jsrun import to_string as _ts
    ename = "Error"
    if isinstance(this, JSFunction):
        named = this.get_own("__error_name__")
        if isinstance(named, JSString):
            ename = named.value
    msg = ""
    if args and args[0] is not UNDEFINED:
        msg = await _ts(interp, args[0])
    obj = JSObject(INTRINSICS.get(ename + "_prototype", INTRINSICS["Error_prototype"]))
    obj.define_own("name", JSString(ename), enumerable=False)
    obj.define_own("message", JSString(msg), enumerable=False)
    return obj


async def aggregate_construct(this, args, interp):
    from magpie_jsrun import to_string as _ts
    errs = args[0] if args else UNDEFINED
    msg = await _ts(interp, args[1]) if len(args) > 1 and args[1] is not UNDEFINED else ""
    obj = JSObject(INTRINSICS["AggregateError_prototype"])
    obj.define_own("name", JSString("AggregateError"), enumerable=False)
    obj.define_own("message", JSString(msg), enumerable=False)
    obj.define_own("errors", errs if isinstance(errs, JSObject) else js_array(interp, []))
    return obj


def promise_construct(this, args, interp):
    from magpie_jsval import JSPromise
    if not args or not isinstance(args[0], JSFunction):
        throw_type("Promise needs an executor")
    p = JSPromise(interp)
    resolve = native("resolve", lambda t, a, i: (p.resolve(a[0] if a else UNDEFINED), UNDEFINED)[1])
    reject = native("reject", lambda t, a, i: (p.reject(a[0] if a else make_error_value("Error", "rejected")), UNDEFINED)[1])

    async def run_exec() -> None:
        try:
            await interp.call_value(args[0], UNDEFINED, [resolve, reject])
        except ThrowExc as e:
            p.reject(e.value)

    asyncio.get_running_loop().create_task(run_exec())
    return p


async def regexp_construct(this, args, interp):
    from magpie_jsrun import to_string as _ts
    if args and isinstance(args[0], JSObject) and args[0].get_own("__regexp__") is not UNDEFINED:
        if len(args) < 2 or args[1] is UNDEFINED:
            src = args[0]
            return make_regexp(src.get_own("__regexp__").value, src.get_own("__regexp_flags__").value)
    pattern = await _ts(interp, args[0]) if args and args[0] is not UNDEFINED else "(?:)"
    flags = await _ts(interp, args[1]) if len(args) > 1 and args[1] is not UNDEFINED else ""
    return make_regexp(pattern, flags)


async def date_construct(this, args, interp):
    from magpie_jsrun import to_number as _tn, to_string as _ts
    obj = JSObject(INTRINSICS["Date_prototype"])
    if not args:
        obj.define_own("__date__", JSNumber(time.time() * 1000.0), enumerable=False)
    elif len(args) == 1:
        a = args[0]
        if isinstance(a, JSObject) and a.get_own("__date__") is not UNDEFINED:
            obj.define_own("__date__", JSNumber(a.get_own("__date__").value), enumerable=False)
        elif isinstance(a, JSString):
            obj.define_own("__date__", JSNumber(parse_date_string(a.value)), enumerable=False)
        else:
            obj.define_own("__date__", JSNumber(await _tn(interp, a)), enumerable=False)
    else:
        vals = [int(await _tn(interp, a)) for a in args]
        while len(vals) < 7:
            vals.append(1 if len(vals) == 2 else 0)
        try:
            dt = datetime.datetime(vals[0], vals[1] + 1, vals[2], vals[3], vals[4], vals[5], vals[6] * 1000)
            ms = dt.timestamp() * 1000.0
        except ValueError:
            ms = math.nan
        obj.define_own("__date__", JSNumber(ms), enumerable=False)
    return obj


class JSMap(JSObject):
    __slots__ = ("pairs",)

    def __init__(self, proto=None) -> None:
        super().__init__(proto)
        self.pairs: list = []


class JSSet(JSObject):
    __slots__ = ("items",)

    def __init__(self, proto=None) -> None:
        super().__init__(proto)
        self.items: list = []


async def map_construct(this, args, interp):
    m = JSMap(INTRINSICS["Map_prototype"])
    if args and args[0] is not UNDEFINED and args[0] is not NULL:
        for entry in await interp.to_iterable(args[0]):
            pair = await interp.to_iterable(entry)
            map_set(m, pair[0] if pair else UNDEFINED, pair[1] if len(pair) > 1 else UNDEFINED)
    return m


def map_set(m: JSMap, k, v) -> None:
    for i, (ek, _) in enumerate(m.pairs):
        if same_value_zero_simple(ek, k):
            m.pairs[i] = (k, v)
            return
    m.pairs.append((k, v))


def same_value_zero_simple(a, b) -> bool:
    return same_value_zero(a, b)


async def set_construct(this, args, interp):
    s = JSSet(INTRINSICS["Set_prototype"])
    if args and args[0] is not UNDEFINED and args[0] is not NULL:
        for item in await interp.to_iterable(args[0]):
            if not any(same_value_zero(x, item) for x in s.items):
                s.items.append(item)
    return s


def weakmap_construct(this, args, interp):
    m = JSMap(INTRINSICS["WeakMap_prototype"])
    return m


def weakset_construct(this, args, interp):
    return JSSet(INTRINSICS["WeakSet_prototype"])


async def arraybuffer_construct(this, args, interp):
    from magpie_jsrun import to_number as _tn
    n = int(await _tn(interp, args[0])) if args else 0
    if n < 0:
        throw_range("bad ArrayBuffer length")
    obj = JSObject(INTRINSICS["ArrayBuffer_prototype"])
    obj.define_own("__buffer__", _RawBytes(bytearray(n)), enumerable=False)
    return obj


class _RawBytes:
    __slots__ = ("data",)

    def __init__(self, data: bytearray) -> None:
        self.data = data


async def dataview_construct(this, args, interp):
    from magpie_jsrun import to_number as _tn
    if not args or not isinstance(args[0], JSObject) or not isinstance(args[0].get_own("__buffer__"), _RawBytes):
        throw_type("DataView needs an ArrayBuffer")
    buf = args[0].get_own("__buffer__").data
    off = int(await _tn(interp, args[1])) if len(args) > 1 else 0
    length = int(await _tn(interp, args[2])) if len(args) > 2 else len(buf) - off
    obj = JSObject(INTRINSICS["DataView_prototype"])
    obj.define_own("__view__", _View(buf, off, length), enumerable=False)
    return obj


class _View:
    __slots__ = ("buf", "off", "length")

    def __init__(self, buf: bytearray, off: int, length: int) -> None:
        self.buf = buf
        self.off = off
        self.length = length


async def typed_construct(tname: str, size: int, kind: str, args, interp):
    from magpie_jsrun import to_number as _tn, to_length as _tl
    length = 0
    buf = None
    off = 0
    if args and isinstance(args[0], JSObject) and isinstance(args[0].get_own("__buffer__"), _RawBytes):
        buf = args[0].get_own("__buffer__").data
        off = int(await _tn(interp, args[1])) if len(args) > 1 else 0
        if len(args) > 2 and args[2] is not UNDEFINED:
            length = int(await _tl(interp, args[2]))
        else:
            length = (len(buf) - off) // size
    elif args and isinstance(args[0], JSObject):
        items = await interp.to_iterable(args[0])
        length = len(items)
        buf = bytearray(length * size)
        for i, item in enumerate(items):
            write_typed(buf, i * size, size, kind, item)
    else:
        length = int(await _tl(interp, args[0])) if args and args[0] is not UNDEFINED else 0
        buf = bytearray(length * size)
    obj = JSObject(INTRINSICS[tname + "_prototype"])
    obj.define_own("__typed__", _Typed(buf, off, length, size, kind), enumerable=False)
    for i in range(length):
        obj.define_own(str(i), read_typed(buf, off + i * size, size, kind))
    obj.define_own("length", JSNumber(length), enumerable=False)
    return obj


class _Typed:
    __slots__ = ("buf", "off", "length", "size", "kind")

    def __init__(self, buf: bytearray, off: int, length: int, size: int, kind: str) -> None:
        self.buf = buf
        self.off = off
        self.length = length
        self.size = size
        self.kind = kind


def write_typed(buf: bytearray, at: int, size: int, kind: str, v) -> None:
    from magpie_jsval import to_number_primitive as _np
    try:
        n = _np(v)
    except ThrowExc:
        n = math.nan
    fmt = {"int": "bhiq"[size // 2] if size in (1, 2, 4, 8) else None}.get("int") if False else None
    order = "<"
    if kind in ("int", "uint", "clamp"):
        bits = size * 8
        if n != n:
            n = 0
        n = int(n)
        if kind == "clamp":
            n = max(0, min(255, round(n)))
        n &= (1 << bits) - 1
        buf[at:at + size] = n.to_bytes(size, "little")
    elif kind == "float":
        buf[at:at + size] = struct.pack("<f" if size == 4 else "<d", n)
    elif kind in ("bigint", "biguint"):
        big = v.value if isinstance(v, JSBigInt) else int(n)
        buf[at:at + size] = (big & ((1 << size * 8) - 1)).to_bytes(size, "little", signed=(kind == "bigint"))
    _ = (fmt, order)


def read_typed(buf: bytearray, at: int, size: int, kind: str):
    raw = bytes(buf[at:at + size])
    if len(raw) < size:
        raw = raw + b"\x00" * (size - len(raw))
    if kind == "int":
        return JSNumber(float(int.from_bytes(raw, "little", signed=True)))
    if kind == "uint":
        return JSNumber(float(int.from_bytes(raw, "little")))
    if kind == "clamp":
        return JSNumber(float(raw[0]))
    if kind == "float":
        return JSNumber(struct.unpack("<f" if size == 4 else "<d", raw)[0])
    if kind == "bigint":
        return JSBigInt(int.from_bytes(raw, "little", signed=True))
    return JSBigInt(int.from_bytes(raw, "little"))


def textencoder_construct(this, args, interp):
    return JSObject(INTRINSICS["TextEncoder_prototype"])


async def textdecoder_construct(this, args, interp):
    from magpie_jsrun import to_string as _ts
    label = (await _ts(interp, args[0])).lower() if args and args[0] is not UNDEFINED else "utf-8"
    obj = JSObject(INTRINSICS["TextDecoder_prototype"])
    obj.define_own("__label__", JSString(label), enumerable=False)
    fatal = False
    if len(args) > 1 and isinstance(args[1], JSObject):
        fatal = to_boolean(args[1].get("fatal"))
    obj.define_own("__fatal__", js_bool(fatal), enumerable=False)
    return obj


async def url_construct(this, args, interp):
    from magpie_jsrun import to_string as _ts
    if not args:
        throw_type("URL needs an input")
    href = await _ts(interp, args[0])
    base = await _ts(interp, args[1]) if len(args) > 1 and args[1] is not UNDEFINED else ""
    try:
        joined = urllib.parse.urljoin(base, href) if base else href
        parts = urllib.parse.urlparse(joined)
        if not parts.scheme:
            raise ValueError("bad url")
    except ValueError:
        raise ThrowExc(make_error_value("TypeError", f"bad URL {href}"))
    obj = JSObject(INTRINSICS["URL_prototype"])
    obj.define_own("__parts__", _Parts(parts), enumerable=False)
    return obj


class _Parts:
    __slots__ = ("parts",)

    def __init__(self, parts) -> None:
        self.parts = parts


async def urlsp_construct(this, args, interp):
    from magpie_jsrun import to_string as _ts
    obj = JSObject(INTRINSICS["URLSearchParams_prototype"])
    first = args[0] if args else UNDEFINED
    if isinstance(first, JSObject):
        pairs = []
        for k in enum_keys(first):
            vv = first.get(k, recv=first)
            vv = await _resolve_tuple(vv, interp) if isinstance(vv, tuple) else vv
            pairs.append((k, await _ts(interp, vv)))
    else:
        query = await _ts(interp, first) if args else ""
        query = query[1:] if query.startswith("?") else query
        pairs = [(k, v) for k, v in urllib.parse.parse_qsl(query, keep_blank_values=True)]
    obj.define_own("__pairs__", _Pairs(pairs), enumerable=False)
    return obj


class _Pairs:
    __slots__ = ("pairs",)

    def __init__(self, pairs: list) -> None:
        self.pairs = pairs


async def headers_construct(this, args, interp):
    from magpie_jsrun import to_string as _ts
    obj = JSObject(INTRINSICS["Headers_prototype"])
    pairs: list = []
    if args and isinstance(args[0], JSObject):
        if isinstance(args[0].get_own("__headers__"), _Headers):
            pairs = list(args[0].get_own("__headers__").pairs)
        else:
            for k in enum_keys(args[0]):
                v = args[0].get(k, recv=args[0])
                v = await _resolve_tuple(v, interp)
                pairs.append((k.lower(), await _ts(interp, v)))
    elif args and isinstance(args[0], JSArray):
        for entry in await interp.to_iterable(args[0]):
            pair = await interp.to_iterable(entry)
            pairs.append(( (await _ts(interp, pair[0])).lower(), await _ts(interp, pair[1])))
    obj.define_own("__headers__", _Headers(pairs), enumerable=False)
    return obj


async def _resolve_tuple(v, interp):
    from magpie_jsrun import resolve_call
    return await resolve_call(v, interp) if isinstance(v, tuple) else v


class _Headers:
    __slots__ = ("pairs",)

    def __init__(self, pairs: list) -> None:
        self.pairs = pairs


async def blob_construct(this, args, interp):
    from magpie_jsrun import to_string as _ts
    parts = b""
    if args and isinstance(args[0], JSObject):
        try:
            items = await interp.to_iterable(args[0])
        except ThrowExc:
            items = []
        buf = bytearray()
        for item in items:
            if isinstance(item, JSString):
                buf.extend(item.value.encode("utf-8"))
            elif isinstance(item, JSObject) and isinstance(item.get_own("__blob__"), bytes):
                buf.extend(item.get_own("__blob__"))
            elif isinstance(item, JSObject) and isinstance(item.get_own("__buffer__"), _RawBytes):
                buf.extend(item.get_own("__buffer__").data)
        parts = bytes(buf)
    ctype = ""
    if len(args) > 1 and isinstance(args[1], JSObject):
        t = args[1].get("type")
        ctype = t.value.lower() if isinstance(t, JSString) else ""
    obj = JSObject(INTRINSICS["Blob_prototype"])
    obj.define_own("__blob__", parts, enumerable=False)
    obj.define_own("__blob_type__", JSString(ctype), enumerable=False)
    return obj


def formdata_construct(this, args, interp):
    obj = JSObject(INTRINSICS["FormData_prototype"])
    obj.define_own("__form__", _Pairs([]), enumerable=False)
    return obj


def abort_construct(this, args, interp):
    obj = JSObject(INTRINSICS["AbortController_prototype"])
    signal = JSObject(INTRINSICS["Object_prototype"])
    signal.define_own("aborted", FALSE)
    signal.define_own("__listeners__", _Pairs([]), enumerable=False)
    obj.define_own("signal", signal)
    return obj


def xhr_construct(this, args, interp):
    obj = JSObject(INTRINSICS["XMLHttpRequest_prototype"])
    obj.define_own("__xhr__", _XHR(), enumerable=False)
    return obj


class _XHR:
    __slots__ = ("method", "url", "async_", "headers", "ready", "status", "body", "listeners", "props")

    def __init__(self) -> None:
        self.method = "GET"
        self.url = ""
        self.async_ = True
        self.headers: list = []
        self.ready = 0
        self.status = 0
        self.body = b""
        self.listeners: dict = {}
        self.props: dict = {}


def _m(obj, name: str, handler, *, length: int = 0) -> None:
    obj.define_own(name, native(name, handler, length=length), enumerable=False)


def _g(obj, name: str, handler) -> None:
    obj.define_accessor(name, native(f"get {name}", handler), None, enumerable=False)


# ── Object ───────────────────────────────────────────────────────────────

def install_object(Object, Object_p) -> None:
    _m(Object_p, "hasOwnProperty", _has_own)
    _m(Object_p, "isPrototypeOf", lambda t, a, i: js_bool(_is_proto(t, a[0] if a else UNDEFINED)))
    _m(Object_p, "propertyIsEnumerable", lambda t, a, i: js_bool(_is_enum(t, a[0] if a else UNDEFINED)))
    _m(Object_p, "toString", _obj_to_string)
    _m(Object_p, "toLocaleString", _obj_to_string)
    _m(Object_p, "valueOf", lambda t, a, i: t)
    for name, fn in (
        ("assign", _object_assign), ("keys", _object_keys), ("values", _object_values),
        ("entries", _object_entries), ("fromEntries", _object_from_entries),
        ("create", _object_create), ("defineProperty", _define_property),
        ("defineProperties", _define_properties), ("getOwnPropertyDescriptor", _get_own_desc),
        ("getOwnPropertyNames", _get_own_names), ("getOwnPropertySymbols", _get_own_syms),
        ("getPrototypeOf", _get_proto), ("setPrototypeOf", _set_proto),
        ("is", _object_is), ("freeze", _freeze_seal(True, True)), ("seal", _freeze_seal(True, False)),
        ("preventExtensions", _prevent_ext), ("isFrozen", _is_frozen_sealed(True)),
        ("isSealed", _is_frozen_sealed(False)), ("isExtensible", _is_extensible),
        ("hasOwn", _has_own_static),
    ):
        _m(Object, name, fn)


def prop_key_sync(v) -> str:
    if isinstance(v, JSSymbol):
        return v.key or f"\0sym:{id(v)}"
    return to_string_primitive(v)


async def _has_own(t, a, i):
    from magpie_jsrun import prop_key as _pk
    return js_bool(isinstance(t, JSObject) and _pk(a[0] if a else UNDEFINED, i) in t.props)


def _is_proto(t, v) -> bool:
    cur = v.proto if isinstance(v, JSObject) else None
    while isinstance(cur, JSObject):
        if cur is t:
            return True
        cur = cur.proto
    return False


def _is_enum(t, v) -> bool:
    from magpie_jsrun import prop_key as _pk
    if not isinstance(t, JSObject):
        return False
    d = t.props.get(_pk(v, None))
    return bool(d and d.get("enumerable", True))


def _obj_to_string(t, a, i):
    from magpie_jsrun import prop_key as _pk
    tag = "Object"
    if isinstance(t, JSObject):
        custom = t.get("@@toStringTag", recv=t)
        if isinstance(custom, JSString):
            tag = custom.value
        elif t.get_own("__date__") is not UNDEFINED:
            tag = "Date"
        elif isinstance(t, JSArray):
            tag = "Array"
        elif isinstance(t, JSFunction):
            return JSString("function () { [magpie code] }")
    return JSString(f"[object {tag}]")


async def _object_assign(t, a, i):
    from magpie_jsrun import prop_key as _pk, to_string as _ts, resolve_call as _rc
    if not a:
        throw_type("assign needs a target")
    target = a[0]
    if target is UNDEFINED or target is NULL:
        throw_type("cannot convert null to object")
    if not isinstance(target, JSObject):
        from magpie_jsrun import box_primitive
        target = box_primitive(target)
    for src in a[1:]:
        if src is UNDEFINED or src is NULL:
            continue
        if isinstance(src, JSObject):
            for k in src.own_keys():
                if src.props[k].get("enumerable", True):
                    v = src.get(k, recv=src)
                    target.define_own(k, await _rc(v, i) if isinstance(v, tuple) else v)
        elif isinstance(src, JSString):
            for j, ch in enumerate(src.value):
                target.define_own(str(j), JSString(ch))
    return target


def _object_keys(t, a, i):
    v = a[0] if a else UNDEFINED
    keys = [k for k in enum_keys(v) if not k.startswith("\0sym:")] if isinstance(v, JSObject) else []
    return js_array(i, [JSString(k) for k in keys])


def _object_values(t, a, i):
    v = a[0] if a else UNDEFINED
    out = []
    if isinstance(v, JSObject):
        for k in enum_keys(v):
            if k.startswith("\0sym:"):
                continue
            item = v.get(k, recv=v)
            out.append(item)
    return js_array(i, out)


def _object_entries(t, a, i):
    v = a[0] if a else UNDEFINED
    out = []
    if isinstance(v, JSObject):
        for k in enum_keys(v):
            if k.startswith("\0sym:"):
                continue
            out.append(js_array(i, [JSString(k), v.get(k, recv=v)]))
    return js_array(i, out)


async def _object_from_entries(t, a, i):
    from magpie_jsrun import prop_key as _pk
    obj = JSObject(INTRINSICS["Object_prototype"])
    if a and a[0] is not UNDEFINED and a[0] is not NULL:
        for entry in await i.to_iterable(a[0]):
            pair = await i.to_iterable(entry)
            if len(pair) < 2:
                throw_type("entry needs a value")
            obj.define_own(_pk(pair[0], i), pair[1])
    return obj


def _object_create(t, a, i):
    proto = a[0] if a else UNDEFINED
    if proto is not UNDEFINED and proto is not NULL and not isinstance(proto, JSObject):
        throw_type("proto needs an object")
    obj = JSObject(proto if isinstance(proto, JSObject) else None)
    if len(a) > 1 and isinstance(a[1], JSObject):
        _define_properties(None, [obj, a[1]], i)
    return obj


def _to_desc(v) -> dict | None:
    if not isinstance(v, JSObject):
        throw_type("descriptor needs an object")
    d: dict = {}
    for k in ("value", "writable", "enumerable", "configurable", "get", "set"):
        item = v.get(k, recv=v)
        if item is not UNDEFINED:
            d[k] = item
    return d


def _apply_desc(obj: JSObject, key: str, d: dict) -> bool:
    if "value" in d or "writable" in d:
        if "get" in d or "set" in d:
            throw_type("bad descriptor")
        old = obj.props.get(key, {})
        return obj.define_own(
            key, d.get("value", old.get("value", UNDEFINED)),
            writable=to_boolean(d["writable"]) if "writable" in d else old.get("writable", True),
            enumerable=to_boolean(d["enumerable"]) if "enumerable" in d else old.get("enumerable", True),
            configurable=to_boolean(d["configurable"]) if "configurable" in d else old.get("configurable", True),
        )
    getter = d.get("get", obj.props.get(key, {}).get("get"))
    setter = d.get("set", obj.props.get(key, {}).get("set"))
    old = obj.props.get(key, {})
    return obj.define_accessor(
        key, getter, setter,
        enumerable=to_boolean(d["enumerable"]) if "enumerable" in d else old.get("enumerable", True),
        configurable=to_boolean(d["configurable"]) if "configurable" in d else old.get("configurable", True),
    )


def _define_property(t, a, i):
    from magpie_jsrun import prop_key as _pk
    if len(a) < 3 or not isinstance(a[0], JSObject):
        throw_type("defineProperty needs an object")
    key = _pk(a[1], i)
    d = _to_desc(a[2])
    if d is None or not _apply_desc(a[0], key, d):
        throw_type(f"cannot redefine {key}")
    return a[0]


def _define_properties(t, a, i):
    if len(a) < 2 or not isinstance(a[0], JSObject) or not isinstance(a[1], JSObject):
        throw_type("defineProperties needs objects")
    for k in a[1].own_keys():
        d = _to_desc(a[1].get(k, recv=a[1]))
        if d is not None and not _apply_desc(a[0], k, d):
            throw_type(f"cannot redefine {k}")
    return a[0]


def _get_own_desc(t, a, i):
    from magpie_jsrun import prop_key as _pk
    if len(a) < 2 or not isinstance(a[0], JSObject):
        return UNDEFINED
    d = a[0].props.get(_pk(a[1], i))
    if d is None:
        return UNDEFINED
    out = JSObject(INTRINSICS["Object_prototype"])
    if d.get("get") is not None or d.get("set") is not None:
        out.define_own("get", d["get"] or UNDEFINED)
        out.define_own("set", d["set"] or UNDEFINED)
    else:
        out.define_own("value", d.get("value", UNDEFINED))
        out.define_own("writable", js_bool(d.get("writable", True)))
    out.define_own("enumerable", js_bool(d.get("enumerable", True)))
    out.define_own("configurable", js_bool(d.get("configurable", True)))
    return out


def _get_own_names(t, a, i):
    v = a[0] if a else UNDEFINED
    keys = [k for k in v.own_keys() if not k.startswith("\0sym:")] if isinstance(v, JSObject) else []
    return js_array(i, [JSString(k) for k in keys])


def _get_own_syms(t, a, i):
    return js_array(i, [])


def _get_proto(t, a, i):
    v = a[0] if a else UNDEFINED
    if isinstance(v, JSObject):
        return v.proto if v.proto is not None else NULL
    return UNDEFINED


def _set_proto(t, a, i):
    if len(a) < 2 or not isinstance(a[0], JSObject):
        throw_type("setPrototypeOf needs an object")
    proto = a[1]
    if proto is not UNDEFINED and proto is not NULL and not isinstance(proto, JSObject):
        return a[0]
    a[0].proto = proto if isinstance(proto, JSObject) else None
    return a[0]


def _object_is(t, a, i):
    x = a[0] if a else UNDEFINED
    y = a[1] if len(a) > 1 else UNDEFINED
    if isinstance(x, JSNumber) and isinstance(y, JSNumber):
        if x.value != x.value and y.value != y.value:
            return TRUE
        if x.value == 0 and y.value == 0:
            return js_bool(math.copysign(1, x.value) == math.copysign(1, y.value))
    return js_bool(strict_equal(x, y))


def _freeze_seal(lock_props: bool, lock_ext: bool):
    def handler(t, a, i):
        v = a[0] if a else UNDEFINED
        if isinstance(v, JSObject):
            if lock_ext:
                v.extensible = False
            if lock_props:
                for k, d in v.props.items():
                    d["configurable"] = False
                    if d.get("get") is None and d.get("set") is None:
                        d["writable"] = False
        return v
    return handler


def _prevent_ext(t, a, i):
    v = a[0] if a else UNDEFINED
    if isinstance(v, JSObject):
        v.extensible = False
    return v


def _is_frozen_sealed(check_writable: bool):
    def handler(t, a, i):
        v = a[0] if a else UNDEFINED
        if not isinstance(v, JSObject):
            return TRUE
        if v.extensible:
            return FALSE
        for d in v.props.values():
            if d.get("configurable", True):
                return FALSE
            if check_writable and d.get("get") is None and d.get("writable", True):
                return FALSE
        return TRUE
    return handler


def _is_extensible(t, a, i):
    v = a[0] if a else UNDEFINED
    return js_bool(not isinstance(v, JSObject) or v.extensible)


async def _has_own_static(t, a, i):
    from magpie_jsrun import prop_key as _pk
    if len(a) < 2 or not isinstance(a[0], JSObject):
        throw_type("hasOwn needs an object")
    return js_bool(_pk(a[1], i) in a[0].props)


# ── Function ─────────────────────────────────────────────────────────────

def install_function(Function, Function_p) -> None:
    _m(Function_p, "call", _fn_call)
    _m(Function_p, "apply", _fn_apply)
    _m(Function_p, "bind", _fn_bind)
    _m(Function_p, "toString", lambda t, a, i: JSString("function () { [magpie code] }"))


async def _fn_call(t, a, i):
    this = a[0] if a else UNDEFINED
    return await i.call_value(t, this, list(a[1:]))


async def _fn_apply(t, a, i):
    this = a[0] if a else UNDEFINED
    argv = await i.to_iterable(a[1]) if len(a) > 1 and a[1] is not UNDEFINED and a[1] is not NULL else []
    return await i.call_value(t, this, argv)


def _fn_bind(t, a, i):
    if not isinstance(t, JSFunction):
        throw_type("bind needs a function")
    bound = JSFunction(kind="bound", proto=INTRINSICS["Function_prototype"])
    bound.handler = t
    bound.bound_this = a[0] if a else UNDEFINED
    bound.bound_args = list(a[1:])
    bound.name = "bound " + t.name
    bound.length = max(0, t.length - len(bound.bound_args))
    bound.interp = i
    bound.define_own("name", JSString(bound.name), enumerable=False)
    bound.define_own("length", JSNumber(bound.length), enumerable=False)
    return bound


# ── Array ────────────────────────────────────────────────────────────────

def install_array(Array, Array_p) -> None:
    Array.define_own("isArray", native("isArray", lambda t, a, i: js_bool(isinstance(a[0] if a else UNDEFINED, JSArray))), enumerable=False)
    Array.define_own("from", native("from", _array_from), enumerable=False)
    Array.define_own("of", native("of", lambda t, a, i: js_array(i, list(a))), enumerable=False)
    for name, fn in (
        ("at", _arr_at), ("concat", _arr_concat), ("copyWithin", _arr_copy_within),
        ("entries", _arr_entries), ("every", _arr_every), ("fill", _arr_fill),
        ("filter", _arr_filter), ("find", _arr_find), ("findIndex", _arr_find_index),
        ("findLast", _arr_find_last), ("findLastIndex", _arr_find_last_index),
        ("flat", _arr_flat), ("flatMap", _arr_flat_map), ("forEach", _arr_for_each),
        ("includes", _arr_includes), ("indexOf", _arr_index_of), ("join", _arr_join),
        ("keys", _arr_keys), ("lastIndexOf", _arr_last_index_of), ("map", _arr_map),
        ("pop", _arr_pop), ("push", _arr_push), ("reduce", _arr_reduce),
        ("reduceRight", _arr_reduce_right), ("reverse", _arr_reverse),
        ("shift", _arr_shift), ("slice", _arr_slice), ("some", _arr_some),
        ("sort", _arr_sort), ("splice", _arr_splice), ("toString", _arr_join),
        ("unshift", _arr_unshift), ("values", _arr_values), ("with", _arr_with),
        ("toReversed", _arr_to_reversed), ("toSorted", _arr_to_sorted),
        ("toSpliced", _arr_to_spliced),
    ):
        _m(Array_p, name, fn)
    Array_p.define_own("@@iterator", Array_p.get("values"), enumerable=False)


async def _array_from(t, a, i):
    from magpie_jsrun import to_length as _tl, to_string as _ts
    src = a[0] if a else UNDEFINED
    mapfn = a[1] if len(a) > 1 else UNDEFINED
    items = await i.to_iterable(src) if not isinstance(src, JSString) or hasattr(src, "__iter__") else [JSString(c) for c in src.value]
    if isinstance(src, JSArray) and mapfn is UNDEFINED:
        out = JSArray(INTRINSICS["Array_prototype"])
        for k in range(src.length()):
            out.set(str(out.length()), src.get(str(k)))
            out.set_length(out.length() + 1)
        return out
    out = []
    for idx, item in enumerate(items):
        out.append(await i.call_value(mapfn, UNDEFINED, [item, JSNumber(idx)]) if isinstance(mapfn, JSFunction) else item)
    return js_array(i, out)


def _arr_self(t):
    if not isinstance(t, JSArray):
        # Strings/arrays-like: operate generically over length.
        return t
    return t


async def _arr_len(i, t) -> int:
    from magpie_jsrun import to_length as _tl
    if isinstance(t, JSArray):
        return t.length()
    return await _tl(i, t.get("length") if isinstance(t, JSObject) else UNDEFINED)


async def _arr_get(i, t, k: int):
    if isinstance(t, JSArray):
        return t.get(str(k))
    v = t.get(str(k)) if isinstance(t, JSObject) else UNDEFINED
    from magpie_jsrun import resolve_call as _rc
    return await _rc(v, i) if isinstance(v, tuple) else v


def _arr_at(t, a, i):
    return _arr_at_impl(t, a, i)


async def _arr_at_impl(t, a, i):
    from magpie_jsrun import to_number as _tn
    n = await _arr_len(i, t)
    idx = int(await _tn(i, a[0])) if a else 0
    if idx < 0:
        idx += n
    if idx < 0 or idx >= n:
        return UNDEFINED
    return await _arr_get(i, t, idx)


async def _arr_concat(t, a, i):
    out = []
    for src in [t, *a]:
        if isinstance(src, JSArray):
            for k in range(src.length()):
                out.append(src.get(str(k)))
        else:
            out.append(src)
    return js_array(i, out)


async def _arr_copy_within(t, a, i):
    from magpie_jsrun import to_number as _tn
    arr = _require_array(t)
    n = arr.length()
    target = int(await _tn(i, a[0])) if a else 0
    start = int(await _tn(i, a[1])) if len(a) > 1 else 0
    end = int(await _tn(i, a[2])) if len(a) > 2 and a[2] is not UNDEFINED else n
    target = max(0, target + n if target < 0 else target)
    start = max(0, start + n if start < 0 else start)
    end = min(n, max(0, end + n if end < 0 else end))
    buf = [arr.get(str(k)) for k in range(start, end)]
    for j, v in enumerate(buf):
        if target + j < n:
            arr.set(str(target + j), v)
    return arr


def _require_array(t):
    if not isinstance(t, JSArray):
        throw_type("array method on non-array")
    return t


def _make_iterator(i, items: list):
    obj = JSObject(INTRINSICS["Object_prototype"])
    state = {"items": items, "pos": 0}

    async def nxt(t, a, interp):
        if state["pos"] >= len(state["items"]):
            return js_object(interp, {"value": UNDEFINED, "done": TRUE})
        v = state["items"][state["pos"]]
        state["pos"] += 1
        return js_object(interp, {"value": v, "done": FALSE})

    obj.define_own("next", native("next", nxt))
    obj.define_own("@@iterator", native("@@iterator", lambda t, a, interp: obj), enumerable=False)
    return obj


def _arr_entries(t, a, i):
    arr = _require_array(t)
    return _make_iterator(i, [js_array(i, [JSNumber(k), arr.get(str(k))]) for k in range(arr.length())])


def _arr_keys(t, a, i):
    arr = _require_array(t)
    return _make_iterator(i, [JSNumber(k) for k in range(arr.length())])


def _arr_values(t, a, i):
    arr = _require_array(t)
    return _make_iterator(i, [arr.get(str(k)) for k in range(arr.length())])


async def _arr_every(t, a, i):
    arr = _require_array(t)
    fn = a[0] if a else UNDEFINED
    if not isinstance(fn, JSFunction):
        throw_type("callback needs a function")
    for k in range(arr.length()):
        if not to_boolean(await i.call_value(fn, a[1] if len(a) > 1 else UNDEFINED, [arr.get(str(k)), JSNumber(k), arr])):
            return FALSE
    return TRUE


async def _arr_some(t, a, i):
    arr = _require_array(t)
    fn = a[0] if a else UNDEFINED
    if not isinstance(fn, JSFunction):
        throw_type("callback needs a function")
    for k in range(arr.length()):
        if to_boolean(await i.call_value(fn, a[1] if len(a) > 1 else UNDEFINED, [arr.get(str(k)), JSNumber(k), arr])):
            return TRUE
    return FALSE


async def _arr_for_each(t, a, i):
    arr = _require_array(t)
    fn = a[0] if a else UNDEFINED
    if not isinstance(fn, JSFunction):
        throw_type("callback needs a function")
    for k in range(arr.length()):
        await i.call_value(fn, a[1] if len(a) > 1 else UNDEFINED, [arr.get(str(k)), JSNumber(k), arr])
    return UNDEFINED


async def _arr_map(t, a, i):
    arr = _require_array(t)
    fn = a[0] if a else UNDEFINED
    if not isinstance(fn, JSFunction):
        throw_type("callback needs a function")
    out = []
    for k in range(arr.length()):
        out.append(await i.call_value(fn, a[1] if len(a) > 1 else UNDEFINED, [arr.get(str(k)), JSNumber(k), arr]))
    return js_array(i, out)


async def _arr_filter(t, a, i):
    arr = _require_array(t)
    fn = a[0] if a else UNDEFINED
    if not isinstance(fn, JSFunction):
        throw_type("callback needs a function")
    out = []
    for k in range(arr.length()):
        v = arr.get(str(k))
        if to_boolean(await i.call_value(fn, a[1] if len(a) > 1 else UNDEFINED, [v, JSNumber(k), arr])):
            out.append(v)
    return js_array(i, out)


async def _arr_find(t, a, i):
    arr = _require_array(t)
    fn = a[0] if a else UNDEFINED
    if not isinstance(fn, JSFunction):
        throw_type("callback needs a function")
    for k in range(arr.length()):
        v = arr.get(str(k))
        if to_boolean(await i.call_value(fn, a[1] if len(a) > 1 else UNDEFINED, [v, JSNumber(k), arr])):
            return v
    return UNDEFINED


async def _arr_find_index(t, a, i):
    arr = _require_array(t)
    fn = a[0] if a else UNDEFINED
    if not isinstance(fn, JSFunction):
        throw_type("callback needs a function")
    for k in range(arr.length()):
        if to_boolean(await i.call_value(fn, a[1] if len(a) > 1 else UNDEFINED, [arr.get(str(k)), JSNumber(k), arr])):
            return JSNumber(k)
    return JSNumber(-1)


async def _arr_find_last(t, a, i):
    arr = _require_array(t)
    fn = a[0] if a else UNDEFINED
    if not isinstance(fn, JSFunction):
        throw_type("callback needs a function")
    for k in range(arr.length() - 1, -1, -1):
        v = arr.get(str(k))
        if to_boolean(await i.call_value(fn, a[1] if len(a) > 1 else UNDEFINED, [v, JSNumber(k), arr])):
            return v
    return UNDEFINED


async def _arr_find_last_index(t, a, i):
    arr = _require_array(t)
    fn = a[0] if a else UNDEFINED
    if not isinstance(fn, JSFunction):
        throw_type("callback needs a function")
    for k in range(arr.length() - 1, -1, -1):
        if to_boolean(await i.call_value(fn, a[1] if len(a) > 1 else UNDEFINED, [arr.get(str(k)), JSNumber(k), arr])):
            return JSNumber(k)
    return JSNumber(-1)


async def _arr_flat(t, a, i):
    from magpie_jsrun import to_number as _tn
    depth = int(await _tn(i, a[0])) if a and a[0] is not UNDEFINED else 1
    return js_array(i, _flatten(_require_array(t), depth))


def _flatten(arr: JSArray, depth: int) -> list:
    out = []
    for k in range(arr.length()):
        v = arr.get(str(k))
        if isinstance(v, JSArray) and depth > 0:
            out.extend(_flatten(v, depth - 1))
        else:
            out.append(v)
    return out


async def _arr_flat_map(t, a, i):
    arr = _require_array(t)
    fn = a[0] if a else UNDEFINED
    if not isinstance(fn, JSFunction):
        throw_type("callback needs a function")
    out = []
    for k in range(arr.length()):
        v = await i.call_value(fn, a[1] if len(a) > 1 else UNDEFINED, [arr.get(str(k)), JSNumber(k), arr])
        if isinstance(v, JSArray):
            out.extend(v.get(str(j)) for j in range(v.length()))
        else:
            out.append(v)
    return js_array(i, out)


async def _arr_reduce(t, a, i):
    arr = _require_array(t)
    fn = a[0] if a else UNDEFINED
    if not isinstance(fn, JSFunction):
        throw_type("callback needs a function")
    n = arr.length()
    if n == 0 and (len(a) < 2 or a[1] is UNDEFINED):
        throw_type("reduce of empty array")
    k = 0
    acc = a[1] if len(a) > 1 and a[1] is not UNDEFINED else arr.get("0")
    if len(a) < 2 or a[1] is UNDEFINED:
        k = 1
    while k < n:
        acc = await i.call_value(fn, UNDEFINED, [acc, arr.get(str(k)), JSNumber(k), arr])
        k += 1
    return acc


async def _arr_reduce_right(t, a, i):
    arr = _require_array(t)
    fn = a[0] if a else UNDEFINED
    if not isinstance(fn, JSFunction):
        throw_type("callback needs a function")
    n = arr.length()
    if n == 0 and (len(a) < 2 or a[1] is UNDEFINED):
        throw_type("reduce of empty array")
    k = n - 1
    acc = a[1] if len(a) > 1 and a[1] is not UNDEFINED else arr.get(str(k))
    if len(a) < 2 or a[1] is UNDEFINED:
        k -= 1
    while k >= 0:
        acc = await i.call_value(fn, UNDEFINED, [acc, arr.get(str(k)), JSNumber(k), arr])
        k -= 1
    return acc


async def _arr_fill(t, a, i):
    from magpie_jsrun import to_number as _tn
    arr = _require_array(t)
    v = a[0] if a else UNDEFINED
    n = arr.length()
    start = int(await _tn(i, a[1])) if len(a) > 1 and a[1] is not UNDEFINED else 0
    end = int(await _tn(i, a[2])) if len(a) > 2 and a[2] is not UNDEFINED else n
    start = max(0, start + n if start < 0 else start)
    end = min(n, max(0, end + n if end < 0 else end))
    for k in range(start, end):
        arr.set(str(k), v)
    return arr


async def _arr_includes(t, a, i):
    from magpie_jsrun import to_number as _tn
    arr = _require_array(t)
    search = a[0] if a else UNDEFINED
    start = int(await _tn(i, a[1])) if len(a) > 1 and a[1] is not UNDEFINED else 0
    start = max(0, start + arr.length() if start < 0 else start)
    for k in range(start, arr.length()):
        if same_value_zero(arr.get(str(k)), search):
            return TRUE
    return FALSE


async def _arr_index_of(t, a, i):
    from magpie_jsrun import to_number as _tn
    arr = _require_array(t)
    search = a[0] if a else UNDEFINED
    start = int(await _tn(i, a[1])) if len(a) > 1 and a[1] is not UNDEFINED else 0
    start = max(0, start + arr.length() if start < 0 else start)
    for k in range(start, arr.length()):
        if strict_equal(arr.get(str(k)), search):
            return JSNumber(k)
    return JSNumber(-1)


async def _arr_last_index_of(t, a, i):
    from magpie_jsrun import to_number as _tn
    arr = _require_array(t)
    search = a[0] if a else UNDEFINED
    start = int(await _tn(i, a[1])) if len(a) > 1 and a[1] is not UNDEFINED else arr.length() - 1
    start = min(arr.length() - 1, start + arr.length() if start < 0 else start)
    for k in range(start, -1, -1):
        if strict_equal(arr.get(str(k)), search):
            return JSNumber(k)
    return JSNumber(-1)


async def _arr_join(t, a, i):
    from magpie_jsrun import to_string as _ts
    sep = await _ts(i, a[0]) if a and a[0] is not UNDEFINED else ","
    if isinstance(t, JSArray):
        parts = []
        for k in range(t.length()):
            v = t.get(str(k))
            parts.append("" if v is UNDEFINED or v is NULL else await _ts(i, v))
        return JSString(sep.join(parts))
    return JSString(sep.join([]))


async def _arr_push(t, a, i):
    arr = _require_array(t)
    for v in a:
        arr.set(str(arr.length()), v)
        arr.set_length(arr.length() + 1)
    return JSNumber(arr.length())


async def _arr_pop(t, a, i):
    arr = _require_array(t)
    n = arr.length()
    if n == 0:
        return UNDEFINED
    v = arr.get(str(n - 1))
    arr.set_length(n - 1)
    return v


async def _arr_shift(t, a, i):
    arr = _require_array(t)
    n = arr.length()
    if n == 0:
        return UNDEFINED
    first = arr.get("0")
    for k in range(1, n):
        arr.set(str(k - 1), arr.get(str(k)))
    arr.set_length(n - 1)
    return first


async def _arr_unshift(t, a, i):
    arr = _require_array(t)
    items = list(a)
    for k in range(arr.length() - 1, -1, -1):
        arr.set(str(k + len(items)), arr.get(str(k)))
    for j, v in enumerate(items):
        arr.set(str(j), v)
    arr.set_length(arr.length() + len(items))
    return JSNumber(arr.length())


async def _arr_slice(t, a, i):
    from magpie_jsrun import to_number as _tn
    arr = _require_array(t)
    n = arr.length()
    start = int(await _tn(i, a[0])) if a and a[0] is not UNDEFINED else 0
    end = int(await _tn(i, a[1])) if len(a) > 1 and a[1] is not UNDEFINED else n
    start = max(0, start + n if start < 0 else start)
    end = min(n, max(0, end + n if end < 0 else end))
    return js_array(i, [arr.get(str(k)) for k in range(start, end)])


async def _arr_splice(t, a, i):
    from magpie_jsrun import to_number as _tn
    arr = _require_array(t)
    n = arr.length()
    start = int(await _tn(i, a[0])) if a and a[0] is not UNDEFINED else 0
    start = max(0, start + n if start < 0 else start)
    start = min(n, start)
    delete = int(await _tn(i, a[1])) if len(a) > 1 and a[1] is not UNDEFINED else n - start
    delete = max(0, min(delete, n - start))
    removed = [arr.get(str(start + k)) for k in range(delete)]
    items = list(a[2:])
    tail = [arr.get(str(k)) for k in range(start + delete, n)]
    for j, v in enumerate(items):
        arr.set(str(start + j), v)
    for j, v in enumerate(tail):
        arr.set(str(start + len(items) + j), v)
    arr.set_length(start + len(items) + len(tail))
    return js_array(i, removed)


async def _arr_reverse(t, a, i):
    arr = _require_array(t)
    n = arr.length()
    for k in range(n // 2):
        x, y = arr.get(str(k)), arr.get(str(n - 1 - k))
        arr.set(str(k), y)
        arr.set(str(n - 1 - k), x)
    return arr


async def _arr_sort(t, a, i):
    from magpie_jsrun import to_string as _ts
    arr = _require_array(t)
    items = [arr.get(str(k)) for k in range(arr.length())]
    fn = a[0] if a and isinstance(a[0], JSFunction) else None
    if fn is None:
        keys = [(await _ts(i, v), j, v) for j, v in enumerate(items)]
        keys.sort(key=lambda r: (r[0], r[1]))
        items = [v for _, _, v in keys]
    else:
        # Insertion sort keeps comparator calls sequential and stable.
        for j in range(1, len(items)):
            key = items[j]
            k = j - 1
            while k >= 0:
                cmp = await to_number_i(i, await i.call_value(fn, UNDEFINED, [key, items[k]]))
                if cmp != cmp:
                    break
                if cmp < 0:
                    items[k + 1] = items[k]
                    k -= 1
                else:
                    break
            items[k + 1] = key
    for k, v in enumerate(items):
        arr.set(str(k), v)
    return arr


async def _arr_with(t, a, i):
    from magpie_jsrun import to_number as _tn
    arr = _require_array(t)
    idx = int(await _tn(i, a[0])) if a else 0
    if idx < 0:
        idx += arr.length()
    if idx < 0 or idx >= arr.length():
        throw_range("bad index")
    out = js_array(i, [arr.get(str(k)) for k in range(arr.length())])
    out.set(str(idx), a[1] if len(a) > 1 else UNDEFINED)
    return out


async def _arr_to_reversed(t, a, i):
    arr = _require_array(t)
    return js_array(i, [arr.get(str(k)) for k in range(arr.length() - 1, -1, -1)])


async def _arr_to_sorted(t, a, i):
    arr = _require_array(t)
    out = js_array(i, [arr.get(str(k)) for k in range(arr.length())])
    return await _arr_sort(out, a, i)


async def _arr_to_spliced(t, a, i):
    arr = _require_array(t)
    out = js_array(i, [arr.get(str(k)) for k in range(arr.length())])
    await _arr_splice(out, a, i)
    return out


# ── String ───────────────────────────────────────────────────────────────

def install_string(String, String_p) -> None:
    String.define_own("fromCharCode", native("fromCharCode", _str_from_char_code), enumerable=False)
    String.define_own("fromCodePoint", native("fromCodePoint", _str_from_code_point), enumerable=False)
    String.define_own("raw", native("raw", _str_raw), enumerable=False)
    for name, fn in (
        ("at", _s_at), ("charAt", _s_char_at), ("charCodeAt", _s_char_code_at),
        ("codePointAt", _s_code_point_at), ("concat", _s_concat), ("endsWith", _s_ends_with),
        ("includes", _s_includes), ("indexOf", _s_index_of), ("lastIndexOf", _s_last_index_of),
        ("localeCompare", _s_locale_compare), ("match", _s_match), ("matchAll", _s_match_all),
        ("normalize", _s_normalize), ("padEnd", _s_pad_end), ("padStart", _s_pad_start),
        ("repeat", _s_repeat), ("replace", _s_replace), ("replaceAll", _s_replace_all),
        ("search", _s_search), ("slice", _s_slice), ("split", _s_split),
        ("startsWith", _s_starts_with), ("substr", _s_substr), ("substring", _s_substring),
        ("toLowerCase", _s_lower), ("toUpperCase", _s_upper), ("toLocaleLowerCase", _s_lower),
        ("toLocaleUpperCase", _s_upper), ("toString", _s_this_string), ("valueOf", _s_this_string),
        ("trim", _s_trim), ("trimStart", _s_trim_start), ("trimEnd", _s_trim_end),
        ("isWellFormed", _s_well_formed), ("toWellFormed", _s_to_well_formed),
    ):
        _m(String_p, name, fn)
    String_p.define_own("@@iterator", native("@@iterator", _s_iterator), enumerable=False)


def _str_this(t, i):
    if isinstance(t, JSString):
        return t.value
    if isinstance(t, JSObject):
        boxed = t.get_own("__boxed__")
        if isinstance(boxed, JSString):
            return boxed.value
    throw_type("string method on non-string")


async def _str_from_char_code(t, a, i):
    from magpie_jsrun import to_number as _tn
    return JSString("".join(chr(int(await _tn(i, v)) % 0x10000) for v in a))


async def _str_from_code_point(t, a, i):
    from magpie_jsrun import to_number as _tn
    out = []
    for v in a:
        cp = int(await _tn(i, v))
        if cp < 0 or cp > 0x10FFFF:
            throw_range("bad code point")
        out.append(chr(cp))
    return JSString("".join(out))


async def _str_raw(t, a, i):
    from magpie_jsrun import to_string as _ts
    if not a or not isinstance(a[0], JSObject):
        throw_type("raw needs a template")
    raw = a[0].get("raw")
    raw = await _resolve_tuple(raw, i) if isinstance(raw, tuple) else raw
    n = raw.length() if isinstance(raw, JSArray) else 0
    out = []
    for k in range(n):
        out.append(await _ts(i, raw.get(str(k))))
        if k + 1 < len(a):
            out.append(await _ts(i, a[k + 1]))
    return JSString("".join(out))


async def _s_at(t, a, i):
    from magpie_jsrun import to_number as _tn
    s = _str_this(t, i)
    idx = int(await _tn(i, a[0])) if a else 0
    if idx < 0:
        idx += len(s)
    if idx < 0 or idx >= len(s):
        return UNDEFINED
    return JSString(s[idx])


async def _s_char_at(t, a, i):
    from magpie_jsrun import to_number as _tn
    s = _str_this(t, i)
    idx = int(await _tn(i, a[0])) if a else 0
    if idx < 0 or idx >= len(s):
        return JSString("")
    return JSString(s[idx])


async def _s_char_code_at(t, a, i):
    from magpie_jsrun import to_number as _tn
    s = _str_this(t, i)
    idx = int(await _tn(i, a[0])) if a else 0
    if idx < 0 or idx >= len(s):
        return JSNumber(math.nan)
    return JSNumber(ord(s[idx]))


async def _s_code_point_at(t, a, i):
    from magpie_jsrun import to_number as _tn
    s = _str_this(t, i)
    idx = int(await _tn(i, a[0])) if a else 0
    if idx < 0 or idx >= len(s):
        return UNDEFINED
    return JSNumber(ord(s[idx]))


async def _s_concat(t, a, i):
    from magpie_jsrun import to_string as _ts
    return JSString(_str_this(t, i) + "".join(await _ts(i, v) for v in a))


async def _s_ends_with(t, a, i):
    from magpie_jsrun import to_string as _ts, to_number as _tn
    s = _str_this(t, i)
    sub = await _ts(i, a[0]) if a else ""
    pos = int(await _tn(i, a[1])) if len(a) > 1 and a[1] is not UNDEFINED else len(s)
    return js_bool(s[:max(0, min(len(s), pos))].endswith(sub))


async def _s_starts_with(t, a, i):
    from magpie_jsrun import to_string as _ts, to_number as _tn
    s = _str_this(t, i)
    sub = await _ts(i, a[0]) if a else ""
    pos = int(await _tn(i, a[1])) if len(a) > 1 and a[1] is not UNDEFINED else 0
    return js_bool(s[max(0, pos):].startswith(sub))


async def _s_includes(t, a, i):
    from magpie_jsrun import to_string as _ts, to_number as _tn
    s = _str_this(t, i)
    sub = await _ts(i, a[0]) if a else ""
    if a and isinstance(a[0], JSObject) and a[0].get_own("__regexp__") is not UNDEFINED:
        throw_type("includes does not take a regexp")
    pos = int(await _tn(i, a[1])) if len(a) > 1 and a[1] is not UNDEFINED else 0
    return js_bool(sub in s[max(0, pos):])


async def _s_index_of(t, a, i):
    from magpie_jsrun import to_string as _ts, to_number as _tn
    s = _str_this(t, i)
    sub = await _ts(i, a[0]) if a else "undefined"
    pos = int(await _tn(i, a[1])) if len(a) > 1 and a[1] is not UNDEFINED else 0
    return JSNumber(s.find(sub, max(0, pos)))


async def _s_last_index_of(t, a, i):
    from magpie_jsrun import to_string as _ts, to_number as _tn
    s = _str_this(t, i)
    sub = await _ts(i, a[0]) if a else "undefined"
    pos = int(await _tn(i, a[1])) if len(a) > 1 and a[1] is not UNDEFINED else len(s)
    return JSNumber(s.rfind(sub, 0, max(0, pos) + (len(sub) if sub else 0)))


async def _s_locale_compare(t, a, i):
    from magpie_jsrun import to_string as _ts
    s = _str_this(t, i)
    other = await _ts(i, a[0]) if a else "undefined"
    return JSNumber((s > other) - (s < other))


async def _s_match(t, a, i):
    s = _str_this(t, i)
    rx = _to_regexp(a[0] if a else UNDEFINED, None, i)
    if "g" in rx.get_own("__regexp_flags__").value:
        out = []
        rx.define_own("lastIndex", JSNumber(0))
        while True:
            m = regexp_exec(rx, s)
            if m is None:
                break
            out.append(m.get("0"))
            if m.get("0").value == "":
                rx.define_own("lastIndex", JSNumber(rx.get_own("lastIndex").value + 1))
        return js_array(i, out)
    return regexp_exec(rx, s) or NULL


async def _s_match_all(t, a, i):
    s = _str_this(t, i)
    rx = _to_regexp(a[0] if a else UNDEFINED, "g", i)
    flags = rx.get_own("__regexp_flags__").value
    if "g" not in flags:
        throw_type("matchAll needs a global regexp")
    clone = make_regexp(rx.get_own("__regexp__").value, flags)
    out = []
    while True:
        m = regexp_exec(clone, s)
        if m is None:
            break
        out.append(m)
        if m.get("0").value == "":
            clone.define_own("lastIndex", JSNumber(clone.get_own("lastIndex").value + 1))
    return _make_iterator(i, out)


def _to_regexp(v, extra_flags, interp):
    from magpie_jsrun import to_string as _ts_sync
    if isinstance(v, JSObject) and v.get_own("__regexp__") is not UNDEFINED:
        if extra_flags:
            flags = v.get_own("__regexp_flags__").value
            for ch in extra_flags:
                if ch not in flags:
                    flags += ch
            return make_regexp(v.get_own("__regexp__").value, flags)
        return v
    if v is UNDEFINED:
        return make_regexp("(?:)", "")
    # to_string may need interp; run synchronously for primitives.
    if isinstance(v, (JSString, JSNumber, JSBoolean)) or v is NULL:
        return make_regexp(to_string_primitive(v), extra_flags or "")
    raise ThrowExc(make_error_value("TypeError", "string method needs a sync string"))


async def _s_normalize(t, a, i):
    from magpie_jsrun import to_string as _ts
    s = _str_this(t, i)
    form = (await _ts(i, a[0])).upper() if a and a[0] is not UNDEFINED else "NFC"
    if form not in ("NFC", "NFD", "NFKC", "NFKD"):
        throw_range("bad normalization form")
    return JSString(unicodedata.normalize(form, s))


async def _s_pad(t, a, i, *, left: bool):
    from magpie_jsrun import to_string as _ts, to_number as _tn
    s = _str_this(t, i)
    width = max(0, int(await _tn(i, a[0]))) if a and a[0] is not UNDEFINED else 0
    fill = await _ts(i, a[1]) if len(a) > 1 and a[1] is not UNDEFINED else " "
    if not fill:
        return JSString(s)
    while len(s) < width:
        s = (fill + s) if left else (s + fill)
    return JSString(s[:width] if False else s[:width] if len(s) > width else s)


async def _s_pad_start(t, a, i):
    return await _s_pad(t, a, i, left=True)


async def _s_pad_end(t, a, i):
    return await _s_pad(t, a, i, left=False)


async def _s_repeat(t, a, i):
    from magpie_jsrun import to_number as _tn
    s = _str_this(t, i)
    n = int(await _tn(i, a[0])) if a and a[0] is not UNDEFINED else 0
    if n < 0 or n > 1000000:
        throw_range("bad repeat count")
    return JSString(s * n)


def _replace_tokens(repl: str, m, text: str) -> str:
    out: list[str] = []
    k = 0
    while k < len(repl):
        c = repl[k]
        if c == "$" and k + 1 < len(repl):
            nxt = repl[k + 1]
            if nxt == "$":
                out.append("$"); k += 2; continue
            if nxt == "&":
                out.append(m.get("0").value); k += 2; continue
            if nxt == "`":
                out.append(text[:int(m.get("index").value)]); k += 2; continue
            if nxt == "'":
                out.append(text[int(m.get("index").value) + len(m.get("0").value):]); k += 2; continue
            if nxt == "<":
                end = repl.find(">", k + 2)
                if end > 0:
                    groups = m.get("groups")
                    g = groups.get(repl[k + 2:end]) if isinstance(groups, JSObject) else UNDEFINED
                    out.append(g.value if isinstance(g, JSString) else "")
                    k = end + 1
                    continue
            if nxt.isdigit():
                num = nxt
                if k + 2 < len(repl) and repl[k + 2].isdigit():
                    num += repl[k + 2]
                try:
                    g = m.get(str(int(num)))
                    out.append(g.value if isinstance(g, JSString) else "")
                except (ValueError, AttributeError):
                    out.append("$" + num)
                k += 1 + len(num)
                continue
        out.append(c)
        k += 1
    return "".join(out)


async def _s_replace(t, a, i):
    from magpie_jsrun import to_string as _ts
    s = _str_this(t, i)
    if len(a) > 0 and isinstance(a[0], JSObject) and a[0].get_own("__regexp__") is not UNDEFINED:
        rx = a[0]
        repl = a[1] if len(a) > 1 else UNDEFINED
        do_all = "g" in rx.get_own("__regexp_flags__").value
        clone = make_regexp(rx.get_own("__regexp__").value, rx.get_own("__regexp_flags__").value)
        out = []
        pos = 0
        while True:
            m = regexp_exec(clone, s)
            if m is None:
                break
            idx = int(m.get("index").value)
            out.append(s[pos:idx])
            if isinstance(repl, JSFunction):
                groups = m.get("groups")
                argv = [m.get("0")]
                for k in range(1, 20):
                    g = m.get(str(k))
                    if g is UNDEFINED:
                        break
                    argv.append(g)
                argv.append(JSNumber(idx))
                argv.append(JSString(s))
                if isinstance(groups, JSObject):
                    argv.append(groups)
                out.append(await _ts(i, await i.call_value(repl, UNDEFINED, argv)))
            else:
                out.append(_replace_tokens(await _ts(i, repl), m, s))
            pos = idx + len(m.get("0").value)
            if not do_all:
                break
            if len(m.get("0").value) == 0:
                clone.define_own("lastIndex", JSNumber(clone.get_own("lastIndex").value + 1))
                if clone.get_own("lastIndex").value > len(s):
                    break
        out.append(s[pos:])
        return JSString("".join(out))
    search = await _ts(i, a[0]) if a else "undefined"
    repl = await _ts(i, a[1]) if len(a) > 1 else "undefined"
    if isinstance(a[1] if len(a) > 1 else None, JSFunction):
        out = await _ts(i, await i.call_value(a[1], UNDEFINED, [JSString(search), JSNumber(s.find(search)), JSString(s)]))
        return JSString(s.replace(search, out, 1) if search in s else s)
    idx = s.find(search)
    if idx < 0:
        return JSString(s)
    return JSString(s[:idx] + repl.replace("$&", search) + s[idx + len(search):])


async def _s_replace_all(t, a, i):
    from magpie_jsrun import to_string as _ts
    s = _str_this(t, i)
    if a and isinstance(a[0], JSObject) and a[0].get_own("__regexp__") is not UNDEFINED:
        if "g" not in a[0].get_own("__regexp_flags__").value:
            throw_type("replaceAll needs a global regexp")
        return await _s_replace(t, a, i)
    search = await _ts(i, a[0]) if a else "undefined"
    if search == "":
        return JSString((await _ts(i, a[1])) .join(["", *list(s), ""]) if len(a) > 1 else s)
    repl = await _ts(i, a[1]) if len(a) > 1 else "undefined"
    return JSString(s.replace(search, repl.replace("$&", search)))


async def _s_search(t, a, i):
    s = _str_this(t, i)
    rx = _to_regexp(a[0] if a else UNDEFINED, None, i)
    m = regexp_exec(rx, s)
    return JSNumber(int(m.get("index").value)) if m else JSNumber(-1)


async def _s_slice(t, a, i):
    from magpie_jsrun import to_number as _tn
    s = _str_this(t, i)
    n = len(s)
    start = int(await _tn(i, a[0])) if a and a[0] is not UNDEFINED else 0
    end = int(await _tn(i, a[1])) if len(a) > 1 and a[1] is not UNDEFINED else n
    start = max(0, start + n if start < 0 else start)
    end = max(0, end + n if end < 0 else end)
    return JSString(s[start:min(n, end)] if start < end else "")


async def _s_split(t, a, i):
    from magpie_jsrun import to_string as _ts, to_number as _tn
    s = _str_this(t, i)
    limit = int(await _tn(i, a[1])) if len(a) > 1 and a[1] is not UNDEFINED else 2**32 - 1
    if not a or a[0] is UNDEFINED:
        return js_array(i, [JSString(s)])
    if isinstance(a[0], JSObject) and a[0].get_own("__regexp__") is not UNDEFINED:
        rx, _, _ = regexp_state(a[0])
        parts = []
        pos = 0
        for m in rx.finditer(s):
            parts.append(s[pos:m.start()])
            parts.extend(g if g is not None else None for g in m.groups())
            pos = m.end()
            if len([p for p in parts if p is not None]) >= limit:
                break
        parts.append(s[pos:])
        return js_array(i, [JSString(p) for p in parts[:limit] if p is not None])
    sep = await _ts(i, a[0])
    if sep == "":
        return js_array(i, [JSString(c) for c in s[:limit]])
    return js_array(i, [JSString(p) for p in s.split(sep)[:limit]])


async def _s_substr(t, a, i):
    from magpie_jsrun import to_number as _tn
    s = _str_this(t, i)
    start = int(await _tn(i, a[0])) if a and a[0] is not UNDEFINED else 0
    if start < 0:
        start = max(0, len(s) + start)
    length = int(await _tn(i, a[1])) if len(a) > 1 and a[1] is not UNDEFINED else len(s)
    return JSString(s[start:start + max(0, length)])


async def _s_substring(t, a, i):
    from magpie_jsrun import to_number as _tn
    s = _str_this(t, i)
    n = len(s)
    a0 = int(await _tn(i, a[0])) if a and a[0] is not UNDEFINED else 0
    a1 = int(await _tn(i, a[1])) if len(a) > 1 and a[1] is not UNDEFINED else n
    a0, a1 = max(0, min(n, a0)), max(0, min(n, a1))
    if a0 > a1:
        a0, a1 = a1, a0
    return JSString(s[a0:a1])


async def _s_lower(t, a, i):
    return JSString(_str_this(t, i).lower())


async def _s_upper(t, a, i):
    return JSString(_str_this(t, i).upper())


async def _s_this_string(t, a, i):
    return JSString(_str_this(t, i))


async def _s_trim(t, a, i):
    return JSString(_str_this(t, i).strip())


async def _s_trim_start(t, a, i):
    return JSString(_str_this(t, i).lstrip())


async def _s_trim_end(t, a, i):
    return JSString(_str_this(t, i).rstrip())


async def _s_well_formed(t, a, i):
    s = _str_this(t, i)
    try:
        s.encode("utf-16", "strict")
        return TRUE
    except UnicodeError:
        return FALSE


async def _s_to_well_formed(t, a, i):
    return JSString(_str_this(t, i).encode("utf-16", "surrogatepass").decode("utf-16", "replace"))


def _s_iterator(t, a, i):
    return _make_iterator(i, [JSString(c) for c in _str_this(t, i)])


# ── Number / Boolean / BigInt / Symbol ───────────────────────────────────

def install_number(Number, Number_p) -> None:
    for k, v in (("EPSILON", 2.220446049250313e-16), ("MAX_SAFE_INTEGER", 9007199254740991.0),
                 ("MIN_SAFE_INTEGER", -9007199254740991.0), ("MAX_VALUE", 1.7976931348623157e308),
                 ("MIN_VALUE", 5e-324), ("POSITIVE_INFINITY", math.inf),
                 ("NEGATIVE_INFINITY", -math.inf), ("NaN", math.nan)):
        Number.define_own(k, JSNumber(v), enumerable=False)
    Number.define_own("isFinite", native("isFinite", lambda t, a, i: js_bool(isinstance(a[0] if a else UNDEFINED, JSNumber) and abs((a[0]).value) != math.inf)), enumerable=False)
    Number.define_own("isNaN", native("isNaN", lambda t, a, i: js_bool(isinstance(a[0] if a else UNDEFINED, JSNumber) and (a[0]).value != (a[0]).value)), enumerable=False)
    Number.define_own("isInteger", native("isInteger", lambda t, a, i: js_bool(isinstance(a[0] if a else UNDEFINED, JSNumber) and (a[0]).value.is_integer())), enumerable=False)
    Number.define_own("isSafeInteger", native("isSafeInteger", lambda t, a, i: js_bool(isinstance(a[0] if a else UNDEFINED, JSNumber) and (a[0]).value.is_integer() and abs((a[0]).value) <= 9007199254740991)), enumerable=False)
    Number.define_own("parseInt", native("parseInt", _parse_int), enumerable=False)
    Number.define_own("parseFloat", native("parseFloat", _parse_float), enumerable=False)
    _m(Number_p, "toString", _num_to_string)
    _m(Number_p, "toFixed", _num_to_fixed)
    _m(Number_p, "toExponential", _num_to_exponential)
    _m(Number_p, "toPrecision", _num_to_precision)
    _m(Number_p, "valueOf", _num_value_of)


def _num_this(t, i) -> float:
    if isinstance(t, JSNumber):
        return t.value
    if isinstance(t, JSObject):
        boxed = t.get_own("__boxed__")
        if isinstance(boxed, JSNumber):
            return boxed.value
    throw_type("number method on non-number")


async def _parse_int(t, a, i):
    from magpie_jsrun import to_string as _ts, to_number as _tn
    s = (await _ts(i, a[0])).strip() if a else "NaN"
    radix = int(await _tn(i, a[1])) if len(a) > 1 and a[1] is not UNDEFINED else 0
    m = re.match(r"[+-]?(?:0[xX][0-9a-fA-F]+|0[bB][01]+|0[oO][0-7]+|\d+)", s)
    if radix == 0:
        if s[:2].lower() == "0x":
            radix = 16
        elif s[:2].lower() in ("0b", "0o"):
            radix = {"0b": 2, "0o": 8}[s[:2].lower()]
        else:
            radix = 10
    if not 2 <= radix <= 36 or not m:
        return JSNumber(math.nan)
    try:
        return JSNumber(float(int(m.group(0), radix)))
    except ValueError:
        return JSNumber(math.nan)


async def _parse_float(t, a, i):
    from magpie_jsrun import to_string as _ts
    s = (await _ts(i, a[0])).strip() if a else ""
    m = re.match(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?|Infinity", s)
    if not m:
        return JSNumber(math.nan)
    try:
        return JSNumber(float(m.group(0)))
    except ValueError:
        return JSNumber(math.nan)


async def _num_to_string(t, a, i):
    from magpie_jsrun import to_number as _tn
    v = _num_this(t, i)
    radix = int(await _tn(i, a[0])) if a and a[0] is not UNDEFINED else 10
    if radix == 10:
        return JSString(number_to_string(v))
    if not 2 <= radix <= 36 or v != v or abs(v) == math.inf:
        return JSString(number_to_string(v))
    neg = v < 0
    n = int(abs(v))
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = ""
    while n:
        out = digits[n % radix] + out
        n //= radix
    return JSString(("-" if neg else "") + (out or "0"))


async def _num_to_fixed(t, a, i):
    from magpie_jsrun import to_number as _tn
    v = _num_this(t, i)
    digits = int(await _tn(i, a[0])) if a and a[0] is not UNDEFINED else 0
    if not 0 <= digits <= 100:
        throw_range("bad fixed digits")
    if abs(v) != math.inf and v == v:
        return JSString(f"{v:.{digits}f}")
    return JSString(number_to_string(v))


async def _num_to_exponential(t, a, i):
    from magpie_jsrun import to_number as _tn
    v = _num_this(t, i)
    if a and a[0] is not UNDEFINED:
        digits = int(await _tn(i, a[0]))
        if not 0 <= digits <= 100:
            throw_range("bad exponential digits")
        if v == v and abs(v) != math.inf:
            mant, exp = f"{v:.{digits}e}".split("e")
            return JSString(f"{mant}e{int(exp):+d}".replace("e+", "e+"))
    return JSString(number_to_string(v))


async def _num_to_precision(t, a, i):
    from magpie_jsrun import to_number as _tn
    v = _num_this(t, i)
    if not a or a[0] is UNDEFINED:
        return JSString(number_to_string(v))
    prec = int(await _tn(i, a[0]))
    if not 1 <= prec <= 100:
        throw_range("bad precision")
    if v != v or abs(v) == math.inf or v == 0:
        return JSString(number_to_string(v))
    return JSString(f"{v:.{prec}g}")


async def _num_value_of(t, a, i):
    return JSNumber(_num_this(t, i))


def install_boolean(Boolean, Boolean_p) -> None:
    _m(Boolean_p, "toString", lambda t, a, i: JSString("true" if _bool_this(t) else "false"))
    _m(Boolean_p, "valueOf", lambda t, a, i: js_bool(_bool_this(t)))


def _bool_this(t) -> bool:
    if isinstance(t, JSBoolean):
        return t.value
    if isinstance(t, JSObject):
        boxed = t.get_own("__boxed__")
        if isinstance(boxed, JSBoolean):
            return boxed.value
    throw_type("boolean method on non-boolean")


def install_bigint(BigIntF, BigInt_p) -> None:
    BigIntF.define_own("asIntN", native("asIntN", _bigint_as_int_n), enumerable=False)
    BigIntF.define_own("asUintN", native("asUintN", _bigint_as_uint_n), enumerable=False)
    _m(BigInt_p, "toString", lambda t, a, i: JSString(str(_bigint_this(t))))
    _m(BigInt_p, "valueOf", lambda t, a, i: JSBigInt(_bigint_this(t)))


def _bigint_this(t) -> int:
    if isinstance(t, JSBigInt):
        return t.value
    throw_type("bigint method on non-bigint")


async def _bigint_as_int_n(t, a, i):
    from magpie_jsrun import to_number as _tn
    bits = int(await _tn(i, a[0])) if a else 0
    v = a[1].value if len(a) > 1 and isinstance(a[1], JSBigInt) else 0
    v %= 1 << bits
    if v >= 1 << (bits - 1):
        v -= 1 << bits
    return JSBigInt(v)


async def _bigint_as_uint_n(t, a, i):
    from magpie_jsrun import to_number as _tn
    bits = int(await _tn(i, a[0])) if a else 0
    v = a[1].value if len(a) > 1 and isinstance(a[1], JSBigInt) else 0
    return JSBigInt(v % (1 << bits))


def install_symbol(SymbolF, Symbol_p) -> None:
    SymbolF.define_own("for", native("for", _symbol_for), enumerable=False)
    SymbolF.define_own("keyFor", native("keyFor", _symbol_key_for), enumerable=False)
    _m(Symbol_p, "toString", lambda t, a, i: JSString(f"Symbol({_sym_this(t).desc})"))
    _m(Symbol_p, "valueOf", lambda t, a, i: _sym_this(t))


_SYMBOL_REGISTRY: dict[str, JSSymbol] = {}


def _sym_this(t) -> JSSymbol:
    if isinstance(t, JSSymbol):
        return t
    throw_type("symbol method on non-symbol")


async def _symbol_for(t, a, i):
    from magpie_jsrun import to_string as _ts
    key = await _ts(i, a[0]) if a else "undefined"
    if key not in _SYMBOL_REGISTRY:
        _SYMBOL_REGISTRY[key] = JSSymbol(key)
    return _SYMBOL_REGISTRY[key]


async def _symbol_key_for(t, a, i):
    v = a[0] if a else UNDEFINED
    if not isinstance(v, JSSymbol):
        throw_type("keyFor needs a symbol")
    for k, sym in _SYMBOL_REGISTRY.items():
        if sym is v:
            return JSString(k)
    return UNDEFINED


# ── Error ────────────────────────────────────────────────────────────────

def install_error(ErrorF, Error_p) -> None:
    for sub in ("EvalError", "RangeError", "ReferenceError", "SyntaxError", "TypeError", "URIError"):
        fn = INTRINSICS[sub]
        fn.define_own("__error_name__", JSString(sub), enumerable=False)
    INTRINSICS["AggregateError"].define_own("__error_name__", JSString("AggregateError"), enumerable=False)
    ErrorF.define_own("__error_name__", JSString("Error"), enumerable=False)
    _m(Error_p, "toString", _error_to_string)


async def _error_to_string(t, a, i):
    from magpie_jsrun import to_string as _ts
    if not isinstance(t, JSObject):
        throw_type("error toString on non-object")
    name = t.get("name")
    name = await _resolve_tuple(name, i) if isinstance(name, tuple) else name
    msg = t.get("message")
    msg = await _resolve_tuple(msg, i) if isinstance(msg, tuple) else msg
    n = await _ts(i, name) if name is not UNDEFINED else "Error"
    m = await _ts(i, msg) if msg is not UNDEFINED else ""
    return JSString(n if not m else f"{n}: {m}")


# ── Promise ──────────────────────────────────────────────────────────────

def install_promise(PromiseF, Promise_p) -> None:
    PromiseF.define_own("resolve", native("resolve", _promise_resolve), enumerable=False)
    PromiseF.define_own("reject", native("reject", lambda t, a, i: _promise_new_rejected(i, a[0] if a else make_error_value("Error", ""))), enumerable=False)
    PromiseF.define_own("all", native("all", _promise_all), enumerable=False)
    PromiseF.define_own("allSettled", native("allSettled", _promise_all_settled), enumerable=False)
    PromiseF.define_own("race", native("race", _promise_race), enumerable=False)
    PromiseF.define_own("any", native("any", _promise_any), enumerable=False)
    PromiseF.define_own("withResolvers", native("withResolvers", _promise_with_resolvers), enumerable=False)
    _m(Promise_p, "then", _promise_then)
    _m(Promise_p, "catch", _promise_catch)
    _m(Promise_p, "finally", _promise_finally)


def _promise_new(i, value=None, *, rejected: bool = False):
    from magpie_jsval import JSPromise
    p = JSPromise(i)
    if rejected:
        p.reject(value)
    else:
        p.resolve(value if value is not None else UNDEFINED)
    return p


def _promise_new_rejected(i, reason):
    return _promise_new(i, reason, rejected=True)


async def _promise_resolve(t, a, i):
    return _promise_new(i, a[0] if a else UNDEFINED)


async def _promise_then(t, a, i):
    if not isinstance(t, JSPromise):
        throw_type("then on non-promise")
    return t.then(a[0] if a and isinstance(a[0], JSFunction) else None,
                  a[1] if len(a) > 1 and isinstance(a[1], JSFunction) else None)


async def _promise_catch(t, a, i):
    if not isinstance(t, JSPromise):
        throw_type("catch on non-promise")
    return t.then(None, a[0] if a and isinstance(a[0], JSFunction) else None)


async def _promise_finally(t, a, i):
    from magpie_jsval import JSPromise
    if not isinstance(t, JSPromise):
        throw_type("finally on non-promise")
    fn = a[0] if a and isinstance(a[0], JSFunction) else None

    async def on_f(v):
        if fn is not None:
            await i.call_value(fn, UNDEFINED, [])
        return v

    async def on_r(e):
        if fn is not None:
            await i.call_value(fn, UNDEFINED, [])
        raise ThrowExc(e)

    return t.then(native("finF", on_f) if fn is not None else None,
                  native("finR", on_r) if fn is not None else None)


async def _promise_all(t, a, i):
    items = await i.to_iterable(a[0]) if a and a[0] is not UNDEFINED else []
    items = list(items)
    out = [UNDEFINED] * len(items)
    p = JSPromise(i)
    if not items:
        p.resolve(js_array(i, []))
        return p
    state = {"left": len(items), "failed": False}

    async def one(idx, item):
        try:
            v = await i.await_value(item)
        except ThrowExc as e:
            if not state["failed"]:
                state["failed"] = True
                p.reject(e.value)
            return
        if state["failed"]:
            return
        out[idx] = v
        state["left"] -= 1
        if state["left"] == 0:
            p.resolve(js_array(i, out))

    for idx, item in enumerate(items):
        asyncio.get_running_loop().create_task(one(idx, item))
    return p


async def _promise_all_settled(t, a, i):
    items = await i.to_iterable(a[0]) if a and a[0] is not UNDEFINED else []
    items = list(items)
    out = [None] * len(items)
    p = JSPromise(i)
    if not items:
        p.resolve(js_array(i, []))
        return p
    state = {"left": len(items)}

    async def one(idx, item):
        try:
            v = await i.await_value(item)
            out[idx] = js_object(i, {"status": JSString("fulfilled"), "value": v})
        except ThrowExc as e:
            out[idx] = js_object(i, {"status": JSString("rejected"), "reason": e.value})
        state["left"] -= 1
        if state["left"] == 0:
            p.resolve(js_array(i, out))

    for idx, item in enumerate(items):
        asyncio.get_running_loop().create_task(one(idx, item))
    return p


async def _promise_race(t, a, i):
    items = await i.to_iterable(a[0]) if a and a[0] is not UNDEFINED else []
    p = JSPromise(i)

    async def one(item):
        try:
            p.resolve(await i.await_value(item))
        except ThrowExc as e:
            p.reject(e.value)

    for item in items:
        asyncio.get_running_loop().create_task(one(item))
    return p


async def _promise_any(t, a, i):
    items = await i.to_iterable(a[0]) if a and a[0] is not UNDEFINED else []
    items = list(items)
    p = JSPromise(i)
    if not items:
        p.reject(make_error_value("AggregateError", "all rejected"))
        return p
    errs = [None] * len(items)
    state = {"left": len(items)}

    async def one(idx, item):
        try:
            p.resolve(await i.await_value(item))
        except ThrowExc as e:
            errs[idx] = e.value
            state["left"] -= 1
            if state["left"] == 0:
                agg = make_error_value("AggregateError", "all rejected")
                if isinstance(agg, JSObject):
                    agg.define_own("errors", js_array(i, errs))
                p.reject(agg)

    for idx, item in enumerate(items):
        asyncio.get_running_loop().create_task(one(idx, item))
    return p


async def _promise_with_resolvers(t, a, i):
    from magpie_jsval import JSPromise
    p = JSPromise(i)
    resolve = native("resolve", lambda tt, aa, ii: (p.resolve(aa[0] if aa else UNDEFINED), UNDEFINED)[1])
    reject = native("reject", lambda tt, aa, ii: (p.reject(aa[0] if aa else make_error_value("Error", "")), UNDEFINED)[1])
    return js_object(i, {"promise": p, "resolve": resolve, "reject": reject})


# ── RegExp prototype ─────────────────────────────────────────────────────

def install_regexp(RegExpF, RegExp_p) -> None:
    RegExpF.define_own("@@species", RegExpF, enumerable=False)
    _m(RegExp_p, "exec", _regexp_exec_m)
    _m(RegExp_p, "test", _regexp_test_m)
    _m(RegExp_p, "toString", _regexp_to_string)
    _m(RegExp_p, "@@replace", _regexp_replace_sym)
    _m(RegExp_p, "@@match", _regexp_match_sym)
    _m(RegExp_p, "@@split", _regexp_split_sym)
    for prop, idx in (("source", 0), ("flags", 1), ("global", 2), ("ignoreCase", 3), ("multiline", 4), ("sticky", 5), ("unicode", 6), ("dotAll", 7), ("hasIndices", 8)):
        _g(RegExp_p, prop, _regexp_flag_getter(prop))


def _regexp_flag_getter(prop: str):
    def get(t, a, i):
        if not isinstance(t, JSObject) or t.get_own("__regexp__") is UNDEFINED:
            throw_type("regexp getter on non-regexp")
        flags = t.get_own("__regexp_flags__").value
        src = t.get_own("__regexp__").value
        table = {
            "source": JSString(src), "flags": JSString(flags),
            "global": js_bool("g" in flags), "ignoreCase": js_bool("i" in flags),
            "multiline": js_bool("m" in flags), "sticky": js_bool("y" in flags),
            "unicode": js_bool("u" in flags or "v" in flags), "dotAll": js_bool("s" in flags),
            "hasIndices": js_bool("d" in flags),
        }
        return table[prop]
    return get


async def _regexp_exec_m(t, a, i):
    from magpie_jsrun import to_string as _ts
    if not isinstance(t, JSObject) or t.get_own("__regexp__") is UNDEFINED:
        throw_type("exec on non-regexp")
    return regexp_exec(t, await _ts(i, a[0]) if a else "undefined") or NULL


async def _regexp_test_m(t, a, i):
    from magpie_jsrun import to_string as _ts
    if not isinstance(t, JSObject) or t.get_own("__regexp__") is UNDEFINED:
        throw_type("test on non-regexp")
    return js_bool(regexp_exec(t, await _ts(i, a[0]) if a else "undefined") is not None)


async def _regexp_to_string(t, a, i):
    if not isinstance(t, JSObject) or t.get_own("__regexp__") is UNDEFINED:
        throw_type("regexp toString on non-regexp")
    return JSString(f"/{t.get_own('__regexp__').value}/{t.get_own('__regexp_flags__').value}")


async def _regexp_replace_sym(t, a, i):
    return await _s_replace(JSString(a[0].value if isinstance(a[0], JSString) else ""), [t, a[1] if len(a) > 1 else UNDEFINED], i)


async def _regexp_match_sym(t, a, i):
    return await _s_match(JSString(a[0].value if isinstance(a[0], JSString) else ""), [t], i)


async def _regexp_split_sym(t, a, i):
    return await _s_split(JSString(a[0].value if isinstance(a[0], JSString) else ""), [t], i)


# ── Date prototype ───────────────────────────────────────────────────────

def install_date(DateF, Date_p) -> None:
    DateF.define_own("now", native("now", lambda t, a, i: JSNumber(time.time() * 1000.0)), enumerable=False)
    DateF.define_own("parse", native("parse", _date_parse), enumerable=False)
    DateF.define_own("UTC", native("UTC", _date_utc), enumerable=False)
    for name in ("getFullYear", "getMonth", "getDate", "getDay", "getHours", "getMinutes",
                 "getSeconds", "getMilliseconds", "getTime", "getTimezoneOffset",
                 "getUTCFullYear", "getUTCMonth", "getUTCDate", "getUTCDay", "getUTCHours",
                 "getUTCMinutes", "getUTCSeconds", "getUTCMilliseconds",
                 "setFullYear", "setMonth", "setDate", "setHours", "setMinutes",
                 "setSeconds", "setMilliseconds", "setTime", "setUTCFullYear", "setUTCMonth",
                 "setUTCDate", "setUTCHours", "setUTCMinutes", "setUTCSeconds", "setUTCMilliseconds",
                 "toString", "toDateString", "toTimeString", "toISOString", "toJSON",
                 "toUTCString", "toLocaleString", "toLocaleDateString", "toLocaleTimeString", "valueOf"):
        _m(Date_p, name, _date_method(name))


async def _date_parse(t, a, i):
    from magpie_jsrun import to_string as _ts
    return JSNumber(parse_date_string(await _ts(i, a[0])) if a else math.nan)


async def _date_utc(t, a, i):
    from magpie_jsrun import to_number as _tn
    vals = [int(await _tn(i, v)) for v in a]
    while len(vals) < 7:
        vals.append(1 if len(vals) == 2 else 0)
    try:
        dt = datetime.datetime(vals[0], vals[1] + 1, vals[2], vals[3], vals[4], vals[5], vals[6] * 1000, tzinfo=datetime.timezone.utc)
        return JSNumber(dt.timestamp() * 1000.0)
    except ValueError:
        return JSNumber(math.nan)


def _date_method(name: str):
    async def handler(t, a, i):
        from magpie_jsrun import to_number as _tn
        ms = date_ms(t)
        utc = name.startswith("getUTC") or name.startswith("setUTC") or name in ("toISOString", "toUTCString", "toJSON")
        if name in ("toString", "valueOf", "getTime"):
            pass
        if name == "valueOf" or name == "getTime":
            return JSNumber(ms)
        if name == "getTimezoneOffset":
            dt = date_parts(ms)
            if dt is None:
                return JSNumber(math.nan)
            off = dt.utcoffset()
            return JSNumber(-off.total_seconds() / 60 if off else 0)
        if name == "setTime":
            t.define_own("__date__", JSNumber(await _tn(i, a[0]) if a else math.nan))
            return JSNumber(t.get_own("__date__").value)
        if name.startswith(("get", "set")) and name not in ("getTimezoneOffset",):
            dt = date_parts(ms, utc=utc)
            if dt is None:
                return JSNumber(math.nan) if name.startswith("get") else JSNumber(math.nan)
            table = {"FullYear": dt.year, "Month": dt.month - 1, "Date": dt.day, "Day": (dt.weekday() + 1) % 7,
                     "Hours": dt.hour, "Minutes": dt.minute, "Seconds": dt.second, "Milliseconds": dt.microsecond // 1000}
            stem = name[3:] if name.startswith("get") else name[3:]
            stem = stem[3:] if stem.startswith("UTC") else stem
            if name.startswith("get"):
                return JSNumber(table[stem])
            vals = {"FullYear": dt.year, "Month": dt.month - 1, "Date": dt.day, "Hours": dt.hour,
                    "Minutes": dt.minute, "Seconds": dt.second, "Milliseconds": dt.microsecond // 1000}
            nums = [int(await _tn(i, v)) for v in a]
            order = ["FullYear", "Month", "Date", "Hours", "Minutes", "Seconds", "Milliseconds"]
            start = order.index(stem)
            for j, num in enumerate(nums):
                if start + j < len(order):
                    vals[order[start + j]] = num
            try:
                if utc:
                    ndt = datetime.datetime(vals["FullYear"], vals["Month"] + 1, vals["Date"], vals["Hours"], vals["Minutes"], vals["Seconds"], vals["Milliseconds"] * 1000, tzinfo=datetime.timezone.utc)
                else:
                    ndt = datetime.datetime(vals["FullYear"], vals["Month"] + 1, vals["Date"], vals["Hours"], vals["Minutes"], vals["Seconds"], vals["Milliseconds"] * 1000).astimezone()
                t.define_own("__date__", JSNumber(ndt.timestamp() * 1000.0))
                return JSNumber(ndt.timestamp() * 1000.0)
            except ValueError:
                t.define_own("__date__", JSNumber(math.nan))
                return JSNumber(math.nan)
        dt = date_parts(ms, utc=utc)
        if dt is None:
            return JSString("Invalid Date")
        dt = date_parts(ms, utc=utc)
        if dt is None:
            return JSString("Invalid Date")
        if name == "toString":
            return JSString(dt.strftime("%a %b %d %Y %H:%M:%S GMT%z"))
        if name == "toDateString":
            return JSString(dt.strftime("%a %b %d %Y"))
        if name == "toTimeString":
            return JSString(dt.strftime("%H:%M:%S GMT%z"))
        if name == "toISOString":
            return JSString(dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z")
        if name in ("toUTCString", "toJSON"):
            return JSString(dt.astimezone(datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT"))
        return JSString(dt.isoformat())
    return handler


# ── Map / Set / Weak ─────────────────────────────────────────────────────

def install_map(MapF, Map_p) -> None:
    _m(Map_p, "set", _map_set_m)
    _m(Map_p, "get", _map_get_m)
    _m(Map_p, "has", _map_has_m)
    _m(Map_p, "delete", _map_delete_m)
    _m(Map_p, "clear", _map_clear_m)
    _m(Map_p, "forEach", _map_for_each)
    _m(Map_p, "keys", _map_keys)
    _m(Map_p, "values", _map_values)
    _m(Map_p, "entries", _map_entries)
    _g(Map_p, "size", lambda t, a, i: JSNumber(len(_map_this(t).pairs)))
    Map_p.define_own("@@iterator", Map_p.get("entries"), enumerable=False)


def _map_this(t) -> JSMap:
    if not isinstance(t, JSMap):
        throw_type("map method on non-map")
    return t


async def _map_set_m(t, a, i):
    m = _map_this(t)
    map_set(m, a[0] if a else UNDEFINED, a[1] if len(a) > 1 else UNDEFINED)
    return t


async def _map_get_m(t, a, i):
    m = _map_this(t)
    k = a[0] if a else UNDEFINED
    for ek, ev in m.pairs:
        if same_value_zero(ek, k):
            return ev
    return UNDEFINED


async def _map_has_m(t, a, i):
    m = _map_this(t)
    k = a[0] if a else UNDEFINED
    return js_bool(any(same_value_zero(ek, k) for ek, _ in m.pairs))


async def _map_delete_m(t, a, i):
    m = _map_this(t)
    k = a[0] if a else UNDEFINED
    for j, (ek, _) in enumerate(m.pairs):
        if same_value_zero(ek, k):
            del m.pairs[j]
            return TRUE
    return FALSE


async def _map_clear_m(t, a, i):
    _map_this(t).pairs.clear()
    return UNDEFINED


async def _map_for_each(t, a, i):
    m = _map_this(t)
    fn = a[0] if a else UNDEFINED
    if not isinstance(fn, JSFunction):
        throw_type("callback needs a function")
    for k, v in list(m.pairs):
        await i.call_value(fn, a[1] if len(a) > 1 else UNDEFINED, [v, k, t])
    return UNDEFINED


def _map_keys(t, a, i):
    return _make_iterator(i, [k for k, _ in _map_this(t).pairs])


def _map_values(t, a, i):
    return _make_iterator(i, [v for _, v in _map_this(t).pairs])


def _map_entries(t, a, i):
    return _make_iterator(i, [js_array(i, [k, v]) for k, v in _map_this(t).pairs])


def install_set(SetF, Set_p) -> None:
    _m(Set_p, "add", _set_add_m)
    _m(Set_p, "has", _set_has_m)
    _m(Set_p, "delete", _set_delete_m)
    _m(Set_p, "clear", _set_clear_m)
    _m(Set_p, "forEach", _set_for_each)
    _m(Set_p, "keys", _set_values_m)
    _m(Set_p, "values", _set_values_m)
    _m(Set_p, "entries", _set_entries_m)
    _g(Set_p, "size", lambda t, a, i: JSNumber(len(_set_this(t).items)))
    Set_p.define_own("@@iterator", Set_p.get("values"), enumerable=False)


def _set_this(t) -> JSSet:
    if not isinstance(t, JSSet):
        throw_type("set method on non-set")
    return t


async def _set_add_m(t, a, i):
    s = _set_this(t)
    v = a[0] if a else UNDEFINED
    if not any(same_value_zero(x, v) for x in s.items):
        s.items.append(v)
    return t


async def _set_has_m(t, a, i):
    s = _set_this(t)
    v = a[0] if a else UNDEFINED
    return js_bool(any(same_value_zero(x, v) for x in s.items))


async def _set_delete_m(t, a, i):
    s = _set_this(t)
    v = a[0] if a else UNDEFINED
    for x in s.items:
        if same_value_zero(x, v):
            s.items.remove(x)
            return TRUE
    return FALSE


async def _set_clear_m(t, a, i):
    _set_this(t).items.clear()
    return UNDEFINED


async def _set_for_each(t, a, i):
    s = _set_this(t)
    fn = a[0] if a else UNDEFINED
    if not isinstance(fn, JSFunction):
        throw_type("callback needs a function")
    for v in list(s.items):
        await i.call_value(fn, a[1] if len(a) > 1 else UNDEFINED, [v, v, t])
    return UNDEFINED


def _set_values_m(t, a, i):
    return _make_iterator(i, list(_set_this(t).items))


def _set_entries_m(t, a, i):
    return _make_iterator(i, [js_array(i, [v, v]) for v in _set_this(t).items])


def install_weak(WeakMapF, WeakMap_p, WeakSetF, WeakSet_p) -> None:
    _m(WeakMap_p, "set", _weakmap_set)
    _m(WeakMap_p, "get", _weakmap_get)
    _m(WeakMap_p, "has", _weakmap_has)
    _m(WeakMap_p, "delete", _weakmap_delete)
    _m(WeakSet_p, "add", _weakset_add)
    _m(WeakSet_p, "has", _weakset_has)
    _m(WeakSet_p, "delete", _weakset_delete)


def _weak_key(v) -> JSObject:
    if not isinstance(v, JSObject):
        throw_type("weak collection needs an object key")
    return v


async def _weakmap_set(t, a, i):
    m = _map_this(t)
    map_set(m, _weak_key(a[0] if a else UNDEFINED), a[1] if len(a) > 1 else UNDEFINED)
    return t


async def _weakmap_get(t, a, i):
    return await _map_get_m(t, a, i)


async def _weakmap_has(t, a, i):
    return await _map_has_m(t, a, i)


async def _weakmap_delete(t, a, i):
    return await _map_delete_m(t, a, i)


async def _weakset_add(t, a, i):
    return await _set_add_m(t, a, i)


async def _weakset_has(t, a, i):
    return await _set_has_m(t, a, i)


async def _weakset_delete(t, a, i):
    return await _set_delete_m(t, a, i)


# ── buffers / typed arrays ───────────────────────────────────────────────

def install_buffer(ArrayBufferF, ArrayBuffer_p, DataViewF, DataView_p) -> None:
    ArrayBufferF.define_own("isView", native("isView", lambda t, a, i: js_bool(isinstance(a[0] if a else UNDEFINED, JSObject) and (a[0].get_own("__typed__") is not UNDEFINED or a[0].get_own("__view__") is not UNDEFINED))), enumerable=False)
    _m(ArrayBuffer_p, "slice", _buffer_slice)
    _g(ArrayBuffer_p, "byteLength", lambda t, a, i: JSNumber(len(_buffer_this(t).data)))
    for name in ("getInt8", "getUint8", "getInt16", "getUint16", "getInt32", "getUint32",
                 "getFloat32", "getFloat64", "getBigInt64", "getBigUint64",
                 "setInt8", "setUint8", "setInt16", "setUint16", "setInt32", "setUint32",
                 "setFloat32", "setFloat64", "setBigInt64", "setBigUint64"):
        _m(DataView_p, name, _dataview_op(name))
    _g(DataView_p, "byteLength", lambda t, a, i: JSNumber(_view_this(t).length))
    _g(DataView_p, "byteOffset", lambda t, a, i: JSNumber(_view_this(t).off))


def _buffer_this(t) -> _RawBytes:
    if not isinstance(t, JSObject) or not isinstance(t.get_own("__buffer__"), _RawBytes):
        throw_type("buffer method on non-buffer")
    return t.get_own("__buffer__")


def _view_this(t) -> _View:
    if not isinstance(t, JSObject) or not isinstance(t.get_own("__view__"), _View):
        throw_type("dataview method on non-view")
    return t.get_own("__view__")


async def _buffer_slice(t, a, i):
    from magpie_jsrun import to_number as _tn
    buf = _buffer_this(t).data
    start = int(await _tn(i, a[0])) if a and a[0] is not UNDEFINED else 0
    end = int(await _tn(i, a[1])) if len(a) > 1 and a[1] is not UNDEFINED else len(buf)
    obj = JSObject(INTRINSICS["ArrayBuffer_prototype"])
    obj.define_own("__buffer__", _RawBytes(bytearray(buf[max(0, start):max(0, end)])), enumerable=False)
    return obj


def _dataview_op(name: str):
    sizes = {"8": 1, "16": 2, "32": 4, "64": 8}
    bits = next(k for k in sizes if name.endswith(k))
    size = sizes[bits]
    is_get = name.startswith("get")
    signed = "Uint" not in name and "Float" not in name and "BigUint" not in name

    async def handler(t, a, i):
        from magpie_jsrun import to_number as _tn
        view = _view_this(t)
        at = int(await _tn(i, a[0])) if a else 0
        little = True
        if (is_get and len(a) > 1 and a[1] is not UNDEFINED) or (not is_get and len(a) > 2 and a[2] is not UNDEFINED):
            little = to_boolean(a[1] if is_get else a[2])
        order = "little" if little else "big"
        raw = bytes(view.buf[view.off + at:view.off + at + size])
        if len(raw) < size:
            throw_range("dataview out of range")
        if is_get:
            if "Float" in name:
                return JSNumber(struct.unpack(("<f" if order == "little" else ">f") if size == 4 else ("<d" if order == "little" else ">d"), raw)[0])
            if "Big" in name:
                return JSBigInt(int.from_bytes(raw, order, signed=signed))
            return JSNumber(float(int.from_bytes(raw, order, signed=signed)))
        v = a[1] if len(a) > 1 else UNDEFINED
        if "Float" in name:
            n = await to_number_i(i, v)
            view.buf[view.off + at:view.off + at + size] = struct.pack(("<f" if order == "little" else ">f") if size == 4 else ("<d" if order == "little" else ">d"), n)
        elif "Big" in name:
            big = v.value if isinstance(v, JSBigInt) else int(await to_number_i(i, v))
            view.buf[view.off + at:view.off + at + size] = (big & ((1 << size * 8) - 1)).to_bytes(size, order, signed=signed)
        else:
            n = int(await to_number_i(i, v)) & ((1 << size * 8) - 1)
            view.buf[view.off + at:view.off + at + size] = n.to_bytes(size, order)
        return UNDEFINED
    return handler


def install_typed_protos() -> None:
    for tname in ("Int8Array", "Uint8Array", "Uint8ClampedArray", "Int16Array", "Uint16Array",
                  "Int32Array", "Uint32Array", "Float32Array", "Float64Array",
                  "BigInt64Array", "BigUint64Array"):
        p = INTRINSICS[tname + "_prototype"]
        _m(p, "set", _typed_set)
        _m(p, "subarray", _typed_subarray)
        _m(p, "slice", _typed_slice)
        _m(p, "fill", _typed_fill)
        _m(p, "values", _typed_values)
        _m(p, "keys", _typed_keys)
        _m(p, "entries", _typed_entries)
        _m(p, "join", _typed_join)
        _m(p, "indexOf", _typed_index_of)
        _m(p, "includes", _typed_includes)
        _g(p, "length", lambda t, a, i: JSNumber(_typed_this(t).length))
        _g(p, "byteLength", lambda t, a, i: JSNumber(_typed_this(t).length * _typed_this(t).size))
        _g(p, "byteOffset", lambda t, a, i: JSNumber(_typed_this(t).off))
        p.define_own("@@iterator", p.get("values"), enumerable=False)


def _typed_this(t) -> _Typed:
    if not isinstance(t, JSObject) or not isinstance(t.get_own("__typed__"), _Typed):
        throw_type("typed method on non-typed-array")
    return t.get_own("__typed__")


def _typed_refresh(t) -> None:
    info = _typed_this(t)
    for k in [k for k in t.props if k.isdigit()]:
        del t.props[k]
    for k in range(info.length):
        t.define_own(str(k), read_typed(info.buf, info.off + k * info.size, info.size, info.kind))


async def _typed_set(t, a, i):
    info = _typed_this(t)
    if not a or a[0] is UNDEFINED:
        return UNDEFINED
    from magpie_jsrun import to_number as _tn
    off = int(await _tn(i, a[1])) if len(a) > 1 and a[1] is not UNDEFINED else 0
    src = a[0]
    items = await i.to_iterable(src) if isinstance(src, JSObject) and not isinstance(src.get_own("__typed__"), _Typed) else None
    if items is None and isinstance(src, JSObject) and isinstance(src.get_own("__typed__"), _Typed):
        other = src.get_own("__typed__")
        items = [read_typed(other.buf, other.off + k * other.size, other.size, other.kind) for k in range(other.length)]
    if items is None:
        throw_type("typed set needs an array")
    for j, item in enumerate(items):
        if off + j >= info.length:
            break
        if isinstance(item, JSBigInt) or info.kind in ("bigint", "biguint"):
            big = item.value if isinstance(item, JSBigInt) else int(await to_number_i(i, item))
            info.buf[info.off + (off + j) * info.size:info.off + (off + j + 1) * info.size] = (big & ((1 << info.size * 8) - 1)).to_bytes(info.size, "little", signed=(info.kind == "bigint"))
        else:
            write_typed(info.buf, info.off + (off + j) * info.size, info.size, info.kind, item)
    _typed_refresh(t)
    return UNDEFINED


async def _typed_subarray(t, a, i):
    from magpie_jsrun import to_number as _tn
    info = _typed_this(t)
    start = int(await _tn(i, a[0])) if a and a[0] is not UNDEFINED else 0
    end = int(await _tn(i, a[1])) if len(a) > 1 and a[1] is not UNDEFINED else info.length
    start = max(0, start + info.length if start < 0 else start)
    end = min(info.length, max(0, end + info.length if end < 0 else end))
    obj = JSObject(t.proto)
    obj.define_own("__typed__", _Typed(info.buf, info.off + start * info.size, max(0, end - start), info.size, info.kind), enumerable=False)
    _typed_refresh(obj)
    obj.define_own("length", JSNumber(max(0, end - start)), enumerable=False)
    return obj


async def _typed_slice(t, a, i):
    from magpie_jsrun import to_number as _tn
    info = _typed_this(t)
    start = int(await _tn(i, a[0])) if a and a[0] is not UNDEFINED else 0
    end = int(await _tn(i, a[1])) if len(a) > 1 and a[1] is not UNDEFINED else info.length
    start = max(0, start + info.length if start < 0 else start)
    end = min(info.length, max(0, end + info.length if end < 0 else end))
    out = JSObject(t.proto)
    length = max(0, end - start)
    buf = bytearray(info.buf[info.off + start * info.size:info.off + end * info.size])
    out.define_own("__typed__", _Typed(buf, 0, length, info.size, info.kind), enumerable=False)
    _typed_refresh(out)
    out.define_own("length", JSNumber(length), enumerable=False)
    return out


async def _typed_fill(t, a, i):
    from magpie_jsrun import to_number as _tn
    info = _typed_this(t)
    v = a[0] if a else UNDEFINED
    start = int(await _tn(i, a[1])) if len(a) > 1 and a[1] is not UNDEFINED else 0
    end = int(await _tn(i, a[2])) if len(a) > 2 and a[2] is not UNDEFINED else info.length
    for k in range(max(0, start), min(info.length, end)):
        write_typed(info.buf, info.off + k * info.size, info.size, info.kind, v)
    _typed_refresh(t)
    return t


def _typed_values(t, a, i):
    info = _typed_this(t)
    return _make_iterator(i, [read_typed(info.buf, info.off + k * info.size, info.size, info.kind) for k in range(info.length)])


def _typed_keys(t, a, i):
    return _make_iterator(i, [JSNumber(k) for k in range(_typed_this(t).length)])


def _typed_entries(t, a, i):
    info = _typed_this(t)
    return _make_iterator(i, [js_array(i, [JSNumber(k), read_typed(info.buf, info.off + k * info.size, info.size, info.kind)]) for k in range(info.length)])


async def _typed_join(t, a, i):
    from magpie_jsrun import to_string as _ts
    info = _typed_this(t)
    sep = await _ts(i, a[0]) if a and a[0] is not UNDEFINED else ","
    return JSString(sep.join(await _ts(i, read_typed(info.buf, info.off + k * info.size, info.size, info.kind)) for k in range(info.length)))


async def _typed_index_of(t, a, i):
    info = _typed_this(t)
    v = a[0] if a else UNDEFINED
    for k in range(info.length):
        if strict_equal(read_typed(info.buf, info.off + k * info.size, info.size, info.kind), v):
            return JSNumber(k)
    return JSNumber(-1)


async def _typed_includes(t, a, i):
    return js_bool((await _typed_index_of(t, a, i)).value != -1)


# ── text codecs ──────────────────────────────────────────────────────────

def install_text(TextEncoderF, TextEncoder_p, TextDecoderF, TextDecoder_p) -> None:
    _m(TextEncoder_p, "encode", _te_encode)
    _m(TextEncoder_p, "encodeInto", _te_encode_into)
    _g(TextEncoder_p, "encoding", lambda t, a, i: JSString("utf-8"))
    _m(TextDecoder_p, "decode", _td_decode)
    _g(TextDecoder_p, "encoding", lambda t, a, i: JSString(t.get_own("__label__").value if isinstance(t.get_own("__label__"), JSString) else "utf-8"))
    _g(TextDecoder_p, "fatal", lambda t, a, i: t.get_own("__fatal__"))


async def _te_encode(t, a, i):
    from magpie_jsrun import to_string as _ts
    data = (await _ts(i, a[0])).encode("utf-8") if a and a[0] is not UNDEFINED else b""
    obj = JSObject(INTRINSICS["Uint8Array_prototype"])
    obj.define_own("__typed__", _Typed(bytearray(data), 0, len(data), 1, "uint"), enumerable=False)
    _typed_refresh(obj)
    obj.define_own("length", JSNumber(len(data)), enumerable=False)
    return obj


async def _te_encode_into(t, a, i):
    from magpie_jsrun import to_string as _ts
    s = await _ts(i, a[0]) if a and a[0] is not UNDEFINED else ""
    dest = a[1] if len(a) > 1 else UNDEFINED
    data = s.encode("utf-8")
    if not isinstance(dest, JSObject) or not isinstance(dest.get_own("__typed__"), _Typed):
        throw_type("encodeInto needs a typed array")
    info = dest.get_own("__typed__")
    n = min(len(data), info.length)
    info.buf[info.off:info.off + n] = data[:n]
    _typed_refresh(dest)
    read = len(data[:n].decode("utf-8", "ignore"))
    return js_object(i, {"read": JSNumber(read), "written": JSNumber(n)})


async def _td_decode(t, a, i):
    if not isinstance(t, JSObject):
        throw_type("decode on non-decoder")
    label = t.get_own("__label__").value if isinstance(t.get_own("__label__"), JSString) else "utf-8"
    fatal = t.get_own("__fatal__") is TRUE
    buf = a[0] if a else UNDEFINED
    data = b""
    if isinstance(buf, JSObject) and isinstance(buf.get_own("__typed__"), _Typed):
        info = buf.get_own("__typed__")
        data = bytes(info.buf[info.off:info.off + info.length * info.size])
    elif isinstance(buf, JSObject) and isinstance(buf.get_own("__buffer__"), _RawBytes):
        data = bytes(buf.get_own("__buffer__").data)
    try:
        return JSString(data.decode(label, "strict" if fatal else "replace"))
    except (LookupError, UnicodeError) as e:
        raise ThrowExc(make_error_value("TypeError", f"cannot decode: {e}"))


# ── URL ──────────────────────────────────────────────────────────────────

def install_url(URLF, URL_p, URLSearchParamsF, URLSearchParams_p) -> None:
    URLF.define_own("canParse", native("canParse", _url_can_parse), enumerable=False)
    URLF.define_own("createObjectURL", native("createObjectURL", lambda t, a, i: JSString("blob:magpie/unsupported")), enumerable=False)
    URLF.define_own("revokeObjectURL", native("revokeObjectURL", lambda t, a, i: UNDEFINED), enumerable=False)
    for name in ("href", "protocol", "username", "password", "host", "hostname", "port", "pathname", "search", "hash", "origin"):
        _url_prop(URL_p, name)
    _m(URL_p, "toString", _url_to_string)
    _m(URL_p, "toJSON", _url_to_string)
    for name, fn in (("append", _sp_append), ("delete", _sp_delete), ("get", _sp_get),
                     ("getAll", _sp_get_all), ("has", _sp_has), ("set", _sp_set),
                     ("sort", _sp_sort), ("toString", _sp_to_string), ("forEach", _sp_for_each),
                     ("keys", _sp_keys), ("values", _sp_values), ("entries", _sp_entries)):
        _m(URLSearchParams_p, name, fn)
    _g(URLSearchParams_p, "size", lambda t, a, i: JSNumber(len(_sp_this(t).pairs)))
    URLSearchParams_p.define_own("@@iterator", URLSearchParams_p.get("entries"), enumerable=False)


def _url_parts(t) -> urllib.parse.ParseResult:
    if not isinstance(t, JSObject) or not isinstance(t.get_own("__parts__"), _Parts):
        throw_type("url member on non-url")
    return t.get_own("__parts__").parts


def _url_emit(t, parts) -> None:
    t.define_own("__parts__", _Parts(parts), enumerable=False)


def _url_prop(proto, name: str) -> None:
    def get(t, a, i):
        p = _url_parts(t)
        table = {
            "href": p.geturl(), "protocol": p.scheme + ":", "username": p.username or "",
            "password": p.password or "", "host": p.netloc, "hostname": p.hostname or "",
            "port": str(p.port) if p.port else "", "pathname": p.path or "/",
            "search": ("?" + p.query) if p.query else "", "hash": ("#" + p.fragment) if p.fragment else "",
            "origin": f"{p.scheme}://{p.netloc}" if p.scheme in ("http", "https") else "null",
        }
        return JSString(table[name])

    async def setv(t, a, i):
        from magpie_jsrun import to_string as _ts
        p = _url_parts(t)
        v = await _ts(i, a[0]) if a else ""
        try:
            if name == "href":
                np = urllib.parse.urlparse(v)
            elif name == "protocol":
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
            elif name in ("username", "password", "origin"):
                return UNDEFINED
            _url_emit(t, np)
        except ValueError:
            pass
        return UNDEFINED

    proto.define_accessor(name, native(f"get {name}", get), native(f"set {name}", setv), enumerable=False)
    if name == "search":
        _g(proto, "searchParams", lambda t, a, i: _url_search_params(t))


def _url_search_params(t):
    obj = JSObject(INTRINSICS["URLSearchParams_prototype"])
    obj.define_own("__pairs__", _Pairs(urllib.parse.parse_qsl(_url_parts(t).query, keep_blank_values=True)), enumerable=False)
    obj.define_own("__url__", t, enumerable=False)
    return obj


async def _url_to_string(t, a, i):
    return JSString(_url_parts(t).geturl())


async def _url_can_parse(t, a, i):
    from magpie_jsrun import to_string as _ts
    if not a:
        return FALSE
    try:
        href = await _ts(i, a[0])
        base = await _ts(i, a[1]) if len(a) > 1 and a[1] is not UNDEFINED else ""
        joined = urllib.parse.urljoin(base, href) if base else href
        return js_bool(bool(urllib.parse.urlparse(joined).scheme))
    except (ValueError, ThrowExc):
        return FALSE


def _sp_this(t) -> _Pairs:
    if not isinstance(t, JSObject) or not isinstance(t.get_own("__pairs__"), _Pairs):
        throw_type("searchparams method on non-searchparams")
    return t.get_own("__pairs__")


def _sp_sync(t) -> None:
    url = t.get_own("__url__")
    if isinstance(url, JSObject) and isinstance(url.get_own("__parts__"), _Parts):
        p = url.get_own("__parts__").parts
        _url_emit(url, p._replace(query=urllib.parse.urlencode(t.get_own("__pairs__").pairs)))


async def _sp_append(t, a, i):
    from magpie_jsrun import to_string as _ts
    sp = _sp_this(t)
    sp.pairs.append((await _ts(i, a[0]) if a else "", await _ts(i, a[1]) if len(a) > 1 else ""))
    _sp_sync(t)
    return UNDEFINED


async def _sp_delete(t, a, i):
    from magpie_jsrun import to_string as _ts
    sp = _sp_this(t)
    name = await _ts(i, a[0]) if a else ""
    sp.pairs = [(k, v) for k, v in sp.pairs if k != name]
    _sp_sync(t)
    return UNDEFINED


async def _sp_get(t, a, i):
    from magpie_jsrun import to_string as _ts
    name = await _ts(i, a[0]) if a else ""
    for k, v in _sp_this(t).pairs:
        if k == name:
            return JSString(v)
    return NULL


async def _sp_get_all(t, a, i):
    from magpie_jsrun import to_string as _ts
    name = await _ts(i, a[0]) if a else ""
    return js_array(i, [JSString(v) for k, v in _sp_this(t).pairs if k == name])


async def _sp_has(t, a, i):
    from magpie_jsrun import to_string as _ts
    name = await _ts(i, a[0]) if a else ""
    return js_bool(any(k == name for k, _ in _sp_this(t).pairs))


async def _sp_set(t, a, i):
    from magpie_jsrun import to_string as _ts
    sp = _sp_this(t)
    name = await _ts(i, a[0]) if a else ""
    value = await _ts(i, a[1]) if len(a) > 1 else ""
    sp.pairs = [(k, v) for k, v in sp.pairs if k != name] + [(name, value)]
    _sp_sync(t)
    return UNDEFINED


async def _sp_sort(t, a, i):
    _sp_this(t).pairs.sort(key=lambda kv: kv[0])
    _sp_sync(t)
    return UNDEFINED


async def _sp_to_string(t, a, i):
    return JSString(urllib.parse.urlencode(_sp_this(t).pairs))


async def _sp_for_each(t, a, i):
    fn = a[0] if a else UNDEFINED
    if not isinstance(fn, JSFunction):
        throw_type("callback needs a function")
    for k, v in list(_sp_this(t).pairs):
        await i.call_value(fn, a[1] if len(a) > 1 else UNDEFINED, [JSString(v), JSString(k), t])
    return UNDEFINED


def _sp_keys(t, a, i):
    return _make_iterator(i, [JSString(k) for k, _ in _sp_this(t).pairs])


def _sp_values(t, a, i):
    return _make_iterator(i, [JSString(v) for _, v in _sp_this(t).pairs])


def _sp_entries(t, a, i):
    return _make_iterator(i, [js_array(i, [JSString(k), JSString(v)]) for k, v in _sp_this(t).pairs])


# ── fetchables ───────────────────────────────────────────────────────────

def install_fetchables(HeadersF, Headers_p, BlobF, Blob_p, FormDataF, FormData_p, AbortControllerF, AbortController_p, XMLHttpRequestF, XMLHttpRequest_p) -> None:
    for name, fn in (("append", _h_append), ("delete", _h_delete), ("get", _h_get),
                     ("getSetCookie", _h_get_set_cookie), ("has", _h_has), ("set", _h_set),
                     ("forEach", _h_for_each), ("keys", _h_keys), ("values", _h_values), ("entries", _h_entries)):
        _m(Headers_p, name, fn)
    _m(Blob_p, "text", _blob_text)
    _m(Blob_p, "arrayBuffer", _blob_buffer)
    _m(Blob_p, "slice", _blob_slice)
    _g(Blob_p, "size", lambda t, a, i: JSNumber(len(_blob_this(t))))
    _g(Blob_p, "type", lambda t, a, i: t.get_own("__blob_type__"))
    _m(FormData_p, "append", _fd_append)
    _m(FormData_p, "delete", _fd_delete)
    _m(FormData_p, "get", _fd_get)
    _m(FormData_p, "getAll", _fd_get_all)
    _m(FormData_p, "has", _fd_has)
    _m(FormData_p, "set", _fd_set)
    _m(FormData_p, "forEach", _fd_for_each)
    _m(FormData_p, "keys", _fd_keys)
    _m(FormData_p, "values", _fd_values)
    _m(FormData_p, "entries", _fd_entries)
    _m(AbortController_p, "abort", _abort_now)
    _g(AbortController_p, "signal", lambda t, a, i: t.get("signal"))
    _m(XMLHttpRequest_p, "open", _xhr_open)
    _m(XMLHttpRequest_p, "send", _xhr_send)
    _m(XMLHttpRequest_p, "abort", _xhr_abort)
    _m(XMLHttpRequest_p, "setRequestHeader", _xhr_set_header)
    _m(XMLHttpRequest_p, "getResponseHeader", _xhr_get_header)
    _m(XMLHttpRequest_p, "getAllResponseHeaders", _xhr_get_all_headers)
    _m(XMLHttpRequest_p, "addEventListener", _xhr_add_listener)
    _m(XMLHttpRequest_p, "removeEventListener", _xhr_remove_listener)
    _m(XMLHttpRequest_p, "dispatchEvent", _xhr_dispatch)
    for prop in ("onreadystatechange", "onload", "onerror", "onloadend", "onabort", "ontimeout", "onprogress", "onloadstart"):
        _xhr_handler_prop(XMLHttpRequest_p, prop)
    for prop, val in (("UNSENT", 0), ("OPENED", 1), ("HEADERS_RECEIVED", 2), ("LOADING", 3), ("DONE", 4)):
        XMLHttpRequestF.define_own(prop, JSNumber(val), enumerable=False)
    for prop in ("readyState", "status", "statusText", "responseText", "response", "responseURL", "responseType", "timeout", "withCredentials"):
        _xhr_state_prop(XMLHttpRequest_p, prop)


def _h_this(t) -> _Headers:
    if not isinstance(t, JSObject) or not isinstance(t.get_own("__headers__"), _Headers):
        throw_type("headers method on non-headers")
    return t.get_own("__headers__")


async def _h_norm(i, v) -> str:
    from magpie_jsrun import to_string as _ts
    return (await _ts(i, v)).lower()


async def _h_append(t, a, i):
    from magpie_jsrun import to_string as _ts
    h = _h_this(t)
    h.pairs.append((await _h_norm(i, a[0]) if a else "", await _ts(i, a[1]) if len(a) > 1 else ""))
    return UNDEFINED


async def _h_delete(t, a, i):
    h = _h_this(t)
    name = await _h_norm(i, a[0]) if a else ""
    h.pairs = [(k, v) for k, v in h.pairs if k != name]
    return UNDEFINED


async def _h_get(t, a, i):
    h = _h_this(t)
    name = await _h_norm(i, a[0]) if a else ""
    vals = [v for k, v in h.pairs if k == name]
    return JSString(", ".join(vals)) if vals else NULL


async def _h_get_set_cookie(t, a, i):
    h = _h_this(t)
    return js_array(i, [JSString(v) for k, v in h.pairs if k == "set-cookie"])


async def _h_has(t, a, i):
    h = _h_this(t)
    name = await _h_norm(i, a[0]) if a else ""
    return js_bool(any(k == name for k, _ in h.pairs))


async def _h_set(t, a, i):
    from magpie_jsrun import to_string as _ts
    h = _h_this(t)
    name = await _h_norm(i, a[0]) if a else ""
    value = await _ts(i, a[1]) if len(a) > 1 else ""
    h.pairs = [(k, v) for k, v in h.pairs if k != name] + [(name, value)]
    return UNDEFINED


async def _h_for_each(t, a, i):
    from magpie_jsrun import to_string as _ts
    fn = a[0] if a else UNDEFINED
    if not isinstance(fn, JSFunction):
        throw_type("callback needs a function")
    for k, v in list(_h_this(t).pairs):
        await i.call_value(fn, a[1] if len(a) > 1 else UNDEFINED, [JSString(v), JSString(k), t])
    return UNDEFINED


def _h_keys(t, a, i):
    return _make_iterator(i, [JSString(k) for k, _ in _h_this(t).pairs])


def _h_values(t, a, i):
    return _make_iterator(i, [JSString(v) for _, v in _h_this(t).pairs])


def _h_entries(t, a, i):
    return _make_iterator(i, [js_array(i, [JSString(k), JSString(v)]) for k, v in _h_this(t).pairs])


def _blob_this(t) -> bytes:
    if not isinstance(t, JSObject) or not isinstance(t.get_own("__blob__"), bytes):
        throw_type("blob method on non-blob")
    return t.get_own("__blob__")


async def _blob_text(t, a, i):
    p = _promise_new(i)
    p.resolve(JSString(_blob_this(t).decode("utf-8", "replace")))
    return p


async def _blob_buffer(t, a, i):
    data = _blob_this(t)
    obj = JSObject(INTRINSICS["ArrayBuffer_prototype"])
    obj.define_own("__buffer__", _RawBytes(bytearray(data)), enumerable=False)
    p = _promise_new(i)
    p.resolve(obj)
    return p


async def _blob_slice(t, a, i):
    from magpie_jsrun import to_number as _tn, to_string as _ts
    data = _blob_this(t)
    start = int(await _tn(i, a[0])) if a and a[0] is not UNDEFINED else 0
    end = int(await _tn(i, a[1])) if len(a) > 1 and a[1] is not UNDEFINED else len(data)
    ctype = await _ts(i, a[2]) if len(a) > 2 and a[2] is not UNDEFINED else ""
    obj = JSObject(INTRINSICS["Blob_prototype"])
    obj.define_own("__blob__", data[max(0, start):max(0, end)], enumerable=False)
    obj.define_own("__blob_type__", JSString(ctype.lower()), enumerable=False)
    return obj


def _fd_this(t) -> _Pairs:
    if not isinstance(t, JSObject) or not isinstance(t.get_own("__form__"), _Pairs):
        throw_type("formdata method on non-formdata")
    return t.get_own("__form__")


async def _fd_append(t, a, i):
    from magpie_jsrun import to_string as _ts
    fd = _fd_this(t)
    fd.pairs.append((await _ts(i, a[0]) if a else "", a[1] if len(a) > 1 else UNDEFINED))
    return UNDEFINED


async def _fd_delete(t, a, i):
    from magpie_jsrun import to_string as _ts
    fd = _fd_this(t)
    name = await _ts(i, a[0]) if a else ""
    fd.pairs = [(k, v) for k, v in fd.pairs if k != name]
    return UNDEFINED


async def _fd_get(t, a, i):
    from magpie_jsrun import to_string as _ts
    name = await _ts(i, a[0]) if a else ""
    for k, v in _fd_this(t).pairs:
        if k == name:
            return v
    return NULL


async def _fd_get_all(t, a, i):
    from magpie_jsrun import to_string as _ts
    name = await _ts(i, a[0]) if a else ""
    return js_array(i, [v for k, v in _fd_this(t).pairs if k == name])


async def _fd_has(t, a, i):
    from magpie_jsrun import to_string as _ts
    name = await _ts(i, a[0]) if a else ""
    return js_bool(any(k == name for k, _ in _fd_this(t).pairs))


async def _fd_set(t, a, i):
    from magpie_jsrun import to_string as _ts
    fd = _fd_this(t)
    name = await _ts(i, a[0]) if a else ""
    value = a[1] if len(a) > 1 else UNDEFINED
    fd.pairs = [(k, v) for k, v in fd.pairs if k != name] + [(name, value)]
    return UNDEFINED


async def _fd_for_each(t, a, i):
    from magpie_jsrun import to_string as _ts
    fn = a[0] if a else UNDEFINED
    if not isinstance(fn, JSFunction):
        throw_type("callback needs a function")
    for k, v in list(_fd_this(t).pairs):
        out = v if isinstance(v, JSValue) else JSString(await _ts(i, v))
        await i.call_value(fn, a[1] if len(a) > 1 else UNDEFINED, [out, JSString(k), t])
    return UNDEFINED


def _fd_keys(t, a, i):
    return _make_iterator(i, [JSString(k) for k, _ in _fd_this(t).pairs])


def _fd_values(t, a, i):
    return _make_iterator(i, [v if isinstance(v, JSValue) else JSString(str(v)) for _, v in _fd_this(t).pairs])


def _fd_entries(t, a, i):
    return _make_iterator(i, [js_array(i, [JSString(k), v if isinstance(v, JSValue) else JSString(str(v))]) for k, v in _fd_this(t).pairs])


async def _abort_now(t, a, i):
    signal = t.get("signal")
    if isinstance(signal, JSObject):
        signal.define_own("aborted", TRUE)
        listeners = signal.get_own("__listeners__")
        if isinstance(listeners, _Pairs):
            for _, fn in listeners.pairs:
                if isinstance(fn, JSFunction):
                    await i.call_value(fn, signal, [])
    return UNDEFINED


def _make_response(i, *, status: int, status_text: str, url: str, headers: list, body: bytes) -> JSObject:
    obj = JSObject(INTRINSICS.get("Response_prototype") or INTRINSICS["Object_prototype"])
    obj.define_own("__response__", _Response(status, status_text, url, headers, body), enumerable=False)
    return obj


class _Response:
    __slots__ = ("status", "status_text", "url", "headers", "body")

    def __init__(self, status: int, status_text: str, url: str, headers: list, body: bytes) -> None:
        self.status = status
        self.status_text = status_text
        self.url = url
        self.headers = headers
        self.body = body


def install_response_proto() -> None:
    if "Response_prototype" in INTRINSICS:
        return
    proto = JSObject(INTRINSICS["Object_prototype"])
    INTRINSICS["Response_prototype"] = proto
    _m(proto, "text", _resp_text)
    _m(proto, "json", _resp_json)
    _m(proto, "arrayBuffer", _resp_buffer)
    _m(proto, "blob", _resp_blob)
    _g(proto, "ok", lambda t, a, i: js_bool(200 <= _resp_this(t).status < 300))
    _g(proto, "status", lambda t, a, i: JSNumber(_resp_this(t).status))
    _g(proto, "statusText", lambda t, a, i: JSString(_resp_this(t).status_text))
    _g(proto, "url", lambda t, a, i: JSString(_resp_this(t).url))
    _g(proto, "headers", lambda t, a, i: _resp_headers(i, t))
    _g(proto, "redirected", lambda t, a, i: FALSE)


def _resp_this(t) -> _Response:
    if not isinstance(t, JSObject) or not isinstance(t.get_own("__response__"), _Response):
        throw_type("response member on non-response")
    return t.get_own("__response__")


async def _resp_text(t, a, i):
    p = _promise_new(i)
    p.resolve(JSString(_resp_this(t).body.decode("utf-8", "replace")))
    return p


async def _resp_json(t, a, i):
    from magpie_jsrun import to_string as _ts
    p = _promise_new(i)
    try:
        p.resolve(json_to_js(i, __import__("json").loads(_resp_this(t).body.decode("utf-8"))))
    except ValueError as e:
        p.reject(make_error_value("SyntaxError", f"bad json: {e}"))
    return p


async def _resp_buffer(t, a, i):
    data = _resp_this(t).body
    obj = JSObject(INTRINSICS["ArrayBuffer_prototype"])
    obj.define_own("__buffer__", _RawBytes(bytearray(data)), enumerable=False)
    p = _promise_new(i)
    p.resolve(obj)
    return p


async def _resp_blob(t, a, i):
    obj = JSObject(INTRINSICS["Blob_prototype"])
    obj.define_own("__blob__", _resp_this(t).body, enumerable=False)
    obj.define_own("__blob_type__", JSString(""), enumerable=False)
    p = _promise_new(i)
    p.resolve(obj)
    return p


def _resp_headers(i, t) -> JSObject:
    obj = JSObject(INTRINSICS["Headers_prototype"])
    obj.define_own("__headers__", _Headers(list(_resp_this(t).headers)), enumerable=False)
    return obj


def _xhr_this(t) -> _XHR:
    if not isinstance(t, JSObject) or not isinstance(t.get_own("__xhr__"), _XHR):
        throw_type("xhr member on non-xhr")
    return t.get_own("__xhr__")


def _xhr_fire(i, t, x: _XHR, kind: str) -> None:
    for fn in x.listeners.get(kind, []):
        if isinstance(fn, JSFunction):
            asyncio.get_running_loop().create_task(_xhr_call(i, fn, t, kind))
    prop = x.props.get("on" + kind)
    if isinstance(prop, JSFunction):
        asyncio.get_running_loop().create_task(_xhr_call(i, prop, t, kind))


async def _xhr_call(i, fn, t, kind: str) -> None:
    try:
        await i.call_value(fn, t, [js_object(i, {"type": JSString(kind), "target": t})])
    except ThrowExc:
        pass


async def _xhr_add_listener(t, a, i):
    from magpie_jsrun import to_string as _ts
    x = _xhr_this(t)
    kind = await _ts(i, a[0]) if a else ""
    if len(a) > 1 and isinstance(a[1], JSFunction):
        x.listeners.setdefault(kind, []).append(a[1])
    return UNDEFINED


async def _xhr_remove_listener(t, a, i):
    from magpie_jsrun import to_string as _ts
    x = _xhr_this(t)
    kind = await _ts(i, a[0]) if a else ""
    fn = a[1] if len(a) > 1 else UNDEFINED
    x.listeners[kind] = [f for f in x.listeners.get(kind, []) if f is not fn]
    return UNDEFINED


async def _xhr_dispatch(t, a, i):
    from magpie_jsrun import to_string as _ts
    kind = "event"
    if a and isinstance(a[0], JSObject):
        k = a[0].get("type")
        if isinstance(k, JSString):
            kind = k.value
    _xhr_fire(i, t, _xhr_this(t), kind)
    return TRUE


def _xhr_handler_prop(proto, name: str) -> None:
    async def setv(t, a, i):
        _xhr_this(t).props[name] = a[0] if a else UNDEFINED
        return UNDEFINED

    def get(t, a, i):
        return _xhr_this(t).props.get(name, NULL)

    proto.define_accessor(name, native(f"get {name}", get), native(f"set {name}", setv), enumerable=False)


def _xhr_state_prop(proto, name: str) -> None:
    def get(t, a, i):
        from magpie_jsrun import to_string as _ts
        x = _xhr_this(t)
        if name == "readyState":
            return JSNumber(x.ready)
        if name == "status":
            return JSNumber(x.status)
        if name == "statusText":
            return JSString("OK" if x.status == 200 else "")
        if name == "responseText":
            return JSString(x.body.decode("utf-8", "replace"))
        if name == "response":
            rtype = x.props.get("responseType", "")
            rtype = rtype.value if isinstance(rtype, JSString) else ""
            if rtype in ("", "text"):
                return JSString(x.body.decode("utf-8", "replace"))
            if rtype == "json":
                try:
                    return json_to_js(i, __import__("json").loads(x.body.decode("utf-8") or "null"))
                except ValueError:
                    return NULL
            return JSString(x.body.decode("utf-8", "replace"))
        if name == "responseURL":
            return JSString(x.url)
        return x.props.get(name, UNDEFINED if name in ("responseType",) else JSNumber(0) if name == "timeout" else FALSE)

    async def setv(t, a, i):
        x = _xhr_this(t)
        if name in ("responseType", "timeout"):
            x.props[name] = a[0] if a else UNDEFINED
        elif name == "withCredentials":
            x.props[name] = js_bool(to_boolean(a[0] if a else UNDEFINED))
        return UNDEFINED

    proto.define_accessor(name, native(f"get {name}", get), native(f"set {name}", setv), enumerable=False)


async def _xhr_open(t, a, i):
    from magpie_jsrun import to_string as _ts
    x = _xhr_this(t)
    x.method = (await _ts(i, a[0])).upper() if a else "GET"
    x.url = await _ts(i, a[1]) if len(a) > 1 else ""
    x.async_ = to_boolean(a[2]) if len(a) > 2 else TRUE
    x.ready = 1
    _xhr_fire(i, t, x, "readystatechange")
    return UNDEFINED


async def _xhr_set_header(t, a, i):
    from magpie_jsrun import to_string as _ts
    x = _xhr_this(t)
    x.headers.append(((await _ts(i, a[0])).lower() if a else "", await _ts(i, a[1]) if len(a) > 1 else ""))
    return UNDEFINED


async def _xhr_get_header(t, a, i):
    from magpie_jsrun import to_string as _ts
    x = _xhr_this(t)
    name = (await _ts(i, a[0])).lower() if a else ""
    vals = [v for k, v in x.resp_headers if k == name] if hasattr(x, "resp_headers") else []
    return JSString(", ".join(vals)) if vals else NULL


async def _xhr_get_all_headers(t, a, i):
    x = _xhr_this(t)
    pairs = getattr(x, "resp_headers", [])
    return JSString("".join(f"{k}: {v}\r\n" for k, v in pairs))


async def _xhr_send(t, a, i):
    from magpie_jsrun import to_string as _ts
    x = _xhr_this(t)
    body = a[0] if a else UNDEFINED
    payload = b""
    if isinstance(body, JSString):
        payload = body.value.encode("utf-8")
    elif isinstance(body, JSObject) and isinstance(body.get_own("__form__"), _Pairs):
        pairs = []
        for k, v in body.get_own("__form__").pairs:
            pairs.append((k, await _ts(i, v) if isinstance(v, JSValue) else str(v)))
        payload = urllib.parse.urlencode(pairs).encode()
    _xhr_fire(i, t, x, "loadstart")
    if _FETCHER is None:
        x.ready, x.status = 4, 0
        _xhr_fire(i, t, x, "readystatechange")
        _xhr_fire(i, t, x, "error")
        _xhr_fire(i, t, x, "loadend")
        return UNDEFINED

    async def run() -> None:
        try:
            resp = await _FETCHER(x.method, x.url, x.headers, payload)
            x.ready, x.status = 4, resp["status"]
            x.body = resp["body"]
            x.resp_headers = resp["headers"]
            _xhr_fire(i, t, x, "readystatechange")
            _xhr_fire(i, t, x, "load")
        except ThrowExc as e:
            x.ready, x.status = 4, 0
            _xhr_fire(i, t, x, "readystatechange")
            _xhr_fire(i, t, x, "error")
        _xhr_fire(i, t, x, "loadend")

    asyncio.get_running_loop().create_task(run())
    return UNDEFINED


async def _xhr_abort(t, a, i):
    x = _xhr_this(t)
    x.ready = 4
    _xhr_fire(i, t, x, "abort")
    _xhr_fire(i, t, x, "loadend")
    return UNDEFINED


# ── JSON / Math ──────────────────────────────────────────────────────────

def json_to_js(i, v):
    if v is None:
        return NULL
    if isinstance(v, bool):
        return js_bool(v)
    if isinstance(v, (int, float)):
        return JSNumber(float(v))
    if isinstance(v, str):
        return JSString(v)
    if isinstance(v, list):
        return js_array(i, [json_to_js(i, x) for x in v])
    if isinstance(v, dict):
        return js_object(i, {str(k): json_to_js(i, x) for k, x in v.items()})
    throw_type("bad json value")


def install_json_math(g: JSObject) -> None:
    JSON = JSObject(INTRINSICS["Object_prototype"])
    JSON.define_own("parse", native("parse", _json_parse), enumerable=False)
    JSON.define_own("stringify", native("stringify", _json_stringify), enumerable=False)
    g.define_own("JSON", JSON)
    INTRINSICS["JSON"] = JSON
    Math = JSObject(INTRINSICS["Object_prototype"])
    for k, v in (("E", math.e), ("LN2", math.log(2)), ("LN10", math.log(10)),
                 ("LOG2E", math.log(math.e, 2)), ("LOG10E", math.log10(math.e)),
                 ("PI", math.pi), ("SQRT1_2", math.sqrt(0.5)), ("SQRT2", math.sqrt(2))):
        Math.define_own(k, JSNumber(v), enumerable=False)
    for name, fn in (
        ("abs", _math1(abs)), ("acos", _math1(math.acos)), ("acosh", _math1(math.acosh)),
        ("asin", _math1(math.asin)), ("asinh", _math1(math.asinh)), ("atan", _math1(math.atan)),
        ("atanh", _math1(math.atanh)), ("cbrt", _math1(lambda x: math.copysign(abs(x) ** (1 / 3), x))),
        ("ceil", _math1(lambda x: float(math.ceil(x)))), ("clz32", _math_clz32),
        ("cos", _math1(math.cos)), ("cosh", _math1(math.cosh)), ("exp", _math1(math.exp)),
        ("expm1", _math1(math.expm1)), ("floor", _math1(lambda x: float(math.floor(x)))),
        ("fround", _math1(lambda x: struct.unpack("f", struct.pack("f", x))[0])),
        ("imul", _math_imul), ("log", _math1(math.log)), ("log1p", _math1(math.log1p)),
        ("log2", _math1(math.log2)), ("log10", _math1(math.log10)),
        ("round", _math1(lambda x: float(math.floor(x + 0.5)) if x == x else x)),
        ("sign", _math1(lambda x: math.nan if x != x else (0.0 if x == 0 else (1.0 if x > 0 else -1.0)))),
        ("sin", _math1(math.sin)), ("sinh", _math1(math.sinh)), ("sqrt", _math1(math.sqrt)),
        ("tan", _math1(math.tan)), ("tanh", _math1(math.tanh)), ("trunc", _math1(lambda x: float(math.trunc(x)) if x == x else x)),
        ("atan2", _math2(math.atan2)), ("hypot", _math_hypot), ("max", _math_max),
        ("min", _math_min), ("pow", _math2(math.pow)), ("random", _math_random),
    ):
        Math.define_own(name, native(name, fn), enumerable=False)
    g.define_own("Math", Math)
    INTRINSICS["Math"] = Math


async def _json_parse(t, a, i):
    from magpie_jsrun import to_string as _ts
    text = await _ts(i, a[0]) if a else ""
    reviver = a[1] if len(a) > 1 and isinstance(a[1], JSFunction) else None
    try:
        val = json.loads(text)
    except ValueError as e:
        raise ThrowExc(make_error_value("SyntaxError", f"bad json: {e}"))
    out = json_to_js(i, val)
    if reviver is not None:
        holder = js_object(i, {"": out})
        out = await _json_walk(i, reviver, holder, "")
    return out


async def _json_walk(i, reviver, holder, key: str):
    val = holder.get(key, recv=holder)
    val = await _resolve_tuple(val, i) if isinstance(val, tuple) else val
    if isinstance(val, JSObject):
        if isinstance(val, JSArray):
            for k in range(val.length()):
                child = await _json_walk(i, reviver, val, str(k))
                if child is UNDEFINED:
                    val.delete(str(k))
                else:
                    val.set(str(k), child)
        else:
            for k in val.own_keys():
                child = await _json_walk(i, reviver, val, k)
                if child is UNDEFINED:
                    val.delete(k)
                else:
                    val.set(k, child)
    return await i.call_value(reviver, holder, [key, val])


async def _json_stringify(t, a, i):
    from magpie_jsrun import to_string as _ts
    replacer = a[1] if len(a) > 1 else UNDEFINED
    space = await _ts(i, a[2]) if len(a) > 2 and a[2] is not UNDEFINED else ""
    gap = space[:10]
    seen: set[int] = []

    async def dump(v, indent: str):
        if isinstance(v, JSString):
            return json.dumps(v.value)
        if isinstance(v, JSNumber):
            return "null" if v.value != v.value or abs(v.value) == math.inf else number_to_string(v.value)
        if isinstance(v, JSBoolean):
            return "true" if v.value else "false"
        if v is NULL:
            return "null"
        if v is UNDEFINED or isinstance(v, (JSFunction, JSSymbol)):
            return None
        if isinstance(v, JSBigInt):
            throw_type("cannot stringify bigint")
        to_json = v.get("toJSON", recv=v) if isinstance(v, JSObject) else UNDEFINED
        to_json = await _resolve_tuple(to_json, i) if isinstance(to_json, tuple) else to_json
        if isinstance(to_json, JSFunction):
            return await dump(await i.call_value(to_json, v, [JSString("")]), indent)
        if id(v) in seen:
            throw_type("circular structure")
        seen.append(id(v))
        try:
            if isinstance(v, JSArray):
                items = []
                for k in range(v.length()):
                    item = v.get(str(k))
                    item = await _resolve_tuple(item, i) if isinstance(item, tuple) else item
                    s = await dump(item, indent + gap)
                    items.append(s if s is not None else "null")
                if not gap:
                    return "[" + ",".join(items) + "]"
                pad, pad2 = indent + gap, indent
                return "[\n" + ",\n".join(pad + s for s in items) + f"\n{pad2}]" if items else "[]"
            if isinstance(v, JSObject):
                keys = [k for k in v.own_keys() if not k.startswith("\0sym:")]
                if isinstance(replacer, JSArray):
                    wanted = []
                    for k in range(replacer.length()):
                        w = replacer.get(str(k))
                        if isinstance(w, JSString):
                            wanted.append(w.value)
                        elif isinstance(w, JSNumber):
                            wanted.append(number_to_string(w.value))
                    keys = [k for k in wanted if k in v.props]
                items = []
                for k in keys:
                    item = v.get(k, recv=v)
                    item = await _resolve_tuple(item, i) if isinstance(item, tuple) else item
                    if isinstance(replacer, JSFunction):
                        item = await i.call_value(replacer, v, [JSString(k), item])
                    s = await dump(item, indent + gap)
                    if s is not None:
                        items.append((k, s))
                if not gap:
                    return "{" + ",".join(f"{json.dumps(k)}:{s}" for k, s in items) + "}"
                pad = indent + gap
                return "{\n" + ",\n".join(f"{pad}{json.dumps(k)}: {s}" for k, s in items) + f"\n{indent}}}" if items else "{}"
            return None
        finally:
            seen.remove(id(v))

    root = a[0] if a else UNDEFINED
    if isinstance(replacer, JSFunction):
        holder = js_object(i, {"": root})
        root = await i.call_value(replacer, holder, [JSString(""), root])
    out = await dump(root, "")
    return JSString(out) if out is not None else UNDEFINED


def _math1(fn):
    async def handler(t, a, i):
        from magpie_jsrun import to_number as _tn
        try:
            return JSNumber(fn(await _tn(i, a[0]) if a else math.nan))
        except (ValueError, OverflowError):
            return JSNumber(math.nan)
    return handler


def _math2(fn):
    async def handler(t, a, i):
        from magpie_jsrun import to_number as _tn
        x = await _tn(i, a[0]) if a else math.nan
        y = await _tn(i, a[1]) if len(a) > 1 else math.nan
        try:
            return JSNumber(fn(x, y))
        except (ValueError, OverflowError):
            return JSNumber(math.nan)
    return handler


async def _math_clz32(t, a, i):
    from magpie_jsrun import to_number as _tn
    n = int(await _tn(i, a[0]) if a else math.nan) & 0xFFFFFFFF
    return JSNumber(32 if n == 0 else 31 - n.bit_length() + 1)


async def _math_imul(t, a, i):
    from magpie_jsrun import to_number as _tn
    x = int(await _tn(i, a[0]) if a else 0) & 0xFFFFFFFF
    y = int(await _tn(i, a[1]) if len(a) > 1 else 0) & 0xFFFFFFFF
    r = (x * y) & 0xFFFFFFFF
    return JSNumber(r - 2**32 if r >= 2**31 else r)


async def _math_hypot(t, a, i):
    from magpie_jsrun import to_number as _tn
    return JSNumber(math.hypot(*[await _tn(i, v) for v in a]))


async def _math_max(t, a, i):
    from magpie_jsrun import to_number as _tn
    if not a:
        return JSNumber(-math.inf)
    vals = [await _tn(i, v) for v in a]
    if any(v != v for v in vals):
        return JSNumber(math.nan)
    return JSNumber(max(vals))


async def _math_min(t, a, i):
    from magpie_jsrun import to_number as _tn
    if not a:
        return JSNumber(math.inf)
    vals = [await _tn(i, v) for v in a]
    if any(v != v for v in vals):
        return JSNumber(math.nan)
    return JSNumber(min(vals))


async def _math_random(t, a, i):
    return JSNumber(random.random())


# ── globals ──────────────────────────────────────────────────────────────

def install_globals(g: JSObject) -> None:
    install_response_proto()
    g.define_own("globalThis", g)
    g.define_own("undefined", UNDEFINED, enumerable=False)
    g.define_own("NaN", JSNumber(math.nan), enumerable=False)
    g.define_own("Infinity", JSNumber(math.inf), enumerable=False)
    for name, fn in (
        ("parseInt", _parse_int), ("parseFloat", _parse_float),
        ("isNaN", _global_is_nan), ("isFinite", _global_is_finite),
        ("encodeURI", _encode_uri), ("decodeURI", _decode_uri),
        ("encodeURIComponent", _encode_uri_component), ("decodeURIComponent", _decode_uri_component),
        ("escape", _escape_fn), ("unescape", _unescape_fn),
        ("queueMicrotask", _queue_microtask), ("setTimeout", _set_timeout),
        ("clearTimeout", _clear_timer), ("setInterval", _set_interval),
        ("clearInterval", _clear_timer), ("atob", _atob), ("btoa", _btoa),
        ("structuredClone", _structured_clone), ("fetch", _fetch_global),
        ("alert", _alert_fn),
    ):
        g.define_own(name, native(name, fn), enumerable=False)
    console = JSObject(INTRINSICS["Object_prototype"])
    for name in ("log", "info", "warn", "error", "debug", "trace"):
        console.define_own(name, native(name, _console_fn_sync(name)), enumerable=False)
    console.define_own("assert", native("assert", _console_assert), enumerable=False)
    console.define_own("count", native("count", _console_count), enumerable=False)
    console.define_own("time", native("time", _console_time), enumerable=False)
    console.define_own("timeEnd", native("timeEnd", _console_time_end), enumerable=False)
    g.define_own("console", console)
    INTRINSICS["console"] = console
    perf = JSObject(INTRINSICS["Object_prototype"])
    perf.define_own("timeOrigin", JSNumber(time.time() * 1000.0), enumerable=False)
    perf.define_own("now", native("now", lambda t, a, i: JSNumber((time.monotonic() - _t0) * 1000.0)), enumerable=False)
    g.define_own("performance", perf)
    crypto = JSObject(INTRINSICS["Object_prototype"])
    crypto.define_own("getRandomValues", native("getRandomValues", _crypto_random), enumerable=False)
    crypto.define_own("randomUUID", native("randomUUID", lambda t, a, i: JSString(str(uuid.uuid4()))), enumerable=False)
    g.define_own("crypto", crypto)


_t0 = time.monotonic()


async def _global_is_nan(t, a, i):
    from magpie_jsrun import to_number as _tn
    return js_bool((await _tn(i, a[0]) if a else math.nan) != (await _tn(i, a[0]) if a else math.nan))


async def _global_is_finite(t, a, i):
    from magpie_jsrun import to_number as _tn
    v = await _tn(i, a[0]) if a else math.nan
    return js_bool(v == v and abs(v) != math.inf)


_UNRESERVED = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.!~*'()"


async def _encode_uri(t, a, i):
    from magpie_jsrun import to_string as _ts
    s = await _ts(i, a[0]) if a else "undefined"
    return JSString(urllib.parse.quote(s, safe=";,/?:@&=+$-_.!~*'()#"))


async def _encode_uri_component(t, a, i):
    from magpie_jsrun import to_string as _ts
    s = await _ts(i, a[0]) if a else "undefined"
    return JSString(urllib.parse.quote(s, safe="!'()*-._~"))


async def _decode_uri(t, a, i):
    from magpie_jsrun import to_string as _ts
    try:
        return JSString(urllib.parse.unquote(await _ts(i, a[0]) if a else ""))
    except ValueError:
        raise ThrowExc(make_error_value("URIError", "bad escape"))


async def _decode_uri_component(t, a, i):
    return await _decode_uri(t, a, i)


async def _escape_fn(t, a, i):
    from magpie_jsrun import to_string as _ts
    s = await _ts(i, a[0]) if a else "undefined"
    out = []
    for ch in s:
        o = ord(ch)
        if ch.isalnum() or ch in "@*_+-./":
            out.append(ch)
        elif o < 256:
            out.append(f"%{o:02X}")
        else:
            out.append(f"%u{o:04X}")
    return JSString("".join(out))


async def _unescape_fn(t, a, i):
    from magpie_jsrun import to_string as _ts
    s = await _ts(i, a[0]) if a else "undefined"
    s = re.sub(r"%u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s)
    return JSString(urllib.parse.unquote(s))


async def _queue_microtask(t, a, i):
    if a and isinstance(a[0], JSFunction):
        fn = a[0]

        async def run() -> None:
            try:
                await i.call_value(fn, UNDEFINED, [])
            except ThrowExc:
                pass

        asyncio.get_running_loop().create_task(run())
    return UNDEFINED


def _events(i):
    if i.events is None:
        i.events = EventState()
    return i.events


async def _set_timeout(t, a, i, *, repeat: float = 0.0):
    from magpie_jsrun import to_number as _tn
    ev = _events(i)
    fn = a[0] if a else UNDEFINED
    ms = await _tn(i, a[1]) if len(a) > 1 and a[1] is not UNDEFINED else 0
    extra = list(a[2:])
    if isinstance(fn, JSString):
        src = fn.value
        code = parse_source(src, name="<timeout>")

        async def run_src() -> None:
            try:
                scope = Environment(i.global_env(), var_scope=False)
                await i.run_program(code, scope)
            except ThrowExc:
                pass

        cb = run_src
    elif isinstance(fn, JSFunction):
        async def run_fn() -> None:
            try:
                await i.call_value(fn, i.global_obj, extra)
            except ThrowExc:
                pass

        cb = run_fn
    else:
        throw_type("timeout needs a function")
    delay = max(0.0, ms) / 1000.0
    return JSNumber(ev.add_timer(time.monotonic() + delay, cb, repeat=(max(0.0, ms) / 1000.0 if repeat else 0.0)))


async def _set_interval(t, a, i):
    from magpie_jsrun import to_number as _tn
    ms = await _tn(i, a[1]) if len(a) > 1 and a[1] is not UNDEFINED else 0
    return await _set_timeout(t, a, i, repeat=max(0.001, ms / 1000.0))


async def _clear_timer(t, a, i):
    from magpie_jsrun import to_number as _tn
    if a and a[0] is not UNDEFINED:
        _events(i).cancel(int(await _tn(i, a[0])))
    return UNDEFINED


async def _atob(t, a, i):
    from magpie_jsrun import to_string as _ts
    try:
        raw = base64.b64decode(await _ts(i, a[0]) if a else "", validate=False)
    except binascii.Error:
        raise ThrowExc(make_error_value("Error", "bad base64"))
    try:
        return JSString(raw.decode("latin-1"))
    except UnicodeError:
        raise ThrowExc(make_error_value("Error", "bad base64"))


async def _btoa(t, a, i):
    from magpie_jsrun import to_string as _ts
    s = await _ts(i, a[0]) if a else ""
    try:
        raw = s.encode("latin-1")
    except UnicodeError:
        raise ThrowExc(make_error_value("Error", "latin-1 only"))
    return JSString(base64.b64encode(raw).decode("ascii"))


async def _structured_clone(t, a, i):
    memo: dict[int, JSValue] = {}

    def clone(v):
        if isinstance(v, (JSString, JSNumber, JSBoolean, JSBigInt, JSNull, JSUndefined)):
            return v
        if isinstance(v, JSSymbol):
            throw_type("cannot clone symbol")
        if isinstance(v, JSFunction):
            throw_type("cannot clone function")
        if id(v) in memo:
            return memo[id(v)]
        if isinstance(v, JSArray):
            out = JSArray(INTRINSICS["Array_prototype"])
            memo[id(v)] = out
            for k in range(v.length()):
                out.set(str(k), clone(v.get(str(k))))
            out.set_length(v.length())
            return out
        if isinstance(v, JSObject):
            if isinstance(v, JSMap):
                out = JSMap(INTRINSICS["Map_prototype"])
                memo[id(v)] = out
                for k, item in v.pairs:
                    out.pairs.append((clone(k), clone(item)))
                return out
            if isinstance(v, JSSet):
                out = JSSet(INTRINSICS["Set_prototype"])
                memo[id(v)] = out
                out.items.extend(clone(x) for x in v.items)
                return out
            raw = v.get_own("__buffer__")
            if isinstance(raw, _RawBytes):
                out = JSObject(INTRINSICS["ArrayBuffer_prototype"])
                memo[id(v)] = out
                out.define_own("__buffer__", _RawBytes(bytearray(raw.data)), enumerable=False)
                return out
            if v.get_own("__date__") is not UNDEFINED:
                out = JSObject(INTRINSICS["Date_prototype"])
                memo[id(v)] = out
                out.define_own("__date__", JSNumber(v.get_own("__date__").value), enumerable=False)
                return out
            if v.get_own("__regexp__") is not UNDEFINED:
                return make_regexp(v.get_own("__regexp__").value, v.get_own("__regexp_flags__").value)
            out = JSObject(INTRINSICS["Object_prototype"])
            memo[id(v)] = out
            for k in v.own_keys():
                out.define_own(k, clone(v.get_own(k)))
            return out
        throw_type("cannot clone value")

    return clone(a[0] if a else UNDEFINED)


async def _fetch_global(t, a, i):
    from magpie_jsrun import to_string as _ts
    if _FETCHER is None:
        p = _promise_new(i)
        p.reject(make_error_value("Error", "network is not wired here"))
        return p
    url = await _ts(i, a[0]) if a else ""
    init = a[1] if len(a) > 1 and isinstance(a[1], JSObject) else None
    method, headers, body, signal = "GET", [], b"", None
    if init is not None:
        m = init.get("method")
        if isinstance(m, JSString):
            method = m.value.upper()
        h = init.get("headers")
        if isinstance(h, JSObject) and isinstance(h.get_own("__headers__"), _Headers):
            headers = list(h.get_own("__headers__").pairs)
        elif isinstance(h, JSObject):
            for k in enum_keys(h):
                vv = h.get(k, recv=h)
                vv = await _resolve_tuple(vv, i) if isinstance(vv, tuple) else vv
                headers.append((k.lower(), await _ts(i, vv)))
        b = init.get("body")
        if isinstance(b, JSString):
            body = b.value.encode("utf-8")
        elif isinstance(b, JSObject) and isinstance(b.get_own("__form__"), _Pairs):
            pairs = []
            for k, v in b.get_own("__form__").pairs:
                pairs.append((k, await _ts(i, v) if isinstance(v, JSValue) else str(v)))
            body = urllib.parse.urlencode(pairs).encode()
            headers.append(("content-type", "application/x-www-form-urlencoded;charset=UTF-8"))
        s = init.get("signal")
        if isinstance(s, JSObject):
            signal = s
    p = _promise_new(i)

    async def run() -> None:
        try:
            if signal is not None and signal.get("aborted") is TRUE:
                p.reject(make_error_value("AbortError", "aborted"))
                return
            resp = await _FETCHER(method, url, headers, body)
            p.resolve(_make_response(i, status=resp["status"], status_text=resp.get("status_text", ""),
                                     url=resp.get("url", url), headers=resp.get("headers", []), body=resp.get("body", b"")))
        except ThrowExc as e:
            p.reject(e.value)
        except Exception as e:
            p.reject(make_error_value("TypeError", f"fetch failed: {e}"))

    asyncio.get_running_loop().create_task(run())
    return p


async def _alert_fn(t, a, i):
    from magpie_jsrun import to_string as _ts
    msg = await _ts(i, a[0]) if a else ""
    if callable(i.options.on_alert):
        i.options.on_alert(msg)
    else:
        i.console_lines.append(f"[alert] {msg}")
    return UNDEFINED


def _console_fn_sync(name: str):
    # Native methods must be plain callables; async work happens in call_value.
    async def handler(t, a, i):
        from magpie_jsrun import to_string as _ts
        line = " ".join(await _ts(i, v) for v in a)
        i.console_lines.append(f"[{name}] {line}" if name != "log" else line)
        return UNDEFINED
    return handler


async def _console_assert(t, a, i):
    from magpie_jsrun import to_string as _ts
    if not a or not to_boolean(a[0]):
        i.console_lines.append("[assert] " + " ".join(await _ts(i, v) for v in a[1:]))
    return UNDEFINED


_console_counts: dict[str, int] = {}


async def _console_count(t, a, i):
    from magpie_jsrun import to_string as _ts
    label = await _ts(i, a[0]) if a and a[0] is not UNDEFINED else "default"
    _console_counts[label] = _console_counts.get(label, 0) + 1
    i.console_lines.append(f"{label}: {_console_counts[label]}")
    return UNDEFINED


_console_times: dict[str, float] = {}


async def _console_time(t, a, i):
    from magpie_jsrun import to_string as _ts
    _console_times[await _ts(i, a[0]) if a and a[0] is not UNDEFINED else "default"] = time.monotonic()
    return UNDEFINED


async def _console_time_end(t, a, i):
    from magpie_jsrun import to_string as _ts
    label = await _ts(i, a[0]) if a and a[0] is not UNDEFINED else "default"
    start = _console_times.pop(label, None)
    i.console_lines.append(f"{label}: {(time.monotonic() - start) * 1000:.2f}ms" if start else f"{label}: no timer")
    return UNDEFINED


async def _crypto_random(t, a, i):
    v = a[0] if a else UNDEFINED
    if not isinstance(v, JSObject) or not isinstance(v.get_own("__typed__"), _Typed):
        throw_type("getRandomValues needs a typed array")
    info = v.get_own("__typed__")
    if info.kind not in ("int", "uint", "clamp"):
        throw_type("getRandomValues needs an integer array")
    rand = random.randbytes(info.length * info.size)
    info.buf[info.off:info.off + info.length * info.size] = rand
    _typed_refresh(v)
    return v


# ── run helpers ──────────────────────────────────────────────────────────

async def drain_timers(interp, *, budget_ms: float = 2000.0) -> None:
    deadline = time.monotonic() + budget_ms / 1000.0
    ev = _events(interp)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    while time.monotonic() < deadline:
        await asyncio.sleep(0)
        now = time.monotonic()
        due = []
        rest = []
        for item in ev.timers:
            when, tid, cb, args, repeat = item
            if tid in ev.cancelled:
                continue
            if when <= now:
                due.append(item)
            else:
                rest.append(item)
        ev.timers = rest
        if not due:
            if not rest:
                break
            nxt = min(w for w, _, _, _, _ in rest)
            await asyncio.sleep(max(0.0, min(nxt - time.monotonic(), deadline - time.monotonic(), 0.5)))
            continue
        for when, tid, cb, args, repeat in sorted(due, key=lambda r: r[1]):
            if tid in ev.cancelled:
                continue
            try:
                out = cb()
                if asyncio.iscoroutine(out):
                    await out
            except ThrowExc as e:
                interp.console_lines.append(f"[timer error] {e.value}")
            except Exception as e:
                interp.console_lines.append(f"[timer bug] {e}")
            if repeat and tid not in ev.cancelled:
                ev.add_timer(time.monotonic() + repeat, cb, args=args, repeat=repeat)


def create_sandbox(options=None, *, extra: dict | None = None):
    from magpie_jsrun import Interpreter as _Interp, JSOptions as _Opts
    opts = options or _Opts()
    g = JSObject(None)
    install_builtins(g)
    g.proto = INTRINSICS["Object_prototype"]
    interp = _Interp(g, opts)
    from magpie_jsval import Environment as _Env
    env = _Env(None, var_scope=True, obj=g)
    env.is_global = True
    env.global_obj = g
    env.record["__global__"] = {"kind": "var", "value": g, "init": True}
    interp.global_env = lambda: env
    if extra:
        for k, v in extra.items():
            g.define_own(k, v)
    return interp, g, env


async def evaluate(source: str, *, name: str = "<test>", options=None, extra: dict | None = None, module: bool = False, timer_ms: float = 1500.0):
    interp, g, env = create_sandbox(options, extra=extra)
    if interp.events is None:
        interp.events = EventState()
    program = parse_source(source, name=name, module=module)
    if not module and program[1] and program[1][0][0] == "expr" and program[1][0][1][0] == "str" and program[1][0][1][1] == "use strict":
        env.strict = True
    exports = {} if module else None
    try:
        await asyncio.wait_for(interp.run_program(program, env, module_exports=exports), timeout=10.0)
    except asyncio.TimeoutError:
        raise ThrowExc(make_error_value("RangeError", "script timed out"))
    await drain_timers(interp, budget_ms=timer_ms)
    return interp, g, env, exports
