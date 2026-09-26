#!/usr/bin/env python3
"""magpie_jsval — JavaScript value model, scopes, and primitive conversions.

No user code ever runs here: anything that could invoke a getter, setter,
``valueOf``/``toString`` or a ``then`` method lives in ``magpie_jsrun`` as an
async helper. This module stays synchronous and structural.
"""
from __future__ import annotations

import asyncio
import math
import re


class ReturnExc(Exception):
    def __init__(self, value) -> None:
        self.value = value


class ThrowExc(Exception):
    def __init__(self, value) -> None:
        self.value = value


class BreakExc(Exception):
    def __init__(self, label) -> None:
        self.label = label


class ContinueExc(Exception):
    def __init__(self, label) -> None:
        self.label = label


class JSValue:
    def type_of(self) -> str:
        return "object"


class JSUndefined(JSValue):
    def type_of(self) -> str:
        return "undefined"


class JSNull(JSValue):
    def type_of(self) -> str:
        return "object"


UNDEFINED = JSUndefined()
NULL = JSNull()


class JSBoolean(JSValue):
    __slots__ = ("value",)

    def __init__(self, value: bool) -> None:
        self.value = bool(value)

    def type_of(self) -> str:
        return "boolean"


TRUE = JSBoolean(True)
FALSE = JSBoolean(False)


def js_bool(v: bool) -> JSBoolean:
    return TRUE if v else FALSE


class JSNumber(JSValue):
    __slots__ = ("value",)

    def __init__(self, value: float) -> None:
        self.value = float(value)

    def type_of(self) -> str:
        return "number"


class JSBigInt(JSValue):
    __slots__ = ("value",)

    def __init__(self, value: int) -> None:
        self.value = int(value)

    def type_of(self) -> str:
        return "bigint"


class JSString(JSValue):
    __slots__ = ("value",)

    def __init__(self, value: str) -> None:
        self.value = str(value)

    def type_of(self) -> str:
        return "string"


class JSSymbol(JSValue):
    __slots__ = ("desc", "key")

    def __init__(self, desc: str = "", *, key: str = "") -> None:
        self.desc = desc
        self.key = key

    def type_of(self) -> str:
        return "symbol"


class JSObject(JSValue):
    __slots__ = ("props", "proto", "extensible", "private_slots")

    def __init__(self, proto: JSValue | None = None) -> None:
        self.props: dict[str, dict] = {}
        self.proto = proto
        self.extensible = True
        self.private_slots: dict[tuple[int, str], JSValue] = {}

    def type_of(self) -> str:
        return "object"

    def own_desc(self, key: str) -> dict | None:
        return self.props.get(key)

    def get_own(self, key: str) -> JSValue:
        d = self.props.get(key)
        if d is None:
            return UNDEFINED
        if d.get("get") is not None or d.get("set") is not None:
            return UNDEFINED
        return d.get("value", UNDEFINED)

    def get(self, key: str, recv: JSValue | None = None):
        """Raw lookup. Accessor getters return ('__call__', fn, recv, args)."""
        obj: JSValue | None = self
        recv = self if recv is None else recv
        while isinstance(obj, JSObject):
            d = obj.props.get(key)
            if d is not None:
                if d.get("get") is not None:
                    getter = d["get"]
                    if getter is None:
                        return UNDEFINED
                    return ("__call__", getter, recv, [])
                return d.get("value", UNDEFINED)
            obj = obj.proto
        return UNDEFINED

    def set(self, key: str, value: JSValue, recv: JSValue | None = None):
        """Raw store. Accessor setters return ('__call__', fn, recv, args)."""
        recv = self if recv is None else recv
        obj: JSValue | None = self
        while isinstance(obj, JSObject):
            d = obj.props.get(key)
            if d is not None:
                if d.get("get") is not None or d.get("set") is not None:
                    setter = d.get("set")
                    if setter is None:
                        return False
                    return ("__call__", setter, recv, [value])
                if not d.get("writable", True):
                    return False
                if obj is self:
                    d["value"] = value
                    return True
                break
            obj = obj.proto
        return self.define_own(key, value)

    def define_own(self, key: str, value: JSValue, *, writable=True, enumerable=True, configurable=True) -> bool:
        if key in self.props and not self.props[key].get("configurable", True):
            old = self.props[key]
            if old.get("get") is not None or old.get("set") is not None:
                return False
            self.props[key] = {
                "value": value, "writable": old.get("writable", True),
                "enumerable": old.get("enumerable", True), "configurable": False,
                "get": None, "set": None,
            }
            return True
        if key not in self.props and not self.extensible:
            return False
        self.props[key] = {
            "value": value, "writable": writable, "enumerable": enumerable,
            "configurable": configurable, "get": None, "set": None,
        }
        return True

    def define_accessor(self, key: str, getter, setter, *, enumerable=True, configurable=True) -> bool:
        if key in self.props and not self.props[key].get("configurable", True):
            return False
        if key not in self.props and not self.extensible:
            return False
        self.props[key] = {
            "value": UNDEFINED, "writable": False, "enumerable": enumerable,
            "configurable": configurable, "get": getter, "set": setter,
        }
        return True

    def delete(self, key: str) -> bool:
        d = self.props.get(key)
        if d is None:
            return True
        if not d.get("configurable", True):
            return False
        del self.props[key]
        return True

    def own_keys(self) -> list[str]:
        return list(self.props.keys())


