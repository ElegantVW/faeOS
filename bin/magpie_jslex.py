#!/usr/bin/env python3
"""magpie_jslex — Magpie's own JavaScript lexer and parser (stdlib-only)."""
from __future__ import annotations

from dataclasses import dataclass


KEYWORDS = {
    "await", "break", "case", "catch", "class", "const", "continue", "debugger",
    "default", "delete", "do", "else", "enum", "export", "extends", "false",
    "finally", "for", "function", "if", "implements", "import", "in",
    "instanceof", "interface", "let", "new", "null", "of", "package",
    "private", "protected", "public", "return", "static", "super", "switch",
    "this", "throw", "true", "try", "typeof", "undefined", "var", "void",
    "while", "with", "yield",
}

PUNCT_4 = (">>>=",)
PUNCT_3 = ("===", "!==", ">>>", "...", "**=", "<<=", ">>=", "&&=", "||=", "??=")
PUNCT_2 = (
    "==", "!=", "<=", ">=", "++", "--", "<<", ">>", "**", "&&", "||", "??",
    "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "?.", "=>",
)
PUNCT_1 = set("(){}[].,;:?~!%^&*+-/<>=|")


@dataclass
class Token:
    kind: str
    value: object
    line: int
    col: int
    nl: bool = False


class LexError(Exception):
    pass


