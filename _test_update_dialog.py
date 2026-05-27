"""Test script: show the update dialog with real markdown content."""
import sys
sys.path.insert(0, ".")

from qt_compat import QApplication, QWidget
from core import DataManager
from services.update.config import UpdateInfo
from services.update.ui import UpdateDialog

app = QApplication(sys.argv)

dm = DataManager()
theme = dm.get_settings().theme
print(f"Current theme: {theme}")

sample = """## 更新内容

### 全新命令系统
- 统一命令注册中心，支持别名、优先级、分类检索
- 命令预处理管道：5 层安全审查（语法 → 语义 → 安全扫描 → 业务规则 → 审计日志）
- 命令变量引擎，支持动态变量
- 命令执行前自动检测优先级
- 命令结果悬浮窗口，搜索/执行/历史一体化
- 支持 PowerShell 与 Git Bash 多终端实时执行

### 插件系统 v1
- 插件管理面板：本地扫描、安装、卸载、内置更新管理
- 标准插件配置模板
- 内置 8 个实用插件（如网工工具、编码转换、文件处理工具、进程管理器等）

### 快捷方式编辑全面升级
- 支持多步骤工作目录配置
- 可视化编辑器升级，支持分组收缩/展开

### 搜索能力增强
- 模糊匹配算法升级，编辑距离匹配
- 中文拼音首字母/全拼搜索支持
- 混合输入法 IME 支持 + 扩展搜索

### 数据安全与恢复
- 历史快照 + 一键恢复
- 配置文件自动修复
- 导入导出与安全检查（ZIP 完整性/文件安全性检查）
- 旧版本语法自动迁移

### 快捷方式体检与修复
- 自动检测失效链接、缺失图标、路径异常
- 提供一键修复方案

### 国际化
- 中英双语系统，运行时实时切换

### 自动更新
- 检测更新、下载、安装、会话管理全链路

### UI 架构重构
- 主窗口内部拆为 7 个独立模块，降低耦合
- 托盘拆为 6 个 Mixin，降低复杂度
- 图标缓存与加载全面增强
- 快捷方式编辑对话框重写

### 安全增强
- 路径安全边界检查，防路径遍历攻击
- URL 协议与重定向安全验证

### 稳定性修复
- 图标缓存与加载重构
- 优先级冲突修复
- 60+ 细节修复与优化

---

**统计**: 233 文件改动 +61,232 / -10,362 行
"""

info = UpdateInfo(
    has_update=True,
    version="9.9.9.9",
    release_date="2026-05-27",
    changelog_zh=sample,
    file_size=30272688,
    download_url="https://github.com/LEISHIQIANG/QuickLauncher/releases/latest",
    file_hash="sha256:" + "a" * 64,
)

# Create a minimal QWidget as parent to get correct theme detection
parent = QWidget()
parent._theme = theme
parent.data_manager = dm

UpdateDialog.show_update_available(info, parent=parent)
print("Dialog closed")
