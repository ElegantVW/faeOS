#!/usr/bin/env python3
"""magpie_jsrun — Magpie's async JavaScript interpreter core (stdlib-only)."""
from __future__ import annotations

import asyncio
import math
import time

from magpie_jsparse import Parser, parse_source
from magpie_jsval import (
    BreakExc, ContinueExc, Environment, FALSE, INTRINSICS, JSArray, JSBigInt,
    JSBoolean, JSFunction, JSNull, JSNumber, JSObject, JSString, JSSymbol,
    JSUndefined, JSValue, NULL, ReturnExc, ThrowExc, TRUE, UNDEFINED,
    enum_keys, js_bool, make_error_value, number_to_string,
    prop_exists, same_value_zero, strict_equal, str_to_number,
    to_boolean, to_length_primitive, to_number_primitive, to_string_primitive,
)


BUDGET_OPS = 4_000_000
BUDGET_MS = 6000

_SYM_REGISTRY: dict[int, JSSymbol] = {}


def js_array_of(interp, *items) -> JSArray:
    arr = JSArray(INTRINSICS["Array_prototype"])
    for item in items:
        arr.set(str(arr.length()), item)
        arr.set_length(arr.length() + 1)
    return arr


async def prop_key(v: JSValue, interp) -> str:
    if isinstance(v, JSSymbol):
        if v.key:
            return v.key
        _SYM_REGISTRY[id(v)] = v
        return f"\0sym:{id(v)}"
    if isinstance(v, JSObject):
        return await to_string(interp, v)
    return to_string_primitive(v)


class JSOptions:
    def __init__(self, **kw) -> None:
        self.budget_ops = kw.get("budget_ops", BUDGET_OPS)
        self.budget_ms = kw.get("budget_ms", BUDGET_MS)
        self.module_loader = kw.get("module_loader")
        self.console = kw.get("console")
        self.on_alert = kw.get("on_alert")


def box_primitive(v: JSValue) -> JSObject:
    if isinstance(v, JSObject):
        return v
    obj = JSObject(INTRINSICS["Object_prototype"])
    if isinstance(v, JSString):
        obj.proto = INTRINSICS["String_prototype"]
        for i, ch in enumerate(v.value):
            obj.define_own(str(i), JSString(ch), enumerable=False)
        obj.define_own("length", JSNumber(len(v.value)), enumerable=False)
    elif isinstance(v, JSNumber):
        obj.proto = INTRINSICS["Number_prototype"]
    elif isinstance(v, JSBoolean):
        obj.proto = INTRINSICS["Boolean_prototype"]
    return obj


async def resolve_call(t, interp):
    _, fn, recv, args = t
    return await interp.call_value(fn, recv, args)


async def prop_get(interp, base: JSValue, key: str):
    if base is UNDEFINED or base is NULL:
        raise ThrowExc(make_error_value("TypeError", f"cannot read {key!r} of {to_string_primitive(base)}"))
    if key.startswith("# "):
        return interp.get_private(base, key[2:])
    boxed = box_primitive(base)
    v = boxed.get(key, recv=base if isinstance(base, JSObject) else boxed)
    if isinstance(v, tuple):
        return await resolve_call(v, interp)
    return v


async def prop_set(interp, base: JSValue, key: str, value: JSValue, *, strict: bool) -> None:
    if key.startswith("# "):
        interp.set_private(base, key[2:], value)
        return
    if base is UNDEFINED or base is NULL:
        raise ThrowExc(make_error_value("TypeError", "cannot set property of null"))
    if not isinstance(base, JSObject):
        if strict:
            raise ThrowExc(make_error_value("TypeError", f"cannot assign to {key}"))
        return
    res = base.set(key, value, recv=base)
    if isinstance(res, tuple):
        await resolve_call(res, interp)
        return
    if not res and strict:
        raise ThrowExc(make_error_value("TypeError", f"cannot assign to {key}"))


async def prop_delete(interp, base: JSValue, key: str) -> bool:
    if base is UNDEFINED or base is NULL:
        raise ThrowExc(make_error_value("TypeError", "cannot delete property of null"))
    if not isinstance(base, JSObject):
        return True
    return base.delete(key)


async def env_get(interp, env: Environment, name: str):
    e: Environment | None = env
    while e is not None:
        if e.obj is not None:
            v = e.obj.get(name, recv=e.obj)
            if v is not UNDEFINED:
                if isinstance(v, tuple):
                    return await resolve_call(v, interp)
                return v
        cell = e.record.get(name)
        if cell is not None:
            if not cell["init"]:
                raise ThrowExc(make_error_value("ReferenceError", f"{name} is not initialized"))
            return cell["value"]
        e = e.parent
    raise ThrowExc(make_error_value("ReferenceError", f"{name} is not defined"))


async def env_set(interp, env: Environment, name: str, value: JSValue, *, strict: bool) -> None:
    e: Environment | None = env
    while e is not None:
        if e.obj is not None:
            v = e.obj.get(name, recv=e.obj)
            if v is not UNDEFINED:
                res = e.obj.set(name, value, recv=e.obj)
                if isinstance(res, tuple):
                    await resolve_call(res, interp)
                    return
                if not res and (strict or e.strict):
                    raise ThrowExc(make_error_value("TypeError", f"cannot assign to {name}"))
                return
        cell = e.record.get(name)
        if cell is not None:
            if not cell["init"]:
                raise ThrowExc(make_error_value("ReferenceError", f"{name} is not initialized"))
            if cell["kind"] == "const":
                raise ThrowExc(make_error_value("TypeError", f"cannot reassign {name}"))
            cell["value"] = value
            mirror_global(e, name, value)
            return
        e = e.parent
    if strict or env.strict:
        raise ThrowExc(make_error_value("ReferenceError", f"{name} is not defined"))
    env.var_env().record[name] = {"kind": "var", "value": value, "init": True}
    mirror_global(env, name, value)


def mirror_global(scope_env: Environment, name: str, value: JSValue) -> None:
    target = scope_env.var_env()
    if target.is_global and target.global_obj is not None:
        cell = target.record.get(name)
        if cell is not None and cell["kind"] == "var":
            target.global_obj.define_own(name, value)


async def to_primitive(interp, v: JSValue, hint: str = "default"):
    if not isinstance(v, JSObject):
        return v
    if hint == "default" and v.get_own("__date__") is not UNDEFINED:
        hint = "string"
    prim = v.get("@@toPrimitive", recv=v)
    if isinstance(prim, tuple):
        out = await resolve_call(prim, interp)
        if not isinstance(out, JSObject):
            return out
    elif prim is not UNDEFINED:
        pass
    methods = ("valueOf", "toString") if hint != "string" else ("toString", "valueOf")
    for name in methods:
        fn = v.get(name, recv=v)
        if isinstance(fn, tuple):
            out = await resolve_call(fn, interp)
            if not isinstance(out, JSObject):
                return out
        elif isinstance(fn, JSFunction):
            out = await interp.call_value(fn, v, [])
            if not isinstance(out, JSObject):
                return out
    raise ThrowExc(make_error_value("TypeError", "cannot convert object to primitive"))


async def to_number(interp, v: JSValue) -> float:
    if isinstance(v, JSObject):
        return to_number_primitive(await to_primitive(interp, v, "number"))
    if isinstance(v, JSSymbol):
        raise ThrowExc(make_error_value("TypeError", "cannot convert symbol to number"))
    return to_number_primitive(v)


async def to_string(interp, v: JSValue) -> str:
    if isinstance(v, JSObject):
        return to_string_primitive(await to_primitive(interp, v, "string"))
    if isinstance(v, JSSymbol):
        raise ThrowExc(make_error_value("TypeError", "cannot convert symbol to string"))
    return to_string_primitive(v)


async def to_int32(interp, v: JSValue) -> int:
    n = await to_number(interp, v)
    if n != n or n in (math.inf, -math.inf) or n == 0:
        return 0
    n = math.trunc(n) % 2**32
    return int(n - 2**32 if n >= 2**31 else n)


async def to_length(interp, v: JSValue) -> int:
    n = await to_number(interp, v)
    if n != n or n <= 0:
        return 0
    return min(2**53 - 1, int(math.trunc(n)))