class Lexer:
    def __init__(self, src: str, name: str = "<script>") -> None:
        self.src = src
        self.name = name
        self.i = 0
        self.n = len(src)
        self.line = 1
        self.col = 1
        self.newline = False

    def peek_char(self, k: int = 0) -> str:
        j = self.i + k
        return self.src[j] if j < self.n else ""

    def advance(self, k: int = 1) -> None:
        for _ in range(k):
            if self.i >= self.n:
                return
            if self.src[self.i] == "\n":
                self.line += 1
                self.col = 1
                self.newline = True
            else:
                self.col += 1
            self.i += 1

    def error(self, msg: str) -> LexError:
        return LexError(f"{self.name}:{self.line}:{self.col}: {msg}")

    def skip_space(self) -> None:
        while self.i < self.n:
            c = self.src[self.i]
            if c in " \t\r\n\v\f﻿":
                self.advance()
            elif c == "/" and self.peek_char(1) == "/":
                while self.i < self.n and self.src[self.i] != "\n":
                    self.advance()
            elif c == "/" and self.peek_char(1) == "*":
                self.advance(2)
                while self.i < self.n and not (self.src[self.i] == "*" and self.peek_char(1) == "/"):
                    self.advance()
                self.advance(2)
            else:
                break

    def tokenize(self) -> list[Token]:
        if self.src.startswith("#!"):
            while self.i < self.n and self.src[self.i] != "\n":
                self.advance()
        toks: list[Token] = []
        allow_regex = True
        while True:
            self.skip_space()
            if self.i >= self.n:
                toks.append(Token("eof", "", self.line, self.col, self.newline))
                return toks
            c = self.src[self.i]
            nl = self.newline
            self.newline = False
            line, col = self.line, self.col
            if c == "`":
                toks.append(self.lex_template(line, col, nl))
                allow_regex = False
            elif c in "\"'":
                toks.append(Token("str", self.lex_string(), line, col, nl))
                allow_regex = False
            elif c.isdigit() or (c == "." and self.peek_char(1).isdigit()):
                kind, val = self.lex_number()
                toks.append(Token(kind, val, line, col, nl))
                allow_regex = False
            elif c == "#" and (self.peek_char(1).isalpha() or self.peek_char(1) in "_$"):
                self.advance()
                toks.append(Token("private", self.lex_name(), line, col, nl))
                allow_regex = False
            elif c.isalpha() or c in "_$":
                name = self.lex_name()
                toks.append(Token("name", name, line, col, nl))
                allow_regex = name in (
                    "return", "throw", "case", "do", "else", "in", "of", "new",
                    "typeof", "void", "delete", "yield", "await", "function",
                    "class", "import", "export", "extends", "super", "this",
                )
            elif c == "/" and allow_regex and self.peek_char(1) not in ("/", "*"):
                toks.append(Token("regex", self.lex_regex(), line, col, nl))
                allow_regex = False
            else:
                punct = self.lex_punct()
                toks.append(Token("punct", punct, line, col, nl))
                allow_regex = punct not in (")", "]", "}", "++", "--")
                if punct in ("(", ",", "=", ":", "[", "!", "~", "+", "-", "*", "/", "%", "&", "|", "^", "?", ";", "{"):
                    allow_regex = True

    def lex_name(self) -> str:
        start = self.i
        while self.i < self.n and (self.src[self.i].isalnum() or self.src[self.i] in "_$"):
            self.advance()
        return self.src[start:self.i]

    def lex_number(self) -> tuple[str, object]:
        start = self.i
        if self.src.startswith(("0x", "0X", "0b", "0B", "0o", "0O"), self.i):
            while self.i < self.n and (self.src[self.i].isalnum() or self.src[self.i] == "_"):
                self.advance()
            text = self.src[start:self.i].replace("_", "")
            bigint = text.endswith(("n", "N"))
            if bigint:
                text = text[:-1]
            try:
                val = int(text, 0)
            except ValueError as e:
                raise self.error("bad numeric literal") from e
            return ("bigint", val) if bigint else ("num", float(val))
        while self.i < self.n and (self.src[self.i].isdigit() or self.src[self.i] == "_"):
            self.advance()
        if self.peek_char() == "." and self.peek_char(1) != ".":
            self.advance()
            while self.i < self.n and (self.src[self.i].isdigit() or self.src[self.i] == "_"):
                self.advance()
        if self.peek_char() in "eE":
            j = self.i + 1
            if j < self.n and self.src[j] in "+-":
                j += 1
            if j < self.n and self.src[j].isdigit():
                self.advance(j - self.i)
                while self.i < self.n and (self.src[self.i].isdigit() or self.src[self.i] == "_"):
                    self.advance()
        text = self.src[start:self.i].replace("_", "")
        fractional = "." in text or "e" in text.lower()
        bigint = False
        if not fractional and self.peek_char() in ("n", "N") and text and text[-1].isdigit():
            self.advance()
            bigint = True
        if bigint:
            try:
                return ("bigint", int(text or "0", 10))
            except ValueError as e:
                raise self.error("bad bigint literal") from e
        try:
            return ("num", float(text))
        except ValueError as e:
            raise self.error("bad numeric literal") from e

    def lex_string(self) -> str:
        quote = self.src[self.i]
        self.advance()
        out: list[str] = []
        while self.i < self.n:
            c = self.src[self.i]
            if c == quote:
                self.advance()
                return "".join(out)
            if c == "\n":
                raise self.error("unterminated string")
            if c != "\\":
                out.append(c)
                self.advance()
                continue
            self.advance()
            e = self.src[self.i] if self.i < self.n else ""
            if e == "n":
                out.append("\n"); self.advance()
            elif e == "r":
                out.append("\r"); self.advance()
            elif e == "t":
                out.append("\t"); self.advance()
            elif e == "b":
                out.append("\b"); self.advance()
            elif e == "f":
                out.append("\f"); self.advance()
            elif e == "v":
                out.append("\v"); self.advance()
            elif e == "0" and not self.peek_char(1).isdigit():
                out.append("\0"); self.advance()
            elif e == "x":
                h = self.src[self.i + 1:self.i + 3]
                if len(h) != 2 or any(ch not in "0123456789abcdefABCDEF" for ch in h):
                    raise self.error("bad hex escape")
                out.append(chr(int(h, 16))); self.advance(3)
            elif e == "u":
                out.append(self.lex_unicode_escape())
            elif e == "\n":
                self.advance()
            elif e == "\r":
                self.advance()
                if self.peek_char() == "\n":
                    self.advance()
            else:
                out.append(e if e else "\\")
                if e:
                    self.advance()
        raise self.error("unterminated string")

    def lex_unicode_escape(self) -> str:
        self.advance()
        if self.peek_char() == "{":
            self.advance()
            start = self.i
            while self.i < self.n and self.src[self.i] != "}":
                self.advance()
            if self.i >= self.n:
                raise self.error("bad unicode escape")
            text = self.src[start:self.i]
            self.advance()
            try:
                return chr(int(text, 16))
            except ValueError as e:
                raise self.error("bad unicode escape") from e
        h = self.src[self.i:self.i + 4]
        if len(h) != 4 or any(ch not in "0123456789abcdefABCDEF" for ch in h):
            raise self.error("bad unicode escape")
        self.advance(4)
        return chr(int(h, 16))

    def lex_template(self, line: int, col: int, nl: bool) -> Token:
        self.advance()
        parts: list[tuple[str, object]] = []
        cooked: list[str] = []
        while self.i < self.n:
            c = self.src[self.i]
            if c == "`":
                self.advance()
                parts.append(("str", "".join(cooked)))
                return Token("template", parts, line, col, nl)
            if c == "$" and self.peek_char(1) == "{":
                parts.append(("str", "".join(cooked)))
                cooked = []
                self.advance(2)
                depth = 1
                start = self.i
                while self.i < self.n and depth:
                    if self.src[self.i] == "{":
                        depth += 1
                    elif self.src[self.i] == "}":
                        depth -= 1
                        if depth == 0:
                            break
                    elif self.src[self.i] in "\"'`":
                        sub = Lexer(self.src[self.i:], self.name)
                        sub.line, sub.col = self.line, self.col
                        if self.src[self.i] == "`":
                            sub.lex_template(self.line, self.col, False)
                        else:
                            sub.lex_string()
                        self.i += sub.i
                        self.line, self.col = sub.line, sub.col
                        continue
                    self.advance()
                expr_src = self.src[start:self.i]
                self.advance()
                sub = Lexer(expr_src, self.name)
                parts.append(("expr", sub.tokenize()))
                continue
            if c == "\\":
                self.advance()
                e = self.src[self.i] if self.i < self.n else ""
                if e == "n":
                    cooked.append("\n"); self.advance()
                elif e == "r":
                    cooked.append("\r"); self.advance()
                elif e == "t":
                    cooked.append("\t"); self.advance()
                elif e in ("`", "$", "\\"):
                    cooked.append(e); self.advance()
                elif e == "u":
                    cooked.append(self.lex_unicode_escape())
                elif e == "\n":
                    self.advance()
                elif e == "\r":
                    self.advance()
                    if self.peek_char() == "\n":
                        self.advance()
                else:
                    cooked.append(e)
                    if e:
                        self.advance()
                continue
            cooked.append(c)
            self.advance()
        raise self.error("unterminated template")

    def lex_regex(self) -> tuple[str, str]:
        self.advance()
        pat: list[str] = []
        in_class = False
        while self.i < self.n:
            c = self.src[self.i]
            if c == "\n":
                raise self.error("unterminated regex")
            if c == "\\":
                pat.append(c)
                self.advance()
                if self.i < self.n:
                    pat.append(self.src[self.i])
                    self.advance()
                continue
            if c == "[":
                in_class = True
            elif c == "]":
                in_class = False
            elif c == "/" and not in_class:
                self.advance()
                flags = ""
                while self.i < self.n and self.src[self.i].isalpha():
                    flags += self.src[self.i]
                    self.advance()
                return ("".join(pat), flags)
            pat.append(c)
            self.advance()
        raise self.error("unterminated regex")

    def lex_punct(self) -> str:
        for size, table in ((4, PUNCT_4), (3, PUNCT_3), (2, PUNCT_2)):
            cand = self.src[self.i:self.i + size]
            if cand in table:
                if cand == "?." and self.i + 2 < self.n and self.src[self.i + 2].isdigit():
                    break
                self.advance(size)
                return cand
        c = self.src[self.i]
        if c not in PUNCT_1:
            raise self.error(f"unexpected character {c!r}")
        self.advance()
        return c
