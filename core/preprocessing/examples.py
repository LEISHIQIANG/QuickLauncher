"""预处理系统使用示例

本文档展示如何使用命令预处理系统。
"""

from core.preprocessing import PreprocessingContext, PreprocessingPipeline
from core.preprocessing.pipeline import create_pipeline_from_settings


# 示例 1: 基本使用
def example_basic():
    """基本预处理示例"""
    pipeline = PreprocessingPipeline(enabled=True, rate_limiting=False)

    context = PreprocessingContext(
        shortcut_id="test-001",
        command="echo hello world",
        command_type="cmd",
    )

    result = pipeline.process(context)

    if result.success:
        print("✓ 命令验证通过")
    else:
        print("✗ 命令验证失败:")
        for error in result.errors:
            print(f"  - {error.message}")


# 示例 2: 检测命令注入
def example_command_injection():
    """命令注入检测示例"""
    pipeline = PreprocessingPipeline(enabled=True, rate_limiting=False)

    context = PreprocessingContext(
        command="echo hello; rm -rf /",
        command_type="cmd",
    )

    result = pipeline.process(context)

    print(f"警告数量: {len(result.warnings)}")
    for warning in result.warnings:
        print(f"  - [{warning.severity}] {warning.description}")


# 示例 3: 原始模式（跳过变量扩展）
def example_raw_mode():
    """原始模式示例 - 命令包含 {} 字符"""
    pipeline = PreprocessingPipeline(enabled=True, rate_limiting=False)

    # PowerShell 脚本块包含 {}
    context = PreprocessingContext(
        command='powershell -Command "Get-Process | Where-Object {$_.CPU -gt 100}"',
        command_type="cmd",
        raw_mode=True,  # 启用原始模式，不解析 {} 为变量
    )

    result = pipeline.process(context)
    print(f"原始模式: {result.metadata.get('raw_mode')}")


# 示例 4: 从设置创建管道
def example_from_settings():
    """从 AppSettings 创建管道"""
    from core.data_models import AppSettings

    settings = AppSettings()
    settings.preprocessing_enabled = True
    settings.preprocessing_strict_mode = False
    settings.security_block_dangerous_patterns = True

    pipeline = create_pipeline_from_settings(settings)

    context = PreprocessingContext(
        command="format C:",
        command_type="cmd",
    )

    result = pipeline.process(context)

    if result.should_block:
        print("✗ 命令被阻止（危险操作）")


# 示例 5: 用户控制选项说明
def example_user_controls():
    """
    用户可控制的预处理选项：

    1. 全局开关（AppSettings）:
       - preprocessing_enabled: 启用/禁用整个预处理系统
       - preprocessing_strict_mode: 严格模式（警告也阻止）
       - preprocessing_audit_enabled: 启用审计日志
       - preprocessing_rate_limiting_enabled: 启用速率限制
       - security_block_dangerous_patterns: 阻止危险模式
       - security_require_variable_quoting: 强制变量引用

    2. 单个命令开关（ShortcutItem）:
       - command_variables_enabled: 是否解析变量（{{clipboard}}等）
       - raw_mode: 原始模式，跳过变量扩展但仍执行安全检查

    区别说明：
    - command_variables_enabled=False: 完全不解析变量
    - raw_mode=True: 不解析变量，但仍执行预处理的其他检查

    推荐使用：
    - 普通用户：使用 command_variables_enabled 控制变量解析
    - 高级用户：使用 raw_mode 处理包含 {} 的特殊命令
    """
    pass


if __name__ == "__main__":
    print("=== 预处理系统示例 ===\n")

    print("1. 基本使用:")
    example_basic()
    print()

    print("2. 命令注入检测:")
    example_command_injection()
    print()

    print("3. 原始模式:")
    example_raw_mode()
    print()

    print("4. 从设置创建:")
    example_from_settings()
