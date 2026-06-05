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
PLUGIN_BLOCKED_IMPORT_ROOTS = frozenset({"subprocess"})
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
