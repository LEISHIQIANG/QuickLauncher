"""Security validation for command preprocessing."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass


@dataclass
class SecurityIssue:
    """Security issue detected during validation."""

    type: str
    severity: str
    description: str
    mitigation: str = ""


def detect_command_injection(command: str, command_type: str) -> list[SecurityIssue]:
    """Detect command injection attempts."""
    issues = []

    if command_type not in ("cmd", "python", "powershell", "bash"):
        return issues

    dangerous_chars = {
        ";": "命令分隔符",
        "&": "后台执行或命令链接",
        "|": "管道操作",
        "<": "输入重定向",
        ">": "输出重定向",
        "$": "变量扩展或子 Shell",
        "`": "命令替换",
    }

    for char, desc in dangerous_chars.items():
        if char in command:
            issues.append(
                SecurityIssue(
                    type="command_injection",
                    severity="high",
                    description=f"检测到危险字符 {char}（{desc}）",
                    mitigation="移除或转义该字符，或使用原始模式",
                )
            )

    chaining_patterns = [("&&", "命令链接"), ("||", "命令链接"), (";", "命令分隔")]
    for pattern, desc in chaining_patterns:
        if pattern in command:
            issues.append(
                SecurityIssue(
                    type="command_chaining",
                    severity="high",
                    description=f"检测到{desc}: {pattern}",
                    mitigation="使用单独命令或链式步骤",
                )
            )

    if command_type == "bash" and re.search(r"\$\(", command):
        issues.append(
            SecurityIssue(
                type="command_substitution",
                severity="high",
                description="检测到命令替换 $(...)，可能导致命令注入",
                mitigation="确认替换内容来源安全，或使用原始模式",
            )
        )

    return issues


def validate_safe_path(path: str, base_dir: str | None = None) -> SecurityIssue | None:
    """Validate path for traversal attempts."""
    if not path:
        return None

    normalized = os.path.normpath(path)

    if ".." in normalized:
        return SecurityIssue(
            type="path_traversal",
            severity="high",
            description="检测到路径遍历尝试",
            mitigation="使用绝对路径或允许目录内的路径",
        )

    if base_dir:
        try:
            abs_path = os.path.abspath(normalized)
            abs_base = os.path.abspath(base_dir)
            if not abs_path.startswith(abs_base):
                return SecurityIssue(
                    type="path_escape",
                    severity="high",
                    description="路径超出允许目录",
                    mitigation=f"路径必须在 {base_dir} 内",
                )
        except Exception:
            pass

    return None


def validate_variable_quoting(command: str, command_type: str) -> list[SecurityIssue]:
    """Validate external variables are properly quoted."""
    issues = []

    if command_type not in ("cmd", "powershell", "bash"):
        return issues

    from core.command_variables import find_unquoted_external_command_variables

    try:
        unquoted = find_unquoted_external_command_variables(command)
        for var in unquoted:
            issues.append(
                SecurityIssue(
                    type="unquoted_variable",
                    severity="high",
                    description=f"变量 {{{var}}} 必须引用",
                    mitigation="将 {{" + var + "}} 改为 {{" + var + ":q}}",
                )
            )
    except Exception:
        pass

    return issues


_DANGEROUS_PATTERNS = [
    # 文件操作
    (re.compile(r"\b(del|erase)\s+", re.I), "文件删除", "medium"),
    (re.compile(r"\b(rmdir|rd)\s+/s", re.I), "递归删除目录", "high"),
    (re.compile(r"\b(Remove-Item|rm)\b.*-Recurse", re.I), "PowerShell 递归删除", "high"),
    (re.compile(r"\b(Remove-Item|rm)\b.*-Force", re.I), "PowerShell 强制删除", "high"),
    (re.compile(r"\bClear-Content\b.*-Force", re.I), "清空文件内容", "medium"),
    # 磁盘操作
    (re.compile(r"\bformat\s+[a-z]:", re.I), "格式化磁盘", "critical"),
    (re.compile(r"\bdiskpart\b", re.I), "磁盘分区操作", "critical"),
    (re.compile(r"\bbcdedit\b", re.I), "启动配置修改", "critical"),
    (re.compile(r"\bbootrec\b", re.I), "启动记录修改", "critical"),
    # 系统操作
    (re.compile(r"\bshutdown\s+/[srg]", re.I), "关机或重启", "medium"),
    (re.compile(r"\b(Stop-Computer|Restart-Computer)\b", re.I), "PowerShell 关机重启", "medium"),
    # 注册表操作
    (re.compile(r"\breg\s+delete\b", re.I), "删除注册表", "high"),
    (re.compile(r"\breg\s+add\b.*\\Run", re.I), "添加自启动项", "high"),
    (re.compile(r"\bRemove-ItemProperty\b.*HKCU", re.I), "删除注册表属性", "high"),
    # 进程操作
    (re.compile(r"\btaskkill\b.*\s/f\b", re.I), "强制结束进程", "medium"),
    (re.compile(r"\bStop-Process\b.*-Force", re.I), "PowerShell 强制停止进程", "medium"),
    # 权限与执行策略
    (re.compile(r"\bSet-ExecutionPolicy\b.*Bypass", re.I), "绕过执行策略", "high"),
    (re.compile(r"\bSet-ExecutionPolicy\b.*Unrestricted", re.I), "取消执行限制", "high"),
    (re.compile(r"\btakeown\b.*\s/f\b", re.I), "获取文件所有权", "high"),
    (re.compile(r"\bicacls\b.*\s/grant\b", re.I), "修改文件权限", "high"),
    # 网络操作
    (re.compile(r"\b(wget|curl|Invoke-WebRequest)\b", re.I), "网络下载", "medium"),
    (re.compile(r"\bStart-BitsTransfer\b", re.I), "BITS 传输", "medium"),
    (re.compile(r"\bInvoke-RestMethod\b", re.I), "REST API 调用", "low"),
    # 数据外泄
    (re.compile(r"\b(ftp|sftp|scp)\b", re.I), "文件传输协议", "high"),
    (re.compile(r"\bSend-MailMessage\b", re.I), "发送邮件", "medium"),
    (re.compile(r"\bInvoke-WebRequest\b.*-Method\s+Post", re.I), "POST 数据上传", "medium"),
    # 持久化
    (re.compile(r"\bschtasks\b.*\s/create\b", re.I), "创建计划任务", "high"),
    (re.compile(r"\bNew-ScheduledTask\b", re.I), "PowerShell 创建计划任务", "high"),
    (re.compile(r"\bRegister-ScheduledTask\b", re.I), "注册计划任务", "high"),
    # 服务操作
    (re.compile(r"\bsc\s+(create|delete|config)\b", re.I), "服务控制", "high"),
    (re.compile(r"\bnet\s+(start|stop)\b", re.I), "网络服务控制", "medium"),
    (re.compile(r"\b(New-Service|Remove-Service)\b", re.I), "PowerShell 服务操作", "high"),
    # 凭证访问
    (re.compile(r"\bmimikatz\b", re.I), "凭证窃取工具", "critical"),
    (re.compile(r"\bInvoke-Mimikatz\b", re.I), "PowerShell 凭证窃取", "critical"),
    (re.compile(r"\bGet-Credential\b", re.I), "获取凭证", "medium"),
    # 横向移动
    (re.compile(r"\bpsexec\b", re.I), "远程执行工具", "high"),
    (re.compile(r"\bwmic\b.*process\s+call\s+create", re.I), "WMI 远程执行", "high"),
    (re.compile(r"\bInvoke-Command\b.*-ComputerName", re.I), "PowerShell 远程执行", "high"),
    # 防御规避
    (re.compile(r"\bSet-MpPreference\b.*-DisableRealtimeMonitoring", re.I), "禁用实时监控", "critical"),
    (re.compile(r"\bAdd-MpPreference\b.*-ExclusionPath", re.I), "添加排除路径", "high"),
    (re.compile(r"\bDisable-WindowsOptionalFeature\b", re.I), "禁用 Windows 功能", "high"),
    # 编码与混淆
    (re.compile(r"-EncodedCommand\b", re.I), "编码命令", "high"),
    (re.compile(r"\[Convert\]::FromBase64String", re.I), "Base64 解码", "medium"),
    (re.compile(r"IEX\s*\(", re.I), "动态执行", "high"),
    (re.compile(r"Invoke-Expression\b", re.I), "表达式执行", "high"),
]


def detect_dangerous_patterns(command: str, command_type: str) -> list[SecurityIssue]:
    """Detect dangerous command patterns."""
    issues = []

    if command_type == "builtin":
        return issues

    for pattern, desc, severity in _DANGEROUS_PATTERNS:
        if pattern.search(command):
            issues.append(
                SecurityIssue(
                    type="dangerous_pattern",
                    severity=severity,
                    description=f"检测到危险操作: {desc}",
                    mitigation="确认操作安全性",
                )
            )

    return issues


def validate_environment_variables(env: dict) -> list[SecurityIssue]:
    """Validate environment variables for security issues."""
    issues = []

    dangerous_vars = ["LD_PRELOAD", "DYLD_INSERT_LIBRARIES", "LD_LIBRARY_PATH"]
    for var in dangerous_vars:
        if var in env:
            issues.append(
                SecurityIssue(
                    type="dangerous_env_var",
                    severity="high",
                    description=f"危险环境变量: {var}",
                    mitigation="移除该环境变量",
                )
            )

    return issues
