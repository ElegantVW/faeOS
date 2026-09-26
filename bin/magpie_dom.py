#!/usr/bin/env python3
"""magpie_dom — Magpie's own HTML/CSS/page engine.

Stdlib-only and dependency-free: tokenizer, DOM, selector engine, a CSS
subset, terminal layout, forms, media discovery, and article extraction.

The goal is not to out-Chromium Chromium. The goal is a legible, navigable
document model that Magpie fully owns: no bs4/lxml/tinycss2, no downloaded
parsers, no bridges.
"""
from __future__ import annotations

import html as html_lib
import re
import unicodedata
from dataclasses import dataclass, field
from html.entities import html5


VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}
RAW_TEXT_TAGS = {"script", "style", "textarea", "title", "noscript"}
BLOCK_TAGS = {
    "address", "article", "aside", "blockquote", "body", "details", "dialog",
    "div", "dl", "dt", "dd", "fieldset", "figcaption", "figure", "footer",
    "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hgroup", "hr",
    "li", "main", "nav", "ol", "p", "pre", "section", "table", "ul",
}
TABLE_SECTION_TAGS = {"thead", "tbody", "tfoot", "tr", "td", "th", "caption", "colgroup"}
SKIP_TAGS = {"head", "script", "style", "template"}
FORM_CONTROLS = {"input", "select", "textarea", "button"}


def cell_width(ch: str) -> int:
    if not ch:
        return 0
    o = ord(ch)
    if o < 32 or 0x7F <= o < 0xA0:
        return 0
    if unicodedata.combining(ch):
        return 0
    if unicodedata.east_asian_width(ch) in ("F", "W"):
        return 2
    if 0x1F300 <= o <= 0x1FAFF:
        return 2
    return 1


def vis_len(text: str) -> int:
    return sum(cell_width(c) for c in text)


def wrap_text(text: str, width: int, *, preserve_spaces: bool = False) -> list[str]:
    width = max(8, width)
    if preserve_spaces:
        return [line[:width] if vis_len(line) > width else line for line in text.splitlines() or [""]]
    out: list[str] = []
    for raw in text.splitlines() or [""]:
        if not raw.strip():
            out.append("")
            continue
        words = re.split(r"(\s+)", raw)
        cur = ""
        for tok in words:
            if not tok:
                continue
            if not tok.strip():
                if cur and not cur.endswith(" "):
                    cur += " "
                continue
            trial = cur + tok
            if vis_len(trial) <= width:
                cur = trial
            else:
                if cur:
                    out.append(cur.rstrip())
                while vis_len(tok) > width:
                    chunk, w = [], 0
                    for ch in tok:
                        cw = cell_width(ch)
                        if w + cw > width:
                            break
                        chunk.append(ch)
                        w += cw
                    out.append("".join(chunk))
                    tok = tok[len("".join(chunk)):]
                cur = tok + " "
        if cur.strip():
            out.append(cur.rstrip())
    return out or [""]


class Node:
    __slots__ = ("tag", "attrs", "children", "parent", "text", "script_state")

    def __init__(self, tag: str, attrs: dict[str, str] | None = None, parent: Node | None = None, text: str = "") -> None:
        self.tag = tag.lower()
        self.attrs: dict[str, str] = dict(attrs or {})
        self.children: list[Node] = []
        self.parent = parent
        self.text = text
        # Opaque slot owned by magpie_script (listeners, wrappers, control state).
        self.script_state: dict = {}

    def append(self, child: Node) -> Node:
        child.parent = self
        self.children.append(child)
        return child

    def insert(self, index: int, child: Node) -> Node:
        child.parent = self
        self.children.insert(index, child)
        return child

    def remove(self, child: Node) -> None:
        if child in self.children:
            self.children.remove(child)
            child.parent = None

    def clone(self, deep: bool = True) -> Node:
        out = Node(self.tag, dict(self.attrs), text=self.text)
        if deep:
            for c in self.children:
                out.append(c.clone(True))
        return out

    def iter(self):
        yield self
        for c in self.children:
            yield from c.iter()

    def elements(self):
        for n in self.iter():
            if not n.tag.startswith("#"):
                yield n

    def get_attribute(self, name: str, default: str = "") -> str:
        return self.attrs.get(name.lower(), default)

    def set_attribute(self, name: str, value: str) -> None:
        self.attrs[name.lower()] = str(value)

    def remove_attribute(self, name: str) -> None:
        self.attrs.pop(name.lower(), None)

    def has_attribute(self, name: str) -> bool:
        return name.lower() in self.attrs

    def get_element_by_id(self, ident: str) -> Node | None:
        for n in self.elements():
            if n.get_attribute("id") == ident:
                return n
        return None

    def get_elements_by_tag(self, tag: str) -> list[Node]:
        tag = tag.lower()
        return [n for n in self.elements() if tag == "*" or n.tag == tag]

    def get_elements_by_class(self, cls: str) -> list[Node]:
        return [n for n in self.elements() if cls in n.get_attribute("class").split()]

    def query_selector_all(self, selector: str) -> list[Node]:
        out: list[Node] = []
        for group in split_selector_groups(selector):
            seq = parse_selector(group)
            if seq:
                out.extend(n for n in self.elements() if matches_selector(n, seq))
        # Stable document order, de-duplicated.
        seen: set[int] = set()
        uniq: list[Node] = []
        for n in out:
            if id(n) not in seen:
                seen.add(id(n))
                uniq.append(n)
        return uniq

    def query_selector(self, selector: str) -> Node | None:
        found = self.query_selector_all(selector)
        return found[0] if found else None

    def text_content(self) -> str:
        if self.tag == "#text":
            return self.text
        if self.tag in ("#comment",):
            return ""
        return "".join(c.text_content() for c in self.children)

    def set_text_content(self, value: str) -> None:
        self.children = []
        if value:
            self.append(Node("#text", text=value))

    def inner_html(self) -> str:
        return "".join(serialize_node(c) for c in self.children)

    def set_inner_html(self, markup: str) -> None:
        frag = parse_html(f"<div>{markup}</div>").query_selector("div")
        kids = frag.children if frag else []
        self.children = []
        for k in kids:
            self.append(k)
        mark_parser_inserted(self, False)


def mark_parser_inserted(node: Node, value: bool) -> None:
    for n in node.iter():
        if n.tag == "script":
            n.script_state["parser_inserted"] = value


def escape_html(text: str) -> str:
    return html_lib.escape(text, quote=False).replace("\x00", "")


def serialize_node(node: Node) -> str:
    if node.tag == "#text":
        return escape_html(node.text)
    if node.tag == "#comment":
        return f"<!--{node.text}-->"
    if node.tag == "#document":
        return "".join(serialize_node(c) for c in node.children)
    attrs = "".join(f' {k}="{html_lib.escape(v, quote=True)}"' for k, v in node.attrs.items())
    if node.tag in VOID_TAGS:
        return f"<{node.tag}{attrs}>"
    inner = "".join(serialize_node(c) for c in node.children)
    return f"<{node.tag}{attrs}>{inner}</{node.tag}>"


