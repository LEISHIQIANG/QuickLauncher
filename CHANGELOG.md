# Changelog

All notable changes to QuickLauncher will be documented in this file.

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
