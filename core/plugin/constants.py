"""Plugin subsystem constants."""

PERMISSIONS_KNOWN = frozenset(
    {
        "clipboard.read",
        "clipboard.write",
        "file.read",
        "file.write",
        "open.url",
        "open.file",
        "process.run",
        "network.request",
        "builtin.command",
        "admin.required",
    }
)

HIGH_RISK_PERMISSIONS = frozenset(
    {
        "process.run",
        "file.write",
        "admin.required",
    }
)

PLUGIN_TRUST_LEVELS = ("builtin", "local-trusted", "community-unverified")
PLUGIN_PACKAGE_EXTENSION = ".qlzip"
# Trust anchors for repository-maintained plugin packages.  A package is
# considered builtin only when both its canonical source path and its digest
# match this table; the writable package path alone is not a trust boundary.
OFFICIAL_PLUGIN_PACKAGE_SHA256 = {
    "api_tester": "611da699b6d434243a9c466e4f911c48b844c9f0e97fda1561e91a6f8e718dbb",
    "disk_cleaner": "e5066468d06869fafe6c38b3f16ad1c9cba87e882a18d2c8fde5df934d0bd627",
    "event_inspector": "3137bc9ebd2f51d4021f849f871093e3b3aa229b21b3e0a254f9a6cfc136b0c2",
    "file_tools": "06d4eae4663baf998a588a7a7b09e6851f831e54a53adc2ea91b52f5427d6d3b",
    "network_tools": "10037cdaffd524e01271c24709851d3c73b849b0e8e5b7448fbb8a52dbad8998",
    "process_tools": "a69f2e03bd08914b70d878bd8b78cb88c34e75f90646a9f234c52534592e3e86",
    "qr_code_scanner": "3bb074a7d47319dce7c8578995c6667b7446cf6a752bf4215e78c76b3da911a0",
    "screenshot_ocr": "dc1001c62b2b83f1c328af6a14ebe255a8fcbdda0f38f88f2e3801f1c4a731e8",
    "startup_tools": "1d1a6a37c9959cba0e85d991b98b57f88c6ebe3ac0dd28b2a339e4cd12a8954f",
    "text_tools": "0741cd2ca930c27b2cd636cb0fb55b6066ed3ad77ecfd2f69d2f9512c6156250",
}
PLUGIN_STATE_SCHEMA = 1
PLUGIN_FAILURE_WINDOW_SECONDS = 10 * 60
PLUGIN_FAILURE_THRESHOLD = 3
PLUGIN_COMMAND_SOFT_TIMEOUT_SECONDS = 30
PLUGIN_ERROR_LOG_MAX_BYTES = 1024 * 1024
PLUGIN_ERROR_LOG_BACKUPS = 3
PLUGIN_PACKAGE_MAX_UNCOMPRESSED_BYTES = 150 * 1024 * 1024
PLUGIN_PACKAGE_MAX_FILES = 1000
PLUGIN_API_MAX_TEXT_FILE_BYTES = 2 * 1024 * 1024
PLUGIN_API_MAX_HTTP_REQUEST_BYTES = 2 * 1024 * 1024
PLUGIN_API_MAX_HTTP_RESPONSE_BYTES = 2 * 1024 * 1024
PLUGIN_API_HTTP_TIMEOUT_SECONDS = 10.0
PLUGIN_API_HTTP_METHODS = frozenset({"GET", "POST", "HEAD"})
PLUGIN_API_MAX_HTTP_HEADERS = 64
PLUGIN_API_MAX_HTTP_HEADER_CHARS = 8192
PLUGIN_BLOCKED_IMPORT_ROOTS = frozenset(
    {
        "ctypes",
        "multiprocessing",
        "socket",
        "subprocess",
    }
)
PLUGIN_OS_BLOCKED_ATTRS = frozenset(
    {
        "execl",
        "execle",
        "execlp",
        "execlpe",
        "execv",
        "execve",
        "execvp",
        "execvpe",
        "popen",
        "spawnl",
        "spawnle",
        "spawnlp",
        "spawnlpe",
        "spawnv",
        "spawnve",
        "spawnvp",
        "spawnvpe",
        "startfile",
        "system",
    }
)