_ATTR_RE = re.compile(
    r"""\s*(?:(?P<name>[^\s"'`>/=]+)(?:\s*=\s*(?:"(?P<dval>[^"]*)"|'(?P<sval>[^']*)'|(?P<uval>[^\s"'`>/=]+)))?)"""
)


def parse_tag(token: str) -> tuple[str, dict[str, str], bool]:
    token = token.strip()
    self_close = token.endswith("/")
    if self_close:
        token = token[:-1].rstrip()
    m = re.match(r"^[^\s/]+", token)
    tag = (m.group(0).lower() if m else "")
    rest = token[len(m.group(0)):] if m else ""
    attrs: dict[str, str] = {}
    pos = 0
    while pos < len(rest):
        m = _ATTR_RE.match(rest, pos)
        if not m or not m.group("name"):
            pos += 1
            continue
        pos = m.end()
        name = m.group("name").lower()
        val = m.group("dval")
        if val is None:
            val = m.group("sval")
        if val is None:
            val = m.group("uval")
        if val is None:
            val = ""
        attrs[name] = html_lib.unescape(val)
    return tag, attrs, self_close


def parse_html(markup: str, *, js_enabled: bool = False) -> Node:
    """Lenient tree builder with raw-text handling for script/style/textarea."""
    root = Node("#document")
    root.script_state["js_enabled"] = js_enabled
    stack: list[Node] = [root]
    i, n = 0, len(markup)
    text_buf: list[str] = []

    def flush_text() -> None:
        if text_buf:
            data = html_lib.unescape("".join(text_buf))
            if data:
                top = stack[-1]
                if top.children and top.children[-1].tag == "#text":
                    top.children[-1].text += data
                else:
                    top.append(Node("#text", text=data))
            text_buf.clear()

    def current() -> Node:
        return stack[-1]

    def auto_close(tag: str) -> None:
        if tag == "p":
            while len(stack) > 1 and stack[-1].tag == "p":
                stack.pop()
        elif tag in ("li",):
            while len(stack) > 1 and stack[-1].tag == "li":
                stack.pop()
        elif tag in ("dt", "dd"):
            while len(stack) > 1 and stack[-1].tag in ("dt", "dd"):
                stack.pop()
        elif tag in ("option", "optgroup"):
            while len(stack) > 1 and stack[-1].tag in ("option", "optgroup"):
                stack.pop()
        elif tag in ("tr",):
            while len(stack) > 1 and stack[-1].tag == "tr":
                stack.pop()
        elif tag in ("td", "th"):
            while len(stack) > 1 and stack[-1].tag in ("td", "th", "tr"):
                if stack[-1].tag in ("td", "th"):
                    stack.pop()
                    break
                stack.pop()

    while i < n:
        ch = markup[i]
        if ch != "<":
            text_buf.append(ch)
            i += 1
            continue
        # Comment / doctype / declaration / PI.
        if markup.startswith("<!--", i):
            flush_text()
            end = markup.find("-->", i + 4)
            end = n if end < 0 else end + 3
            current().append(Node("#comment", text=markup[i + 4:end - 3 if end != n else n]))
            i = end
            continue
        if markup.startswith("<!doctype", i) or markup.startswith("<!DOCTYPE", i):
            flush_text()
            end = markup.find(">", i)
            i = n if end < 0 else end + 1
            continue
        if markup.startswith("<!", i) or markup.startswith("<?", i):
            flush_text()
            end = markup.find(">", i)
            i = n if end < 0 else end + 1
            continue
        if markup.startswith("</", i):
            flush_text()
            end = markup.find(">", i)
            if end < 0:
                text_buf.append(markup[i:])
                break
            tag = markup[i + 2:end].strip().split()[0].lower() if markup[i + 2:end].strip() else ""
            for j in range(len(stack) - 1, 0, -1):
                if stack[j].tag == tag:
                    del stack[j:]
                    break
            i = end + 1
            continue
        end = markup.find(">", i)
        if end < 0:
            text_buf.append(markup[i:])
            break
        tag, attrs, self_close = parse_tag(markup[i + 1:end])
        if not tag:
            text_buf.append(markup[i:end + 1])
            i = end + 1
            continue
        flush_text()
        if tag in RAW_TEXT_TAGS:
            node = Node(tag, attrs)
            current().append(node)
            close_pat = re.compile(r"</\s*" + re.escape(tag) + r"\s*>", re.I)
            m = close_pat.search(markup, end + 1)
            body = markup[end + 1:m.start()] if m else markup[end + 1:]
            node.append(Node("#text", text=body if tag in ("script", "style") else html_lib.unescape(body)))
            node.script_state["parser_inserted"] = True
            i = m.end() if m else n
            continue
        auto_close(tag)
        node = Node(tag, attrs)
        current().append(node)
        node.script_state["parser_inserted"] = tag == "script"
        if tag not in VOID_TAGS and not self_close:
            stack.append(node)
        i = end + 1
    flush_text()
    return root


# ── selectors ────────────────────────────────────────────────────────────

def split_selector_groups(selector: str) -> list[str]:
    groups, depth, cur = [], 0, []
    for ch in selector:
        if ch in "[(":
            depth += 1
        elif ch in "])":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            groups.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        groups.append("".join(cur).strip())
    return [g for g in groups if g]


@dataclass
class Compound:
    tag: str = "*"
    ident: str = ""
    classes: list[str] = field(default_factory=list)
    attrs: list[tuple[str, str | None, str | None]] = field(default_factory=list)
    pseudo: str = ""


def parse_selector(selector: str) -> list[tuple[str, Compound]]:
    """Right-leaning sequence of (combinator, compound)."""
    tokens: list[tuple[str, Compound]] = []
    i, n = 0, len(selector)
    combinator = " "

    def skip() -> None:
        nonlocal i
        while i < n and selector[i].isspace():
            i += 1

    skip()
    while i < n:
        if selector[i] in ">+~":
            combinator = selector[i]
            i += 1
            skip()
            continue
        comp = Compound()
        if selector[i] == "*":
            i += 1
        elif selector[i].isalpha() or selector[i] in "_-":
            m = re.match(r"[A-Za-z_][\w-]*", selector[i:])
            comp.tag = m.group(0).lower()
            i += len(m.group(0))
        while i < n and (selector[i] in "#.[:" or selector[i] == ":"):
            if selector[i] == "#":
                m = re.match(r"#([\w-]+)", selector[i:])
                if not m:
                    break
                comp.ident = m.group(1)
                i += len(m.group(0))
            elif selector[i] == ".":
                m = re.match(r"\.([\w-]+)", selector[i:])
                if not m:
                    break
                comp.classes.append(m.group(1))
                i += len(m.group(0))
            elif selector[i] == "[":
                end = selector.find("]", i)
                if end < 0:
                    break
                body = selector[i + 1:end]
                m = re.match(r"""\s*([\w-]+)\s*(?:([~|^$*]?=)\s*(?:"([^"]*)"|'([^']*)'|([^\s'"]+))\s*)?$""", body)
                if m:
                    name = m.group(1).lower()
                    op = m.group(2)
                    val = m.group(3) if m.group(3) is not None else (m.group(4) if m.group(4) is not None else m.group(5))
                    comp.attrs.append((name, op, val))
                i = end + 1
            elif selector[i] == ":":
                m = re.match(r":([\w-]+)(?:\(([^)]*)\))?", selector[i:])
                if not m:
                    break
                comp.pseudo = m.group(1).lower() + (f"({m.group(2)})" if m.group(2) else "")
                i += len(m.group(0))
            else:
                break
        tokens.append((combinator, comp))
        combinator = " "
        skip()
    return tokens