class JSArray(JSObject):
    __slots__ = ()

    def __init__(self, proto: JSValue | None = None) -> None:
        super().__init__(proto)
        self.props["length"] = {
            "value": JSNumber(0), "writable": True, "enumerable": False,
            "configurable": False, "get": None, "set": None,
        }

    def length(self) -> int:
        v = self.props["length"]["value"]
        return int(v.value) if isinstance(v, JSNumber) else 0

    def set_length(self, n: int) -> None:
        n = max(0, n)
        for k in [k for k in self.props if k.isdigit() and int(k) >= n]:
            del self.props[k]
        self.props["length"]["value"] = JSNumber(n)


class JSFunction(JSObject):
    __slots__ = ("kind", "node", "env", "this_mode", "is_async", "handler", "name", "length", "home", "bound_this", "bound_args", "class_info", "interp")

    def __init__(self, *, kind="interpreted", proto=None) -> None:
        super().__init__(proto)
        self.kind = kind
        self.node = None
        self.env = None
        self.this_mode = "sloppy"
        self.is_async = False
        self.handler = None
        self.name = ""
        self.length = 0
        self.home = None
        self.bound_this = None
        self.bound_args: list = []
        self.class_info = None
        self.interp = None


class JSPromise(JSObject):
    """Promise with interpreter-bound dispatch for interpreted handlers."""

    __slots__ = ("state", "value", "handlers", "interp")

    def __init__(self, interp=None) -> None:
        super().__init__(INTRINSICS.get("Promise_prototype"))
        self.state = 0
        self.value: JSValue = UNDEFINED
        self.handlers: list = []
        self.interp = interp

    def type_of(self) -> str:
        return "object"

    def then(self, on_fulfilled, on_rejected):
        nxt = JSPromise(self.interp)
        self.handlers.append((on_fulfilled, on_rejected, nxt))
        if self.state != 0:
            self._schedule()
        return nxt

    def _schedule(self) -> None:
        handlers, self.handlers = self.handlers, []
        if not handlers:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is None or self.interp is None:
            # No driver: settle synchronously for native-only chains.
            for on_f, on_r, nxt in handlers:
                try:
                    if self.state == 1:
                        nxt.resolve(on_f(self.value) if on_f is not None else self.value)
                    else:
                        if on_r is None:
                            nxt.reject(self.value)
                        else:
                            nxt.resolve(on_r(self.value))
                except ThrowExc as e:
                    nxt.reject(e.value)
                except Exception as e:
                    nxt.reject(JSString(f"promise job failed: {e}"))
            return
        for on_f, on_r, nxt in handlers:
            loop.call_soon(self._dispatch_one, on_f, on_r, nxt)

    def _dispatch_one(self, on_f, on_r, nxt) -> None:
        interp = self.interp

        async def run() -> None:
            try:
                if self.state == 1:
                    handler = on_f
                    if handler is None:
                        if nxt is not None:
                            nxt.resolve(self.value)
                        return
                    if isinstance(handler, JSFunction):
                        out = await interp.call_value(handler, UNDEFINED, [self.value])
                    else:
                        out = handler(self.value)
                    if nxt is not None:
                        nxt.resolve(out)
                else:
                    handler = on_r
                    if handler is None:
                        if nxt is not None:
                            nxt.reject(self.value)
                        return
                    if isinstance(handler, JSFunction):
                        out = await interp.call_value(handler, UNDEFINED, [self.value])
                    else:
                        out = handler(self.value)
                    if nxt is not None:
                        nxt.resolve(out)
            except ThrowExc as e:
                if nxt is not None:
                    nxt.reject(e.value)
            except Exception as e:
                if nxt is not None:
                    nxt.reject(JSString(f"promise job failed: {e}"))

        if interp is None:
            try:
                if self.state == 1:
                    if on_f is None:
                        if nxt is not None:
                            nxt.resolve(self.value)
                    elif isinstance(on_f, JSFunction):
                        if nxt is not None:
                            nxt.resolve(self.value)
                    else:
                        out = on_f(self.value)
                        if nxt is not None:
                            nxt.resolve(out)
                else:
                    if on_r is None:
                        if nxt is not None:
                            nxt.reject(self.value)
                    elif isinstance(on_r, JSFunction):
                        if nxt is not None:
                            nxt.reject(self.value)
                    else:
                        out = on_r(self.value)
                        if nxt is not None:
                            nxt.resolve(out)
            except ThrowExc as e:
                if nxt is not None:
                    nxt.reject(e.value)
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is None:
            return
        loop.create_task(run())

    def resolve(self, value) -> None:
        if self.state != 0:
            return
        if value is self:
            self.reject(JSString("promise resolved with itself"))
            return
        if isinstance(value, JSPromise):
            if value.state == 0:
                value.handlers.append((self.resolve, self.reject, None))
            elif value.state == 1:
                self.resolve(value.value)
            else:
                self.reject(value.value)
            return
        if isinstance(value, JSObject):
            then = value.get("then")
            if isinstance(then, JSFunction) and self.interp is not None:
                interp = self.interp

                async def adopt() -> None:
                    try:
                        out = await interp.call_value(then, value, [
                            _callback(self.resolve), _callback_arg(self.reject),
                        ])
                        _ = out
                    except ThrowExc as e:
                        self.reject(e.value)
                    except Exception as e:
                        self.reject(JSString(f"thenable failed: {e}"))

                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                if loop is not None:
                    loop.create_task(adopt())
                    return
        self.state = 1
        self.value = value
        self._schedule()

    def reject(self, reason) -> None:
        if self.state != 0:
            return
        self.state = 2
        self.value = reason if isinstance(reason, JSValue) else JSString(str(reason))
        self._schedule()

    def __await__(self):
        async def wait():
            if self.state == 1:
                return self.value
            if self.state == 2:
                raise ThrowExc(self.value)
            loop = asyncio.get_running_loop()
            fut = loop.create_future()

            def settle() -> None:
                if fut.done():
                    return
                if self.state == 1:
                    fut.set_result(self.value)
                elif self.state == 2:
                    fut.set_result(("__throw__", self.value))

            self.handlers.append((lambda v: settle(), lambda e: settle(), None))
            out = await fut
            if isinstance(out, tuple) and out and out[0] == "__throw__":
                raise ThrowExc(out[1])
            return out

        return wait().__await__()


