"""Re-export of built-in command handlers.

The actual handler implementations live in per-domain modules:

* :mod:`core.commands_encoding` — url encode, color, hash, uuid, timestamp, base64
* :mod:`core.commands_network` — ip, netdiag, cidr, tls, wifi, hosts, port, dns
* :mod:`core.commands_text` — json, jwt, path-audit
* :mod:`core.commands_clipboard` — clip, copy-path, selected
* :mod:`core.commands_utils` — qr, explorer, conflict

This module keeps the historical ``from core.commands import cmd_qr`` style
imports working without changes.
"""

from __future__ import annotations

import socket  # noqa: F401  # re-exported so tests can mock.patch("core.commands.socket")
import ssl  # noqa: F401  # re-exported so tests can mock.patch("core.commands.ssl")

from .commands_clipboard import (  # noqa: F401
    cmd_clip as cmd_clip,
)
from .commands_clipboard import (
    cmd_copy_path as cmd_copy_path,
)
from .commands_clipboard import (
    cmd_selected as cmd_selected,
)
from .commands_encoding import (  # noqa: F401
    _hash_file as _hash_file,
)
from .commands_encoding import (
    _hex_to_rgb as _hex_to_rgb,
)
from .commands_encoding import (
    cmd_base64 as cmd_base64,
)
from .commands_encoding import (
    cmd_color as cmd_color,
)
from .commands_encoding import (
    cmd_hash as cmd_hash,
)
from .commands_encoding import (
    cmd_timestamp as cmd_timestamp,
)
from .commands_encoding import (
    cmd_urlencode as cmd_urlencode,
)
from .commands_encoding import (
    cmd_uuid as cmd_uuid,
)
from .commands_git import cmd_git as cmd_git  # noqa: F401
from .commands_maintenance import cmd_clean_cache as cmd_clean_cache  # noqa: F401
from .commands_maintenance import cmd_config_repair as cmd_config_repair  # noqa: F401
from .commands_network import (  # noqa: F401
    _fetch_public_ip as _fetch_public_ip,
)
from .commands_network import (
    _format_cert_subject as _format_cert_subject,
)
from .commands_network import (
    _get_local_ipv4_addresses as _get_local_ipv4_addresses,
)
from .commands_network import (
    _get_primary_local_ip as _get_primary_local_ip,
)
from .commands_network import (
    _normalize_host_input as _normalize_host_input,
)
from .commands_network import (
    _normalize_tls_target as _normalize_tls_target,
)
from .commands_network import (
    _parse_ping_summary as _parse_ping_summary,
)
from .commands_network import (
    _run_cmd as _run_cmd,
)
from .commands_network import (
    cmd_cidr as cmd_cidr,
)
from .commands_network import (
    cmd_dns as cmd_dns,
)
from .commands_network import (
    cmd_hosts as cmd_hosts,
)
from .commands_network import (
    cmd_ip as cmd_ip,
)
from .commands_network import (
    cmd_netdiag as cmd_netdiag,
)
from .commands_network import (
    cmd_port as cmd_port,
)
from .commands_network import (
    cmd_tls as cmd_tls,
)
from .commands_network import (
    cmd_wifi as cmd_wifi,
)
from .commands_plugins import cmd_plugin_list as cmd_plugin_list  # noqa: F401
from .commands_plugins import cmd_plugin_new as cmd_plugin_new  # noqa: F401
from .commands_plugins import cmd_plugin_reload as cmd_plugin_reload  # noqa: F401
from .commands_system import cmd_process as cmd_process  # noqa: F401
from .commands_system import cmd_sysreport as cmd_sysreport  # noqa: F401
from .commands_text import (  # noqa: F401
    _decode_base64url_json as _decode_base64url_json,
)
from .commands_text import (
    _text_from_args_or_clipboard as _text_from_args_or_clipboard,
)
from .commands_text import (
    cmd_json as cmd_json,
)
from .commands_text import (
    cmd_jwt as cmd_jwt,
)
from .commands_text import (
    cmd_path_audit as cmd_path_audit,
)
from .commands_utils import (  # noqa: F401
    _cleanup_qr_temp_files as _cleanup_qr_temp_files,
)
from .commands_utils import (
    _qr_get_local_ip as _qr_get_local_ip,
)
from .commands_utils import (
    _start_qr_file_server as _start_qr_file_server,
)
from .commands_utils import (
    _stop_all_qr_file_servers as _stop_all_qr_file_servers,
)
from .commands_utils import (
    cmd_conflict as cmd_conflict,
)
from .commands_utils import (
    cmd_explorer as cmd_explorer,
)
from .commands_utils import (
    cmd_qr as cmd_qr,
)
from .commands_utils import (
    stop_qr_file_server as stop_qr_file_server,
)
from .commands_windows import cmd_env as cmd_env  # noqa: F401
from .commands_windows import cmd_god as cmd_god  # noqa: F401

__all__ = [
    "_cleanup_qr_temp_files",
    "_decode_base64url_json",
    "_fetch_public_ip",
    "_format_cert_subject",
    "_get_local_ipv4_addresses",
    "_get_primary_local_ip",
    "_hash_file",
    "_hex_to_rgb",
    "_normalize_host_input",
    "_normalize_tls_target",
    "_parse_ping_summary",
    "_qr_get_local_ip",
    "_run_cmd",
    "_start_qr_file_server",
    "_stop_all_qr_file_servers",
    "_text_from_args_or_clipboard",
    "cmd_base64",
    "cmd_cidr",
    "cmd_clean_cache",
    "cmd_clip",
    "cmd_color",
    "cmd_conflict",
    "cmd_config_repair",
    "cmd_copy_path",
    "cmd_dns",
    "cmd_env",
    "cmd_explorer",
    "cmd_git",
    "cmd_god",
    "cmd_hash",
    "cmd_hosts",
    "cmd_ip",
    "cmd_json",
    "cmd_jwt",
    "cmd_netdiag",
    "cmd_path_audit",
    "cmd_plugin_list",
    "cmd_plugin_new",
    "cmd_plugin_reload",
    "cmd_port",
    "cmd_process",
    "cmd_qr",
    "cmd_selected",
    "cmd_sysreport",
    "cmd_timestamp",
    "cmd_tls",
    "cmd_urlencode",
    "cmd_uuid",
    "cmd_wifi",
    "stop_qr_file_server",
]