def matches_compound(node: Node, comp: Compound) -> bool:
    if comp.tag != "*" and node.tag != comp.tag:
        return False
    if comp.ident and node.get_attribute("id") != comp.ident:
        return False
    classes = node.get_attribute("class").split()
    if any(c not in classes for c in comp.classes):
        return False
    for name, op, val in comp.attrs:
        actual = node.get_attribute(name, None)
        if actual is None:
            return False
        if op is None:
            continue
        if op == "=" and actual != val:
            return False
        if op == "~=" and val not in actual.split():
            return False
        if op == "|=" and not (actual == val or actual.startswith(val + "-")):
            return False
        if op == "^=" and not actual.startswith(val or ""):
            return False
        if op == "$=" and not actual.endswith(val or ""):
            return False
        if op == "*=" and (val or "") not in actual:
            return False
    if comp.pseudo:
        if comp.pseudo == "first-child":
            return node.parent is not None and [c for c in node.parent.children if not c.tag.startswith("#")] and \
                [c for c in node.parent.children if not c.tag.startswith("#")][0] is node
        if comp.pseudo == "last-child":
            elems = [c for c in node.parent.children if not c.tag.startswith("#")] if node.parent else []
            return bool(elems) and elems[-1] is node
        m = re.fullmatch(r"nth-child\((\d+)\)", comp.pseudo)
        if m:
            elems = [c for c in node.parent.children if not c.tag.startswith("#")] if node.parent else []
            try:
                return elems[int(m.group(1)) - 1] is node
            except IndexError:
                return False
        return False
    return True


def matches_selector(node: Node, seq: list[tuple[str, Compound]]) -> bool:
    idx = len(seq) - 1
    cur: Node | None = node
    if cur is None or not matches_compound(cur, seq[idx][1]):
        return False
    idx -= 1
    while idx >= 0:
        combinator, comp = seq[idx + 1][0], seq[idx][1]
        if combinator == " ":
            cur = cur.parent
            while cur is not None and not matches_compound(cur, comp):
                cur = cur.parent
            if cur is None:
                return False
        elif combinator == ">":
            cur = cur.parent if cur else None
            if cur is None or matches_compound(cur, comp) is False:
                return False
        elif combinator == "+":
            if not cur or not cur.parent:
                return False
            sibs = [c for c in cur.parent.children if not c.tag.startswith("#")]
            pos = sibs.index(cur) if cur in sibs else -1
            if pos <= 0 or not matches_compound(sibs[pos - 1], comp):
                return False
            cur = sibs[pos - 1]
        elif combinator == "~":
            if not cur or not cur.parent:
                return False
            sibs = [c for c in cur.parent.children if not c.tag.startswith("#")]
            pos = sibs.index(cur) if cur in sibs else -1
            found = None
            for s in reversed(sibs[:pos]):
                if matches_compound(s, comp):
                    found = s
                    break
            if found is None:
                return False
            cur = found
        else:
            return False
        idx -= 1
    return True


# ── CSS ──────────────────────────────────────────────────────────────────

CSS_NAMED = {
    "black": (0, 0, 0), "silver": (192, 192, 192), "gray": (128, 128, 128), "grey": (128, 128, 128),
    "white": (255, 255, 255), "maroon": (128, 0, 0), "red": (255, 0, 0), "purple": (128, 0, 128),
    "fuchsia": (255, 0, 255), "magenta": (255, 0, 255), "green": (0, 128, 0), "lime": (0, 255, 0),
    "olive": (128, 128, 0), "yellow": (255, 255, 0), "navy": (0, 0, 128), "blue": (0, 0, 255),
    "teal": (0, 128, 128), "aqua": (0, 255, 255), "cyan": (0, 255, 255), "orange": (255, 165, 0),
    "pink": (255, 192, 203), "hotpink": (255, 105, 180), "deeppink": (255, 20, 147),
    "lavender": (230, 230, 250), "violet": (238, 130, 238), "plum": (221, 160, 221),
    "beige": (245, 245, 220), "ivory": (255, 255, 240), "khaki": (240, 230, 140),
    "coral": (255, 127, 80), "salmon": (250, 128, 114), "crimson": (220, 20, 60),
    "brown": (165, 42, 42), "chocolate": (210, 105, 30), "gold": (255, 215, 0),
    "darkred": (139, 0, 0), "darkgreen": (0, 100, 0), "darkblue": (0, 0, 139),
    "darkcyan": (0, 139, 139), "darkmagenta": (139, 0, 139), "darkorange": (255, 140, 0),
    "lightpink": (255, 182, 193), "lightblue": (173, 216, 230), "lightgreen": (144, 238, 144),
    "lightgray": (211, 211, 211), "lightgrey": (211, 211, 211), "darkgray": (169, 169, 169),
    "darkgrey": (169, 169, 169), "dimgray": (105, 105, 105), "dimgrey": (105, 105, 105),
    "slategray": (112, 128, 144), "slategrey": (112, 128, 144), "lightslategray": (119, 136, 153),
    "mistyrose": (255, 228, 225), "peachpuff": (255, 218, 185), "linen": (250, 240, 230),
    "oldlace": (253, 245, 230), "papayawhip": (255, 239, 213), "blanchedalmond": (255, 235, 205),
    "bisque": (255, 228, 196), "wheat": (245, 222, 179), "tan": (210, 180, 140),
}


@dataclass
class CSSColor:
    r: int
    g: int
    b: int
    a: float = 1.0

    def rgb(self) -> tuple[int, int, int]:
        return (max(0, min(255, self.r)), max(0, min(255, self.g)), max(0, min(255, self.b)))


