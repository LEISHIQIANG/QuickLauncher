# 开发指南

## 开发环境设置

### 1. 克隆仓库
```bash
git clone <repository-url>
cd QuickLauncher_52PJ_V1.5.6.5
```

### 2. 安装依赖
```bash
# 安装运行依赖
pip install -r requirements.txt

# 安装开发依赖
pip install -r requirements-dev.txt
```

### 3. 设置 Pre-commit Hooks
```bash
pre-commit install
```

## 开发流程

### 代码规范

**类型注解**:
- 所有公共函数必须有类型注解
- 使用 `typing` 模块的类型提示

**代码风格**:
- 遵循 PEP 8
- 使用 Black 格式化（行长度 120）
- 使用 Ruff 进行 linting

**命名规范**:
- 类名: PascalCase
- 函数/变量: snake_case
- 常量: UPPER_SNAKE_CASE
- 私有成员: _leading_underscore

### 提交前检查

```bash
# 1. 格式化代码
black .

# 2. 运行 linter
ruff check . --fix

# 3. 类型检查
mypy core ui bootstrap

# 4. 运行测试
pytest --cov

# 5. 安全扫描
bandit -r core ui bootstrap -ll
```

### Git 提交规范

使用语义化提交信息:

```
<type>: <subject>

<body>
```

**Type 类型**:
- `feat`: 新功能
- `fix`: Bug 修复
- `docs`: 文档更新
- `style`: 代码格式（不影响功能）
- `refactor`: 重构
- `perf`: 性能优化
- `test`: 测试相关
- `chore`: 构建/工具相关

**示例**:
```
feat: 添加快捷方式拖拽排序功能

- 实现图标拖拽逻辑
- 更新数据模型
- 添加单元测试
```

## 测试指南

### 运行测试
```bash
# 运行所有测试
pytest

# 运行特定测试文件
pytest tests/test_data_manager.py

# 运行带覆盖率的测试
pytest --cov --cov-report=html

# 查看覆盖率报告
start htmlcov/index.html
```

### 编写测试

**测试文件命名**: `test_<module_name>.py`

**测试函数命名**: `test_<function_name>_<scenario>`

**示例**:
```python
def test_data_manager_save_creates_backup():
    """测试数据管理器保存时创建备份"""
    manager = DataManager()
    manager.save()
    assert manager.auto_backup_dir.exists()
```

### 测试覆盖率要求
- 新代码: >80%
- 核心模块: >70%
- 整体项目: >50%

## 安全最佳实践

### 1. 命令执行
```python
# ❌ 不安全
os.system(f"start {user_input}")

# ✅ 安全
import shlex
args = shlex.split(user_input)
subprocess.run(args, shell=False)
```

### 2. 路径处理
```python
# ❌ 不安全
path = base_dir + "/" + user_input

# ✅ 安全
from pathlib import Path
path = Path(base_dir) / user_input
if not path.resolve().is_relative_to(base_dir):
    raise ValueError("Invalid path")
```

### 3. 日志记录
```python
# ❌ 可能泄露敏感信息
logger.info(f"User password: {password}")

# ✅ 安全
logger.info("User authenticated successfully")
```

## 性能优化指南

### 1. 使用性能监控
```python
from core.performance_monitor import performance_monitor

@performance_monitor(threshold_ms=100)
def expensive_operation():
    # 耗时操作
    pass
```

### 2. 缓存策略
```python
from functools import lru_cache

@lru_cache(maxsize=128)
def get_icon(path: str):
    # 图标提取
    pass
```

### 3. 异步操作
```python
from qt_compat import QThread

class Worker(QThread):
    def run(self):
        # 耗时操作
        pass
```

## 文档编写

### Docstring 格式
使用 Google 风格:

```python
def function_name(param1: str, param2: int) -> bool:
    """函数简短描述

    详细描述（可选）

    Args:
        param1: 参数1描述
        param2: 参数2描述

    Returns:
        返回值描述

    Raises:
        ValueError: 异常描述
    """
    pass
```

### 生成文档
```bash
cd docs
sphinx-build -b html . _build
```

## 常见问题

### Q: Pre-commit hooks 失败怎么办？
A: 根据错误信息修复代码，或运行 `ruff check . --fix` 和 `black .` 自动修复

### Q: 类型检查报错但代码正常运行？
A: 添加类型注解或在 `mypy.ini` 中配置忽略规则

### Q: 测试覆盖率不足？
A: 为未覆盖的代码路径添加测试用例

### Q: CI 构建失败？
A: 查看 GitHub Actions 日志，本地运行相同的检查命令

## 发布流程

1. 更新版本号（`core/__init__.py`）
2. 更新 CHANGELOG
3. 运行完整测试套件
4. 创建 Git tag
5. 推送到远程仓库
6. GitHub Actions 自动构建

## 联系方式

- 问题反馈: GitHub Issues
- 开发讨论: GitHub Discussions

---

**最后更新**: 2026-05-10