async def abstract_equal(interp, a: JSValue, b: JSValue) -> bool:
    if type(a) is type(b):
        return strict_equal(a, b)
    if (a is NULL and b is UNDEFINED) or (a is UNDEFINED and b is NULL):
        return True
    if isinstance(a, JSNumber) and isinstance(b, JSString):
        return await abstract_equal(interp, a, JSNumber(str_to_number(b.value)))
    if isinstance(a, JSString) and isinstance(b, JSNumber):
        return await abstract_equal(interp, JSNumber(str_to_number(a.value)), b)
    if isinstance(a, JSBoolean):
        return await abstract_equal(interp, JSNumber(1 if a.value else 0), b)
    if isinstance(b, JSBoolean):
        return await abstract_equal(interp, a, JSNumber(1 if b.value else 0))
    if isinstance(a, JSBigInt) and isinstance(b, JSBigInt):
        return a.value == b.value
    if isinstance(a, JSBigInt) and isinstance(b, JSNumber):
        bn = b.value
        if bn != bn or bn in (math.inf, -math.inf) or not bn.is_integer():
            return False
        return a.value == int(bn)
    if isinstance(a, JSNumber) and isinstance(b, JSBigInt):
        return await abstract_equal(interp, b, a)
    if isinstance(a, (JSString, JSNumber, JSBigInt)) and isinstance(b, JSObject):
        return await abstract_equal(interp, a, await to_primitive(interp, b))
    if isinstance(a, JSObject) and isinstance(b, (JSString, JSNumber, JSBigInt)):
        return await abstract_equal(interp, await to_primitive(interp, a), b)
    return False


async def less_than(interp, a: JSValue, b: JSValue) -> bool | None:
    pa, pb = await to_primitive(interp, a, "number"), await to_primitive(interp, b, "number")
    if isinstance(pa, JSString) and isinstance(pb, JSString):
        return pa.value < pb.value
    na, nb = to_number_primitive(pa), to_number_primitive(pb)
    if na != na or nb != nb:
        return None
    return na < nb


async def add_values(interp, a: JSValue, b: JSValue):
    if isinstance(a, JSBigInt) or isinstance(b, JSBigInt):
        if isinstance(a, JSBigInt) and isinstance(b, JSBigInt):
            return JSBigInt(a.value + b.value)
        raise ThrowExc(make_error_value("TypeError", "cannot mix bigint and number"))
    pa, pb = await to_primitive(interp, a), await to_primitive(interp, b)
    if isinstance(pa, JSString) or isinstance(pb, JSString):
        return JSString(to_string_primitive(pa) + to_string_primitive(pb))
    return JSNumber(to_number_primitive(pa) + to_number_primitive(pb))