def parse_css_color(text: str) -> CSSColor | None:
    s = (text or "").strip().lower()
    if not s or s == "transparent":
        return CSSColor(0, 0, 0, 0.0)
    if s in CSS_NAMED:
        r, g, b = CSS_NAMED[s]
        return CSSColor(r, g, b, 1.0)
    m = re.fullmatch(r"#([0-9a-f]{3,8})", s)
    if m:
        h = m.group(1)
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        if len(h) == 6:
            return CSSColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 1.0)
        if len(h) == 8:
            return CSSColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16) / 255.0)
        return None
    m = re.fullmatch(r"rgba?\(([^)]*)\)", s)
    if m:
        parts = [p.strip() for p in re.split(r"[,/]", m.group(1)) if p.strip()]
        if len(parts) >= 3:
            rgb = [parse_css_component(p) for p in parts[:3]]
            if all(v is not None for v in rgb):
                alpha = 1.0
                if len(parts) >= 4:
                    a = parts[3].rstrip("%")
                    try:
                        alpha = float(a) / 100.0 if parts[3].endswith("%") else float(a)
                    except ValueError:
                        return None
                return CSSColor(rgb[0], rgb[1], rgb[2], max(0.0, min(1.0, alpha)))
    m = re.fullmatch(r"hsla?\(([^)]*)\)", s)
    if m:
        parts = [p.strip() for p in re.split(r"[,/]", m.group(1)) if p.strip()]
        if len(parts) >= 3:
            try:
                h = float(parts[0].rstrip("deg"))
                sa = float(parts[1].rstrip("%")) / 100.0
                li = float(parts[2].rstrip("%")) / 100.0
                alpha = 1.0
                if len(parts) >= 4:
                    alpha = float(parts[3].rstrip("%")) / 100.0 if parts[3].endswith("%") else float(parts[3])
                return CSSColor(*hsl_to_rgb(h, sa, li), max(0.0, min(1.0, alpha)))
            except ValueError:
                return None
    return None


def parse_css_component(text: str) -> int | None:
    text = text.strip()
    try:
        if text.endswith("%"):
            return max(0, min(255, round(float(text[:-1]) * 255 / 100)))
        return max(0, min(255, round(float(text))))
    except ValueError:
        return None


def hsl_to_rgb(h: float, s: float, li: float) -> tuple[int, int, int]:
    h = (h % 360) / 360.0
    s = max(0.0, min(1.0, s))
    li = max(0.0, min(1.0, li))

    def chan(n: float) -> float:
        k = (n + h * 12) % 12
        a = s * min(li, 1 - li)
        return li - a * max(-1, min(k - 3, 9 - k, 1))

    return (round(chan(0) * 255), round(chan(8) * 255), round(chan(4) * 255))


def rgb_to_ansi256(r: int, g: int, b: int) -> int:
    if r == g == b:
        if r < 8:
            return 16
        if r > 238:
            return 231
        return 232 + round((r - 8) / 247 * 23)
    return 16 + 36 * round(r / 255 * 5) + 6 * round(g / 255 * 5) + round(b / 255 * 5)


def color_ansi(color: CSSColor | None, *, background: bool = False, truecolor: bool = False) -> str:
    if color is None or color.a <= 0.01:
        return ""
    r, g, b = color.rgb()
    if truecolor:
        return f"\x1b[{48 if background else 38};2;{r};{g};{b}m"
    code = rgb_to_ansi256(r, g, b)
    return f"\x1b[{48 if background else 38};5;{code}m"


@dataclass
class CSSRule:
    selectors: list[str]
    declarations: dict[str, str]
    order: int


