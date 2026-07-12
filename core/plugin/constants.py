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
    "api_tester": "ffa720e56a95b010c8a3ec38ac9cd00f2095855bf26433365f65291faeaa8aef",
    "disk_cleaner": "e01d959afde16b768dd5ef87c101cde807c9cc107c4924228aee5cc5e61e2f3f",
    "event_inspector": "5b30d5624a371548798132949a06b00c027c75c3d527eb4dfb0562e3b0c161fe",
    "file_tools": "1408082784cef004f2866d95fb8fec53952b8a1fcad827d0b1fc4c37d420cddd",
    "network_tools": "9c30417a19149a96c58698454915eac445e165787027e3f10d332330dafad838",
    "process_tools": "ea7a4f891adfbb0045c36037f6db41900ab7b9c9ee8a8c6fac93bd29771c8754",
    "qr_code_scanner": "49ce5a3b14994c871b3bf46c7f82e4819268952d718a15e7dcc14ab8970635d3",
    "screenshot_ocr": "323f9f5431e7560f11ff707dba93faba7354555a4901778e8efcc49118f1ddb9",
    "startup_tools": "af443e9a737e557f52f33cb3215f09b3e2c1cc55e277d33999aca61563fa1c9d",
    "text_tools": "b02f4f89d6874652e286c8c7b7a4370c77d2483ca17bb6100826b31cee60916f",
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
