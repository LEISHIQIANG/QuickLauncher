"""Theme-aware QSS builder for the P1-06 style refactor.

The :class:`StyleBuilder` collects token replacements and produces a
QSS string.  It is the building block for the higher-level
:func:`get_button_style`, :func:`get_input_style` etc. helpers that
will replace the hand-rolled ``f"...{color}..."`` strings currently
scattered across :mod:`ui/styles/style.py`.

The builder is intentionally tiny: it only knows about three token
shapes (``color``, ``font`` and ``radius``) and supports two
substitution modes:

* :func:`with_color` / :func:`with_font` / :func:`with_radius` —
  single token replacement, returns a new builder (immutable-style).
* :func:`extend` — bulk replacement using a ``dict``.

Rendering is deferred until :func:`render` is called so the builder
can be threaded through view-model code that needs to read or
mutate it before producing the final QSS.
"""

from __future__ import annotations

from collections.abc import Mapping


def _normalize_hex(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return text
    if text.startswith("rgba") or text.startswith("rgb"):
        return text
    return text


class StyleBuilder:
    """Immutable QSS builder with token replacement.

    The builder owns the *template* QSS string and a token table.
    :func:`render` returns the template with the tokens expanded.
    """

    __slots__ = ("_template", "_tokens")

    def __init__(
        self,
        template: str = "",
        tokens: Mapping[str, str] | None = None,
    ) -> None:
        self._template = str(template or "")
        self._tokens: dict[str, str] = dict(tokens or {})

    # ── accessors ────────────────────────────────────────────────────

    @property
    def template(self) -> str:
        return self._template

    @property
    def tokens(self) -> Mapping[str, str]:
        return dict(self._tokens)

    # ── mutators (return new builder) ───────────────────────────────

    def with_template(self, template: str) -> StyleBuilder:
        return StyleBuilder(str(template or ""), self._tokens)

    def with_color(self, token: str, value: str) -> StyleBuilder:
        tokens = dict(self._tokens)
        tokens[str(token)] = _normalize_hex(value)
        return StyleBuilder(self._template, tokens)

    def with_colors(self, mapping: Mapping[str, str]) -> StyleBuilder:
        tokens = dict(self._tokens)
        for token, value in mapping.items():
            tokens[str(token)] = _normalize_hex(value)
        return StyleBuilder(self._template, tokens)

    def with_font(self, token: str, value: str) -> StyleBuilder:
        tokens = dict(self._tokens)
        tokens[str(token)] = str(value or "")
        return StyleBuilder(self._template, tokens)

    def with_radius(self, token: str, value: int) -> StyleBuilder:
        tokens = dict(self._tokens)
        tokens[str(token)] = f"{int(value)}px"
        return StyleBuilder(self._template, tokens)

    def extend(self, **kwargs: str) -> StyleBuilder:
        tokens = dict(self._tokens)
        for key, value in kwargs.items():
            key = str(key)
            if key.startswith("color_"):
                tokens[key] = _normalize_hex(value)
            elif key.startswith("radius_"):
                tokens[key] = f"{int(value)}px"
            else:
                tokens[key] = str(value)
        return StyleBuilder(self._template, tokens)

    # ── render ───────────────────────────────────────────────────────

    def render(self) -> str:
        out = str(self._template)
        if self._tokens:
            for key, value in self._tokens.items():
                marker = "{{" + key + "}}"
                out = out.replace(marker, value)
        # Simple direct unescape — no regex tricks
        out = out.replace("{{", "{")
        out = out.replace("}}", "}")
        return out

    # ── Python protocol ──────────────────────────────────────────────

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"StyleBuilder(tokens={self._tokens!r})"


__all__ = ["StyleBuilder"]
