"""Enhanced math and list processors for action chains."""

from __future__ import annotations

from typing import Any

from core.command_registry import CommandResult

from ._proc_helpers import (
    ok,
    ok_list,
    parse_list,
    string_values,
    to_num,
    value_to_text,
)


def execute_extra_math_processor(processor_id: str, values: dict[str, Any]) -> CommandResult | None:
    """Handle enhanced and extended math processors. Returns None if not a math processor."""
    text_values = string_values(values)

    # ── Enhanced: Basic math ──
    if processor_id == "math_abs":
        return ok(str(abs(to_num(values.get("number", 0)))))
    if processor_id == "math_ceil":
        import math as _m

        return ok(str(_m.ceil(to_num(values.get("number", 0)))))
    if processor_id == "math_floor":
        import math as _m

        return ok(str(_m.floor(to_num(values.get("number", 0)))))
    if processor_id == "math_round":
        n = to_num(values.get("number", 0))
        d = int(text_values.get("decimals", "0") or "0")
        return ok(str(round(n, d)))
    if processor_id == "math_clamp":
        n = to_num(values.get("number", 0))
        lo = to_num(values.get("min", 0))
        hi = to_num(values.get("max", 100))
        return ok(str(max(lo, min(n, hi))))

    # ── Extended: Advanced math ──
    if processor_id == "math_sin":
        import math as _m

        return ok(str(_m.sin(to_num(values.get("angle", 0)))))
    if processor_id == "math_cos":
        import math as _m

        return ok(str(_m.cos(to_num(values.get("angle", 0)))))
    if processor_id == "math_tan":
        import math as _m

        return ok(str(_m.tan(to_num(values.get("angle", 0)))))
    if processor_id == "math_sqrt":
        import math as _m

        return ok(str(_m.sqrt(to_num(values.get("number", 0)))))
    if processor_id == "math_log":
        import math as _m

        x = to_num(values.get("number", 1))
        b = to_num(values.get("base", 2.718281828459045))
        return ok(str(_m.log(x, b) if b != 2.718281828459045 else _m.log(x)))
    if processor_id == "math_factorial":
        import math as _m

        return ok(str(_m.factorial(int(to_num(values.get("number", 0))))))
    if processor_id == "math_gcd":
        import math as _m

        return ok(str(_m.gcd(int(to_num(values.get("a", 0))), int(to_num(values.get("b", 0))))))
    if processor_id == "math_lcm":
        import math as _m

        a = int(to_num(values.get("a", 0)))
        b = int(to_num(values.get("b", 0)))
        return ok(str(abs(a * b) // _m.gcd(a, b)))
    if processor_id == "math_fibonacci":
        n = int(to_num(values.get("count", 10)))
        if n <= 0:
            return ok_list([])
        fib = [0, 1]
        for _ in range(2, n):
            fib.append(fib[-1] + fib[-2])
        return ok_list(fib)

    return None


def execute_extra_list_processor(processor_id: str, values: dict[str, Any]) -> CommandResult | None:
    """Handle enhanced list processors. Returns None if not a list processor."""

    # ── Enhanced: List operations ──
    if processor_id == "list_count":
        lst = parse_list(values.get("list", ""))
        v = value_to_text(values.get("value", ""))
        return ok(str(lst.count(v)))
    if processor_id == "list_sum":
        lst = parse_list(values.get("list", ""))
        total = sum(to_num(x) for x in lst)
        return ok(str(int(total) if total == int(total) else total))
    if processor_id == "list_min":
        lst = parse_list(values.get("list", ""))
        return ok(min(lst) if lst else "")
    if processor_id == "list_max":
        lst = parse_list(values.get("list", ""))
        return ok(max(lst) if lst else "")
    if processor_id == "list_avg":
        lst = parse_list(values.get("list", ""))
        nums = [float(x) for x in lst if x.strip()]
        if not nums:
            return ok("0")
        avg = sum(nums) / len(nums)
        return ok(str(int(avg) if avg == int(avg) else avg))
    if processor_id == "list_remove":
        lst = parse_list(values.get("list", ""))
        v = value_to_text(values.get("value", ""))
        filtered = [x for x in lst if x != v]
        return ok_list(filtered)
    if processor_id == "list_find":
        lst = parse_list(values.get("list", ""))
        v = value_to_text(values.get("value", ""))
        found = v in lst
        return ok(v if found else "")

    return None
