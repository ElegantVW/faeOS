#!/usr/bin/env python3
"""magpie_jsparse — Magpie's own JavaScript parser (stdlib-only)."""
from __future__ import annotations

from magpie_jslex import KEYWORDS, Lexer, Token


class ParseError(Exception):
    pass


def js_number_key(v: float) -> str:
    if v.is_integer() and abs(v) < 1e21:
        return str(int(v))
    return repr(v)


class Parser:
    def __init__(self, tokens: list[Token], name: str = "<script>") -> None:
        self.toks = tokens
        self.pos = 0
        self.name = name
        self.in_function = 0
        self.in_async = 0
        self.in_loop = 0
        self.in_switch = 0

    def peek(self, k: int = 0) -> Token:
        j = self.pos + k
        if j >= len(self.toks):
            return self.toks[-1]
        return self.toks[j]

    def next(self) -> Token:
        t = self.peek()
        if self.pos < len(self.toks):
            self.pos += 1
        return t

    def error(self, msg: str, tok: Token | None = None) -> ParseError:
        t = tok or self.peek()
        return ParseError(f"{self.name}:{t.line}:{t.col}: {msg}")

    def at_punct(self, v: str, k: int = 0) -> bool:
        t = self.peek(k)
        return t.kind == "punct" and t.value == v

    def at_name(self, v: str, k: int = 0) -> bool:
        t = self.peek(k)
        return t.kind == "name" and t.value == v

    def expect_punct(self, v: str) -> Token:
        if not self.at_punct(v):
            raise self.error(f"expected {v!r}")
        return self.next()

    def semicolon(self) -> None:
        if self.at_punct(";"):
            self.next()
            return
        t = self.peek()
        if t.nl or t.kind == "eof" or (t.kind == "punct" and t.value == "}"):
            return
        raise self.error("expected semicolon")

    def parse_program(self, *, module: bool = False):
        stmts = []
        if module:
            self.in_async += 1
        try:
            while self.peek().kind != "eof":
                stmts.append(self.parse_statement(module=module))
        finally:
            if module:
                self.in_async -= 1
        return ("program", stmts, module)

    def parse_statement(self, *, module: bool = False):
        t = self.peek()
        if t.kind == "punct" and t.value == ";":
            self.next()
            return ("empty",)
        if t.kind == "punct" and t.value == "{":
            return self.parse_block()
        if t.kind == "name":
            if t.value in ("var", "let", "const"):
                return self.parse_var_statement()
            if t.value == "async" and self.peek(1).kind == "name" and self.peek(1).value == "function":
                self.next(); self.next()
                ident = None
                if self.peek().kind == "name" and self.peek().value not in KEYWORDS:
                    ident = self.next().value
                else:
                    raise self.error("function needs a name")
                params = self.parse_params()
                self.in_function += 1
                self.in_async += 1
                try:
                    body = self.parse_block()
                finally:
                    self.in_async -= 1
                    self.in_function -= 1
                return ("func_decl", ident, params, body, True, False)
            if t.value == "function":
                return self.parse_function_decl()
            if t.value == "class":
                return self.parse_class_decl()
            if t.value == "if":
                return self.parse_if()
            if t.value == "switch":
                return self.parse_switch()
            if t.value == "for":
                return self.parse_for()
            if t.value == "while":
                return self.parse_while()
            if t.value == "do":
                return self.parse_do()
            if t.value == "try":
                return self.parse_try()
            if t.value == "throw":
                self.next()
                if self.peek().nl:
                    raise self.error("throw needs an expression on the same line")
                node = self.parse_expression()
                self.semicolon()
                return ("throw", node)
            if t.value == "return":
                if not self.in_function:
                    raise self.error("return outside function")
                self.next()
                nxt = self.peek()
                if nxt.nl or (nxt.kind == "punct" and nxt.value in (";", "}",)) or nxt.kind == "eof":
                    val = ("undef",)
                else:
                    val = self.parse_expression()
                self.semicolon()
                return ("return", val)
            if t.value in ("break", "continue"):
                self.next()
                label = None
                nxt = self.peek()
                if nxt.kind == "name" and not nxt.nl and nxt.value not in KEYWORDS and nxt.value not in ("in", "of", "instanceof"):
                    label = nxt.value
                    self.next()
                self.semicolon()
                if t.value == "break" and not label and not self.in_loop and not self.in_switch:
                    raise self.error("break outside loop or switch")
                if t.value == "continue" and not label and not self.in_loop:
                    raise self.error("continue outside loop")
                return (t.value, label)
            if t.value == "debugger":
                self.next()
                self.semicolon()
                return ("debugger",)
            if t.value == "with":
                self.next()
                self.expect_punct("(")
                obj = self.parse_expression()
                self.expect_punct(")")
                return ("with", obj, self.parse_statement())
            if t.value == "export" and module:
                return self.parse_export()
            if t.value == "import" and module and self.peek(1).kind == "punct" and self.peek(1).value != "(":
                return self.parse_import()
            if self.peek(1).kind == "punct" and self.peek(1).value == ":":
                label = t.value
                self.next(); self.next()
                return ("label", label, self.parse_statement(module=module))
        expr = self.parse_expression()
        self.semicolon()
        return ("expr", expr)

    def parse_block(self):
        self.expect_punct("{")
        stmts = []
        while not self.at_punct("}"):
            if self.peek().kind == "eof":
                raise self.error("unterminated block")
            stmts.append(self.parse_statement())
        self.expect_punct("}")
        return ("block", stmts)

    def parse_var_statement(self):
        kind = self.next().value
        decls = [self.parse_declarator()]
        while self.at_punct(","):
            self.next()
            decls.append(self.parse_declarator())
        self.semicolon()
        return ("var", kind, decls)

    def parse_declarator(self):
        pat = self.parse_binding_pattern()
        init = None
        if self.at_punct("="):
            self.next()
            init = self.parse_assignment()
        return (pat, init)

    def parse_binding_pattern(self):
        t = self.peek()
        if t.kind == "punct" and t.value == "[":
            self.next()
            elems = []
            while not self.at_punct("]"):
                if self.peek().kind == "eof":
                    raise self.error("unterminated pattern")
                if self.at_punct(","):
                    self.next()
                    elems.append(("hole",))
                    continue
                if self.at_punct("..."):
                    self.next()
                    elems.append(("rest", self.parse_binding_pattern()))
                    if not self.at_punct("]"):
                        raise self.error("rest must be last")
                    break
                pat = self.parse_binding_pattern()
                if self.at_punct("="):
                    self.next()
                    pat = ("default", pat, self.parse_assignment())
                elems.append(pat)
                if self.at_punct(","):
                    self.next()
            self.expect_punct("]")
            return ("array_pat", elems)
        if t.kind == "punct" and t.value == "{":
            self.next()
            props = []
            while not self.at_punct("}"):
                if self.peek().kind == "eof":
                    raise self.error("unterminated pattern")
                if self.at_punct("..."):
                    self.next()
                    props.append(("rest", self.parse_binding_pattern()))
                    break
                if self.peek().kind == "str":
                    key = ("str", self.next().value)
                elif self.peek().kind == "num":
                    key = ("num", self.next().value)
                elif self.peek().kind == "punct" and self.peek().value == "[":
                    self.next()
                    key = ("computed", self.parse_assignment())
                    self.expect_punct("]")
                else:
                    key = ("ident", self.expect_name())
                if self.at_punct(":"):
                    self.next()
                    pat = self.parse_binding_pattern()
                    if self.at_punct("="):
                        self.next()
                        pat = ("default", pat, self.parse_assignment())
                    props.append(("prop", key, pat))
                elif self.at_punct("="):
                    self.next()
                    props.append(("prop", key, ("default", ("ident", key[1] if key[0] == "ident" else None), self.parse_assignment())))
                else:
                    if key[0] != "ident" or not key[1]:
                        raise self.error("shorthand needs an identifier")
                    props.append(("prop", key, ("ident", key[1])))
                if self.at_punct(","):
                    self.next()
            self.expect_punct("}")
            return ("object_pat", props)
        if t.kind == "name" and t.value not in KEYWORDS:
            self.next()
            return ("ident", t.value)
        raise self.error("expected binding pattern")

    def expect_name(self) -> str:
        t = self.peek()
        if t.kind == "name" and t.value not in KEYWORDS:
            self.next()
            return str(t.value)
        raise self.error("expected identifier")

    def parse_function_decl(self):
        func = self.parse_function_expr(require_id=False)
        if func[1] is None:
            raise self.error("function needs a name")
        return ("func_decl",) + func[1:]

    def parse_function_expr(self, *, require_id: bool = True, async_flag: bool = False):
        self.expect_name_value("function")
        if self.at_punct("*"):
            raise self.error("generators are not supported yet")
        ident = None
        t = self.peek()
        if t.kind == "name" and t.value not in KEYWORDS:
            ident = t.value
            self.next()
        elif require_id:
            raise self.error("function needs a name")
        params = self.parse_params()
        self.in_function += 1
        prev_async = self.in_async
        self.in_async += 1 if async_flag else 0
        body = self.parse_block()
        self.in_async = prev_async
        self.in_function -= 1
        return ("func", ident, params, body, async_flag, False)

    def expect_name_value(self, v: str) -> None:
        t = self.peek()
        if t.kind != "name" or t.value != v:
            raise self.error(f"expected {v!r}")
        self.next()

    def parse_params(self):
        self.expect_punct("(")
        params = []
        while not self.at_punct(")"):
            if self.peek().kind == "eof":
                raise self.error("unterminated parameters")
            if self.at_punct("..."):
                self.next()
                params.append(("rest", self.parse_binding_pattern(), None))
            else:
                pat = self.parse_binding_pattern()
                default = None
                if self.at_punct("="):
                    self.next()
                    default = self.parse_assignment()
                params.append(("param", pat, default))
            if self.at_punct(","):
                self.next()
        self.expect_punct(")")
        return params

    def parse_class_decl(self):
        node = self.parse_class_expr(require_id=True)
        return ("class_decl",) + node[1:]

    def parse_class_expr(self, *, require_id: bool = False):
        self.expect_name_value("class")
        ident = None
        t = self.peek()
        if t.kind == "name" and t.value not in KEYWORDS:
            ident = t.value
            self.next()
        elif require_id:
            raise self.error("class needs a name")
        heritage = None
        if self.at_name("extends"):
            self.next()
            heritage = self.parse_member()
        self.expect_punct("{")
        members = []
        while not self.at_punct("}"):
            if self.peek().kind == "eof":
                raise self.error("unterminated class")
            if self.at_punct(";"):
                self.next()
                continue
            members.append(self.parse_class_member())
        self.expect_punct("}")
        return ("class", ident, heritage, members)

    def parse_class_member(self):
        static = False
        if self.at_name("static"):
            if self.peek(1).kind == "punct" and self.peek(1).value == "{":
                self.next()
                return ("static_block", self.parse_block())
            static = True
            self.next()
        async_flag = False
        if self.at_name("async") and not (self.peek(1).kind == "punct" and self.peek(1).value in ("(", "=", ";", "}")):
            save = self.pos
            self.next()
            t = self.peek()
            if t.kind in ("name", "str", "num", "private") or (t.kind == "punct" and t.value == "["):
                async_flag = True
            else:
                self.pos = save
        if self.at_punct("*"):
            raise self.error("generators are not supported yet")
        t = self.peek()
        if t.kind == "private":
            self.next()
            key, computed = ("private", t.value), False
        elif t.kind == "punct" and t.value == "[":
            self.next()
            key = ("computed", self.parse_assignment())
            self.expect_punct("]")
            computed = True
        elif t.kind == "str":
            key, computed = ("str", self.next().value), False
        elif t.kind == "num":
            key, computed = ("num", self.next().value), False
        elif t.kind == "name":
            key, computed = ("ident", self.next().value), False
        else:
            raise self.error("bad class member")
        if key[0] == "ident" and key[1] in ("get", "set") and not async_flag:
            nxt = self.peek()
            if nxt.kind in ("name", "str", "num", "private") or (nxt.kind == "punct" and nxt.value == "["):
                kind = key[1]
                if nxt.kind == "private":
                    sub, comp = ("private", self.next().value), False
                elif nxt.kind == "punct":
                    self.next()
                    sub = ("computed", self.parse_assignment())
                    self.expect_punct("]")
                    comp = True
                elif nxt.kind == "name":
                    sub, comp = ("ident", self.next().value), False
                elif nxt.kind == "str":
                    sub, comp = ("str", self.next().value), False
                else:
                    sub, comp = ("num", self.next().value), False
                return ("method", kind, static, sub, comp, self.finish_method_body(self.parse_params(), False))
        if self.at_punct("("):
            func = self.finish_method_body(self.parse_params(), async_flag)
            kind = "ctor" if (key == ("ident", "constructor") and not static) else "method"
            return ("method", kind, static, key, computed, func)
        if self.at_punct("="):
            self.next()
            init = self.parse_assignment()
            self.semicolon()
            return ("field", static, key, computed, init)
        if self.at_punct(";") or self.peek().nl or self.at_punct("}"):
            if self.at_punct(";"):
                self.next()
            return ("field", static, key, computed, None)
        raise self.error("bad class member")

    def finish_method_body(self, params, async_flag: bool):
        self.in_function += 1
        prev = self.in_async
        self.in_async += 1 if async_flag else 0
        body = self.parse_block()
        self.in_async = prev
        self.in_function -= 1
        return ("method_func", params, body, async_flag)

    def parse_if(self):
        self.expect_name_value("if")
        self.expect_punct("(")
        test = self.parse_expression()
        self.expect_punct(")")
        cons = self.parse_statement()
        alt = None
        if self.at_name("else"):
            self.next()
            alt = self.parse_statement()
        return ("if", test, cons, alt)

    def parse_switch(self):
        self.expect_name_value("switch")
        self.expect_punct("(")
        disc = self.parse_expression()
        self.expect_punct(")")
        self.expect_punct("{")
        cases = []
        self.in_switch += 1
        try:
            while not self.at_punct("}"):
                if self.peek().kind == "eof":
                    raise self.error("unterminated switch")
                if self.at_name("case"):
                    self.next()
                    test = self.parse_expression()
                    self.expect_punct(":")
                    stmts = []
                    while not self.at_punct("}") and not self.at_name("case") and not self.at_name("default"):
                        stmts.append(self.parse_statement())
                    cases.append((test, stmts))
                elif self.at_name("default"):
                    self.next()
                    self.expect_punct(":")
                    stmts = []
                    while not self.at_punct("}") and not self.at_name("case") and not self.at_name("default"):
                        stmts.append(self.parse_statement())
                    cases.append((None, stmts))
                else:
                    raise self.error("expected case or default")
        finally:
            self.in_switch -= 1
        self.expect_punct("}")
        return ("switch", disc, cases)

    def parse_for(self):
        self.expect_name_value("for")
        if self.at_name("await"):
            raise self.error("for-await is not supported yet")
        self.expect_punct("(")
        if self.peek().kind == "name" and self.peek().value in ("var", "let", "const"):
            kind = self.next().value
            save = self.pos
            try:
                pat = self.parse_binding_pattern()
            except ParseError:
                self.pos = save
                pat = None
            if pat is not None and self.at_name("of"):
                self.next()
                right = self.parse_assignment()
                self.expect_punct(")")
                return ("forof", (kind, pat, None), right, self.loop_body())
            if pat is not None and self.at_name("in"):
                self.next()
                right = self.parse_expression()
                self.expect_punct(")")
                return ("forin", (kind, pat, None), right, self.loop_body())
            self.pos = save
            pat = self.parse_binding_pattern()
            init_expr = None
            if self.at_punct("="):
                self.next()
                init_expr = self.parse_assignment()
            if self.at_name("of"):
                if init_expr is not None:
                    raise self.error("for-of head cannot have an initializer")
                self.next()
                right = self.parse_assignment()
                self.expect_punct(")")
                return ("forof", (kind, pat, None), right, self.loop_body())
            if self.at_name("in"):
                if init_expr is not None and kind != "var":
                    raise self.error("for-in head cannot have an initializer")
                self.next()
                right = self.parse_expression()
                self.expect_punct(")")
                return ("forin", (kind, pat, init_expr), right, self.loop_body())
            self.expect_punct(";")
            test = None if self.at_punct(";") else self.parse_expression()
            self.expect_punct(";")
            update = None if self.at_punct(")") else self.parse_expression()
            self.expect_punct(")")
            return ("for", ("var", kind, [(pat, init_expr)]), test, update, self.loop_body())
        if self.at_punct(";"):
            self.next()
            test = None if self.at_punct(";") else self.parse_expression()
            self.expect_punct(";")
            update = None if self.at_punct(")") else self.parse_expression()
            self.expect_punct(")")
            return ("for", None, test, update, self.loop_body())
        start = self.pos
        expr = self.parse_expression()
        if self.at_name("of"):
            self.next()
            right = self.parse_assignment()
            self.expect_punct(")")
            return ("forof", expr, right, self.loop_body())
        if self.at_name("in"):
            self.next()
            right = self.parse_expression()
            self.expect_punct(")")
            return ("forin", expr, right, self.loop_body())
        self.pos = start
        init = self.parse_expression() if not self.at_punct(";") else None
        self.expect_punct(";")
        test = None if self.at_punct(";") else self.parse_expression()
        self.expect_punct(";")
        update = None if self.at_punct(")") else self.parse_expression()
        self.expect_punct(")")
        return ("for", init, test, update, self.loop_body())

    def loop_body(self):
        self.in_loop += 1
        try:
            return self.parse_statement()
        finally:
            self.in_loop -= 1

    def parse_while(self):
        self.expect_name_value("while")
        self.expect_punct("(")
        test = self.parse_expression()
        self.expect_punct(")")
        return ("while", test, self.loop_body())

    def parse_do(self):
        self.expect_name_value("do")
        body = self.loop_body()
        self.expect_name_value("while")
        self.expect_punct("(")
        test = self.parse_expression()
        self.expect_punct(")")
        self.semicolon()
        return ("do", body, test)

    def parse_try(self):
        self.expect_name_value("try")
        block = self.parse_block()
        handler = None
        final = None
        if self.at_name("catch"):
            self.next()
            param = None
            if self.at_punct("("):
                self.next()
                if not self.at_punct(")"):
                    param = self.parse_binding_pattern()
                self.expect_punct(")")
            handler = (param, self.parse_block())
        if self.at_name("finally"):
            self.next()
            final = self.parse_block()
        if handler is None and final is None:
            raise self.error("try needs catch or finally")
        return ("try", block, handler, final)

    def parse_export(self):
        self.expect_name_value("export")
        if self.at_punct("*"):
            self.next()
            if self.at_name("as"):
                self.next()
                alias = self.expect_name()
                self.expect_name_value("from")
                src = self.expect_module_source()
                self.semicolon()
                return ("export_star_as", alias, src)
            self.expect_name_value("from")
            src = self.expect_module_source()
            self.semicolon()
            return ("export_star", src)
        if self.at_punct("{"):
            self.next()
            items = []
            while not self.at_punct("}"):
                name = self.expect_name()
                alias = name
                if self.at_name("as"):
                    self.next()
                    alias = self.expect_name()
                items.append((name, alias))
                if self.at_punct(","):
                    self.next()
            self.expect_punct("}")
            src = None
            if self.at_name("from"):
                self.next()
                src = self.expect_module_source()
            self.semicolon()
            return ("export_list", items, src)
        if self.at_name("default"):
            self.next()
            if self.peek().kind == "name" and self.peek().value in ("function", "class", "async"):
                return ("export_default", self.parse_statement(module=True))
            expr = self.parse_assignment()
            self.semicolon()
            return ("export_default", ("expr", expr))
        if self.peek().kind == "name" and self.peek().value in ("var", "let", "const", "function", "class", "async"):
            return ("export_decl", self.parse_statement(module=True))
        raise self.error("bad export")

    def parse_import(self):
        self.expect_name_value("import")
        if self.at_punct("("):
            self.pos -= 1
            expr = self.parse_expression()
            self.semicolon()
            return ("expr", expr)
        default = None
        named: list[tuple[str, str]] = []
        namespace = None
        t = self.peek()
        if t.kind == "name" and t.value not in KEYWORDS:
            default = t.value
            self.next()
            if self.at_punct(","):
                self.next()
            else:
                self.expect_name_value("from")
                src = self.expect_module_source()
                self.semicolon()
                return ("import", default, [], None, src)
        if self.at_punct("*"):
            self.next()
            self.expect_name_value("as")
            namespace = self.expect_name()
        elif self.at_punct("{"):
            self.next()
            while not self.at_punct("}"):
                name = self.expect_name()
                alias = name
                if self.at_name("as"):
                    self.next()
                    alias = self.expect_name()
                named.append((name, alias))
                if self.at_punct(","):
                    self.next()
            self.expect_punct("}")
        elif self.peek().kind == "str":
            src = self.next().value
            self.semicolon()
            return ("import_side", str(src))
        else:
            raise self.error("bad import")
        self.expect_name_value("from")
        src = self.expect_module_source()
        self.semicolon()
        return ("import", default, named, namespace, src)

    def expect_module_source(self) -> str:
        t = self.peek()
        if t.kind != "str":
            raise self.error("module source must be a string")
        self.next()
        return str(t.value)

    def parse_expression(self):
        first = self.parse_assignment()
        if self.at_punct(","):
            seq = [first]
            while self.at_punct(","):
                self.next()
                seq.append(self.parse_assignment())
            return ("seq", seq)
        return first

    def parse_assignment(self):
        arrow = self.try_parse_arrow()
        if arrow is not None:
            return arrow
        left = self.parse_conditional()
        t = self.peek()
        if t.kind == "punct" and t.value in ("=", "+=", "-=", "*=", "/=", "%=", "**=", "<<=", ">>=", ">>>=", "&=", "|=", "^=", "&&=", "||=", "??="):
            op = t.value
            self.next()
            return ("assign", op, left, self.parse_assignment())
        return left

    def try_parse_arrow(self):
        save = self.pos
        async_flag = False
        if self.at_name("async"):
            if self.peek(1).kind == "name" and self.peek(1).value == "function":
                return None
            async_flag = True
            self.next()
        t = self.peek()
        params = None
        if t.kind == "name" and t.value not in KEYWORDS and self.peek(1).kind == "punct" and self.peek(1).value == "=>":
            params = [("param", ("ident", t.value), None)]
            self.next(); self.next()
        elif t.kind == "punct" and t.value == "(":
            try:
                self.next()
                plist = []
                while not self.at_punct(")"):
                    if self.peek().kind == "eof":
                        raise self.error("bad arrow parameters")
                    if self.at_punct("..."):
                        self.next()
                        plist.append(("rest", self.parse_binding_pattern(), None))
                    else:
                        pat = self.parse_binding_pattern()
                        default = None
                        if self.at_punct("="):
                            self.next()
                            default = self.parse_assignment()
                        plist.append(("param", pat, default))
                    if self.at_punct(","):
                        self.next()
                self.expect_punct(")")
            except ParseError:
                self.pos = save
                return None
            if not self.at_punct("=>"):
                self.pos = save
                return None
            self.next()
            params = plist
        else:
            self.pos = save
            return None
        if async_flag:
            self.in_async += 1
        self.in_function += 1
        try:
            body = self.parse_block() if self.at_punct("{") else ("return_block", self.parse_assignment())
        finally:
            self.in_function -= 1
            if async_flag:
                self.in_async -= 1
        return ("arrow", params, body, async_flag)

    def parse_conditional(self):
        test = self.parse_nullish()
        if self.at_punct("?"):
            self.next()
            cons = self.parse_assignment()
            self.expect_punct(":")
            return ("cond", test, cons, self.parse_assignment())
        return test

    def parse_nullish(self):
        node = self.parse_logical_or()
        while self.at_punct("??"):
            self.next()
            node = ("binary", "??", node, self.parse_logical_or())
        return node

    def parse_logical_or(self):
        node = self.parse_logical_and()
        while self.at_punct("||"):
            self.next()
            node = ("binary", "||", node, self.parse_logical_and())
        return node

    def parse_logical_and(self):
        node = self.parse_bitwise_or()
        while self.at_punct("&&"):
            self.next()
            node = ("binary", "&&", node, self.parse_bitwise_or())
        return node

    def parse_bitwise_or(self):
        node = self.parse_bitwise_xor()
        while self.at_punct("|") and not self.at_punct("||"):
            self.next()
            node = ("binary", "|", node, self.parse_bitwise_xor())
        return node

    def parse_bitwise_xor(self):
        node = self.parse_bitwise_and()
        while self.at_punct("^"):
            self.next()
            node = ("binary", "^", node, self.parse_bitwise_and())
        return node

    def parse_bitwise_and(self):
        node = self.parse_equality()
        while self.at_punct("&") and not self.at_punct("&&"):
            self.next()
            node = ("binary", "&", node, self.parse_equality())
        return node

    def parse_equality(self):
        node = self.parse_relational()
        while self.peek().kind == "punct" and self.peek().value in ("==", "!=", "===", "!=="):
            op = self.next().value
            node = ("binary", op, node, self.parse_relational())
        return node

    def parse_relational(self):
        node = self.parse_shift()
        while True:
            t = self.peek()
            if t.kind == "punct" and t.value in ("<", ">", "<=", ">="):
                self.next()
                node = ("binary", t.value, node, self.parse_shift())
            elif t.kind == "name" and t.value in ("in", "instanceof"):
                self.next()
                node = ("binary", t.value, node, self.parse_shift())
            else:
                return node

    def parse_shift(self):
        node = self.parse_additive()
        while self.peek().kind == "punct" and self.peek().value in ("<<", ">>", ">>>"):
            op = self.next().value
            node = ("binary", op, node, self.parse_additive())
        return node

    def parse_additive(self):
        node = self.parse_multiplicative()
        while self.peek().kind == "punct" and self.peek().value in ("+", "-"):
            op = self.next().value
            node = ("binary", op, node, self.parse_multiplicative())
        return node

    def parse_multiplicative(self):
        node = self.parse_exponent()
        while self.peek().kind == "punct" and self.peek().value in ("*", "/", "%"):
            op = self.next().value
            node = ("binary", op, node, self.parse_exponent())
        return node

    def parse_exponent(self):
        node = self.parse_unary()
        if self.at_punct("**"):
            self.next()
            node = ("binary", "**", node, self.parse_exponent())
        return node

    def parse_unary(self):
        t = self.peek()
        if t.kind == "punct" and t.value in ("++", "--"):
            self.next()
            return ("update", t.value, self.parse_unary(), True)
        if t.kind == "punct" and t.value in ("+", "-", "~", "!"):
            self.next()
            return ("unary", t.value, self.parse_unary())
        if t.kind == "name" and t.value in ("typeof", "void", "delete"):
            self.next()
            return ("unary", t.value, self.parse_unary())
        if t.kind == "name" and t.value == "await":
            if not self.in_async:
                raise self.error("await outside async function")
            self.next()
            return ("await", self.parse_unary())
        if t.kind == "name" and t.value == "yield":
            raise self.error("generators are not supported yet")
        return self.parse_postfix()

    def parse_postfix(self):
        node = self.parse_member()
        t = self.peek()
        if t.kind == "punct" and t.value in ("++", "--") and not t.nl:
            self.next()
            return ("update", t.value, node, False)
        return node

    def parse_member(self):
        if self.at_name("new"):
            if self.peek(1).kind == "punct" and self.peek(1).value == ".":
                self.next(); self.next()
                if not self.at_name("target"):
                    raise self.error("only new.target is supported")
                self.next()
                return ("new_target",)
            self.next()
            callee = self.parse_new_callee()
            args = self.parse_args() if self.at_punct("(") else []
            return self.parse_chain_tail(("new", callee, args))
        return self.parse_chain_tail(self.parse_primary())

    def parse_new_callee(self):
        # `new` callees allow member access but not calls: `new a.b()` must
        # not parse `a()` as the callee.
        node = self.parse_primary()
        while True:
            t = self.peek()
            if t.kind == "punct" and t.value == ".":
                self.next()
                node = ("member", node, self.parse_property_name(), False, False)
            elif t.kind == "punct" and t.value == "[":
                self.next()
                prop = self.parse_expression()
                self.expect_punct("]")
                node = ("member", node, prop, False, True)
            else:
                return node

    def parse_chain_tail(self, node):
        chain_base = None
        chain_ops: list = []
        while True:
            t = self.peek()
            if t.kind == "punct" and t.value == "?.":
                if chain_base is None:
                    chain_base, chain_ops = node, []
                self.next()
                chain_ops.append(self.parse_chain_op(optional=True))
                continue
            if t.kind == "punct" and t.value in (".", "["):
                if chain_base is not None:
                    chain_ops.append(self.parse_chain_op(optional=False))
                    continue
                if t.value == ".":
                    self.next()
                    node = ("member", node, self.parse_property_name(), False, False)
                else:
                    self.next()
                    prop = self.parse_expression()
                    self.expect_punct("]")
                    node = ("member", node, prop, False, True)
                continue
            if t.kind == "punct" and t.value == "(":
                if chain_base is not None:
                    chain_ops.append(("call", self.parse_args(), False))
                    continue
                node = ("call", node, self.parse_args(), False)
                continue
            if t.kind == "template":
                if chain_base is not None:
                    chain_ops.append(("tagged", t.value, False))
                    self.next()
                    continue
                node = ("tagged", node, t.value)
                self.next()
                continue
            break
        return ("chain", chain_base, chain_ops) if chain_base is not None else node

    def parse_chain_op(self, *, optional: bool):
        t = self.peek()
        if t.kind == "punct" and t.value == "(":
            return ("call", self.parse_args(), optional)
        if t.kind == "punct" and t.value == "[":
            self.next()
            prop = self.parse_expression()
            self.expect_punct("]")
            return ("member", prop, True, optional)
        return ("member", self.parse_property_name(), False, optional)

    def parse_property_name(self):
        t = self.peek()
        if t.kind == "name":
            self.next()
            return ("literal_prop", t.value)
        if t.kind == "str":
            self.next()
            return ("literal_prop", t.value)
        if t.kind == "num":
            self.next()
            return ("literal_prop", js_number_key(t.value))
        if t.kind == "private":
            self.next()
            return ("private_prop", t.value)
        raise self.error("expected property name")

    def parse_args(self):
        self.expect_punct("(")
        args = []
        while not self.at_punct(")"):
            if self.peek().kind == "eof":
                raise self.error("unterminated call")
            if self.at_punct("..."):
                self.next()
                args.append(("spread", self.parse_assignment()))
            else:
                args.append(self.parse_assignment())
            if self.at_punct(","):
                self.next()
        self.expect_punct(")")
        return args

    def parse_primary(self):
        t = self.peek()
        if t.kind == "name":
            v = t.value
            if v == "true":
                self.next(); return ("bool", True)
            if v == "false":
                self.next(); return ("bool", False)
            if v == "null":
                self.next(); return ("null",)
            if v == "undefined":
                self.next(); return ("undef",)
            if v == "this":
                self.next(); return ("this",)
            if v == "super":
                self.next(); return ("super",)
            if v == "function":
                return self.parse_function_expr(require_id=False)
            if v == "class":
                return self.parse_class_expr()
            if v == "async" and self.peek(1).kind == "name" and self.peek(1).value == "function":
                self.next(); self.next()
                if self.at_punct("*"):
                    raise self.error("generators are not supported yet")
                ident = None
                if self.peek().kind == "name" and self.peek().value not in KEYWORDS:
                    ident = self.next().value
                params = self.parse_params()
                self.in_function += 1
                self.in_async += 1
                try:
                    body = self.parse_block()
                finally:
                    self.in_async -= 1
                    self.in_function -= 1
                return ("func", ident, params, body, True, False)
            if v == "import" and self.peek(1).kind == "punct" and self.peek(1).value == "(":
                self.next()
                return ("dynamic_import", self.parse_args())
            if v == "import" and self.peek(1).kind == "punct" and self.peek(1).value == ".":
                self.next(); self.next()
                if not self.at_name("meta"):
                    raise self.error("only import.meta is supported")
                self.next()
                return ("import_meta",)
            if v not in KEYWORDS:
                self.next()
                return ("ident", v)
            raise self.error(f"unexpected keyword {v!r}")
        if t.kind == "num":
            self.next(); return ("num", t.value)
        if t.kind == "bigint":
            self.next(); return ("bigint", t.value)
        if t.kind == "str":
            self.next(); return ("str", t.value)
        if t.kind == "template":
            self.next(); return ("template", t.value)
        if t.kind == "regex":
            self.next(); return ("regex", t.value[0], t.value[1])
        if t.kind == "punct":
            if t.value == "(":
                self.next()
                if self.at_punct(")"):
                    raise self.error("empty parentheses")
                expr = self.parse_expression()
                self.expect_punct(")")
                return expr
            if t.value == "[":
                return self.parse_array()
            if t.value == "{":
                return self.parse_object()
        raise self.error("expected expression")

    def parse_array(self):
        self.expect_punct("[")
        elems = []
        while not self.at_punct("]"):
            if self.peek().kind == "eof":
                raise self.error("unterminated array")
            if self.at_punct(","):
                self.next()
                elems.append(("hole",))
                continue
            if self.at_punct("..."):
                self.next()
                elems.append(("spread", self.parse_assignment()))
            else:
                elems.append(self.parse_assignment())
            if self.at_punct(","):
                self.next()
        self.expect_punct("]")
        return ("array", elems)

    def parse_object(self):
        self.expect_punct("{")
        props = []
        while not self.at_punct("}"):
            if self.peek().kind == "eof":
                raise self.error("unterminated object")
            if self.at_punct("..."):
                self.next()
                props.append(("spread", self.parse_assignment()))
                if self.at_punct(","):
                    self.next()
                continue
            t = self.peek()
            async_flag = False
            if t.kind == "name" and t.value == "async" and not self.peek(1).nl:
                nxt = self.peek(1)
                if nxt.kind in ("name", "str", "num") or (nxt.kind == "punct" and nxt.value == "["):
                    async_flag = True
                    self.next()
                    t = self.peek()
            if t.kind == "punct" and t.value == "*":
                raise self.error("generators are not supported yet")
            if t.kind == "punct" and t.value == "[":
                self.next()
                key = ("computed", self.parse_assignment())
                self.expect_punct("]")
                computed = True
            elif t.kind == "str":
                key, computed = ("str", self.next().value), False
            elif t.kind == "num":
                key, computed = ("num", self.next().value), False
            elif t.kind == "name":
                key, computed = ("ident", self.next().value), False
            else:
                raise self.error("bad object key")
            if key[0] == "ident" and key[1] in ("get", "set") and not async_flag:
                nxt = self.peek()
                if nxt.kind in ("name", "str", "num") or (nxt.kind == "punct" and nxt.value == "["):
                    kind = key[1]
                    if nxt.kind == "punct":
                        self.next()
                        sub = ("computed", self.parse_assignment())
                        self.expect_punct("]")
                        comp = True
                    elif nxt.kind == "name":
                        sub, comp = ("ident", self.next().value), False
                    elif nxt.kind == "str":
                        sub, comp = ("str", self.next().value), False
                    else:
                        sub, comp = ("num", self.next().value), False
                    props.append(("accessor", kind, sub, comp, self.finish_method_body(self.parse_params(), False)))
                    if self.at_punct(","):
                        self.next()
                    continue
            if self.at_punct(":"):
                self.next()
                props.append(("value", key, computed, self.parse_assignment()))
            elif self.at_punct("("):
                props.append(("method", key, computed, self.finish_method_body(self.parse_params(), async_flag)))
            else:
                if key[0] != "ident" or computed or async_flag:
                    raise self.error("bad shorthand property")
                props.append(("shorthand", key[1]))
            if self.at_punct(","):
                self.next()
        self.expect_punct("}")
        return ("object", props)


def parse_source(src: str, *, name: str = "<script>", module: bool = False):
    return Parser(Lexer(src, name).tokenize(), name).parse_program(module=module)