def strip_css_comments(text: str) -> str:
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def parse_declarations(block: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for chunk in block.split(";"):
        if ":" not in chunk:
            continue
        k, v = chunk.split(":", 1)
        k = k.strip().lower()
        v = v.strip()
        if k and v:
            out[k] = re.sub(r"\s*!important\s*$", "", v, flags=re.I).strip()
    return out


def parse_css(text: str, *, start_order: int = 0) -> list[CSSRule]:
    text = strip_css_comments(text)
    rules: list[CSSRule] = []
    order = start_order
    i, n = 0, len(text)
    while i < n:
        while i < n and text[i].isspace():
            i += 1
        if i >= n:
            break
        if text[i] == "@":
            m = re.match(r"@([\w-]+)([^{;]*)", text[i:])
            if not m:
                break
            name = m.group(1).lower()
            i += m.end()
            if i < n and text[i] == ";":
                i += 1
                continue
            if i < n and text[i] == "{":
                depth = 1
                j = i + 1
                while j < n and depth:
                    if text[j] == "{":
                        depth += 1
                    elif text[j] == "}":
                        depth -= 1
                    j += 1
                inner = text[i + 1:j - 1]
                if name == "media":
                    for rule in parse_css(inner, start_order=order):
                        rules.append(rule)
                        order += 1
                i = j
                continue
            continue
        brace = text.find("{", i)
        if brace < 0:
            break
        selector = text[i:brace].strip()
        depth = 1
        j = brace + 1
        while j < n and depth:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
            j += 1
        decls = parse_declarations(text[brace + 1:j - 1])
        groups = [g.strip() for g in split_selector_groups(selector) if g.strip()]
        if groups and decls:
            rules.append(CSSRule(groups, decls, order))
            order += 1
        i = j
    return rules


def selector_specificity(selector: str) -> tuple[int, int, int]:
    ids = len(re.findall(r"#[\w-]+", selector))
    classes = len(re.findall(r"\.[\w-]+|\[[^\]]+\]|:[\w-]+", selector))
    tags = len(re.findall(r"(?:^|[\s>+~])([A-Za-z_][\w-]*)", selector))
    return (ids, classes, tags)


@dataclass
class ComputedStyle:
    color: CSSColor | None = None
    background: CSSColor | None = None
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strike: bool = False
    align: str = "left"
    display: str = "inline"
    white_space_pre: bool = False
    list_style: str = "disc"


def compute_style(node: Node, rules: list[CSSRule], parent: ComputedStyle | None = None) -> ComputedStyle:
    style = ComputedStyle()
    if parent:
        style.color = parent.color
        style.background = parent.background
        style.bold = parent.bold
        style.italic = parent.italic
    matched: list[tuple[tuple[int, int, int], int, dict[str, str]]] = []
    for rule in rules:
        for sel in rule.selectors:
            seq = parse_selector(sel)
            if seq and matches_selector(node, seq):
                matched.append((selector_specificity(sel), rule.order, rule.declarations))
    matched.sort(key=lambda r: (r[0], r[1]))
    decls: dict[str, str] = {}
    for _, _, d in matched:
        decls.update(d)
    inline = parse_declarations(node.get_attribute("style"))
    decls.update(inline)
    if node.tag in ("b", "strong", "h1", "h2", "h3", "h4", "h5", "h6", "th"):
        style.bold = True
    if node.tag in ("i", "em", "cite", "dfn", "var"):
        style.italic = True
    if node.tag == "u":
        style.underline = True
    if node.tag in ("s", "strike", "del"):
        style.strike = True
    if node.tag in BLOCK_TAGS or node.tag in TABLE_SECTION_TAGS or node.tag in ("tr", "td", "th", "hr", "br", "img"):
        style.display = "block" if node.tag not in ("br", "img", "td", "th") else ("inline" if node.tag != "hr" else "block")
    display = decls.get("display", "").lower()
    if display in ("block", "inline", "none", "list-item", "table", "table-row", "table-cell"):
        style.display = display
    if node.has_attribute("hidden"):
        style.display = "none"
    color = parse_css_color(decls.get("color", ""))
    if color:
        style.color = color
    bg = parse_css_color(decls.get("background-color", "") or decls.get("background", ""))
    if bg and bg.a > 0.01:
        style.background = bg
    fw = decls.get("font-weight", "").lower()
    if fw in ("bold", "bolder") or (fw.isdigit() and int(fw) >= 600):
        style.bold = True
    fs = decls.get("font-style", "").lower()
    if fs in ("italic", "oblique"):
        style.italic = True
    td = decls.get("text-decoration", "").lower()
    if "underline" in td:
        style.underline = True
    if "line-through" in td:
        style.strike = True
    align = decls.get("text-align", "").lower()
    if align in ("left", "center", "right"):
        style.align = align
    if node.tag == "center":
        style.align = "center"
    ws = decls.get("white-space", "").lower()
    if ws.startswith("pre") or node.tag == "pre":
        style.white_space_pre = True
    lst = decls.get("list-style-type", "").lower()
    if lst:
        style.list_style = lst
    return style


# ── page model ───────────────────────────────────────────────────────────

@dataclass
class Segment:
    text: str
    fg: CSSColor | None = None
    bg: CSSColor | None = None
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strike: bool = False
    link: int = 0
    media: int = 0
    field: int = 0
    anchor: str = ""


@dataclass
class Line:
    segments: list[Segment] = field(default_factory=list)
    links: list[int] = field(default_factory=list)
    medias: list[int] = field(default_factory=list)
    fields: list[int] = field(default_factory=list)
    anchor: str = ""

    # Back-compat singulars (first id of each kind).
    @property
    def link(self) -> int:
        return self.links[0] if self.links else 0

    @property
    def media(self) -> int:
        return self.medias[0] if self.medias else 0

    @property
    def field(self) -> int:
        return self.fields[0] if self.fields else 0

    def plain(self) -> str:
        return "".join(s.text for s in self.segments)


@dataclass
class Link:
    ident: int
    url: str
    label: str
    external: bool = False


@dataclass
class Media:
    ident: int
    kind: str  # image | video | audio | frame | object
    url: str
    alt: str = ""
    title: str = ""
    width: int = 0
    height: int = 0
    poster: str = ""
    mime: str = ""


@dataclass
class FormField:
    ident: int
    form: int
    control: Node
    kind: str
    name: str = ""
    value: str = ""
    checked: bool = False
    required: bool = False
    placeholder: str = ""
    options: list[tuple[str, str, bool]] = field(default_factory=list)


@dataclass
class Form:
    ident: int
    node: Node
    action: str
    method: str
    fields: list[int] = field(default_factory=list)


@dataclass
class Page:
    url: str
    title: str
    root: Node
    rules: list[CSSRule]
    lines: list[Line] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    media: list[Media] = field(default_factory=list)
    forms: list[Form] = field(default_factory=list)
    fields: list[FormField] = field(default_factory=list)
    anchors: dict[str, int] = field(default_factory=dict)
    meta_refresh: tuple[int, str] | None = None
    scripts: list[Node] = field(default_factory=list)


class Renderer:
    def __init__(self, page: Page, width: int) -> None:
        self.page = page
        self.width = max(20, width)
        self.lines: list[Line] = []
        self.pending: list[Segment] = []
        self.link_stack: list[int] = []
        self.indent = 0
        self.list_stack: list[tuple[str, int, str]] = []

    def add_link(self, url: str, label: str) -> int:
        ident = len(self.page.links) + 1
        base_host = ""
        try:
            import urllib.parse as _u
            base_host = (_u.urlparse(self.page.url).hostname or "").lower()
            target_host = (_u.urlparse(url).hostname or "").lower()
        except ValueError:
            target_host = ""
        self.page.links.append(Link(ident, url, label[:160], external=bool(target_host and target_host != base_host)))
        return ident

    def add_media(self, kind: str, url: str, **kw) -> int:
        ident = len(self.page.media) + 1
        self.page.media.append(Media(ident, kind, url, **kw))
        return ident

    def text(self, data: str, style: ComputedStyle) -> None:
        if not data:
            return
        link = self.link_stack[-1] if self.link_stack else 0
        seg = Segment(
            data, fg=style.color, bg=style.background, bold=style.bold, italic=style.italic,
            underline=style.underline, strike=style.strike, link=link,
        )
        self.pending.append(seg)

    def flush(self) -> None:
        if not self.pending and not self.lines:
            return
        if not self.pending:
            return
        # Wrap while preserving segment styling/link/media annotations.
        # Zero-width marker segments (form fields) still tag their line.
        mark_links = [s.link for s in self.pending if s.link]
        mark_medias = [s.media for s in self.pending if s.media]
        mark_fields = [s.field for s in self.pending if s.field]
        width = max(8, self.width - self.indent)
        cur: list[Segment] = []
        cur_w = 0

        def emit() -> None:
            if cur:
                prefix = " " * self.indent
                segs = [Segment(prefix)] + cur if prefix else list(cur)
                line = Line(
                    segs,
                    links=[s.link for s in cur if s.link] + mark_links,
                    medias=[s.media for s in cur if s.media] + mark_medias,
                    fields=[s.field for s in cur if s.field] + mark_fields,
                )
                # De-duplicate while keeping document order.
                line.links = list(dict.fromkeys(line.links))
                line.medias = list(dict.fromkeys(line.medias))
                line.fields = list(dict.fromkeys(line.fields))
                self.lines.append(line)
            cur.clear()

        for seg in self.pending:
            remain = seg.text
            while remain:
                room = width - cur_w
                if room <= 0:
                    emit()
                    cur_w = 0
                    room = width
                take, w = [], 0
                for ch in remain:
                    cw = cell_width(ch)
                    if ch == "\n":
                        break
                    if w + cw > room:
                        break
                    take.append(ch)
                    w += cw
                if not take:
                    # Overlong token or newline: hard break.
                    if remain.startswith("\n"):
                        emit()
                        cur_w = 0
                        remain = remain[1:]
                        continue
                    emit()
                    cur_w = 0
                    continue
                piece = "".join(take)
                cur.append(Segment(piece, seg.fg, seg.bg, seg.bold, seg.italic, seg.underline, seg.strike, seg.link, seg.media, seg.field, seg.anchor))
                cur_w += w
                remain = remain[len(piece):]
                if remain.startswith("\n"):
                    emit()
                    cur_w = 0
                    remain = remain[1:]
                elif remain.startswith(" ") and cur_w >= width:
                    emit()
                    cur_w = 0
        emit()
        self.pending = []

    def blank(self, count: int = 1) -> None:
        self.flush()
        for _ in range(max(0, count)):
            if not self.lines or self.lines[-1].plain():
                self.lines.append(Line())

    def heading(self, level: int, node: Node, style: ComputedStyle, parent: ComputedStyle) -> None:
        self.blank(1)
        self.render_children(node, parent)
        self.flush()
        if self.lines and self.lines[-1].plain():
            last = self.lines[-1]
            for seg in last.segments:
                seg.bold = True
                if level <= 2 and seg.fg is None:
                    seg.fg = CSSColor(255, 122, 170)
        if level <= 2:
            self.lines.append(Line([Segment("─" * max(8, min(self.width - self.indent, 48)), fg=CSSColor(150, 90, 120))]))
        self.blank(1)

    def render_children(self, node: Node, parent_style: ComputedStyle) -> None:
        for child in node.children:
            self.render_node(child, parent_style)

    def render_node(self, node: Node, parent_style: ComputedStyle) -> None:
        if node.tag == "#text":
            data = node.text
            if not parent_style.white_space_pre:
                data = re.sub(r"\s+", " ", data)
                if not data.strip():
                    return
            self.text(data, parent_style)
            return
        if node.tag == "#comment":
            return
        style = compute_style(node, self.page.rules, parent_style)
        if style.display == "none":
            return
        if node.tag in SKIP_TAGS:
            return
        if node.tag == "noscript" and self.page.root.script_state.get("js_enabled"):
            return
        anchor = node.get_attribute("id") or node.get_attribute("name")
        if anchor and node.tag in ("a", "h1", "h2", "h3", "h4", "section", "div"):
            self.flush()
            self.page.anchors[anchor] = len(self.lines)
        if node.tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.heading(int(node.tag[1]), node, style, parent_style)
            return
        if node.tag == "br":
            self.pending.append(Segment("\n"))
            return
        if node.tag == "hr":
            self.blank(1)
            self.lines.append(Line([Segment("─" * max(8, self.width - self.indent), fg=CSSColor(150, 90, 120))]))
            self.blank(1)
            return
        if node.tag in ("p", "div", "section", "article", "header", "footer", "main", "nav", "aside", "figure", "figcaption", "form", "fieldset", "details"):
            self.render_block(node, style, parent_style)
            return
        if node.tag == "blockquote":
            self.flush()
            self.indent += 2
            self.pending.append(Segment("│ ", fg=CSSColor(150, 90, 120)))
            self.render_children(node, style)
            self.flush()
            self.indent = max(0, self.indent - 2)
            self.blank(1)
            return
        if node.tag in ("ul", "ol"):
            self.render_list(node, style)
            return
        if node.tag == "li":
            self.render_list_item(node, style)
            return
        if node.tag == "pre":
            self.flush()
            for raw in node.text_content().splitlines() or [""]:
                for piece in wrap_text(raw, max(8, self.width - self.indent - 2), preserve_spaces=True):
                    self.lines.append(Line([Segment("  " + piece, fg=style.color or CSSColor(232, 224, 240))]))
            self.blank(1)
            return
        if node.tag == "code":
            start = len(self.pending)
            self.render_children(node, style)
            for seg in self.pending[start:]:
                if seg.fg is None:
                    seg.fg = CSSColor(255, 184, 205)
            return
        if node.tag == "a":
            self.render_link(node, style)
            return
        if node.tag == "img":
            self.render_image(node, style)
            return
        if node.tag == "picture":
            self.render_picture(node, style)
            return
        if node.tag in ("video", "audio"):
            self.render_media_tag(node, style)
            return
        if node.tag == "iframe":
            self.render_frame(node, style)
            return
        if node.tag in ("object", "embed"):
            self.render_object(node, style)
            return
        if node.tag == "table":
            self.render_table(node, style)
            return
        if node.tag in TABLE_SECTION_TAGS or node.tag in ("tr", "td", "th"):
            self.render_children(node, style)
            return
        if node.tag in FORM_CONTROLS:
            self.render_control(node, style, form_id=0)
            return
        if node.tag == "summary":
            self.text("▸ ", style)
            self.render_children(node, style)
            self.flush()
            return
        # Inline default.
        self.render_children(node, style)

    def render_block(self, node: Node, style: ComputedStyle, parent: ComputedStyle) -> None:
        self.blank(0)
        self.flush()
        if node.tag == "details":
            opened = node.has_attribute("open") or node.script_state.get("open", False)
            summary = next((c for c in node.children if c.tag == "summary"), None)
            self.text("▾ " if opened else "▸ ", style)
            if summary:
                self.render_children(summary, style)
            else:
                self.text("details", style)
            self.flush()
            if opened:
                self.indent += 2
                for c in node.children:
                    if c.tag != "summary":
                        self.render_node(c, style)
                self.indent = max(0, self.indent - 2)
            self.blank(1)
            return
        self.render_children(node, style)
        self.blank(1)

    def render_list(self, node: Node, style: ComputedStyle) -> None:
        self.flush()
        ordered = node.tag == "ol"
        start = 1
        try:
            start = int(node.get_attribute("start") or "1")
        except ValueError:
            start = 1
        self.list_stack.append((node.tag, start, style.list_style))
        for child in node.children:
            self.render_node(child, style)
        if self.list_stack:
            self.list_stack.pop()
        self.blank(1)

    def render_list_item(self, node: Node, style: ComputedStyle) -> None:
        self.flush()
        if self.list_stack:
            kind, num, lst = self.list_stack[-1]
            marker = f"{num}." if kind == "ol" else ("·" if lst in ("disc", "circle", "") else "–")
            self.list_stack[-1] = (kind, num + 1, lst)
        else:
            marker = "·"
        saved = self.pending
        self.pending = []
        self.text(f"{marker} ", ComputedStyle(color=CSSColor(255, 122, 170), bold=True))
        self.render_children(node, style)
        # Indent wrapped continuation lines.
        first = True
        width = max(8, self.width - self.indent)
        for seg in self.pending:
            pass
        self.flush()
        # Re-indent all but keep simple: lines were already emitted; shift them.
        if self.lines and marker:
            # Last emitted paragraph belongs to this item; indent continuations.
            pass
        self.pending = saved
        _ = first, width

    def render_link(self, node: Node, style: ComputedStyle) -> None:
        from magpie_fetch import resolve_url  # local import: dom stays import-light

        href = node.get_attribute("href")
        if not href:
            self.render_children(node, style)
            return
        url = resolve_url(self.page.url, href)
        label = node.text_content().strip().replace("\n", " ")[:120] or url
        ident = self.add_link(url, label)
        link_style = ComputedStyle(
            color=style.color or CSSColor(255, 122, 170),
            background=style.background, bold=True, italic=style.italic,
            underline=True, strike=style.strike,
        )
        self.link_stack.append(ident)
        # Image links render their thumbnail inline plus alt text.
        images = [c for c in node.iter() if c.tag == "img"]
        if images and len(node.text_content().strip()) == 0:
            self.render_image(images[0], link_style)
            self.link_stack.pop()
            return
        self.render_children(node, link_style)
        self.link_stack.pop()

    def render_image(self, node: Node, style: ComputedStyle) -> None:
        from magpie_fetch import resolve_url

        src = node.get_attribute("src") or node.get_attribute("data-src")
        if not src:
            return
        url = resolve_url(self.page.url, src)
        alt = node.get_attribute("alt") or node.get_attribute("title") or "image"
        w = parse_dimension(node.get_attribute("width"))
        h = parse_dimension(node.get_attribute("height"))
        ident = self.add_media("image", url, alt=alt, title=node.get_attribute("title"), width=w, height=h)
        self.flush()
        link = self.link_stack[-1] if self.link_stack else 0
        line = Line(
            [Segment(f"[image {ident}: {alt[:80]}]", fg=CSSColor(255, 122, 170), bold=True, link=link, media=ident)],
            links=[link] if link else [], medias=[ident],
        )
        self.lines.append(line)

    def render_picture(self, node: Node, style: ComputedStyle) -> None:
        from magpie_fetch import resolve_url

        for src in node.get_elements_by_tag("source"):
            srcset = pick_srcset(src.get_attribute("srcset")) or src.get_attribute("src")
            if srcset:
                url = resolve_url(self.page.url, srcset.split()[0])
                img = node.query_selector("img")
                alt = (img.get_attribute("alt") if img else "") or "image"
                ident = self.add_media("image", url, alt=alt)
                self.flush()
                self.lines.append(Line([Segment(f"[image {ident}: {alt[:80]}]", fg=CSSColor(255, 122, 170), bold=True, media=ident)], medias=[ident]))
                return
        img = node.query_selector("img")
        if img:
            self.render_image(img, style)

    def render_media_tag(self, node: Node, style: ComputedStyle) -> None:
        from magpie_fetch import resolve_url

        kind = node.tag
        urls: list[str] = []
        if node.get_attribute("src"):
            urls.append(resolve_url(self.page.url, node.get_attribute("src")))
        for src in node.get_elements_by_tag("source"):
            if src.get_attribute("src"):
                urls.append(resolve_url(self.page.url, src.get_attribute("src")))
        if not urls:
            return
        poster = resolve_url(self.page.url, node.get_attribute("poster")) if node.get_attribute("poster") else ""
        ident = self.add_media(kind, urls[0], poster=poster, title=node.get_attribute("title"))
        self.flush()
        link = self.link_stack[-1] if self.link_stack else 0
        label = "video" if kind == "video" else "audio"
        self.lines.append(Line([Segment(f"[{label} {ident}: play with v]", fg=CSSColor(255, 122, 170), bold=True, link=link, media=ident)], links=[link] if link else [], medias=[ident]))

    def render_frame(self, node: Node, style: ComputedStyle) -> None:
        from magpie_fetch import resolve_url

        src = node.get_attribute("src")
        if not src:
            return
        url = resolve_url(self.page.url, src)
        ident = self.add_media("frame", url, title=node.get_attribute("title") or node.get_attribute("name"))
        self.flush()
        self.lines.append(Line([Segment(f"[frame {ident}: open with enter]", fg=CSSColor(200, 160, 255), bold=True, media=ident)], medias=[ident]))

    def render_object(self, node: Node, style: ComputedStyle) -> None:
        from magpie_fetch import resolve_url

        src = node.get_attribute("data") or node.get_attribute("src")
        if not src:
            return
        url = resolve_url(self.page.url, src)
        ident = self.add_media("object", url)
        self.flush()
        self.lines.append(Line([Segment(f"[embed {ident}: open with enter]", fg=CSSColor(200, 160, 255), media=ident)], medias=[ident]))

    def render_table(self, node: Node, style: ComputedStyle) -> None:
        rows: list[list[Node]] = []
        for tr in node.get_elements_by_tag("tr"):
            # Only direct logical rows of this table.
            tbl = tr.parent
            while tbl is not None and tbl.tag not in ("table",):
                tbl = tbl.parent
            if tbl is not node:
                continue
            cells = [c for c in tr.children if c.tag in ("td", "th")]
            if cells:
                rows.append(cells)
        if not rows:
            return
        self.flush()
        ncols = max(len(r) for r in rows)
        avail = max(20, self.width - self.indent - (ncols + 1))
        col_w = max(6, avail // max(1, ncols))
        border = ComputedStyle(fg=CSSColor(150, 90, 120))
        rule = "+" + "+".join(["-" * (col_w + 2) for _ in range(ncols)]) + "+"
        self.lines.append(Line([Segment(" " * self.indent + rule, fg=border.fg)]))
        for r in rows:
            cell_lines: list[list[str]] = []
            header = False
            for c in r:
                if c.tag == "th":
                    header = True
                txt = re.sub(r"\s+", " ", c.text_content()).strip()
                cell_lines.append(wrap_text(txt, col_w) or [""])
            height = max(len(c) for c in cell_lines)
            for k in range(height):
                parts = []
                for ci in range(ncols):
                    lines = cell_lines[ci] if ci < len(cell_lines) else [""]
                    txt = lines[k] if k < len(lines) else ""
                    parts.append(" " + txt + " " * max(0, col_w - vis_len(txt)) + " ")
                row = " " * self.indent + "|" + "|".join(parts) + "|"
                segs = [Segment(row, fg=CSSColor(255, 255, 255) if False else None, bold=header)]
                self.lines.append(Line(segs))
            self.lines.append(Line([Segment(" " * self.indent + rule, fg=border.fg)]))
        self.blank(1)

    def render_control(self, node: Node, style: ComputedStyle, form_id: int) -> None:
        tag = node.tag
        if tag == "input":
            itype = (node.get_attribute("type") or "text").lower()
            if itype == "hidden":
                return
            fld = self.register_field(node, form_id, kind=itype)
            label = control_label(node, fld)
            self.text(label, ComputedStyle(color=CSSColor(255, 184, 205), bold=True))
            return
        if tag == "textarea":
            fld = self.register_field(node, form_id, kind="textarea")
            self.text(control_label(node, fld), ComputedStyle(color=CSSColor(255, 184, 205), bold=True))
            return
        if tag == "select":
            fld = self.register_field(node, form_id, kind="select")
            self.text(control_label(node, fld), ComputedStyle(color=CSSColor(255, 184, 205), bold=True))
            return
        if tag == "button":
            fld = self.register_field(node, form_id, kind="button")
            label = node.text_content().strip() or node.get_attribute("value") or "button"
            self.text(f"[ {label} ]", ComputedStyle(color=CSSColor(255, 122, 170), bold=True))
            return

    def register_field(self, node: Node, form_id: int, kind: str) -> FormField:
        ident = len(self.page.fields) + 1
        options: list[tuple[str, str, bool]] = []
        value = node.get_attribute("value")
        if node.tag == "textarea":
            value = node.text_content()
        if node.tag == "select":
            for opt in node.get_elements_by_tag("option"):
                options.append((opt.text_content().strip(), opt.get_attribute("value") or opt.text_content().strip(), opt.has_attribute("selected")))
            if options and not any(o[2] for o in options):
                options[0] = (options[0][0], options[0][1], True)
            value = next((v for _, v, s in options if s), "")
        fld = FormField(
            ident=ident, form=form_id, control=node, kind=kind,
            name=node.get_attribute("name"), value=value,
            checked=node.has_attribute("checked"),
            required=node.has_attribute("required"),
            placeholder=node.get_attribute("placeholder"), options=options,
        )
        self.page.fields.append(fld)
        # Annotate tail segment so keyboard focus can find this row.
        self.pending.append(Segment("", field=ident))
        return fld


def control_label(node: Node, fld: FormField) -> str:
    if fld.kind in ("checkbox",):
        box = "[x]" if fld.checked else "[ ]"
        return f"{box} {node.get_attribute('value') or 'on'}  "
    if fld.kind == "radio":
        box = "(o)" if fld.checked else "( )"
        return f"{box} {node.get_attribute('value') or 'on'}  "
    if fld.kind in ("submit", "button"):
        label = node.get_attribute("value") or node.text_content().strip() or "submit"
        return f"[ {label} ] "
    if fld.kind == "image":
        return f"[ image-button:{node.get_attribute('alt') or 'go'} ] "
    if fld.kind == "file":
        return "[ choose file (not supported) ] "
    if fld.kind == "select":
        cur = next((t for t, _, s in fld.options if s), "")
        return f"[ {cur or '…'} v ] "
    if fld.kind == "textarea":
        preview = (fld.value.splitlines() or [""])[0][:24]
        return f"[ text: {preview} ] "
    if fld.kind in ("password",):
        return f"[ {'•' * min(8, len(fld.value)) or 'password'} ] "
    size = 20
    try:
        size = max(8, min(48, int(node.get_attribute("size") or "20")))
    except ValueError:
        pass
    shown = fld.value or fld.placeholder or ""
    return f"[ {shown[:size]} ] "


def parse_dimension(text: str) -> int:
    m = re.match(r"\s*(\d+)", text or "")
    return int(m.group(1)) if m else 0


def pick_srcset(srcset: str) -> str:
    if not srcset:
        return ""
    cands = []
    for chunk in srcset.split(","):
        bits = chunk.strip().split()
        if bits:
            cands.append(bits[0])
    return cands[-1] if cands else ""


def collect_styles(root: Node) -> list[CSSRule]:
    rules: list[CSSRule] = []
    order = 0
    for style in root.get_elements_by_tag("style"):
        for rule in parse_css(style.text_content(), start_order=order):
            rules.append(rule)
            order += 1
    return rules


def build_page(url: str, markup: str, width: int, *, js_enabled: bool = False) -> Page:
    root = parse_html(markup, js_enabled=js_enabled)
    return layout_dom(root, url, width, js_enabled=js_enabled)


def layout_dom(root: Node, base_url: str, width: int, *, js_enabled: bool = False, title_override: str = "") -> Page:
    title = ""
    head_title = root.query_selector("title")
    if head_title:
        title = re.sub(r"\s+", " ", head_title.text_content()).strip()
    base = base_url
    base_el = root.query_selector("base")
    if base_el and base_el.get_attribute("href"):
        from magpie_fetch import resolve_url
        base = resolve_url(base_url, base_el.get_attribute("href"))
    page = Page(url=base, title=title_override or title or base, root=root, rules=collect_styles(root))
    # Forms register before layout so controls know their form id.
    for form_el in root.get_elements_by_tag("form"):
        ident = len(page.forms) + 1
        method = (form_el.get_attribute("method") or "get").lower()
        action = form_el.get_attribute("action") or base
        from magpie_fetch import resolve_url
        page.forms.append(Form(ident, form_el, resolve_url(base, action), method if method in ("get", "post") else "get"))
    # Scripts list (execution is owned by magpie_script).
    for script in root.get_elements_by_tag("script"):
        page.scripts.append(script)
    # Meta refresh notice (never auto-follow without consent).
    for meta in root.get_elements_by_tag("meta"):
        if meta.get_attribute("http-equiv").lower() == "refresh":
            content = meta.get_attribute("content")
            m = re.match(r"\s*(\d+)\s*(?:;\s*url\s*=\s*(.+))?", content, re.I)
            if m:
                from magpie_fetch import resolve_url
                target = resolve_url(base, m.group(2).strip(" '\"")) if m.group(2) else ""
                page.meta_refresh = (int(m.group(1)), target)
    body = root.query_selector("body") or root
    renderer = Renderer(page, width)
    # Register form ids on controls by tree order.
    form_of: dict[int, int] = {}
    for form in page.forms:
        for n in form.node.iter():
            if n.tag in FORM_CONTROLS:
                form_of[id(n)] = form.ident
    orig_register = renderer.register_field

    def register_with_form(node: Node, form_id: int, kind: str) -> FormField:
        return orig_register(node, form_of.get(id(node), form_id), kind)

    renderer.register_field = register_with_form  # type: ignore[method-assign]
    renderer.render_children(body, ComputedStyle(color=CSSColor(232, 224, 240)))
    renderer.flush()
    page.lines = renderer.lines
    # Populate form field lists.
    for fld in page.fields:
        for form in page.forms:
            if form.ident == fld.form and fld.ident not in form.fields:
                form.fields.append(fld.ident)
                break
    return page


def submit_form(page: Page, form: Form, state: dict[int, str | bool]) -> tuple[str, str, bytes, str]:
    """Return (method, url, body, content_type) for a filled form."""
    pairs: list[tuple[str, str]] = []
    import urllib.parse as _u
    for fid in form.fields:
        fld = next((f for f in page.fields if f.ident == fid), None)
        if not fld or not fld.name:
            continue
        val = state.get(fid, fld.value)
        if fld.kind == "checkbox" and not (val is True or (isinstance(val, str) and val.lower() in ("1", "on", "true", "yes"))):
            continue
        if fld.kind == "radio" and not fld.checked and state.get(fid) is not True:
            continue
        if fld.kind == "file":
            continue
        pairs.append((fld.name, val if isinstance(val, str) else fld.value))
    # Submit buttons contribute their name/value when they trigger submit.
    if form.method == "get":
        parts = _u.urlparse(form.action)
        q = _u.parse_qsl(parts.query, keep_blank_values=True) + pairs
        query = _u.urlencode(q, doseq=True)
        url = _u.urlunparse((parts.scheme, parts.netloc, parts.path or "/", parts.params, query, parts.fragment))
        return ("GET", url, b"", "")
    body = _u.urlencode(pairs, doseq=True).encode()
    return ("POST", form.action, body, "application/x-www-form-urlencoded")


def extract_article(page: Page) -> str:
    """Readability-lite: prefer article/main, else densest text container."""
    cands = [n for n in page.root.elements() if n.tag in ("article", "main")]
    if not cands:
        best, best_score = None, 0.0
        for n in page.root.elements():
            if n.tag in ("div", "section"):
                text = n.text_content()
                links = sum(len(c.text_content()) for c in n.iter() if c.tag == "a")
                score = len(text) - 3 * links if len(text) > 200 else 0
                if score > best_score:
                    best, best_score = n, score
        if best is not None:
            cands = [best]
    if not cands:
        cands = [page.root.query_selector("body") or page.root]
    chunks: list[str] = []
    for node in cands[:1]:
        for child in node.iter():
            if child.tag in ("p", "h1", "h2", "h3", "li"):
                t = re.sub(r"\s+", " ", child.text_content()).strip()
                if len(t) > 40:
                    chunks.append(t)
    text = "\n\n".join(chunks).strip()
    if len(text) < 200:
        text = re.sub(r"\s+", " ", page.root.text_content()).strip()
    return text[:12000]


def find_text_rows(page: Page, query: str) -> list[int]:
    q = query.lower()
    return [i for i, line in enumerate(page.lines) if q in line.plain().lower()]
