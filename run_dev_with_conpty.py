"""一次性把 ConPTY 默认打开，跑 dev 用。

用法：
    python run_dev_with_conpty.py
"""

import os
import runpy
import sys

# Inject the toggle BEFORE any capture-path code is imported.
sys.path.insert(0, os.path.dirname(__file__))

import infrastructure.process.runtime as _rt

_rt._USE_CONPTY_DEFAULT = True
print("[dev] ConPTY capture 已启用，请验证 dev 模式下还有没有黑窗")
print("[dev] 要切回原路径：编辑 infrastructure/process/runtime.py 把 _USE_CONPTY_DEFAULT 改回 False")

# Hand off to the real main.py.
sys.argv = [sys.argv[0], *sys.argv[1:]]
runpy.run_path(os.path.join(os.path.dirname(__file__), "main.py"), run_name="__main__")