def _callback(fn):
    from magpie_jsval import JSFunction as _F  # local: same module, explicit
    del _F
    return fn


def _callback_arg(fn):
    return fn


INTRINSICS: dict[str, JSValue] = {}


def schedule_microtask(job) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        job()
        return
    loop.call_soon(job)


def to_boolean(v: JSValue) -> bool:
    if v is UNDEFINED or v is NULL:
        return False
    if isinstance(v, JSBoolean):
        return v.value
    if isinstance(v, JSNumber):
        return v.value != 0 and v.value == v.value
    if isinstance(v, JSBigInt):
        return v.value != 0
    if isinstance(v, JSString):
        return len(v.value) > 0
    return True


def str_to_number(s: str) -> float:
    t = s.strip()
    if not t:
        return 0.0
    low = t.lower()
    if low in ("infinity", "+infinity"):
        return math.inf
    if low == "-infinity":
        return -math.inf
    try:
        if re.fullmatch(r"[+-]?0[xX][0-9a-fA-F]+", t):
            return float(int(t, 16))
        if re.fullmatch(r"[+-]?0[bB][01]+", t):
            return float(int(t, 2))
        if re.fullmatch(r"[+-]?0[oO][0-7]+", t):
            return float(int(t, 8))
        return float(t)
    except ValueError:
        return math.nan


