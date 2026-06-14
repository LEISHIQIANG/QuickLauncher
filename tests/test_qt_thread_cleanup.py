from ui.utils.qt_thread_cleanup import _disconnect_named_signals


class _DeletedQObjectProxy:
    def __getattr__(self, _name):
        raise RuntimeError("wrapped C/C++ object has been deleted")


def test_disconnect_named_signals_tolerates_deleted_qobject():
    _disconnect_named_signals(_DeletedQObjectProxy(), ("finished", "result_ready"))
