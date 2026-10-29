"""极简 .env 加载器。

项目原先全用 os.getenv，但没有任何读取 .env 的代码——所以就算在根目录
建了 .env，变量也不会生效，llm.available() 永远是 False。这里补上。

不引入 python-dotenv：只有 40 行，且导入顺序可控（在 engine/__init__.py
最前面调用，保证 engine.llm 读取配置时变量已经在 os.environ 里）。

规则：
- 支持 KEY=value、export KEY=value、# 注释、引号包裹
- 已存在的真实环境变量优先，不被文件覆盖（部署时用 export 生效的那份更可信）
"""
from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_LOADED = False


def _parse(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key, val = key.strip(), val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        if key:
            out[key] = val
    return out


def load(force: bool = False) -> None:
    """读取根目录下的 .env / .env.local，写入 os.environ。"""
    global _LOADED
    if _LOADED and not force:
        return
    _LOADED = True
    for name in (".env", ".env.local"):
        for key, val in _parse(_ROOT / name).items():
            if force or key not in os.environ:
                os.environ[key] = val


def get(key: str, default: str = "") -> str:
    load()
    return os.getenv(key, default)
