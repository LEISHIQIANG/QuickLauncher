# GitHub 上传指南

## 准备完成清单

### ✅ 已创建的文件
- [x] LICENSE - MIT 开源协议
- [x] CHANGELOG.md - 版本更新历史
- [x] README.md - 增强的项目说明（含徽章、安装指南）
- [x] .github/workflows/ci.yml - CI/CD 流水线
- [x] .github/ISSUE_TEMPLATE/bug_report.md - Bug 报告模板
- [x] .github/ISSUE_TEMPLATE/feature_request.md - 功能请求模板
- [x] .github/PULL_REQUEST_TEMPLATE.md - PR 模板

### ✅ 已配置的文件
- [x] .gitignore - 完善的忽略规则
- [x] 项目结构已整理
- [x] 文档已归类到 docs/
- [x] 资源已归类到 assets/

### ✅ 已删除的敏感/不必要文件
- [x] 虚拟环境目录
- [x] 缓存文件
- [x] 临时文件
- [x] 构建产物（dist/ 在 .gitignore 中）

---

## 推送到 GitHub

### 1. 检查当前状态
```bash
git status
```

### 2. 添加远程仓库（如果还没添加）
```bash
git remote add origin https://github.com/LEISHIQIANG/QuickLauncher.git
```

如果已存在，更新远程地址：
```bash
git remote set-url origin https://github.com/LEISHIQIANG/QuickLauncher.git
```

### 3. 暂存所有更改
```bash
# 添加新文件和修改
git add .

# 添加删除的文件（builtin_icons 移动）
git add -A
```

### 4. 提交更改
```bash
git commit -m "feat: 项目优化和 GitHub 准备

- 添加代码质量工具 (mypy, ruff, black, pre-commit)
- 添加 CI/CD 流水线
- 完善文档体系
- 优化项目结构
- 添加 LICENSE 和 CHANGELOG
- 创建 GitHub 模板
- 修复构建脚本路径问题
- 清理虚拟环境和缓存文件（节省 1GB）

详见 docs/DAILY_SUMMARY.md"
```

### 5. 推送到 GitHub
```bash
# 首次推送（如果是新分支）
git push -u origin main

# 或者如果分支已存在
git push origin main
```

如果遇到冲突或需要强制推送（谨慎使用）：
```bash
git push -f origin main
```

---

## 推送后的配置

### 1. GitHub 仓库设置

访问: https://github.com/LEISHIQIANG/QuickLauncher/settings

#### 基本设置
- **Description**: 一款轻量级的鼠标中键快速启动工具
- **Website**: (可选)
- **Topics**: `windows`, `launcher`, `productivity`, `python`, `pyqt5`

#### 功能设置
- [x] Issues - 启用问题追踪
- [x] Projects - 启用项目管理（可选）
- [x] Wiki - 启用 Wiki（可选）
- [x] Discussions - 启用讨论（可选）

#### Actions 权限
- Settings → Actions → General
- 允许所有 actions 和可重用工作流

### 2. 创建 Release

1. 访问: https://github.com/LEISHIQIANG/QuickLauncher/releases/new
2. Tag version: `v1.5.6.6`
3. Release title: `QuickLauncher v1.5.6.6`
4. 描述: 从 CHANGELOG.md 复制内容
5. 上传构建好的安装包（如果有）
6. 发布

### 3. 设置分支保护（可选）

Settings → Branches → Add rule
- Branch name pattern: `main`
- [x] Require pull request reviews before merging
- [x] Require status checks to pass before merging
  - [x] CI

---

## 验证清单

推送后请验证：

### GitHub 页面
- [ ] README 正确显示，徽章正常
- [ ] LICENSE 文件可见
- [ ] CHANGELOG 可访问
- [ ] 文档目录结构正确
- [ ] .gitignore 生效（config/, dist/ 等未上传）

### CI/CD
- [ ] Actions 标签页显示工作流
- [ ] CI 自动运行
- [ ] 检查 CI 是否通过

### 文档
- [ ] docs/ 目录下所有文档可访问
- [ ] 链接正常工作

### 问题模板
- [ ] Issues → New issue 显示模板选项
- [ ] Bug 报告模板正常
- [ ] 功能请求模板正常

---

## 常见问题

### Q: 推送时提示 "rejected"
A: 远程有新提交，先拉取：
```bash
git pull origin main --rebase
git push origin main
```

### Q: 文件太大无法推送
A: 检查 .gitignore 是否正确配置，确保大文件被忽略

### Q: CI 失败
A: 查看 Actions 日志，通常是依赖安装或测试失败

### Q: 想要撤销推送
A: 谨慎操作，可能影响其他协作者
```bash
git reset --hard HEAD~1
git push -f origin main
```

---

## 下一步

1. **添加徽章**: 在 README 中添加 CI 状态徽章
2. **编写 Wiki**: 详细的使用文档
3. **设置 GitHub Pages**: 托管 Sphinx 文档
4. **配置 Dependabot**: 自动依赖更新
5. **添加贡献者指南**: 吸引开源贡献

---

**准备完成！现在可以推送到 GitHub 了。**

仓库地址: https://github.com/LEISHIQIANG/QuickLauncher