async def arithmetic(interp, op: str, a: JSValue, b: JSValue):
    if op == "+":
        return await add_values(interp, a, b)
    if isinstance(a, JSBigInt) or isinstance(b, JSBigInt):
        if not (isinstance(a, JSBigInt) and isinstance(b, JSBigInt)):
            raise ThrowExc(make_error_value("TypeError", "cannot mix bigint and number"))
        x, y = a.value, b.value
        if op == "+":
            return JSBigInt(x + y)
        if op == "-":
            return JSBigInt(x - y)
        if op == "*":
            return JSBigInt(x * y)
        if op == "/":
            if y == 0:
                raise ThrowExc(make_error_value("RangeError", "bigint division by zero"))
            return JSBigInt(abs(x) // abs(y) * (1 if x * y >= 0 else -1))
        if op == "%":
            if y == 0:
                raise ThrowExc(make_error_value("RangeError", "bigint modulo by zero"))
            return JSBigInt(x % y)
        if op == "**":
            if y < 0:
                raise ThrowExc(make_error_value("RangeError", "negative bigint exponent"))
            return JSBigInt(x**y)
        raise ThrowExc(make_error_value("TypeError", f"bad bigint operator {op}"))
    x, y = await to_number(interp, a), await to_number(interp, b)
    if op == "+":
        return JSNumber(x + y)
    if op == "-":
        return JSNumber(x - y)
    if op == "*":
        return JSNumber(x * y)
    if op == "/":
        return JSNumber(x / y)
    if op == "%":
        return JSNumber(math.fmod(x, y) if y != 0 else math.nan)
    if op == "**":
        try:
            return JSNumber(math.pow(x, y))
        except (OverflowError, ValueError):
            return JSNumber(math.inf if x > 0 else math.nan)
    raise ThrowExc(make_error_value("InternalError", f"bad arithmetic {op}"))


def pattern_names(pat) -> list[str]:
    if pat[0] == "ident":
        return [pat[1]]
    if pat[0] == "default":
        return pattern_names(pat[1])
    if pat[0] == "array_pat":
        out = []
        for e in pat[1]:
            if e[0] == "hole":
                continue
            out.extend(pattern_names(e[1] if e[0] == "rest" else e))
        return out
    if pat[0] == "object_pat":
        out = []
        for item in pat[1]:
            out.extend(pattern_names(item[1] if item[0] == "rest" else item[2]))
        return out
    if pat[0] == "rest":
        return pattern_names(pat[1])
    return []


def stmt_bound_names(stmt) -> list[str]:
    if stmt[0] == "var":
        out = []
        for pat, _ in stmt[2]:
            out.extend(pattern_names(pat))
        return out
    if stmt[0] in ("func_decl", "class_decl"):
        return [stmt[1]] if stmt[1] else []
    return []


def expr_to_pattern(node):
    kind = node[0]
    if kind == "ident":
        return node
    if kind == "array":
        elems = []
        for e in node[1]:
            if e[0] == "hole":
                elems.append(e)
            elif e[0] == "spread":
                elems.append(("rest", expr_to_pattern(e[1])))
            else:
                elems.append(expr_to_pattern(e))
        return ("array_pat", elems)
    if kind == "object":
        props = []
        for p in node[1]:
            if p[0] == "spread":
                props.append(("rest", expr_to_pattern(p[1])))
            elif p[0] == "value":
                _, keynode, computed, val = p
                if keynode[0] == "ident" and not computed:
                    key = ("ident", keynode[1])
                elif keynode[0] in ("str", "num"):
                    key = keynode
                else:
                    raise ThrowExc(make_error_value("SyntaxError", "bad destructuring key"))
                props.append(("prop", key, expr_to_pattern(val)))
            elif p[0] == "shorthand":
                props.append(("prop", ("ident", p[1]), ("ident", p[1])))
            else:
                raise ThrowExc(make_error_value("SyntaxError", "bad destructuring pattern"))
        return ("object_pat", props)
    if kind == "assign" and node[1] == "=":
        return ("default", expr_to_pattern(node[2]), node[3])
    raise ThrowExc(make_error_value("ReferenceError", "bad assignment target"))


def env_this(env: Environment):
    e: Environment | None = env
    while e is not None:
        cell = e.record.get("this")
        if cell is not None:
            if not cell["init"]:
                raise ThrowExc(make_error_value("ReferenceError", "this is not initialized (call super first)"))
            return cell["value"]
        e = e.parent
    return UNDEFINED


def env_super_home(env: Environment):
    e: Environment | None = env
    while e is not None:
        if "__home__" in e.record:
            return e.record["__home__"]["value"]
        e = e.parent
    return UNDEFINED


class Interpreter:
    def __init__(self, global_obj: JSObject, options: JSOptions | None = None) -> None:
        self.global_obj = global_obj
        self.options = options or JSOptions()
        self.ops = 0
        self.deadline = time.monotonic() + self.options.budget_ms / 1000.0
        self.events = None  # set by the bindings layer (EventState in jslib)
        self.console_lines: list[str] = self.options.console if self.options.console is not None else []

    def tick(self) -> None:
        self.ops += 1
        if self.ops >= self.options.budget_ops or ((self.ops & 0x3FFF) == 0 and time.monotonic() > self.deadline):
            raise ThrowExc(make_error_value("RangeError", "script budget exhausted"))

    # ── entry ──
    async def run_program(self, program, env: Environment, *, module_exports: dict | None = None):
        _, stmts, module = program
        scope = Environment(env, var_scope=True) if module else env
        self.hoist_block(stmts, scope)
        for st in stmts:
            await self.exec_stmt(st, scope, exports=module_exports)
        return module_exports or {}

    def hoist_block(self, stmts: list, env: Environment) -> None:
        for st in stmts:
            if st[0] == "func_decl":
                fn = self.make_function(st[1] or "", st[2], st[3], env, st[4], False)
                if st[1]:
                    try:
                        env.declare("var", st[1])
                    except ThrowExc:
                        pass
                    env.initialize(st[1], fn)
            elif st[0] == "var":
                if st[1] == "var":
                    for pat, _ in st[2]:
                        for name in pattern_names(pat):
                            try:
                                env.declare("var", name)
                            except ThrowExc:
                                pass
                else:
                    for pat, _ in st[2]:
                        for name in pattern_names(pat):
                            env.declare(st[1], name)
            elif st[0] == "import":
                _, default, named, namespace, _ = st
                if default:
                    env.declare("const", default)
                for _, alias in named:
                    env.declare("const", alias)
                if namespace:
                    env.declare("const", namespace)

    # ── statements ──
    async def exec_stmt(self, node, env: Environment, *, exports: dict | None = None):
        self.tick()
        kind = node[0]
        if kind in ("empty", "debugger"):
            return
        if kind == "block":
            child = Environment(env, strict=env.strict)
            self.hoist_block(node[1], child)
            for st in node[1]:
                await self.exec_stmt(st, child)
            return
        if kind == "var":
            for pat, init in node[2]:
                val = await self.eval_expr(init, env) if init is not None else UNDEFINED
                await self.bind_pattern(pat, val, env)
            return
        if kind == "func_decl":
            fn = self.make_function(node[1] or "", node[2], node[3], env, node[4], False)
            if node[1]:
                env.initialize(node[1], fn)
            return
        if kind == "class_decl":
            cls = await self.eval_class(node[1] or "", node[2], node[3], env)
            if node[1]:
                env.declare("let", node[1])
                env.initialize(node[1], cls)
            return
        if kind == "expr":
            await self.eval_expr(node[1], env)
            return
        if kind == "if":
            if to_boolean(await self.eval_expr(node[1], env)):
                await self.exec_stmt(node[2], env)
            elif node[3] is not None:
                await self.exec_stmt(node[3], env)
            return
        if kind == "switch":
            child = Environment(env, strict=env.strict)
            val = await self.eval_expr(node[1], env)
            matched = False
            try:
                for test, stmts in node[2]:
                    if not matched:
                        matched = test is None or strict_equal(val, await self.eval_expr(test, env))
                    if matched:
                        for st in stmts:
                            await self.exec_stmt(st, child)
            except BreakExc as b:
                if b.label is not None:
                    raise
            return
        if kind == "for":
            await self.exec_for(node, env)
            return
        if kind in ("forin", "forof"):
            await self.exec_for_in_of(node, env)
            return
        if kind == "while":
            while to_boolean(await self.eval_expr(node[1], env)):
                try:
                    await self.exec_stmt(node[2], env)
                except ContinueExc as c:
                    if c.label is not None:
                        raise
                except BreakExc as b:
                    if b.label is not None:
                        raise
                    break
            return
        if kind == "do":
            while True:
                try:
                    await self.exec_stmt(node[1], env)
                except ContinueExc as c:
                    if c.label is not None:
                        raise
                except BreakExc as b:
                    if b.label is not None:
                        raise
                    break
                if not to_boolean(await self.eval_expr(node[2], env)):
                    break
            return
        if kind == "try":
            try:
                await self.exec_stmt(node[1], env)
            except ThrowExc as e:
                if node[2] is None:
                    raise
                param, hbody = node[2]
                child = Environment(env, strict=env.strict)
                if param is not None:
                    await self.bind_pattern(param, e.value, child)
                await self.exec_stmt(hbody, child)
            finally:
                if node[3] is not None:
                    await self.exec_stmt(node[3], env)
            return
        if kind == "throw":
            raise ThrowExc(await self.eval_expr(node[1], env))
        if kind == "return":
            raise ReturnExc(await self.eval_expr(node[1], env))
        if kind == "break":
            raise BreakExc(node[1])
        if kind == "continue":
            raise ContinueExc(node[1])
        if kind == "label":
            try:
                await self.exec_stmt(node[2], env)
            except (BreakExc, ContinueExc) as e:
                if e.label != node[1]:
                    raise
            return
        if kind == "with":
            obj = await self.eval_expr(node[1], env)
            if not isinstance(obj, JSObject):
                raise ThrowExc(make_error_value("TypeError", "with needs an object"))
            await self.exec_stmt(node[2], Environment(env, obj=obj, strict=env.strict))
            return
        if kind == "return_block":
            raise ReturnExc(await self.eval_expr(node[1], env))
        if kind == "export_decl":
            await self.exec_stmt(node[1], env)
            if exports is not None and node[1][0] in ("func_decl", "class_decl", "var"):
                for name in stmt_bound_names(node[1]):
                    exports[name] = await env_get(self, env, name)
            return
        if kind == "export_list":
            _, items, src = node
            if src:
                mod = await self.load_module(src, env)
                if exports is not None:
                    for name, alias in items:
                        exports[alias] = mod.get(name, UNDEFINED)
                return
            if exports is not None:
                for name, alias in items:
                    exports[alias] = await env_get(self, env, name)
            return
        if kind == "export_star":
            mod = await self.load_module(node[1], env)
            if exports is not None:
                exports.update(mod)
            return
        if kind == "export_star_as":
            mod = await self.load_module(node[2], env)
            ns = JSObject(INTRINSICS["Object_prototype"])
            for k, v in mod.items():
                ns.define_own(k, v, enumerable=False)
            if exports is not None:
                exports[node[1]] = ns
            return
        if kind == "export_default":
            val = node[1]
            if val[0] == "expr":
                out = await self.eval_expr(val[1], env)
            else:
                await self.exec_stmt(val, env)
                names = stmt_bound_names(val)
                out = await env_get(self, env, names[0]) if names else UNDEFINED
            if exports is not None:
                exports["default"] = out
            return
        if kind == "import":
            _, default, named, namespace, src = node
            mod = await self.load_module(src, env)
            if default:
                env.initialize(default, mod.get("default", UNDEFINED))
            for name, alias in named:
                env.initialize(alias, mod.get(name, UNDEFINED))
            if namespace:
                ns = JSObject(INTRINSICS["Object_prototype"])
                for k, v in mod.items():
                    ns.define_own(k, v, enumerable=False)
                env.initialize(namespace, ns)
            return
        if kind == "import_side":
            await self.load_module(node[1], env)
            return
        raise ThrowExc(make_error_value("InternalError", f"unknown statement {kind}"))

    async def load_module(self, src: str, env: Environment) -> dict:
        loader = self.options.module_loader
        if loader is None:
            raise ThrowExc(make_error_value("Error", f"module loading is not available for {src}"))
        out = loader(src)
        if asyncio.iscoroutine(out):
            out = await out
        return out

    async def exec_for(self, node, env: Environment) -> None:
        _, init, test, update, body = node
        loop_env = Environment(env, strict=env.strict)
        decl_kind = None
        decl_names: list[str] = []
        if isinstance(init, tuple) and init and init[0] == "var":
            decl_kind = init[1]
            for pat, _ in init[2]:
                decl_names.extend(pattern_names(pat))
            await self.exec_stmt(init, loop_env)
        elif init is not None:
            await self.eval_expr(init, env)
        while True:
            if test is not None and not to_boolean(await self.eval_expr(test, loop_env)):
                break
            if decl_kind in ("let", "const"):
                iter_env = Environment(loop_env, strict=loop_env.strict)
                for name in decl_names:
                    val = await env_get(self, loop_env, name)
                    iter_env.declare(decl_kind, name)
                    iter_env.initialize(name, val)
                scope = iter_env
            else:
                scope = loop_env
            try:
                await self.exec_stmt(body, scope)
            except ContinueExc as c:
                if c.label is not None:
                    raise
            except BreakExc as b:
                if b.label is not None:
                    raise
                break
            finally:
                if decl_kind == "let":
                    for name in decl_names:
                        try:
                            loop_env.record[name]["value"] = scope.record[name]["value"]
                        except (KeyError, AttributeError):
                            pass
            if update is not None:
                await self.eval_expr(update, loop_env)

    async def exec_for_in_of(self, node, env: Environment) -> None:
        kind, left, right, body = node
        decl = left if isinstance(left, tuple) and left and left[0] in ("var", "let", "const") else None
        decl_kind = decl[0] if decl else None
        if kind == "forof":
            items = await self.to_iterable(await self.eval_expr(right, env))
        else:
            items = [JSString(k) for k in enum_keys(await self.eval_expr(right, env))]
        loop_env = Environment(env, strict=env.strict)
        for item in items:
            scope = Environment(loop_env, strict=loop_env.strict)
            if decl:
                if decl[2] is not None:
                    raise ThrowExc(make_error_value("SyntaxError", "for head cannot have an initializer"))
                pat = decl[1]
                for name in pattern_names(pat):
                    scope.declare(decl_kind, name)
                await self.bind_pattern(pat, item, scope)
            else:
                await self.assign_pattern(expr_to_pattern(left), item, loop_env)
                scope = loop_env
            try:
                await self.exec_stmt(body, scope)
            except ContinueExc as c:
                if c.label is not None:
                    raise
            except BreakExc as b:
                if b.label is not None:
                    raise
                break

    async def to_iterable(self, v: JSValue) -> list:
        if isinstance(v, JSArray):
            out = []
            for i in range(v.length()):
                item = v.get(str(i))
                out.append(await resolve_call(item, self) if isinstance(item, tuple) else item)
            return out
        if isinstance(v, JSString):
            return [JSString(c) for c in v.value]
        if isinstance(v, JSObject):
            pairs = getattr(v, "pairs", None)
            if isinstance(pairs, list) and all(isinstance(e, tuple) and len(e) == 2 for e in pairs):
                return [js_array_of(self, k, item) for k, item in pairs]
            items = getattr(v, "items", None)
            if isinstance(items, list):
                return list(items)
            it = v.get("@@iterator", recv=v)
            if isinstance(it, tuple):
                it = await resolve_call(it, self)
            if isinstance(it, JSFunction):
                res = await self.call_value(it, v, [])
                out = []
                while True:
                    nxt = await self.call_method(res, "next", [])
                    if not isinstance(nxt, JSObject):
                        raise ThrowExc(make_error_value("TypeError", "iterator returned a primitive"))
                    done = nxt.get("done", recv=nxt)
                    done = await resolve_call(done, self) if isinstance(done, tuple) else done
                    if to_boolean(done):
                        break
                    val = nxt.get("value", recv=nxt)
                    out.append(await resolve_call(val, self) if isinstance(val, tuple) else val)
                    if len(out) > 100000:
                        raise ThrowExc(make_error_value("RangeError", "iterator too long"))
                return out
            raw = v.get_own("__map_keys__")
            if raw is not UNDEFINED:
                return list(raw)
            raw = v.get_own("__set_values__")
            if raw is not UNDEFINED:
                return list(raw)
        raise ThrowExc(make_error_value("TypeError", "value is not iterable"))

    # ── patterns ──
    async def bind_pattern(self, pat, value: JSValue, env: Environment) -> None:
        if pat[0] == "ident":
            env.initialize(pat[1], value)
            return
        if pat[0] == "default":
            if value is UNDEFINED:
                value = await self.eval_expr(pat[2], env)
            await self.bind_pattern(pat[1], value, env)
            return
        if pat[0] == "array_pat":
            items = await self.to_iterable(value) if value is not UNDEFINED and value is not NULL else []
            idx = 0
            for elem in pat[1]:
                if elem[0] == "hole":
                    idx += 1
                elif elem[0] == "rest":
                    rest = JSArray(INTRINSICS["Array_prototype"])
                    for item in items[idx:]:
                        rest.set(str(rest.length()), item)
                        rest.set_length(rest.length() + 1)
                    await self.bind_pattern(elem[1], rest, env)
                    idx = len(items)
                else:
                    await self.bind_pattern(elem, items[idx] if idx < len(items) else UNDEFINED, env)
                    idx += 1
            return
        if pat[0] == "object_pat":
            if not isinstance(value, JSObject):
                raise ThrowExc(make_error_value("TypeError", "destructuring needs an object"))
            seen: set[str] = set()
            for item in pat[1]:
                if item[0] == "rest":
                    rest = JSObject(INTRINSICS["Object_prototype"])
                    for k in value.own_keys():
                        if k not in seen and value.props[k].get("enumerable", True):
                            rest.define_own(k, value.get_own(k))
                    await self.bind_pattern(item[1], rest, env)
                else:
                    key = await self.pattern_key(item[1], env)
                    seen.add(key)
                    await self.bind_pattern(item[2], await prop_get(self, value, key), env)
            return
        raise ThrowExc(make_error_value("SyntaxError", "bad binding pattern"))

    async def pattern_key(self, keynode, env: Environment) -> str:
        if keynode[0] == "ident":
            return keynode[1]
        if keynode[0] == "str":
            return keynode[1]
        if keynode[0] == "num":
            from magpie_jsparse import js_number_key
            return js_number_key(keynode[1])
        return await to_string(self, await self.eval_expr(keynode[1], env))

    async def assign_pattern(self, pat, value: JSValue, env: Environment) -> None:
        if pat[0] == "ident":
            await env_set(self, env, pat[1], value, strict=env.strict)
            return
        if pat[0] == "default":
            if value is UNDEFINED:
                value = await self.eval_expr(pat[2], env)
            await self.assign_pattern(pat[1], value, env)
            return
        if pat[0] == "array_pat":
            items = await self.to_iterable(value) if value is not UNDEFINED and value is not NULL else []
            idx = 0
            for elem in pat[1]:
                if elem[0] == "hole":
                    idx += 1
                elif elem[0] == "rest":
                    rest = JSArray(INTRINSICS["Array_prototype"])
                    for item in items[idx:]:
                        rest.set(str(rest.length()), item)
                        rest.set_length(rest.length() + 1)
                    await self.assign_pattern(elem[1], rest, env)
                    idx = len(items)
                else:
                    await self.assign_pattern(elem, items[idx] if idx < len(items) else UNDEFINED, env)
                    idx += 1
            return
        if pat[0] == "object_pat":
            if not isinstance(value, JSObject):
                raise ThrowExc(make_error_value("TypeError", "destructuring needs an object"))
            seen = set()
            for item in pat[1]:
                if item[0] == "rest":
                    rest = JSObject(INTRINSICS["Object_prototype"])
                    for k in value.own_keys():
                        if k not in seen and value.props[k].get("enumerable", True):
                            rest.define_own(k, value.get_own(k))
                    await self.assign_pattern(item[1], rest, env)
                else:
                    key = await self.pattern_key(item[1], env)
                    seen.add(key)
                    await self.assign_pattern(item[2], await prop_get(self, value, key), env)
            return
        raise ThrowExc(make_error_value("ReferenceError", "bad assignment target"))

    # ── expressions ──
    async def eval_expr(self, node, env: Environment):
        self.tick()
        kind = node[0]
        if kind == "num":
            return JSNumber(node[1])
        if kind == "bigint":
            return JSBigInt(node[1])
        if kind == "str":
            return JSString(node[1])
        if kind == "bool":
            return js_bool(node[1])
        if kind == "null":
            return NULL
        if kind == "undef":
            return UNDEFINED
        if kind == "regex":
            from magpie_jslib import make_regexp
            return make_regexp(node[1], node[2])
        if kind == "template":
            return await self.eval_template(node[1], env, tag=None)
        if kind == "tagged":
            return await self.eval_template(node[2], env, tag=node[1])
        if kind == "array":
            return await self.eval_array(node[1], env)
        if kind == "object":
            return await self.eval_object(node[1], env)
        if kind == "func":
            return self.make_function(node[1] or "", node[2], node[3], env, node[4], False)
        if kind == "arrow":
            return self.make_function("", node[1], node[2], env, node[3], False, arrow=True)
        if kind == "class":
            return await self.eval_class(node[1] or "", node[2], node[3], env)
        if kind == "ident":
            return await env_get(self, env, node[1])
        if kind == "this":
            return env_this(env)
        if kind == "super":
            home = env_super_home(env)
            if isinstance(home, JSObject):
                return home.proto if home.proto is not None else NULL
            return NULL
        if kind == "new_target":
            e: Environment | None = env
            while e is not None:
                if "new.target" in e.record:
                    return e.record["new.target"]["value"]
                e = e.parent
            return UNDEFINED
        if kind == "member":
            return await self.eval_member(node, env)
        if kind == "call":
            return await self.eval_call(node, env)
        if kind == "chain":
            return await self.eval_chain(node, env)
        if kind == "new":
            callee = await self.eval_expr(node[1], env)
            return await self.construct(callee, await self.eval_args(node[2], env))
        if kind == "unary":
            return await self.eval_unary(node[1], node[2], env)
        if kind == "update":
            return await self.eval_update(node[1], node[2], node[3], env)
        if kind == "binary":
            return await self.eval_binary(node[1], node[2], node[3], env)
        if kind == "assign":
            return await self.eval_assign(node[1], node[2], node[3], env)
        if kind == "cond":
            branch = node[2] if to_boolean(await self.eval_expr(node[1], env)) else node[3]
            return await self.eval_expr(branch, env)
        if kind == "seq":
            out = UNDEFINED
            for item in node[1]:
                out = await self.eval_expr(item, env)
            return out
        if kind == "await":
            return await self.await_value(await self.eval_expr(node[1], env))
        if kind == "dynamic_import":
            args = await self.eval_args(node[1], env)
            if not args:
                raise ThrowExc(make_error_value("TypeError", "import needs a source"))
            spec = await to_string(self, args[0])
            mod = await self.load_module(spec, env)
            ns = JSObject(INTRINSICS["Object_prototype"])
            for k, v in mod.items():
                ns.define_own(k, v, enumerable=False)
            from magpie_jsval import JSPromise
            p = JSPromise(self)
            p.resolve(ns)
            return p
        if kind == "import_meta":
            raise ThrowExc(make_error_value("Error", "import.meta is not supported"))
        raise ThrowExc(make_error_value("InternalError", f"unknown expression {kind}"))

    async def eval_args(self, args: list, env: Environment) -> list:
        out = []
        for a in args:
            if a[0] == "spread":
                out.extend(await self.to_iterable(await self.eval_expr(a[1], env)))
            else:
                out.append(await self.eval_expr(a, env))
        return out

    async def eval_template(self, parts, env: Environment, *, tag):
        strings, values = [], []
        for kind, item in parts:
            if kind == "str":
                strings.append(item)
            else:
                values.append(await self.eval_expr(Parser(item, "<template>").parse_expression(), env))
        if tag is None:
            out = []
            for i, s in enumerate(strings):
                out.append(s)
                if i < len(values):
                    out.append(await to_string(self, values[i]))
            return JSString("".join(out))
        tag_fn = await self.eval_expr(tag, env)
        arr = JSArray(INTRINSICS["Array_prototype"])
        raw = JSArray(INTRINSICS["Array_prototype"])
        for s in strings:
            for target in (arr, raw):
                target.set(str(target.length()), JSString(s))
                target.set_length(target.length() + 1)
        arr.define_own("raw", raw, enumerable=False)
        return await self.call_value(tag_fn, UNDEFINED, [arr, *values])

    async def eval_array(self, elems: list, env: Environment):
        arr = JSArray(INTRINSICS["Array_prototype"])
        for e in elems:
            if e[0] == "hole":
                arr.set_length(arr.length() + 1)
            elif e[0] == "spread":
                for item in await self.to_iterable(await self.eval_expr(e[1], env)):
                    arr.set(str(arr.length()), item)
                    arr.set_length(arr.length() + 1)
            else:
                arr.set(str(arr.length()), await self.eval_expr(e, env))
                arr.set_length(arr.length() + 1)
        return arr

    async def eval_object(self, props: list, env: Environment):
        obj = JSObject(INTRINSICS["Object_prototype"])
        for p in props:
            if p[0] == "spread":
                src = await self.eval_expr(p[1], env)
                if isinstance(src, JSObject):
                    for k in src.own_keys():
                        if src.props[k].get("enumerable", True):
                            v = src.get(k, recv=src)
                            obj.define_own(k, await resolve_call(v, self) if isinstance(v, tuple) else v)
                elif isinstance(src, JSString):
                    for i, ch in enumerate(src.value):
                        obj.define_own(str(i), JSString(ch))
                elif src is not UNDEFINED and src is not NULL:
                    raise ThrowExc(make_error_value("TypeError", "spread needs an object"))
            elif p[0] == "value":
                key = await self.object_key(p[1], p[2], env)
                obj.define_own(key, await self.eval_expr(p[3], env))
            elif p[0] == "shorthand":
                obj.define_own(p[1], await env_get(self, env, p[1]))
            elif p[0] == "method":
                key = await self.object_key(p[1], p[2], env)
                fn = self.make_function(key, p[3][1], p[3][2], env, p[3][3], False, home=obj)
                obj.define_own(key, fn, enumerable=True)
            elif p[0] == "accessor":
                key = await self.object_key(p[2], p[3], env)
                fn = self.make_function(key, p[4][1], p[4][2], env, p[4][3], False, home=obj)
                old = obj.props.get(key)
                getter = old.get("get") if old else None
                setter = old.get("set") if old else None
                if p[1] == "get":
                    getter = fn
                else:
                    setter = fn
                obj.define_accessor(key, getter, setter)
        return obj

    async def object_key(self, keynode, computed: bool, env: Environment) -> str:
        if not computed:
            if keynode[0] == "ident":
                return keynode[1]
            if keynode[0] == "str":
                return keynode[1]
            if keynode[0] == "num":
                from magpie_jsparse import js_number_key
                return js_number_key(keynode[1])
        v = await self.eval_expr(keynode[1] if keynode[0] == "computed" else keynode, env)
        return await prop_key(v, self)

    async def eval_member(self, node, env: Environment):
        _, obj_node, prop_node, optional, computed = node
        if obj_node[0] == "super":
            this = env_this(env)
            home = env_super_home(env)
            proto = home.proto if isinstance(home, JSObject) else None
            if proto is None:
                raise ThrowExc(make_error_value("TypeError", "super has no prototype"))
            key = await self.member_key(prop_node, computed, env)
            if (this is UNDEFINED or this is NULL) and optional:
                return UNDEFINED
            v = proto.get(key, recv=this if isinstance(this, JSObject) else proto)
            return await resolve_call(v, self) if isinstance(v, tuple) else v
        base = await self.eval_expr(obj_node, env)
        if (base is UNDEFINED or base is NULL) and optional:
            return UNDEFINED
        key = await self.member_key(prop_node, computed, env)
        return await prop_get(self, base, key)

    async def member_key(self, prop_node, computed: bool, env: Environment) -> str:
        if prop_node[0] == "literal_prop":
            return prop_node[1]
        if prop_node[0] == "private_prop":
            return "# " + prop_node[1]
        return await prop_key(await self.eval_expr(prop_node, env), self)

    def get_private(self, base: JSValue, name: str):
        if isinstance(base, JSObject):
            for (cls_id, field), val in base.private_slots.items():
                if field == name:
                    return val
        raise ThrowExc(make_error_value("TypeError", f"private member {name} is not accessible"))

    def set_private(self, base: JSValue, name: str, value: JSValue) -> None:
        if isinstance(base, JSObject):
            for key in base.private_slots:
                if key[1] == name:
                    base.private_slots[key] = value
                    return
        raise ThrowExc(make_error_value("TypeError", f"private member {name} is not accessible"))

    async def eval_call(self, node, env: Environment):
        _, callee_node, args, _ = node
        if callee_node[0] == "member":
            if callee_node[1][0] == "super":
                this = env_this(env)
                home = env_super_home(env)
                proto = home.proto if isinstance(home, JSObject) else None
                if proto is None:
                    raise ThrowExc(make_error_value("TypeError", "super has no prototype"))
                key = await self.member_key(callee_node[2], callee_node[4], env)
                v = proto.get(key, recv=this if isinstance(this, JSObject) else proto)
                fn = await resolve_call(v, self) if isinstance(v, tuple) else v
                return await self.call_value(fn, this, await self.eval_args(args, env))
            base = await self.eval_expr(callee_node[1], env)
            key = await self.member_key(callee_node[2], callee_node[4], env)
            fn = await prop_get(self, base, key)
            return await self.call_value(fn, base, await self.eval_args(args, env))
        if callee_node[0] == "super":
            return await self.eval_super_call(args, env)
        if callee_node[0] == "chain":
            fn = await self.eval_chain(callee_node, env)
            return await self.call_value(fn, UNDEFINED, await self.eval_args(args, env))
        fn = await self.eval_expr(callee_node, env)
        this = self.global_obj if not env.strict else UNDEFINED
        return await self.call_value(fn, this, await self.eval_args(args, env))

    async def eval_super_call(self, args, env: Environment):
        e: Environment | None = env
        while e is not None:
            if "__ctor__" in e.record:
                break
            e = e.parent
        if e is None:
            raise ThrowExc(make_error_value("TypeError", "super() outside a derived constructor"))
        info = e.record["__ctor__"]["value"]
        if not isinstance(info, dict) or not info.get("derived"):
            raise ThrowExc(make_error_value("TypeError", "super() outside a derived constructor"))
        if info.get("super_called"):
            raise ThrowExc(make_error_value("TypeError", "super() already called"))
        argv = await self.eval_args(args, env)
        parent = info["parent"]
        ctor_fn = info.get("ctor")
        derived_proto = None
        if isinstance(ctor_fn, JSFunction):
            derived_proto = ctor_fn.get("prototype", recv=ctor_fn)
            derived_proto = await resolve_call(derived_proto, self) if isinstance(derived_proto, tuple) else derived_proto
        if parent is NULL:
            # `extends null`: no parent call; plain object with our prototype.
            this = JSObject(derived_proto if isinstance(derived_proto, JSObject) else INTRINSICS["Object_prototype"])
        else:
            this = await self.construct(parent, argv)
            # Derived instances keep the derived prototype (e.g. B.prototype),
            # even though `this` was allocated by the parent constructor.
            if isinstance(this, JSObject) and isinstance(derived_proto, JSObject):
                this.proto = derived_proto
        e.record["this"] = {"kind": "var", "value": this, "init": True}
        info["super_called"] = True
        await self.apply_fields(info, e)
        return this

    async def eval_chain(self, node, env: Environment):
        _, base_node, ops = node
        if base_node[0] == "super":
            current: JSValue = env_super_home(env)
            if isinstance(current, JSObject):
                current = current.proto if current.proto is not None else NULL
            recv: JSValue = env_this(env)
        else:
            current = await self.eval_expr(base_node, env)
            recv = current
        if current is UNDEFINED or current is NULL:
            return UNDEFINED
        for op in ops:
            if op[0] == "member":
                _, prop_node, computed, optional = op
                if current is UNDEFINED or current is NULL:
                    if optional:
                        return UNDEFINED
                    raise ThrowExc(make_error_value("TypeError", "cannot read property of null"))
                key = await self.member_key(prop_node, computed, env)
                if base_node[0] == "super" and isinstance(current, JSObject):
                    v = current.get(key, recv=recv if isinstance(recv, JSObject) else current)
                    current = await resolve_call(v, self) if isinstance(v, tuple) else v
                else:
                    recv = current
                    current = await prop_get(self, current, key)
            elif op[0] == "call":
                if current is UNDEFINED or current is NULL:
                    if op[2]:
                        return UNDEFINED
                    raise ThrowExc(make_error_value("TypeError", "value is not a function"))
                argv = await self.eval_args(op[1], env)
                current = await self.call_value(current, recv, argv)
                recv = current
            elif op[0] == "tagged":
                current = await self.eval_template(op[1], env, tag=current)
        return current

    async def eval_unary(self, op: str, arg_node, env: Environment):
        if op == "typeof":
            try:
                val = await self.eval_expr(arg_node, env)
            except ThrowExc as e:
                name = e.value.get_own("name") if isinstance(e.value, JSObject) else UNDEFINED
                if isinstance(name, JSString) and name.value == "ReferenceError":
                    return JSString("undefined")
                raise
            if isinstance(val, JSFunction):
                return JSString("function")
            return JSString(val.type_of())
        if op == "void":
            await self.eval_expr(arg_node, env)
            return UNDEFINED
        if op == "delete":
            return js_bool(await self.eval_delete(arg_node, env))
        val = await self.eval_expr(arg_node, env)
        if op == "!":
            return js_bool(not to_boolean(val))
        if op == "+":
            return JSNumber(await to_number(self, val))
        if op == "-":
            return JSNumber(-await to_number(self, val))
        if op == "~":
            return JSNumber(await to_int32(self, val) ^ -1)
        raise ThrowExc(make_error_value("InternalError", f"bad unary {op}"))

    async def eval_delete(self, node, env: Environment) -> bool:
        if node[0] == "ident":
            e: Environment | None = env
            while e is not None:
                if e.obj is None and node[1] in e.record:
                    if env.strict:
                        raise ThrowExc(make_error_value("SyntaxError", "cannot delete a binding"))
                    return False
                e = e.parent
            return True
        if node[0] == "member":
            base = await self.eval_expr(node[1], env)
            key = await self.member_key(node[2], node[4], env)
            return await prop_delete(self, base, key)
        if node[0] == "chain":
            _, base_node, ops = node
            if not ops or ops[-1][0] != "member":
                await self.eval_chain(node, env)
                return True
            base = await self.eval_expr(base_node, env)
            current = base
            for op in ops[:-1]:
                if op[0] == "member":
                    current = await prop_get(self, current, await self.member_key(op[1], op[2], env))
                elif op[0] == "call":
                    current = await self.call_value(current, current, await self.eval_args(op[1], env))
            if current is UNDEFINED or current is NULL:
                return True
            last = ops[-1]
            return await prop_delete(self, current, await self.member_key(last[1], last[2], env))
        await self.eval_expr(node, env)
        return True

    async def eval_update(self, op: str, target, prefix: bool, env: Environment):
        old = await self.read_reference(target, env)
        new = JSBigInt(old.value + (1 if op == "++" else -1)) if isinstance(old, JSBigInt) else JSNumber(await to_number(self, old) + (1 if op == "++" else -1))
        await self.write_reference(target, new, env)
        return new if prefix else old

    async def read_reference(self, node, env: Environment):
        if node[0] == "ident":
            return await env_get(self, env, node[1])
        if node[0] == "member":
            base = await self.eval_expr(node[1], env)
            return await prop_get(self, base, await self.member_key(node[2], node[4], env))
        if node[0] == "chain":
            return await self.eval_chain(node, env)
        raise ThrowExc(make_error_value("ReferenceError", "bad reference"))

    async def write_reference(self, node, value: JSValue, env: Environment) -> None:
        if node[0] == "ident":
            await env_set(self, env, node[1], value, strict=env.strict)
            return
        if node[0] == "member":
            if node[1][0] == "super":
                this = env_this(env)
                home = env_super_home(env)
                proto = home.proto if isinstance(home, JSObject) else None
                if proto is None or not isinstance(this, JSObject):
                    raise ThrowExc(make_error_value("TypeError", "bad super assignment"))
                res = proto.set(await self.member_key(node[2], node[4], env), value, recv=this)
                if isinstance(res, tuple):
                    await resolve_call(res, self)
                    return
                if not res:
                    raise ThrowExc(make_error_value("TypeError", "cannot assign to super property"))
                return
            base = await self.eval_expr(node[1], env)
            await prop_set(self, base, await self.member_key(node[2], node[4], env), value, strict=env.strict)
            return
        if node[0] == "chain":
            raise ThrowExc(make_error_value("ReferenceError", "bad chain assignment"))
        raise ThrowExc(make_error_value("ReferenceError", "bad assignment target"))

    async def eval_binary(self, op: str, lnode, rnode, env: Environment):
        if op == "&&":
            left = await self.eval_expr(lnode, env)
            return left if not to_boolean(left) else await self.eval_expr(rnode, env)
        if op == "||":
            left = await self.eval_expr(lnode, env)
            return left if to_boolean(left) else await self.eval_expr(rnode, env)
        if op == "??":
            left = await self.eval_expr(lnode, env)
            return left if left is not UNDEFINED and left is not NULL else await self.eval_expr(rnode, env)
        left = await self.eval_expr(lnode, env)
        right = await self.eval_expr(rnode, env)
        if op == "+":
            return await add_values(self, left, right)
        if op in ("-", "*", "/", "%", "**"):
            return await arithmetic(self, op, left, right)
        if op in ("<", ">", "<=", ">="):
            fwd = await less_than(self, left, right) if op in ("<", "<=") else await less_than(self, right, left)
            if fwd is None:
                return FALSE
            if op in ("<", ">"):
                return js_bool(fwd)
            if fwd:
                return TRUE
            back = await less_than(self, right, left)
            fwd2 = await less_than(self, left, right)
            return js_bool(back is False and fwd2 is False)
        if op in ("==", "!=", "===", "!=="):
            eq = await abstract_equal(self, left, right) if op in ("==", "!=") else strict_equal(left, right)
            return js_bool(eq if op in ("==", "===") else not eq)
        if op == "in":
            if not isinstance(right, JSObject):
                raise ThrowExc(make_error_value("TypeError", "right of in needs an object"))
            return js_bool(prop_exists(right, await prop_key(left, self)))
        if op == "instanceof":
            return js_bool(await self.instance_of(left, right))
        if op in ("&", "|", "^", "<<", ">>", ">>>"):
            a, b = await to_int32(self, left), await to_int32(self, right)
            if op == "&":
                return JSNumber(a & b)
            if op == "|":
                return JSNumber(a | b)
            if op == "^":
                return JSNumber(a ^ b)
            if op == "<<":
                return JSNumber(((a << (b & 31)) & 0xFFFFFFFF) - 2**32 if (a << (b & 31)) & 0x80000000 else ((a << (b & 31)) & 0xFFFFFFFF))
            if op == ">>":
                return JSNumber(a >> (b & 31))
            return JSNumber((a & 0xFFFFFFFF) >> (b & 31))
        raise ThrowExc(make_error_value("InternalError", f"bad binary {op}"))

    async def instance_of(self, left: JSValue, right: JSValue) -> bool:
        if not isinstance(right, JSFunction):
            raise ThrowExc(make_error_value("TypeError", "right of instanceof is not callable"))
        proto = right.get("prototype", recv=right)
        proto = await resolve_call(proto, self) if isinstance(proto, tuple) else proto
        if not isinstance(proto, JSObject):
            raise ThrowExc(make_error_value("TypeError", "function has no object prototype"))
        if not isinstance(left, JSObject):
            return False
        obj: JSValue | None = left
        seen = 0
        while isinstance(obj, JSObject) and seen < 1000:
            obj = obj.proto
            if obj is proto:
                return True
            seen += 1
        return False

    async def eval_assign(self, op: str, left, right_node, env: Environment):
        if op == "=" and left[0] in ("array", "object"):
            pat = expr_to_pattern(left)
            val = await self.eval_expr(right_node, env)
            await self.assign_pattern(pat, val, env)
            return val
        if left[0] in ("array", "object"):
            raise ThrowExc(make_error_value("ReferenceError", "bad assignment target"))
        right = await self.eval_expr(right_node, env)
        if op == "=":
            await self.write_reference(left, right, env)
            return right
        old = await self.read_reference(left, env)
        if op == "&&=":
            if not to_boolean(old):
                return old
            await self.write_reference(left, right, env)
            return right
        if op == "||=":
            if to_boolean(old):
                return old
            await self.write_reference(left, right, env)
            return right
        if op == "??=":
            if old is not UNDEFINED and old is not NULL:
                return old
            await self.write_reference(left, right, env)
            return right
        out = await arithmetic(self, op[:-1], old, right)
        await self.write_reference(left, out, env)
        return out

    async def await_value(self, val):
        from magpie_jsval import JSPromise
        if isinstance(val, JSPromise):
            return await val
        if isinstance(val, JSObject):
            then = val.get("then", recv=val)
            then = await resolve_call(then, self) if isinstance(then, tuple) else then
            if isinstance(then, JSFunction):
                p = JSPromise(self)
                try:
                    out = await self.call_value(then, val, [
                        self._promise_fn(p.resolve), self._promise_fn(p.reject, is_reject=True),
                    ])
                    _ = out
                except ThrowExc as e:
                    p.reject(e.value)
                return await p
        return val

    def _promise_fn(self, settle, *, is_reject: bool = False):
        from magpie_jslib import native as _native
        def handler(this, args, interp):
            v = args[0] if args else UNDEFINED
            settle(v if isinstance(v, JSValue) else v)
            return UNDEFINED
        fn = _native("resolve", handler)
        fn.interp = self
        return fn

    # ── calls ──
    def make_function(self, name: str, params, body, env: Environment, is_async: bool, _gen: bool, *, arrow: bool = False, home=None):
        fn = JSFunction(kind="interpreted", proto=INTRINSICS["Function_prototype"])
        fn.node = ("closure", params, body)
        fn.env = env
        fn.is_async = is_async
        fn.this_mode = "arrow" if arrow else ("strict" if env.strict else "sloppy")
        fn.name = name
        fn.length = sum(1 for kind, _, default in params if kind == "param" and default is None)
        fn.home = home
        fn.interp = self
        fn.define_own("name", JSString(name), enumerable=False)
        fn.define_own("length", JSNumber(fn.length), enumerable=False)
        if not arrow:
            proto = JSObject(INTRINSICS["Object_prototype"])
            proto.define_own("constructor", fn, enumerable=False)
            fn.define_own("prototype", proto, enumerable=False)
        return fn

    def use_strict_body(self, body) -> bool:
        if body[0] == "block":
            for st in body[1]:
                if st[0] != "expr" or st[1][0] != "str":
                    break
                if st[1][1] == "use strict":
                    return True
        return False

    async def call_value(self, fn: JSValue, this: JSValue, args: list):
        if isinstance(fn, JSFunction) and fn.kind == "bound":
            return await self.call_value(fn.handler, fn.bound_this, [*fn.bound_args, *args])
        if not isinstance(fn, JSFunction):
            raise ThrowExc(make_error_value("TypeError", "value is not a function"))
        if fn.kind == "native":
            out = fn.handler(this, args, self)
            if asyncio.iscoroutine(out):
                out = await out
            return out
        _, params, body = fn.node
        arrow = fn.this_mode == "arrow"
        strict = fn.this_mode == "strict" or self.use_strict_body(body)
        call_env = Environment(fn.env, var_scope=True, strict=strict)
        if not arrow:
            call_env.record["this"] = {"kind": "var", "value": this, "init": True}
            call_env.record["__home__"] = {"kind": "var", "value": fn.home or UNDEFINED, "init": True}
            arg_obj = JSArray(INTRINSICS["Array_prototype"])
            for a in args:
                arg_obj.set(str(arg_obj.length()), a)
                arg_obj.set_length(arg_obj.length() + 1)
            call_env.record["arguments"] = {"kind": "var", "value": arg_obj, "init": True}
        pos = 0
        for kind, pat, default in params:
            if kind == "rest":
                rest = JSArray(INTRINSICS["Array_prototype"])
                for a in args[pos:]:
                    rest.set(str(rest.length()), a)
                    rest.set_length(rest.length() + 1)
                for name in pattern_names(pat):
                    call_env.declare("var", name)
                await self.bind_pattern(pat, rest, call_env)
                pos = len(args)
                break
            val = args[pos] if pos < len(args) else UNDEFINED
            if val is UNDEFINED and default is not None:
                val = await self.eval_expr(default, call_env)
            for name in pattern_names(pat):
                call_env.declare("var", name)
            await self.bind_pattern(pat, val, call_env)
            pos += 1
        self.hoist_block(body[1] if body[0] == "block" else [], call_env)
        if fn.is_async:
            from magpie_jsval import JSPromise
            promise = JSPromise(self)

            async def runner() -> None:
                try:
                    await self.exec_stmt(body, call_env)
                    promise.resolve(UNDEFINED)
                except ReturnExc as e:
                    promise.resolve(e.value)
                except ThrowExc as e:
                    promise.reject(e.value)
                except Exception as e:
                    promise.reject(make_error_value("InternalError", f"async failed: {e}"))

            asyncio.get_running_loop().create_task(runner())
            return promise
        try:
            await self.exec_stmt(body, call_env)
            return UNDEFINED
        except ReturnExc as e:
            return e.value

    async def construct(self, fn: JSValue, args: list):
        if isinstance(fn, JSFunction) and fn.kind == "bound":
            return await self.construct(fn.handler, [*fn.bound_args, *args])
        if not isinstance(fn, JSFunction):
            raise ThrowExc(make_error_value("TypeError", "value is not a constructor"))
        if fn.kind == "native":
            out = fn.handler(fn, args, self)
            if asyncio.iscoroutine(out):
                out = await out
            if isinstance(out, JSObject):
                return out
            raise ThrowExc(make_error_value("TypeError", "native constructor returned a primitive"))
        if fn.is_async:
            raise ThrowExc(make_error_value("TypeError", "async function is not a constructor"))
        _, params, body = fn.node
        info = fn.class_info or {}
        call_env = Environment(fn.env, var_scope=True, strict=True)
        call_env.record["new.target"] = {"kind": "var", "value": fn, "init": True}
        call_env.record["__home__"] = {"kind": "var", "value": fn.home or UNDEFINED, "init": True}
        info = dict(info)
        info["ctor"] = fn
        call_env.record["__ctor__"] = {"kind": "var", "value": info, "init": True}
        arg_obj = JSArray(INTRINSICS["Array_prototype"])
        for a in args:
            arg_obj.set(str(arg_obj.length()), a)
            arg_obj.set_length(arg_obj.length() + 1)
        call_env.record["arguments"] = {"kind": "var", "value": arg_obj, "init": True}
        pos = 0
        for kind, pat, default in params:
            if kind == "rest":
                rest = JSArray(INTRINSICS["Array_prototype"])
                for a in args[pos:]:
                    rest.set(str(rest.length()), a)
                    rest.set_length(rest.length() + 1)
                for name in pattern_names(pat):
                    call_env.declare("var", name)
                await self.bind_pattern(pat, rest, call_env)
                break
            val = args[pos] if pos < len(args) else UNDEFINED
            if val is UNDEFINED and default is not None:
                val = await self.eval_expr(default, call_env)
            for name in pattern_names(pat):
                call_env.declare("var", name)
            await self.bind_pattern(pat, val, call_env)
            pos += 1
        self.hoist_block(body[1] if body[0] == "block" else [], call_env)
        if info.get("derived"):
            call_env.record["this"] = {"kind": "var", "value": UNDEFINED, "init": False}
            try:
                await self.exec_stmt(body, call_env)
            except ReturnExc as e:
                if isinstance(e.value, JSObject):
                    return e.value
                # Primitive returns from derived constructors are ignored.
            cell = call_env.record.get("this")
            if cell is None or not cell["init"]:
                raise ThrowExc(make_error_value("ReferenceError", "this is not initialized (call super first)"))
            return cell["value"]
        proto = fn.get("prototype", recv=fn)
        proto = await resolve_call(proto, self) if isinstance(proto, tuple) else proto
        this = JSObject(proto if isinstance(proto, JSObject) else INTRINSICS["Object_prototype"])
        call_env.record["this"] = {"kind": "var", "value": this, "init": True}
        self.copy_private_methods(fn, this)
        await self.apply_fields(info, call_env)
        try:
            await self.exec_stmt(body, call_env)
        except ReturnExc as e:
            if isinstance(e.value, JSObject):
                return e.value
            # Primitive returns from base constructors are ignored.
            return this
        return this

    def copy_private_methods(self, fn: JSFunction, this: JSObject) -> None:
        info = fn.class_info or {}
        for (cls_id, name), (method, static) in (info.get("private_methods") or {}).items():
            if not static:
                this.private_slots[(cls_id, name)] = method

    async def apply_fields(self, info: dict, call_env: Environment) -> None:
        this = call_env.record.get("this", {}).get("value")
        if not isinstance(this, JSObject):
            return
        for key, computed, init_node, cls_id in info.get("fields", []):
            key_name = await self.class_key(key, computed, call_env)
            val = await self.eval_expr(init_node, call_env) if init_node is not None else UNDEFINED
            if isinstance(key_name, tuple) and key_name[0] == "private":
                this.private_slots[(cls_id, key_name[1])] = val
            else:
                this.define_own(key_name, val)
        for (cls_id, name), (method, static) in (info.get("private_methods") or {}).items():
            if not static:
                this.private_slots.setdefault((cls_id, name), method)

    async def call_method(self, recv: JSValue, name: str, args: list):
        fn = await prop_get(self, recv, name)
        return await self.call_value(fn, recv, args)

    async def eval_class(self, name: str, heritage, members, env: Environment):
        parent_ctor = None
        parent_proto: JSValue = INTRINSICS["Object_prototype"]
        if heritage is not None:
            parent_ctor = await self.eval_expr(heritage, env)
            if parent_ctor is NULL:
                parent_proto = NULL
            elif isinstance(parent_ctor, JSFunction):
                proto = parent_ctor.get("prototype", recv=parent_ctor)
                proto = await resolve_call(proto, self) if isinstance(proto, tuple) else proto
                parent_proto = proto if isinstance(proto, JSObject) else INTRINSICS["Object_prototype"]
            else:
                raise ThrowExc(make_error_value("TypeError", "extends needs a constructor or null"))
        inner = Environment(env, strict=True)
        proto = JSObject(INTRINSICS["Object_prototype"])
        cls_id = id(members)
        info: dict = {
            "derived": parent_ctor is not None,
            "parent": parent_ctor,
            "fields": [],
            "private_methods": {},
            "class_id": cls_id,
        }
        ctor_member = next((m for m in members if m[0] == "method" and m[1] == "ctor" and not m[2]), None)
        if ctor_member is not None:
            _, _, _, _, _, func = ctor_member
            ctor = self.make_function(name, func[1], func[2], inner, func[3], False, home=proto)
        elif info["derived"]:
            ctor = self.make_default_derived_ctor(name, inner, parent_ctor)
        else:
            ctor = self.make_function(name, [], ("block", []), inner, False, False, home=proto)
        ctor.class_info = info
        ctor.name = name
        ctor.define_own("name", JSString(name), enumerable=False)
        ctor.define_own("prototype", proto, enumerable=False)
        proto.define_own("constructor", ctor, enumerable=False)
        if parent_ctor is not None:
            ctor.proto = parent_ctor
        if parent_proto is NULL:
            proto.proto = None
        else:
            proto.proto = parent_proto if isinstance(parent_proto, JSObject) else INTRINSICS["Object_prototype"]
        static_scope = Environment(inner, strict=True)
        static_scope.record["this"] = {"kind": "var", "value": ctor, "init": True}
        for m in members:
            if m[0] == "static_block":
                await self.exec_stmt(m[1], static_scope)
                continue
            if m[0] == "field":
                _, static, key, computed, init = m
                if static:
                    key_name = await self.class_key(key, computed, static_scope)
                    val = await self.eval_expr(init, static_scope) if init is not None else UNDEFINED
                    if isinstance(key_name, tuple) and key_name[0] == "private":
                        ctor.private_slots[(cls_id, key_name[1])] = val
                    else:
                        ctor.define_own(key_name, val)
                else:
                    info["fields"].append((key, computed, init, cls_id))
                continue
            _, kind, static, key, computed, func = m
            if kind == "ctor":
                continue
            fn = self.make_function("", func[1], func[2], inner, func[3], False)
            key_name = await self.class_key(key, computed, inner if not static else static_scope)
            if isinstance(key_name, tuple) and key_name[0] == "private":
                info["private_methods"][(cls_id, key_name[1])] = (fn, static)
                continue
            if static:
                fn.home = ctor
                if kind == "method":
                    ctor.define_own(key_name, fn, enumerable=False)
                else:
                    old = ctor.props.get(key_name)
                    getter = old.get("get") if old else None
                    setter = old.get("set") if old else None
                    if kind == "get":
                        getter = fn
                    else:
                        setter = fn
                    ctor.define_accessor(key_name, getter, setter, enumerable=False)
            else:
                fn.home = proto
                if kind == "method":
                    proto.define_own(key_name, fn, enumerable=False)
                else:
                    old = proto.props.get(key_name)
                    getter = old.get("get") if old else None
                    setter = old.get("set") if old else None
                    if kind == "get":
                        getter = fn
                    else:
                        setter = fn
                    proto.define_accessor(key_name, getter, setter, enumerable=False)
        if name:
            inner.declare("let", name)
            inner.initialize(name, ctor)
        return ctor

    def make_default_derived_ctor(self, name: str, env: Environment, parent):
        params = [("rest", ("ident", "args"), None)]
        body = ("block", [("expr", ("call", ("super",), [("spread", ("ident", "args"))], False))])
        fn = self.make_function(name, params, body, env, False, False)
        fn.class_info = {"derived": True, "parent": parent, "fields": [], "private_methods": {}, "class_id": id(body)}
        return fn

    async def class_key(self, key, computed: bool, env: Environment):
        if not computed:
            if key[0] == "ident":
                return key[1]
            if key[0] == "str":
                return key[1]
            if key[0] == "num":
                from magpie_jsparse import js_number_key
                return js_number_key(key[1])
            if key[0] == "private":
                return ("private", key[1])
            if key[0] == "computed":
                return await prop_key(await self.eval_expr(key[1], env), self)
        return await prop_key(await self.eval_expr(key[1], env), self)


async def run_with_budget(interp: Interpreter, coro, *, budget_ms: float):
    try:
        return await asyncio.wait_for(coro, timeout=max(0.05, budget_ms / 1000.0))
    except asyncio.TimeoutError as e:
        raise ThrowExc(make_error_value("RangeError", "script timed out")) from e
