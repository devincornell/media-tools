'''Reading and writing ffmpeg filtergraph text, following ffmpeg's own escaping rules.

A filtergraph is escaped on two levels (see "Notes on filtergraph escaping" in the ffmpeg-filters manual):

1. Each option value is read with `:` as the separator, so `\\`, `'` and `:` in a value must be escaped.
2. The whole argument string of a filter is read with `[ ] , ;` as separators, so those (and `\\`, `'`) must be
   escaped or quoted again.

The tokenizer here is a port of `av_get_token()`, so text produced by `format_filter()` is read back by ffmpeg
exactly as it is by `parse_filtergraph()`.
'''
from __future__ import annotations

import dataclasses
import re

WHITESPACE = " \n\t\r"
_KEY_CHARS = re.compile(r"[A-Za-z0-9_\-/.]")


class FiltergraphSyntaxError(ValueError):
    '''The text is not a valid filtergraph.'''


def get_token(text: str, pos: int, terms: str) -> tuple[str, int]:
    '''Port of `av_get_token`: read up to an unescaped, unquoted terminator, removing one level of escaping.'''
    n = len(text)
    while pos < n and text[pos] in WHITESPACE:
        pos += 1
    out: list[str] = []
    end = 0  # characters before `end` are protected from trailing-whitespace trimming
    while pos < n and text[pos] not in terms:
        c = text[pos]
        pos += 1
        if c == "\\" and pos < n:
            out.append(text[pos])
            pos += 1
            end = len(out)
        elif c == "'":
            while pos < n and text[pos] != "'":
                out.append(text[pos])
                pos += 1
            if pos < n:
                pos += 1
                end = len(out)
        else:
            out.append(c)
    while len(out) > end and out[-1] in WHITESPACE:
        out.pop()
    return "".join(out), pos


def escape_value(value: str, *, positional: bool = False) -> str:
    '''First-level escaping of one option value (separator `:`).'''
    specials = "\\':=" if positional else "\\':"
    last = len(value) - 1
    return "".join(
        f"\\{c}" if c in specials or (c in WHITESPACE and i in (0, last)) else c
        for i, c in enumerate(value)
    )


def quote_args(args: str) -> str:
    '''Second-level escaping of a filter's whole argument string (separators `[ ] , ;`).'''
    if not args:
        return args
    if not (set(args) & set("[],;'\\") or args[0] in WHITESPACE or args[-1] in WHITESPACE):
        return args
    return "\\'".join(f"'{piece}'" if piece else "" for piece in args.split("'"))


def format_args(args: list[str], options: list[tuple[str, str]]) -> str:
    '''Join positional and named option values into one escaped argument string.'''
    parts = [escape_value(a, positional=True) for a in args]
    parts += [f"{k}={escape_value(v)}" for k, v in options]
    return quote_args(":".join(parts))


def format_filter(name: str, args: list[str], options: list[tuple[str, str]]) -> str:
    '''`name=args` as it appears in a filtergraph (just `name` without arguments).'''
    joined = format_args(args, options)
    return f"{name}={joined}" if joined else name


def parse_args(args: str) -> tuple[list[str], list[tuple[str, str]]]:
    '''Split an (already level-2 unescaped) argument string into positional values and named options.'''
    positional: list[str] = []
    named: list[tuple[str, str]] = []
    pos, n = 0, len(args)
    while pos < n:
        key, after_key = _read_key(args, pos)
        if key is not None:
            value, pos = get_token(args, after_key, ":")
            named.append((key, value))
        else:
            if named:
                raise FiltergraphSyntaxError(f"Positional value after named options: {args[pos:]!r}")
            value, pos = get_token(args, pos, ":")
            positional.append(value)
        if pos < n:
            pos += 1  # skip ':'
    return positional, named


def _read_key(text: str, pos: int) -> tuple[str | None, int]:
    '''Port of libavutil's `get_key`: a key is `[A-Za-z0-9_-/.]+` followed by `=`.'''
    n = len(text)
    while pos < n and text[pos] in WHITESPACE:
        pos += 1
    start = pos
    while pos < n and _KEY_CHARS.match(text[pos]):
        pos += 1
    key = text[start:pos]
    while pos < n and text[pos] in WHITESPACE:
        pos += 1
    if not key or pos >= n or text[pos] != "=":
        return None, start
    return key, pos + 1


@dataclasses.dataclass
class ParsedFilter:
    '''One filter instance as written in a filtergraph.'''

    name: str
    args: list[str]
    options: list[tuple[str, str]]
    in_labels: list[str]
    out_labels: list[str]


def parse_filtergraph(text: str) -> list[list[ParsedFilter]]:
    '''Parse filtergraph text into chains (`;`-separated) of filters (`,`-separated).'''
    chains: list[list[ParsedFilter]] = []
    chain: list[ParsedFilter] = []
    pos, n = 0, len(text)
    pos = _skip_ws(text, pos)
    if pos >= n:
        return []
    while True:
        in_labels, pos = _parse_labels(text, pos)
        name, pos = get_token(text, pos, "=,;[")
        if not name:
            raise FiltergraphSyntaxError(f"Expected a filter name at position {pos}: {text[pos:pos + 20]!r}")
        if not re.fullmatch(r"[A-Za-z0-9_]+(@[A-Za-z0-9_]+)?", name):
            raise FiltergraphSyntaxError(f"Invalid filter name: {name!r}")
        name = name.split("@", 1)[0]
        args: list[str] = []
        options: list[tuple[str, str]] = []
        if pos < n and text[pos] == "=":
            raw, pos = get_token(text, pos + 1, "[],;")
            args, options = parse_args(raw)
        out_labels, pos = _parse_labels(text, pos)
        chain.append(ParsedFilter(name, args, options, in_labels, out_labels))
        pos = _skip_ws(text, pos)
        if pos >= n:
            chains.append(chain)
            return chains
        sep = text[pos]
        pos = _skip_ws(text, pos + 1)
        if sep == ",":
            continue
        if sep == ";":
            chains.append(chain)
            chain = []
            if pos >= n:
                return chains
            continue
        raise FiltergraphSyntaxError(f"Unexpected {sep!r} at position {pos - 1}")


def _skip_ws(text: str, pos: int) -> int:
    while pos < len(text) and text[pos] in WHITESPACE:
        pos += 1
    return pos


def _parse_labels(text: str, pos: int) -> tuple[list[str], int]:
    labels: list[str] = []
    pos = _skip_ws(text, pos)
    while pos < len(text) and text[pos] == "[":
        close = text.find("]", pos + 1)
        if close < 0:
            raise FiltergraphSyntaxError(f"Unterminated label at position {pos}")
        label = text[pos + 1:close].strip()
        if not label:
            raise FiltergraphSyntaxError(f"Empty label at position {pos}")
        labels.append(label)
        pos = _skip_ws(text, close + 1)
    return labels, pos
