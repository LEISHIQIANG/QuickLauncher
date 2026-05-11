# Changelog

All notable changes to QuickLauncher will be documented in this file.

## [1.5.6.7] - 2026-05-11

### Fixed (P0 Critical)
- **鼠标钩子卡住问题**: 添加双重保护机制（物理状态检查 + 2秒超时保护），彻底解决中键点击后左键卡住的问题
- **滚轮翻页动画卡顿**: 实现平滑插值系统，快速滚动时动画流畅不重置，支持自适应速度调整
- 修复 `refresh_data` 未重置动画状态导致的页面索引越界问题
- 修复 `_switch_page` 未更新目标页面导致的键盘切换动画方向错误
- 修复 `paintEvent` 使用旧动画变量导致的渲染失效问题
- 修复快速滚动时负数进度值导致的渲染异常

### Added
- 新增 `core/error_handler.py` 统一异常处理工具模块
- 新增 `core/application.py` 应用生命周期管理类
- 新增 pytest 测试框架配置 (`pytest.ini`)
- 新增 `tests/test_error_handler.py` 单元测试

### Changed
- 重构 `main.py` 异常处理，使用 `safe_execute` 替代宽泛的 try-except
- 优化 `hooks_dll/hooks.cpp` 鼠标钩子状态同步逻辑
- 重写 `popup_renderer.py` 动画渲染系统，基于 `_page_offset` 实现平滑过渡
- 优化 `popup_window.py` 滚轮事件处理，支持速度感知的动画加速
- 优化 Win11 打包脚本，排除 qt5network.dll 减小包体积

### Technical Details
- 鼠标钩子使用 `GetAsyncKeyState(VK_MBUTTON)` 检测物理状态
- 滚轮动画采用 `_page_offset` (float) 平滑插值到 `_target_page`
- 动画速度根据滚轮频率自适应调整（0.15秒内连续滚动视为快速）
- 超时保护机制：2秒后自动释放卡住的钩子状态

## [1.5.6.6] - 2026-05-10

### Added
- 完整的代码质量基础设施 (mypy, ruff, black, pre-commit)
- 性能监控模块 (`core/performance_monitor.py`)
- GitHub Actions CI/CD 流水线
- 完整的文档体系 (Sphinx, 架构文档, 开发指南)
- 测试覆盖率配置
- 依赖版本锁定 (`requirements.lock`)

### Changed
- 优化项目文件结构，资源文件归类到 `assets/`
- 更新构建脚本以适配新的目录结构
- 改进 `.gitignore` 配置

### Fixed
- 修复构建脚本中的路径引用问题
- 修复 `core/builtin_icons.py` 中的路径

### Removed
- 删除虚拟环境目录 (节省 1GB 空间)
- 删除所有缓存和临时文件
- 删除旧的 PerformanceMonitor 项目

### Security
- 添加依赖版本上限约束
- 添加 bandit 安全扫描
- CI/CD 添加权限控制

## [1.5.6.5] - 2026-04-29

### Added
- 基础功能实现

## [1.5.6.4] - 2026-04-28

### Added
- 初始版本发布
