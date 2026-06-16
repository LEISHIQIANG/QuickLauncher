# QuickLauncher GitHub 维护指南

本文档记录当前仓库的 GitHub 维护、CI 和发布操作。它不是首次建仓清单。

仓库地址：https://github.com/LEISHIQIANG/QuickLauncher

## 当前仓库口径

| 项 | 当前值 |
|---|---|
| 默认分支 | `main` |
| 当前源码版本 | 以 `core/version.py` 的 `APP_VERSION` 为准，目前为 `1.6.3.1` |
| 发布状态 | `stable` |
| 运行平台 | Windows 10 / 11 x64 |
| 源码 Python | CPython 3.12 |
| CI 平台 | GitHub Actions `windows-latest` + Python 3.12 |
| 发布包 | `QuickLauncher_Setup_<version>.exe`、`QuickLauncher_Portable_<version>.zip` |

## GitHub 页面内容

GitHub 首页主要来自：

- `README.md`：中文首页。
- `README_EN.md`：英文首页。
- `README_FULL.md`：中文完整文档。
- `README_FULL_EN.md`：英文完整文档。
- `CHANGELOG.md`：版本变更。
- `LICENSE`：MIT 协议。

修改功能描述时，至少同步 `README.md`、`README_EN.md`、`README_FULL.md` 和 `README_FULL_EN.md`。涉及插件、Hook、系统图标时同步对应子目录 README。

## CI 工作流

工作流文件：[.github/workflows/ci.yml](workflows/ci.yml)

CI 会在 push 和 pull request 上运行：

1. 安装 `requirements.txt` 和 `requirements-dev.txt`。
2. 执行源码门禁：

   ```powershell
   python scripts/release_gate.py --skip-tests --skip-smoke
   ```

3. 执行重点测试：

   ```powershell
   python -m pytest `
     tests/test_release_gate.py `
     tests/test_diagnostics.py `
     tests/test_shortcut_health.py `
     tests/test_ui_smoke.py `
     tests/test_pinyin_search.py `
     tests/test_exception_logging_policy.py `
     tests/test_popup_search_ui.py `
     tests/test_chain_registry_processors.py `
     tests/test_processor_loader.py `
     tests/test_path_security.py `
     tests/test_update_trust.py
   ```

4. 执行 mypy 子集：

   ```powershell
   python -m mypy --follow-imports=skip services/update
   ```

## 本地推送前检查

推荐在 Windows 本地使用同样的 Python 3.12：

```powershell
git status --short --branch
py -3.12 -m pip install -r requirements.txt -r requirements-dev.txt
py -3.12 scripts/release_gate.py --skip-smoke
py -3.12 main.py --safe-mode --smoke-test
```

如果只改文档，至少执行：

```powershell
py -3.12 -m pytest tests/test_release_metadata.py tests/test_release_gate.py -q
```

## 推送流程

```powershell
git status --short --branch
git diff -- README.md README_EN.md README_FULL.md README_FULL_EN.md
git add <需要提交的文件>
git commit -m "docs: update project documentation"
git push origin main
```

注意：

- 不要使用 `git add .` 盲目提交构建产物、缓存、用户配置或无关本地改动。
- 当前项目经常会出现未跟踪 `%SystemDrive%/`、`dist/`、`.pytest_cache/` 等运行残留，提交前要确认没有被暂存。
- 除非明确需要改写历史，不要使用强制推送。

## 发布包构建

```powershell
scripts\build_win11_setup.bat
```

构建脚本会输出：

- `dist/QuickLauncher_Setup_<version>.exe`
- `dist/QuickLauncher_Portable_<version>.zip`
- `dist/QuickLauncher_release_<version>.json`
- `dist/QuickLauncher_Setup_<version>.sha256`
- `dist/QuickLauncher_Portable_<version>.sha256`

构建脚本会调用：

```powershell
scripts\check_release_artifacts.py --allow-source-runtime-plugins --run-smoke
```

发布包策略：

- 发布包保留空 `plugins/` 运行时安装目录。
- 官方插件以 `.plugins/*.qlzip` 形式维护，不把源码插件目录直接塞入主程序。
- 安装器关闭 QuickLauncher 本体时不能使用 `taskkill /T`，由 QuickLauncher 启动的其他程序必须保持独立生命周期。

## 上传或覆盖 Release 资产

同名资产覆盖使用：

```powershell
gh release upload <tag> `
  dist\QuickLauncher_Setup_<version>.exe `
  dist\QuickLauncher_Portable_<version>.zip `
  --clobber
```

上传后需要验证远端资产：

- 名称。
- 文件大小。
- SHA-256 digest。

不要只看 `gh release upload` 返回成功。

## 仓库设置建议

### About

- Description: `Windows desktop quick launcher and lightweight automation tool`
- Topics: `windows`, `launcher`, `productivity`, `automation`, `pyqt5`, `nuitka`

### Actions

- 允许 GitHub Actions 运行。
- 默认 CI 已覆盖源码门禁和重点测试。

### Branch protection

如果启用 `main` 分支保护，建议至少要求：

- CI 通过。
- 禁止直接强推。

## 常见问题

### CI 中 release gate 失败

先本地复现：

```powershell
py -3.12 scripts/release_gate.py --skip-smoke
```

检查是否是 ruff、pytest 覆盖率、异常审计、compileall、release metadata 或 post-package smoke 中的某一步失败。

### 推送被 rejected

远端已有新提交时：

```powershell
git pull origin main --rebase
git push origin main
```

不要直接强推覆盖远端，除非已经明确确认需要改写历史。

### Release 覆盖后文件不对

使用 `gh release view` / `gh api` 查看资产，比较远端大小和 SHA-256。只依赖上传命令成功不够。

### README 与代码不一致

以代码和包清单为准：

- `core/version.py`：版本。
- `core/data_models.py`：快捷方式类型和设置字段。
- `core/builtin_command_catalog.py`：内置命令。
- `core/chain/registry.py`：动作链处理器。
- `.plugins/*.qlzip`：官方插件包。
- `scripts/release_gate.py` 和 `.github/workflows/ci.yml`：验证门禁。
