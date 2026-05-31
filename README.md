# QuickLauncher 插件目录

这个目录存放 QuickLauncher 本地插件，会被 `core.plugin_manager.PluginManager` 扫描并注册到统一命令中心。

## CHANGELOG 记录要求

每次修改本目录下插件代码后，必须在项目根目录的 `CHANGELOG.md` 中记录变更。以日期为章节标题（一天一章），注明修改的文件和主要内容。格式示例：

```text
## 2026-05-31

- plugins/my_plugin/main.py：修复路径处理错误
```

## 插件开发指南

完整开发指南见项目根目录：

```text
PLUGIN_DEV.md
```