def number_to_string(x: float) -> str:
    if x != x:
        return "NaN"
    if x == math.inf:
        return "Infinity"
    if x == -math.inf:
        return "-Infinity"
    if x == 0:
        return "0"
    if x.is_integer() and abs(x) < 1e21:
        return str(int(x))
    r = repr(x)
    m = re.fullmatch(r"(-?)(\d)(?:\.(\d+))?[eE]([+-]?\d+)", r)
    if m:
        exp = int(m.group(4))
        digits = m.group(2) + (m.group(3) or "")
        frac = (digits[1:] or "0").rstrip("0") or "0"
        return f"{m.group(1)}{digits[0]}.{frac}e{exp:+d}".replace("e+", "e+")
    return r


def to_number_primitive(v: JSValue) -> float:
    if isinstance(v, JSNumber):
        return v.value
    if v is UNDEFINED:
        return math.nan
    if v is NULL:
        return 0.0
    if isinstance(v, JSBoolean):
        return 1.0 if v.value else 0.0
    if isinstance(v, JSBigInt):
        return float(v.value)
    if isinstance(v, JSString):
        return str_to_number(v.value)
    raise ThrowExc(make_error_value("TypeError", "object needs coercion"))


def to_string_primitive(v: JSValue) -> str:
    if isinstance(v, JSString):
        return v.value
    if isinstance(v, JSNumber):
        return number_to_string(v.value)
    if isinstance(v, JSBoolean):
        return "true" if v.value else "false"
    if v is UNDEFINED:
        return "undefined"
    if v is NULL:
        return "null"
    if isinstance(v, JSBigInt):
        return str(v.value)
    raise ThrowExc(make_error_value("TypeError", "object needs coercion"))


def to_int32_primitive(v: JSValue) -> int:
    n = to_number_primitive(v)
    if n != n or n in (math.inf, -math.inf) or n == 0:
        return 0
    n = math.trunc(n) % 2**32
    return int(n - 2**32 if n >= 2**31 else n)


def to_length_primitive(v: JSValue) -> int:
    n = to_number_primitive(v)
    if n != n or n <= 0:
        return 0
    return min(2**53 - 1, int(math.trunc(n)))


def same_value_zero(a: JSValue, b: JSValue) -> bool:
    if type(a) is not type(b):
        return False
    if isinstance(a, JSNumber):
        if a.value != a.value and b.value != b.value:
            return True
        return a.value == b.value
    if isinstance(a, JSString):
        return a.value == b.value
    if isinstance(a, JSBoolean):
        return a.value == b.value
    if isinstance(a, JSBigInt):
        return a.value == b.value
    return a is b


def strict_equal(a: JSValue, b: JSValue) -> bool:
    if type(a) is not type(b):
        return False
    if isinstance(a, JSNumber):
        if a.value != a.value or b.value != b.value:
            return False
        return a.value == b.value
    return same_value_zero(a, b)


def prop_exists(obj: JSObject, key: str) -> bool:
    cur: JSValue | None = obj
    while isinstance(cur, JSObject):
        if key in cur.props:
            return True
        cur = cur.proto
    return False


def enum_keys(v: JSValue) -> list[str]:
    if isinstance(v, JSObject):
        out: list[str] = []
        seen: set[str] = set()
        cur: JSValue | None = v
        while isinstance(cur, JSObject):
            for k, d in cur.props.items():
                if k not in seen and d.get("enumerable", True):
                    seen.add(k)
                    out.append(k)
            cur = cur.proto
        return out
    if v is UNDEFINED or v is NULL:
        return []
    return []


class Environment:
    def __init__(self, parent: Environment | None = None, *, var_scope: bool = False, strict: bool = False, obj: JSObject | None = None) -> None:
        self.parent = parent
        self.var_scope = var_scope
        self.strict = strict
        self.obj = obj
        self.record: dict[str, dict] = {}
        self.is_global = False
        self.global_obj: JSObject | None = None

    def _mirror(self, scope_env, name: str, value: JSValue) -> None:
        target = scope_env.var_env()
        if target.is_global and target.global_obj is not None:
            cell = target.record.get(name)
            if cell is not None and cell["kind"] == "var":
                target.global_obj.define_own(name, value)

    def var_env(self) -> Environment:
        env = self
        while env is not None and not env.var_scope:
            env = env.parent
        return env or self

    def declare(self, kind: str, name: str) -> None:
        if kind == "var":
            self.var_env().record.setdefault(name, {"kind": "var", "value": UNDEFINED, "init": True})
        else:
            if name in self.record:
                raise ThrowExc(make_error_value("SyntaxError", f"duplicate declaration {name}"))
            self.record[name] = {"kind": kind, "value": UNDEFINED, "init": False}

    def initialize(self, name: str, value: JSValue) -> None:
        env: Environment | None = self
        while env is not None:
            if name in env.record:
                env.record[name]["value"] = value
                env.record[name]["init"] = True
                self._mirror(env, name, value)
                return
            env = env.parent
        self.var_env().record[name] = {"kind": "var", "value": value, "init": True}
        self._mirror(self, name, value)

    def raw_get(self, name: str):
        """Declarative lookup only; object scopes handled by the driver."""
        env: Environment | None = self
        while env is not None:
            if env.obj is None and name in env.record:
                cell = env.record[name]
                if not cell["init"]:
                    raise ThrowExc(make_error_value("ReferenceError", f"{name} is not initialized"))
                return cell["value"]
            env = env.parent
        return None

    def raw_set(self, name: str, value: JSValue, *, strict: bool) -> bool:
        env: Environment | None = self
        while env is not None:
            if env.obj is None and name in env.record:
                cell = env.record[name]
                if not cell["init"]:
                    raise ThrowExc(make_error_value("ReferenceError", f"{name} is not initialized"))
                if cell["kind"] == "const":
                    raise ThrowExc(make_error_value("TypeError", f"cannot reassign {name}"))
                cell["value"] = value
                return True
            env = env.parent
        return False


def make_error_value(name: str, message: str = "") -> JSValue:
    proto = INTRINSICS.get(name + "_prototype", INTRINSICS.get("Error_prototype"))
    if proto is None:
        return JSString(f"{name}: {message}")
    obj = JSObject(proto)
    obj.define_own("name", JSString(name), enumerable=False)
    obj.define_own("message", JSString(message), enumerable=False)
    return obj
