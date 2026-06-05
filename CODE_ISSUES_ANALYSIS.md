# QuickLauncher V1.6.3.0 深度问题分析报告

---

## 1. C++ EnsureCallbackThread 非线程安全

**问题**

`hooks_dll/hooks.cpp` 第 221-229 行的 `EnsureCallbackThread()` 函数在多线程环境下可能被同时调用（鼠标钩子回调和键盘钩子回调分别在系统线程池的不同线程上执行），但内部没有互斥锁保护 `g_callbackThreadRunning` 和 `g_callbackThread` 两个全局变量。当鼠标和键盘钩子几乎同时触发时，两个线程可能同时通过条件检查，各自创建一个回调线程和一个 Event 对象，第一个 Event 句柄被第二个覆盖导致句柄泄漏，且两个回调线程会竞争同一个回调队列。

**问题分析**

`WH_MOUSE_LL` 和 `WH_KEYBOARD_LL` 的回调函数分别在系统线程池线程上执行，不受应用主线程控制。当用户快速操作（例如同时按下键盘和移动鼠标），两个钩子回调可能在微秒级间隔内同时调用 `EnsureCallbackThread()`。函数内部先检查 `g_callbackThreadRunning`（bool 变量），再检查 `g_callbackThread`（HANDLE），然后创建 Event 和 Thread。这个 check-then-act 序列不是原子的，属于经典的 TOCTOU（Time of Check, Time of Use）竞态条件。后果包括：回调事件丢失（写入已覆盖的 Event 句柄）、回调队列被两个线程同时消费导致数据竞争、以及泄漏的线程和 Event 句柄在长时间运行后耗尽系统资源。

**解决思路**

在 `EnsureCallbackThread` 中使用 `std::mutex` + `std::lock_guard` 保护整个初始化序列，或使用 `std::call_once` + `std::once_flag` 确保回调线程只创建一次。推荐 `std::call_once` 方案，因为它语义更清晰且无额外锁开销：

```cpp
static std::once_flag s_callbackThreadOnce;
std::call_once(s_callbackThreadOnce, []() {
    g_callbackEvent = CreateEventW(nullptr, FALSE, FALSE, nullptr);
    g_callbackThread = CreateThread(nullptr, 0, CallbackThreadProc, nullptr, 0, nullptr);
    g_callbackThreadRunning = true;
});
```

---

## 2. thread.terminate() 强制终止线程

**问题**

`ui/config_window/command_dialog.py` 第 1474 行、`shortcut_dialog.py` 第 346 行和第 496 行、`url_dialog.py` 第 720 行，在用户取消操作或超时等待时直接调用 `thread.terminate()` 强制终止正在运行的 QThread。

**问题分析**

`QThread.terminate()` 调用操作系统级的 `TerminateThread()`（Windows），这是一个极其危险的操作：被终止的线程不会执行任何 `finally` 块、不会释放持有的锁（包括 Python GIL）、不会调用 C++ 析构函数。具体风险包括：（1）如果被终止的线程正在执行 COM 调用（如 Shell 操作），COM 状态可能损坏导致后续 COM 调用全部失败；（2）如果被终止的线程持有一个 Python 锁（如 `importlib` 的模块导入锁），其他线程可能永久死锁；（3）如果被终止的线程启动了子进程，子进程会成为孤儿进程继续运行。代码中虽然有 `_orphaned_threads` 类变量作为"后备"记录被终止的线程，但这本身就是一个补丁式设计，说明开发者已经意识到 `terminate()` 的风险但选择了妥协方案。

**解决思路**

全面替换为协作式取消机制。在每个 Worker 线程的 `run()` 方法中定期检查 `_stop_requested` 标志，`terminate()` 的调用点改为设置标志 + `wait(timeout)`。如果 `wait()` 超时（线程确实卡死），记录日志并向用户报告，而不是强制终止。代码中 `shortcut_dialog.py` 第 339 行已有 `requestInterruption()` 的使用先例，应将其作为标准模式推广到所有线程管理点。对于不可中断的外部调用（如 `subprocess.run`），使用带超时的 `subprocess.run(timeout=...)` 并在超时时通过 `process.kill()` 只终止子进程而非线程。

---

## 3. QApplication.processEvents() 滥用

**问题**

`ui/launcher_popup/popup_window.py` 第 406、660、771、772 行（其中第 771-772 行连续调用两次）、`ui/config_window/icon_grid.py` 第 173、1558 行、`ui/launcher_popup/popup_search.py` 第 775 行，在 UI 刷新逻辑中强制调用 `QApplication.processEvents()` 来立即处理挂起的事件。

**问题分析**

`processEvents()` 会在当前调用栈中间插入一个嵌套的事件循环，导致事件重入。典型问题场景：用户点击按钮 A -> 触发处理函数 -> 处理函数调用 `processEvents()` -> 嵌套事件循环中处理了用户点击按钮 B -> 按钮 B 的处理函数在按钮 A 的处理函数尚未完成时就开始执行，两个调用栈交叉，共享状态被破坏。第 771-772 行连续调用两次 `processEvents()` 尤其说明问题——第一次调用没有处理完所有事件，需要第二次来"补漏"，这表明事件处理存在时序依赖，是一种脆弱的修补方式。在 DPI 切换场景中（`popup_window.py` 第 770 行附近），调用 `processEvents()` 是为了等待窗口尺寸更新生效，但这种做法不可靠，因为 DPI 信息的传播可能延迟超过一次 `processEvents()` 的处理范围。

**解决思路**

（1）对于 UI 刷新需求，用 `QTimer.singleShot(0, callback)` 替代 `processEvents()`，将后续操作延迟到下一个事件循环迭代，避免嵌套事件循环；（2）对于 DPI 更新等待，使用平台 API `SetWindowPos` 配合 `SWP_FRAMECHANGED` 标志强制窗口立即重新计算布局，或使用 `QEvent.WinIdChange` 信号监听窗口重建完成；（3）对于图标网格的即时刷新（`icon_grid.py`），改为在数据更新后调用 `update()` 让 Qt 在下一次绘制周期自然重绘。

---

## 4. 非 Qt 线程中 emit pyqtSignal 不可靠

**问题**

`ui/tray_mixins/update_mixin.py` 第 56-71 行的 `_bg_check` 函数在 `threading.Thread`（Python 原生线程）中运行，并通过 `self._update_event_signal.emit()` 发送 pyqtSignal。第 25-27 行的 `add_listener` 回调也在非 Qt 线程中被调用后 emit 信号。

**问题分析**

PyQt 的信号槽机制在跨线程时默认使用 `AutoConnection`，该连接类型通过比较发送方和接收方的线程 ID 来决定是直接调用（`DirectConnection`）还是排队（`QueuedConnection`）。问题在于 `threading.Thread` 不是 Qt 管理的线程，PyQt 无法正确识别其线程 ID，在某些边界情况下可能将 `AutoConnection` 判定为 `DirectConnection`，导致槽函数直接在 Python 线程中执行。而槽函数中包含 UI 操作（如更新标签文本、显示对话框），在非 GUI 线程中操作 Qt 控件会导致随机崩溃（Windows 上表现为 `QWidget: Must construct a QApplication before a QPaintDevice` 或段错误）。`threading.Thread` 和 `QThread` 的根本区别在于 `QThread` 在创建时会注册到 Qt 的事件分发系统，而 `threading.Thread` 不会。

**解决思路**

（1）将所有 `threading.Thread` 替换为 `QThread`，确保 PyQt 能正确识别线程归属；（2）如果必须使用 `threading.Thread`（例如与第三方库集成），在信号连接时显式指定 `Qt.QueuedConnection`：`self._update_event_signal.connect(self._on_update_event, Qt.QueuedConnection)`，强制信号走事件队列；（3）项目中已有 `QThread` 的成功使用模式（如 `ExportThread`、`_FactoryResetThread`），应统一采用此模式。

---

## 5. HotkeyManager 通过 sys.modules["__main__"] 获取 DLL 实例

**问题**

`hooks/hotkey_manager.py` 第 224-231 行，`set_hotkey` 方法通过 `sys.modules.get("__main__")` 查找全局变量 `keyboard_hook` 来获取 DLL 实例：

```python
if hasattr(sys.modules.get("__main__"), "keyboard_hook"):
    kb = sys.modules["__main__"].keyboard_hook
    if hasattr(kb, "_dll"):
        self._dll = kb._dll
```

**问题分析**

这段代码依赖 `__main__` 模块中存在名为 `keyboard_hook` 的全局变量，且该变量具有 `_dll` 属性。这种耦合方式存在多重问题：（1）在 PyInstaller/Nuitka 打包后，`__main__` 可能指向打包器的引导模块而非 `main.py`，全局变量不存在；（2）`HotkeyManager` 可能在 `keyboard_hook` 初始化之前就被创建和调用（初始化顺序在 `main.py` 中通过函数调用顺序隐式控制，非常脆弱）；（3）单元测试中无法模拟 `__main__` 的全局变量，测试必须通过复杂的 monkey-patching；（4）如果有人重构 `main.py` 中变量名（如改为 `self._keyboard_hook`），此处会静默失败（`hasattr` 返回 False），快捷键功能无声失效。

**解决思路**

通过构造函数注入 DLL 实例：`HotkeyManager.__init__(self, dll=None)`，在 `main.py` 初始化时显式传入。如果需要延迟绑定（DLL 可能尚未加载），提供一个 `set_dll(dll)` 方法，由 `main.py` 在 DLL 加载完成后主动调用。移除所有对 `sys.modules["__main__"]` 的访问。

---

## 6. ModuleRegistry.get() 硬编码为 ActionChainLoader

**问题**

`core/module_registry.py` 第 72-77 行，`get()` 方法硬编码了 `ACTION_CHAIN_MODULE_ID` 的判断：

```python
def get(self, module_id, *, data_manager=None):
    if module_id == ACTION_CHAIN_MODULE_ID:
        return self.load_action_chain(data_manager=data_manager)
    return ModuleRecord(module_id, MODULE_MISSING, {}, None, "module_not_registered")
```

**问题分析**

任何非 `quicklauncher.action_chain` 的 `module_id` 都直接返回 `MODULE_MISSING` 状态。虽然第 78 行存在 `register_external_manifest` 方法允许外部模块注册 manifest，但 `get()` 完全不会查询 `_external_manifests` 字典，导致注册过的模块永远无法被获取。整个 `ModuleRegistry` 实质上是一个只服务于 ActionChain 的专用加载器，但类名和接口设计暗示它应该是一个通用的模块注册中心。这意味着未来如果要添加新模块（如剪贴板管理器模块、工作区切换模块），开发者会发现注册机制形同虚设，必须修改 `get()` 的源码。

**解决思路**

重构 `get()` 为通用流程：先检查 `_external_manifests` 字典中是否有匹配的 `module_id`，如果有则走通用的 manifest -> import -> 实例化流程；将 `_load_action_chain` 提取为通用 `_load_module(module_id, manifest)` 方法。保留 ActionChain 作为默认模块的快捷路径，但不再作为唯一路径。

---

## 7. 动作链权限检查形同虚设

**问题**

`core/action_chain_host.py` 第 131-156 行，`DefaultActionChainHostAPI` 的 `check_permission` 和 `request_confirmation` 方法无条件返回 `True`：

```python
def check_permission(self, permission: str, *, chain_id: str = "") -> bool:
    return True

def request_confirmation(self, title: str, message: str, *, chain_id: str = "") -> bool:
    return True
```

**问题分析**

动作链模块支持执行任意脚本（`chain.script_cell`）、运行系统命令（`process.run`）、文件操作等高危操作。虽然 `ActionChainModule._check_processor_permissions`（`modules/action_chain/entry.py` 第 161-213 行）会检查每个 processor 的 capability 声明，但最终这些 capability 请求都会路由到 `check_permission`，而该方法无条件放行。这意味着用户从任何来源导入的动作链都可以无限制执行危险操作，权限系统的安全屏障在最关键的检查点被完全移除。`request_confirmation` 同样无条件返回 True，用户永远不会看到任何确认对话框。

**解决思路**

实现分层的权限检查：（1）对 `network`、`filesystem`、`process` 等高危 capability，弹出用户确认对话框（使用 `QMessageBox.warning` + 明确的操作描述）；（2）维护一个用户授权数据库（JSON 文件），记录用户对每个动作链 + capability 组合的授权决策，避免重复弹窗；（3）对来自 `community-unverified` 信任级别的插件动作链，默认拒绝高危操作并要求逐项确认。

---

## 8. 版本号不一致

**问题**

项目版本号分散在多个文件中且不同步：`core/version.py` 第 8 行为 `"1.6.2.0"`、目录名为 `QuickLauncher_V1.6.3.0`、`CHANGELOG.md` 第 8 行标注 `[1.6.3.0] Unreleased`、`scripts/build_encrypted.bat` 第 18 行默认版本为 `1.6.1.0`、`scripts/build_win11_setup.bat` 第 18 行默认版本为 `1.6.2.0`。

**问题分析**

`core/version.py` 中的 `APP_VERSION` 是运行时版本号的权威来源（`main.py` 和更新检查器都从此读取），但它落后于实际开发版本。构建脚本的默认版本号作为 `core/version.py` 读取失败时的 fallback，却各自不同且都落后。后果：（1）构建出的安装包版本号为 `1.6.2.0`，用户更新检查器可能无法正确识别新版本；（2）`CHANGELOG.md` 中 1.6.3.0 的变更记录已写好但版本号未同步，发布时会混乱；（3）Inno Setup 安装脚本（`scripts/installer.iss`）从构建脚本接收版本号，版本号错误会写入注册表和"程序和功能"面板。

**解决思路**

（1）立即更新 `core/version.py` 为 `"1.6.3.0"`，同步两个构建脚本的默认版本；（2）建立版本号单源机制——在 `pyproject.toml` 或独立的 `VERSION` 文件中定义唯一版本，`core/version.py` 和各构建脚本都从此文件读取；（3）在 `scripts/release_gate.py` 中增加版本号一致性检查步骤，比对 `core/version.py`、`CHANGELOG.md` 首行、构建脚本默认值是否一致。

---

## 9. 全量配置恢复/备份阻塞主线程

**问题**

`ui/config_window/settings_data_actions.py` 第 128-134 行调用 `self.data_manager.restore_full_config(path)` 和第 104 行调用 `self.data_manager.backup_full_config(path)`，均在主线程同步执行。这两个操作涉及 ZIP 压缩/解压、大量图标文件拷贝，在配置目录较大时可能耗时数秒。

**问题分析**

配置备份需要打包整个配置目录（包括图标缓存、背景图片、用户自定义设置），配置恢复需要解压并覆盖当前配置。典型用户的配置目录可达 50-200MB（包含大量 PNG 图标缓存），ZIP 操作在此量级下耗时 3-10 秒。在此期间主线程被完全阻塞，Qt 事件循环停止运行，窗口无法响应任何用户操作（包括拖动、最小化、关闭），Windows 可能将应用标记为"无响应"并在标题栏显示"(Not Responding)"。代码中仅用 `QApplication.setOverrideCursor(Qt.WaitCursor)` 改变光标形态，这只是一种视觉安慰，不能解决事件循环阻塞的根本问题。同文件中的 `export_shareable_config`（第 155 行）和 `import_shareable_config`（第 175 行）存在同样问题。

**解决思路**

参照同文件中已有的 `ExportThread` 模式（用于单个配置导出），为备份和恢复操作创建对应的 `BackupThread` 和 `RestoreThread`（继承 `QThread`），在线程中执行 I/O 操作，通过 `pyqtSignal` 向主线程报告进度。配合 `QProgressDialog` 显示进度条和取消按钮。对于恢复操作，需要额外注意：恢复完成后可能需要重新加载配置并刷新 UI，这部分逻辑应放在槽函数中（线程完成后通过信号触发）。

---

## 10. 守护线程无生命周期管理

**问题**

项目中大量使用 `threading.Thread(..., daemon=True).start()` 模式创建"fire and forget"后台线程，分布在 `ui/launcher_popup/popup_background.py` 第 328 行、`ui/tray_mixins/startup_mixin.py` 第 104/150/172 行、`ui/tray_mixins/update_mixin.py` 第 71 行、`ui/launcher_popup/popup_item_execution.py` 第 439 行、`ui/launcher_popup/popup_search.py` 第 623 行、`ui/config_window/hotkey_dialog.py` 第 526 行、`ui/config_window/folder_panel.py` 第 1418 行等多处。

**问题分析**

`daemon=True` 意味着当主线程退出时，这些线程会被操作系统强制终止，不执行任何清理代码。具体问题：（1）如果线程正在写入文件（如配置保存、日志刷新），强制终止会导致文件损坏或不完整；（2）如果线程持有一个网络连接（如更新检查的 HTTP 请求），连接不会被正常关闭，服务端可能保持半开连接；（3）这些线程没有保存引用，无法在应用退出时主动通知它们停止工作——例如用户点击"退出"后，一个守护线程可能仍在后台执行耗时的图标提取操作，访问已被主线程释放的 Qt 对象；（4）`startup_mixin.py` 第 172 行的线程负责开机自启动配置，如果应用在自启动完成前退出，线程写入注册表的操作可能在中途中断导致注册表状态不一致。

**解决思路**

（1）建立全局线程注册中心（`ThreadRegistry`），所有后台线程创建时注册，退出时注销；（2）在 `main.py` 的 `_shutdown_runtime_components` 中遍历注册中心，为每个线程设置停止标志并 `join(timeout=3)`；（3）将所有 `threading.Thread` 替换为带有 `_stop_event`（`threading.Event`）的自定义线程基类，`run()` 方法中定期检查 `_stop_event.is_set()`；（4）对于短期一次性任务，使用 `QThreadPool` + `QRunnable` 替代手动创建线程，Qt 会在应用退出时自动等待线程池中的任务完成。

---

## 11. 插件命令执行每次创建新线程池

**问题**

`core/plugin_manager.py` 第 704-736 行的 `_wrap_handler` 内部，每次调用插件命令 handler 时都创建一个新的 `ThreadPoolExecutor(max_workers=1)`，提交任务，等待结果，然后 `shutdown(wait=False, cancel_futures=True)`。

**问题分析**

在 Windows 上创建一个线程的成本约为 1ms（包括线程栈分配和 TLS 初始化），加上 Python GIL 的竞争开销。对于搜索源类型的插件命令（用户每输入一个字符都可能触发），这意味着每次搜索都要承担线程创建和销毁的开销。如果搜索源插件有 5 个，用户快速输入 10 个字符，就会产生 50 次线程创建/销毁周期。`shutdown(wait=False)` 还意味着即使线程池开始关闭，被取消的 future 背后的线程可能仍在执行插件代码，形成"僵尸线程"。如果此时插件被 disable，这些僵尸线程仍持有对 `PluginAPI` 实例的引用，可能访问已被清理的资源。

**解决思路**

在 `PluginManager` 级别维护一个共享的 `ThreadPoolExecutor`（`max_workers` 设为 CPU 核心数或可配置值），所有插件命令执行共享此线程池。在 `PluginManager.shutdown()` 时统一关闭。对于需要隔离的插件（如标记为 `community-unverified`），可以为其分配独立的线程池以防止一个插件的长时间阻塞影响其他插件。搜索源执行（`core/command_registry.py` 第 173-209 行的 `execute_search_source`）存在同样的问题，也应改为共享线程池模式。

---

## 12. 插件 reload 窗口期风险

**问题**

`core/plugin_manager.py` 第 1496-1535 行的 `reload_plugin` 方法先调用 `disable_plugin`（第 1503 行）完全卸载旧命令，然后调用 `load_plugin`（第 1520 行）重新加载。如果新的 `load_plugin` 失败，插件进入 `error` 状态，用户之前可用的所有命令都不可用。

**问题分析**

这是一个"先破后立"的策略：先完全移除旧版本的所有命令注册、事件钩子和搜索源，再尝试加载新版本。加载失败的原因可能是新版本代码有语法错误、缺少依赖、或者 manifest 格式变更。一旦失败，用户从"一切正常"变成"功能全失"。对于高频使用的命令（如用户每天使用数十次的快速启动命令），这种中断非常严重。而且由于 `PluginAPI.commit_staged()` 的事务性设计（第 532-610 行），新命令只有在全部注册成功后才会提交，所以失败时不会出现"注册了一半"的脏状态，但结果是零命令可用。

**解决思路**

实现"蓝绿部署"式 reload：（1）创建临时 `CommandRegistry` 和 `PluginAPI` 实例；（2）在临时实例中尝试加载新版插件；（3）如果加载成功，原子性地替换旧实例（通过交换引用）；（4）如果加载失败，丢弃临时实例，旧插件继续运行不受影响。整个过程对用户透明，不会有任何功能中断。

---

## 13. 插件加载后 sys.modules 残留

**问题**

`core/plugin_manager.py` 第 1378-1396 行的 `_do_load` 方法通过 `importlib.util.spec_from_file_location` 将插件加载到 `sys.modules` 中（键名为 `_plugin_{id}`）。当 `loader.register(api)` 或 `api.commit_staged()` 在模块加载成功后抛出异常时，`load_plugin` 的 `except` 块（第 1357-1366 行）只记录了错误状态，没有清理 `sys.modules` 中的模块残留。

**问题分析**

Python 的 `sys.modules` 是一个全局字典，所有通过 `import` 或 `importlib` 加载的模块都会在此注册。当插件模块成功加载（第 1379-1380 行执行了 `spec.loader.exec_module(loader)`）但后续步骤失败时，模块对象已经驻留在 `sys.modules` 中。该模块对象引用了 `PluginAPI` 实例、回调函数、以及插件代码中创建的所有对象。由于 `sys.modules` 持有对模块的强引用，垃圾回收器无法回收这些对象，导致内存泄漏。更严重的是，如果用户尝试 reload 这个失败的插件，`_do_load` 在第 1379 行检查 `if module_name in sys.modules` 会发现旧模块存在，直接使用旧模块而不会重新加载新代码——这意味着 reload 操作实际上不会更新代码，用户会看到"reload 后问题依旧"的困惑现象。

**解决思路**

在 `load_plugin` 的 `except` 块中增加 `sys.modules.pop(f"_plugin_{plugin_id}", None)` 清理操作。同时在 `_do_load` 中使用 try/finally 确保异常路径下的清理。对于子模块，需要在加载时记录所有新增的 `sys.modules` 键名，在失败时一并清理。

---

## 14. 插件受限 builtins 安全绕过

**问题**

`core/plugin_manager.py` 第 85-116 行的 `_make_plugin_builtins` 函数通过将 `eval` 和 `exec` 设为 `None` 来限制插件代码，但插件可以通过 `type(lambda: 0).__code__`、`__class__.__bases__` 链、`ctypes` 模块、或 `importlib` 轻易绕过这些限制。

**问题分析**

当前的安全限制是一种浅层的"黑名单"方式：移除 `eval`/`exec`、限制 `open`/`__import__`。但 Python 的对象模型允许从任何对象出发遍历整个类型系统。例如：`(lambda: 0).__class__.__bases__[0].__subclasses__()` 可以获取所有已加载的类，从中找到 `os._wrap_close` 等类可以获取 `os` 模块的引用，进而执行任意系统命令。`ctypes.pythonapi` 可以直接调用 CPython 内部 API。虽然 `community-unverified` 信任级别在设计上就不是安全沙箱，但当前的实现给用户提供了一种虚假的安全感——设置界面显示"受限权限"，实际上限制可以轻松绕过。

**解决思路**

如果需要真正的安全隔离：（1）使用子进程运行不受信任的插件，通过 IPC（如 `multiprocessing.Pipe`）通信，进程级别的隔离无法被 Python 层面的技巧绕过；（2）使用 RestrictedPython 库进行 AST 级别的代码审查和转换；（3）作为最低限度，在文档和 UI 中明确声明 `community-unverified` 不是安全沙箱，用户应仅安装来源可信的插件。当前的浅层限制可以保留作为"减速带"，但不应作为安全特性宣传。

---

## 15. DLL 加载失败不可恢复

**问题**

`hooks/hooks_wrapper.py` 第 42-54 行的 `get_instance` 类方法使用 `_load_attempted` 标志确保 DLL 只尝试加载一次。当首次加载失败时，返回一个 `dll=None` 的空实例，后续调用永远返回这个失败实例，不会重试。

**问题分析**

DLL 加载失败的原因可能是暂时性的：DLL 文件尚未部署完成（安装程序正在拷贝）、文件被杀毒软件临时锁定、或依赖的 VC++ 运行时尚未安装。在这些情况下，一旦首次加载失败，`_load_attempted = True` 被设置，即使几秒后 DLL 文件变得可用，应用也必须完全重启才能重新加载。对于用户来说，这意味着安装过程中如果启动顺序不当（应用先于 DLL 部署启动），钩子功能将永久不可用直到手动重启应用。

**解决思路**

（1）添加 `reset()` 类方法清除 `_load_attempted` 和 `_instance`，在特定场景下（如检测到 DLL 文件出现、用户手动触发"重新加载钩子"按钮）调用；（2）在诊断窗口（`diagnostics_window.py`）中增加"重新加载 DLL"功能按钮；（3）考虑使用 `watchdog`（项目已依赖此库）监控 DLL 文件变化，在文件从不存在变为存在时自动触发重新加载。

---

## 16. hook_pause 上下文管理器异常路径可能永久暂停钩子

**问题**

`hooks/hook_pause.py` 第 24-39 行的 `mouse_hook_paused` 上下文管理器在 `restore_previous=False`（默认值）时，finally 块无条件执行 `hook.set_paused(False)`。如果存在嵌套的暂停/恢复操作，内层上下文管理器的 finally 会覆盖外层的暂停意图。

**问题分析**

考虑以下场景：对话框 A 打开时使用 `mouse_hook_paused(hook, restore_previous=True)` 暂停钩子（保存了之前的状态"未暂停"），然后对话框 B 在 A 的内部打开时使用 `mouse_hook_paused(hook)`（默认 `restore_previous=False`）。B 关闭时 finally 执行 `hook.set_paused(False)`，钩子恢复——但此时 A 仍然打开，期望钩子保持暂停。A 关闭时 finally 执行 `hook.set_paused(False)`（恢复到保存的"未暂停"状态），结果正确，但 B 关闭到 A 关闭之间钩子处于错误的"未暂停"状态。更危险的是如果异常路径中 hook 的 `set_paused` 调用本身失败（例如 DLL 已卸载），钩子可能永久停留在暂停状态。

**解决思路**

（1）将默认行为改为 `restore_previous=True`，保存并恢复先前状态；（2）实现引用计数式暂停：`hook.pause()` 增加暂停计数，`hook.resume()` 减少计数，只有计数归零时才真正恢复钩子；（3）在 finally 块中增加 try/except 保护，确保 `set_paused` 的异常不会传播到调用方。

---

## 17. 全局回调字典缺乏类型安全

**问题**

`core/__init__.py` 第 50-102 行的全局回调机制使用无类型的字典 `_callbacks`，`register_callback` 接受任意 name（字符串）和 callback（可调用对象），`call_callback` 通过 `*args, **kwargs` 传递参数，注册时和调用时的签名不匹配只能在运行时发现。

**问题分析**

这种设计的问题链：（1）回调名称是魔法字符串（如 `"show_window"`、`"refresh_data"`），分散在各模块中使用，没有集中定义，容易出现拼写错误（如 `"show_widnow"`）且不报编译错误；（2）`call_callback` 在第 76 行通过 `except Exception` 捕获所有异常并记录日志后静默返回 None（第 87-90 行），这意味着调用方永远无法区分"回调未注册"和"回调执行出错"两种完全不同的情况；（3）注册时的参数签名与调用时不匹配（如注册了 `lambda title, content: ...` 但调用时只传了 `title`）会在 `call_callback` 内部抛出 `TypeError`，被静默吞掉后返回 None，调用方以为执行成功但实际什么也没做。

**解决思路**

（1）定义回调名称枚举类 `class CallbackNames:` 集中管理所有回调名称，避免魔法字符串；（2）在 `register_callback` 中使用 `inspect.signature` 验证回调签名并记录预期参数；（3）在 `call_callback` 中区分"未注册"和"执行错误"，对"未注册"返回特定的 sentinel 值，对"执行错误"根据严重程度决定是否向上抛出；（4）考虑使用 `typing.Protocol` 为每种回调定义接口类型，利用 mypy 进行编译期检查。

---

## 18. UpdateChecker 运算符优先级 bug

**问题**

`services/update/checker.py` 第 187 行：

```python
if resp.get("draft") or resp.get("prerelease") and self._config.channel == "stable":
```

**问题分析**

Python 中 `and` 优先级高于 `or`，实际等价于 `if resp.get("draft") or (resp.get("prerelease") and self._config.channel == "stable")`。这意味着：（1）当 `draft=True` 时，无论 channel 是什么（包括 beta），都会跳过该版本——draft 版本在 beta 渠道也被跳过，这可能不是预期行为；（2）当 `draft=False, prerelease=True, channel="beta"` 时，不会跳过预发布版本——这符合预期。但代码没有用括号明确表达意图，任何维护者阅读这段代码都需要停下来回忆运算符优先级，增加了误读和后续修改引入 bug 的风险。

**解决思路**

添加括号明确优先级，并加注释解释逻辑：

```python
# Draft 版本始终跳过；预发布版本仅在 stable 渠道跳过
if resp.get("draft") or (resp.get("prerelease") and self._config.channel == "stable"):
```

如果 beta 渠道也应该跳过 draft，这个行为已经正确；如果 beta 渠道应该接受 draft，需要修改条件为 `(resp.get("draft") and self._config.channel != "dev") or ...`。

---

## 19. services/__init__.py 的 init_services() 是空操作

**问题**

`services/__init__.py` 第 8-13 行的 `init_services()` 函数仅设置 `_initialized` 标志并打印 debug 日志，没有实际初始化任何服务（UpdateChecker、UpdateDownloader、UpdateInstaller 等）。

**问题分析**

服务的生命周期完全由 UI 层各处散落的代码自行管理：UpdateChecker 在 `update_mixin.py` 中创建和启动，UpdateDownloader 在下载按钮点击时临时创建，UpdateInstaller 在安装确认对话框中临时创建。没有统一的启动/停止/健康检查机制，也没有服务依赖排序。这导致：（1）无法确定所有服务是否已正确初始化；（2）应用退出时没有统一的服务关闭入口，各服务的后台线程可能仍在运行；（3）如果需要添加新服务（如遥测服务、配置同步服务），没有标准化的注册和初始化流程。

**解决思路**

实现一个 ServiceManager 类，提供 `register(service)`、`start_all()`、`stop_all()`、`get(service_type)` 方法。在 `init_services()` 中注册所有核心服务并按依赖顺序启动。在 `main.py` 的退出处理中调用 `stop_all()` 优雅关闭所有服务。

---

## 20. 内联样式表硬编码（332 处/36 个文件）

**问题**

项目 UI 层共有 332 处 `setStyleSheet` 调用分布在 36 个文件中，使用 f-string 拼接颜色值构建 QSS 样式字符串。重灾区文件包括 `command_dialog.py`（34 处）、`chain_dialog.py`（31 处）、`icon_grid.py`（26 处）。项目已有 `ui/styles/style.py`（59.7KB）中定义的 `Glassmorphism` 等样式类，但绝大多数代码未使用。

**问题分析**

样式散落在 36 个文件中导致：（1）同一类控件（如 QPushButton）的样式在多处重复定义，细微差异难以追踪；（2）主题切换时需要逐文件修改，容易遗漏导致部分控件保持旧主题；（3）每次 `setStyleSheet` 调用都触发 Qt 样式引擎重新解析和重绘，在 `set_theme()` 方法中集中批量设置（如 `main_window.py` 第 226-270 行）造成多次不必要的重绘；（4）无法通过 Qt 的样式表级联机制（如全局 `QApplication.setStyleSheet()`）统一管理。

**解决思路**

（1）将分散的样式定义统一到 `ui/styles/style.py` 的主题管理类中，通过组件类型 + 主题获取样式字符串；（2）对相同样式的控件使用共享的 stylesheet 常量；（3）考虑使用 QSS 文件 + `QApplication.setStyleSheet()` 全局应用，通过控件类选择器（如 `QPushButton#close_btn`）区分不同按钮样式；（4）将 `set_theme()` 中的多次 `setStyleSheet` 调用合并为一次整体样式设置，减少重绘次数。

---

## 21. 固定像素尺寸硬编码（149 处/30 个文件）

**问题**

项目 UI 层共有 149 处 `setFixedSize`/`setFixedHeight`/`setFixedWidth` 调用分布在 30 个文件中，所有尺寸均为绝对像素值。典型如 `main_window.py` 第 534 行 `self.setFixedSize(total_width, 560)`、`command_dialog.py` 第 686 行 `self.command_edit.setFixedHeight(92)`、`batch_launch_dialog.py` 第 517 行 `self.setFixedSize(700, 500)`。

**问题分析**

Windows 用户中有相当比例使用 125%/150%/200% 的 DPI 缩放（尤其是 4K 显示器和笔记本电脑）。固定像素尺寸在这些设置下会导致：（1）按钮和输入框物理尺寸缩小，难以点击（200% 缩放下一半的物理尺寸）；（2）文字被截断或溢出固定高度的容器；（3）`setFixedSize` 完全锁死窗口尺寸，在低分辨率屏幕上可能无法完整显示。虽然项目中有 `devicePixelRatio()` 的使用（背景图片加载逻辑），但 UI 控件尺寸未做任何 DPI 适配。

**解决思路**

（1）定义 `dp(value)` 缩放函数，根据当前屏幕 DPI 动态计算像素值（`dp = lambda v: int(v * screen_scale_factor)`）；（2）将 `setFixedSize` 替换为 `setMinimumSize`/`setMaximumSize`，允许弹性布局；（3）对需要固定比例的控件，使用 `QFontMetrics` 计算基于文字高度的相对尺寸；（4）对窗口整体尺寸，使用 `QScreen.availableGeometry()` 的百分比而非固定值。

---

## 22. 硬编码颜色值（627 处/33 个文件）

**问题**

项目 UI 层共有 366 处 `QColor(...)` 构造调用和 261 处十六进制颜色字面量，合计 627 处硬编码颜色值分布在 33 个文件中。相同的 RGBA 值（如 `QColor(28, 28, 30, 180)` 暗色背景）至少在 8 个文件中重复出现。项目已在 `ui/styles/style.py` 中定义了 `Glassmorphism` 颜色常量类，但绝大多数代码未引用。

**问题分析**

627 处颜色硬编码意味着任何调色板调整（如增加高对比度模式、支持自定义主题色、修复色盲友好配色）都需要逐个修改大量文件。同一颜色在不同文件中可能因手误出现微小偏差（如 `QColor(28, 28, 30, 180)` vs `QColor(28, 28, 31, 180)`），导致视觉不一致。

**解决思路**

（1）扩展 `Glassmorphism` 类为完整的语义化调色板（`BG_PRIMARY_DARK`、`BG_PRIMARY_LIGHT`、`BORDER_DEFAULT`、`TEXT_PRIMARY` 等），全部 UI 代码通过语义化名称引用；（2）将 `QColor(28, 28, 30, 180)` 这样的公共值提取为模块级常量；（3）考虑引入 QPalette 或 CSS 变量式主题引擎集中管理颜色。

---

## 23. is_win11() 条件分支两侧值相同（17 处）

**问题**

项目中有 17 处 `is_win11()` 三元表达式两侧返回值完全相同，全部为 `8 if is_win11() else 8`。分布在 `welcome_guide.py`、`base_dialog.py`、`main_window.py`、`icon_grid.py`、`settings_helpers.py`、`settings_panel.py`、`themed_messagebox.py`、`log_window.py`、`toast_notification.py`、`themed_tool_window.py`、`services/update/ui.py` 等文件中。

**问题分析**

这是明显的代码残留。之前 Win10 和 Win11 可能使用不同的圆角半径（如 Win10 为 0 或 4，Win11 为 8），后来统一为 8，但忘记移除条件判断。这些无意义的条件分支增加代码噪音、误导新维护者（以为 Win10/Win11 有区别）、并产生不必要的函数调用开销（`is_win11()` 内部调用 `get_windows_version()`）。

**解决思路**

全局替换 `8 if is_win11() else 8` 为 `8`。如果将来需要恢复 Win10/Win11 区分，应在 `ui/utils/window_effect.py` 中提供一个 `get_corner_radius()` 函数集中管理，而非在 17 个文件中各自写条件表达式。

---

## 24. 鼠标拖动缺少边界检查

**问题**

`ui/config_window/main_window.py` 第 345-355 行的 `TitleBar.mouseMoveEvent` 实现窗口拖动时，`self.parent_window.move(self.parent_window.pos() + diff)` 直接使用鼠标差值移动窗口，没有任何屏幕边界约束。

**问题分析**

用户可以将窗口拖到屏幕外（包括多显示器之间的间隙区域），导致窗口完全不可见且无法通过鼠标拖回。窗口也可以被拖到任务栏下方。在多显示器配置中问题更严重——窗口可能被拖到非活跃显示器上，用户需要在系统设置中重新定位。

**解决思路**

在 `move()` 之前获取所有屏幕的合并可用几何区域，约束窗口位置确保标题栏至少 40 像素在可见区域内。使用 `QApplication.screens()` 遍历所有屏幕，合并 `availableGeometry()`，然后用 `QRect.intersected()` 或手动 clamp 坐标。

---

## 25. 事件过滤器过度使用

**问题**

`ui/command_panel_window.py` 第 280-287 行的 `_install_input_cancel_event_filters` 对 `self.findChildren(QWidget)` 返回的所有子控件（可能 50-100+ 个）安装事件过滤器，但实际上只关心非 `command_input` 控件的 `MouseButtonPress` 事件（用于点击空白区域取消焦点）。

**问题分析**

所有被安装过滤器的控件的每个事件（鼠标移动、键盘、绘制、定时器等高频事件）都会进入 `eventFilter` 方法经过 `try/except` 和多个 `if/elif` 判断，绝大多数事件被直接忽略。在高刷新率显示器（120Hz/144Hz）下，`MouseMove` 和 `Paint` 事件以极高频率触发，Python 层的事件过滤可能成为性能瓶颈。此外，动态添加的子控件不会自动获得过滤器。

**解决思路**

（1）在面板级别重写 `mousePressEvent`（第 640-644 行已有此实现），移除对所有子控件的事件过滤器安装；（2）如果确实需要在特定控件上拦截点击，应显式列出这些控件而非使用 `findChildren` 通配。

---

## 26. Lambda 闭包内存泄漏风险（71 处/23 个文件）

**问题**

项目 UI 层共有 71 处 `.connect(lambda` 调用分布在 23 个文件中。典型的高风险模式包括：线程清理 lambda（`dialog.finished.connect(lambda: setattr(self, "_active_file_dialog", None))`，5 处重复）、循环中的 lambda（`icon_grid.py` 第 1236-1238 行在循环中为每个 grid item 创建 3 个 lambda）。

**问题分析**

Lambda 通过闭包捕获 `self` 引用，形成 `self -> signal -> lambda -> self` 的循环引用链。对于短生命周期的对话框，如果其信号发送方（如 QThread）的生命周期超过对话框，lambda 会持有对话框的强引用阻止 GC。在 `icon_grid.py` 的循环场景中，如果有 100 个快捷方式，就有 300 个 lambda 闭包持有整个 icon_grid 对象的引用，每个 lambda 还各自持有一个 shortcut 对象的引用。虽然 Python 的循环 GC 理论上可以处理循环引用，但 Qt 的 C++ 层对象不参与 Python GC，信号连接在 C++ 层持有 lambda 引用，打破了 Python 循环 GC 的能力。

**解决思路**

（1）使用 `functools.partial` 替代 lambda（不持有 `self` 引用，通过参数传递）；（2）对线程清理 lambda，改用 `thread.destroyed.connect(lambda: setattr(...))` 模式；（3）对循环中的连接，考虑使用 `QSignalMapper` 或在控件上存储数据属性（`widget.setProperty("shortcut", shortcut)`），在统一的 slot 中通过 `sender().property("shortcut")` 获取数据。

---

## 27. Toast 单例引用阻止垃圾回收

**问题**

`ui/toast_notification.py` 第 32-33 行的 `_current_instance` 类变量在 Toast 隐藏后永远不会被置为 `None`。`hideEvent`（第 238-254 行）没有清理此引用。

**问题分析**

Toast 显示完成后触发淡出动画（约 400ms），淡出结束后调用 `self.hide()`，`hideEvent` 被触发但不清理 `_current_instance`。如果应用长时间不再显示新的 Toast（例如用户停止操作后），旧的 Toast 实例（包括其持有的所有 Qt 资源和子控件引用）会因为类变量的强引用而无法被 GC。虽然单个 Toast 的内存占用不大，但这是一个资源管理习惯的问题——任何"用完不释放"的模式都可能在长时间运行的应用中累积。

**解决思路**

在 `hideEvent` 中添加：`if ToastNotification._current_instance is self: ToastNotification._current_instance = None`。

---

## 28. 核心模块缺乏测试覆盖

**问题**

以下核心模块完全没有测试覆盖：`core/windows_uipi.py`（8.0KB，UIPI 安全隔离）、`core/windows_service.py`（8.7KB，Windows 服务模式）、`bootstrap/` 全目录（5 个文件，启动引导层）、`hooks/key_map.py`（键位映射）、`hooks/mouse_hook_dll.py` 和 `hooks/keyboard_hook_dll.py`（DLL 封装）、`hooks/hook_pause.py`（钩子暂停控制）、`services/api/base_client.py`（API 客户端）。此外，`core/chain/registry.py`（110.5KB，约 3000+ 行）是项目最大的单文件，仅通过间接引用被测试，没有针对其完整 API 的专项单元测试。

**问题分析**

`core/windows_uipi.py` 负责 Windows UIPI 权限隔离，如果逻辑有误，可能导致权限提升漏洞或正常功能被误拦截。`bootstrap/` 是应用启动的第一道关卡，DPI 设置、日志初始化、虚拟环境检测、依赖引导、IPC 单实例控制全部在此完成，任何一个环节的 bug 都可能导致应用无法启动。`core/chain/registry.py` 作为最大的单文件，承载动作链处理器注册表的全部逻辑，复杂度极高，仅靠间接测试难以覆盖边界情况。

**解决思路**

（1）优先为 `core/windows_uipi.py` 和 `bootstrap/` 添加单元测试；（2）为 `core/chain/registry.py` 编写专项测试，覆盖注册、查询、冲突解决、覆盖注册等核心 API；（3）在 `scripts/release_gate.py` 中增加覆盖率检查步骤（`pytest --cov --cov-fail-under=70`），防止覆盖率退化；（4）为 `hooks/` 目录下的纯逻辑文件（`key_map.py`、`hook_pause.py`）添加参数化单元测试。

---

## 29. release_gate.py 不包含覆盖率检查

**问题**

`scripts/release_gate.py` 第 54-88 行定义了 5 个发布门控步骤：ruff lint、pytest、broad exception audit、compileall、release metadata，但没有包含 `pytest --cov` 覆盖率检查。

**问题分析**

发布门控的目的是确保每次发布前代码质量不低于基线。没有覆盖率检查意味着覆盖率可以在不被发现的情况下持续下降——开发者可能在修改核心逻辑时删除了测试或跳过了为新代码编写测试，这些退化都不会被门控拦截。长期来看，这会导致测试覆盖率逐渐降低，关键路径失去测试保护。

**解决思路**

在 `_default_steps()` 中增加覆盖率检查步骤，运行 `pytest --cov=core --cov=services --cov-fail-under=70`（阈值可根据当前基线设定）。将覆盖率报告输出到 `htmlcov/` 目录供开发者本地查看。

---

## 30. C++ 层共享变量缺乏原子保护

**问题**

`hooks_dll/hooks.cpp` 第 18-72 行的全局变量声明中，`g_altHeld` 使用了 `std::atomic<bool>`（第 53 行），但 `g_altTapCount`（第 65 行，`int`）和 `g_otherKeyPressed`（第 66 行，`bool`）等变量未使用 `std::atomic`。这些变量在 `MouseHookProc`（第 530-648 行）和 `KeyboardHookProc` 中被读写。

**问题分析**

`WH_MOUSE_LL` 和 `WH_KEYBOARD_LL` 回调虽然通常在同一个消息泵线程上执行，但 `g_otherKeyPressed` 在键盘钩子回调中被设置、在鼠标钩子回调中被读取和重置。如果两个钩子的回调恰好在不同线程上执行（理论上 Windows 低级钩子保证在同一线程，但这依赖于消息泵的实现细节），就构成数据竞争。在 x86/x64 架构上，`int` 和 `bool` 的读写通常是原子的（硬件保证），但在 ARM 架构上不是，且编译器可能生成非原子的读写指令。更重要的是，非 `atomic` 变量允许编译器进行激进的优化（如将变量缓存在寄存器中不写回内存），导致另一个线程看不到最新的值。

**解决思路**

将 `g_altTapCount` 改为 `std::atomic<int>`，`g_otherKeyPressed` 改为 `std::atomic<bool>`。这是最小成本的修改，不改变逻辑但消除了潜在的数据竞争。

---

## 31. hooks/__init__.py 导入失败静默处理

**问题**

`hooks/__init__.py` 第 1-20 行，MouseHook 和 KeyboardHook 的导入失败被 `except Exception` 静默捕获，仅打印 warning 日志。`__all__` 中仍然导出它们（值可能为 None）。

**问题分析**

使用方代码 `from hooks import MouseHook` 可能得到 `None` 而不报错。后续调用 `MouseHook()` 会抛出 `TypeError: 'NoneType' object is not callable`，这个错误信息完全没有提及根因（DLL 加载失败），调试时需要回溯到 `__init__.py` 的 warning 日志才能找到真正原因。在用户反馈 bug 时，他们通常不会查看 debug 日志，只会报告"快捷键功能不工作"。

**解决思路**

在导入失败时提供占位类（stub class），实例化时抛出清晰的错误信息：

```python
class _MouseHookUnavailable:
    def __init__(self, *args, **kwargs):
        raise RuntimeError("鼠标钩子不可用：DLL 加载失败，请检查 hooks_dll/hooks.dll 是否存在")
MouseHook = _MouseHookUnavailable
```

或者在 `__all__` 中根据导入结果动态调整，避免导出 None。

---

## 32. action_chain migrate_chain_data 是空操作

**问题**

`modules/action_chain/migrations/__init__.py` 第 4-7 行的 `migrate_chain_data` 函数只设置了 `schema_version`，没有实际的数据迁移逻辑。当前 `schema_version=1` 所以无害，但未来 schema 升级时会出问题。

**问题分析**

当 `schema_version` 从 1 升级到 2 时，旧的动作链数据（JSON 格式）不会经过任何转换直接被新版本使用。如果新版本引入了必需字段、修改了字段类型、或重命名了字段，旧数据在反序列化时会产生 `KeyError`、`TypeError` 等运行时错误。由于动作链数据是用户精心配置的自动化流程，数据丢失或损坏对用户的影响非常大。

**解决思路**

实现版本迁移链：维护 `migrations = {1: migrate_1_to_2, 2: migrate_2_to_3, ...}` 映射，`migrate_chain_data` 检查当前版本与目标版本，按顺序执行所有中间迁移步骤。每个迁移函数应该是幂等的（重复执行不产生副作用），并在迁移前创建数据备份。

---

## 33. 无障碍支持完全缺失

**问题**

在整个项目代码库中搜索 `setAccessibleName`、`setAccessibleDescription`、`QAccessible` 等无障碍 API 调用，结果为零。所有自定义绘制的控件（`DotWidget`、`IconWidget`、`CommandHistoryDropButton` 等）均未设置无障碍属性。

**问题分析**

屏幕阅读器用户（如视障用户、或 Windows Narrator/NVDA/JAWS 用户）完全无法使用本应用。标题栏按钮使用 Unicode 字符（`"‹"`、`"⚙"`、`"✕"`）作为文本，屏幕阅读器可能无法正确朗读。图标网格中的快捷方式项没有文本标签的无障碍等价物。命令面板的输入建议弹出窗口对辅助技术完全不可见。

**解决思路**

（1）为所有交互控件添加 `setAccessibleName` 和 `setAccessibleDescription`；（2）确保 Tab 键序合理，所有可交互控件可通过键盘访问；（3）为图标网格项提供 `Qt.AccessibleDescriptionRole`；（4）使用 Windows Accessibility Insights 工具验证。

---

## 34. mypy 类型检查形同虚设

**问题**

`mypy.ini` 配置 `check_untyped_defs = False`（第 4 行）和 `ignore_missing_imports = True`（第 3 行），导致大量未类型标注的代码不会被 mypy 检查，所有第三方库的 import 错误被忽略。同时 mypy 未集成到 pre-commit 钩子中，类型检查依赖手动运行。

**问题分析**

`check_untyped_defs = False` 意味着 mypy 只检查显式标注了类型签名的函数体内部，而项目中绝大多数函数没有类型标注，mypy 实际检查范围极小。`ignore_missing_imports = True` 虽然避免了第三方库类型存根缺失的报错，但也屏蔽了跨模块引用的类型错误。最终结果是 mypy 即使运行也无法发现实质性的类型问题。

**解决思路**

（1）渐进式启用：先为核心模块（`core/`、`hooks/`）开启 `check_untyped_defs = True`，逐步添加类型标注；（2）在 `mypy.ini` 中为不同模块配置不同的严格程度；（3）将 mypy 添加到 `.pre-commit-config.yaml`；（4）添加 ruff 的 `"S"` 规则集以检测安全问题。

---

## 35. 钩子安装失败无自动重试 / 进程崩溃时无 atexit 回退清理

**问题**

`InstallMouseHook`/`InstallKeyboardHook`（`hooks_dll/hooks.cpp:883-941, 978-1035`）在 `SetWindowsHookEx` 失败时仅记录 `g_lastHookError` 并返回 false，Python 侧 `_install_mouse_backend`（`tray_mixins/hooks_mixin.py:19-63`）在失败时仅 log error 并设置 `self.mouse_hook = None`，无任何重试机制。整个代码库搜索 `__del__` 无结果，`atexit.register` 仅在 `core/commands.py:535-536` 用于 QR 文件服务器清理，未注册任何钩子卸载或插件资源清理。`_reload_hooks_now`（`tray_app.py:742-763`）是手动触发路径，缺乏自动故障恢复。

**问题分析**

`SetWindowsHookEx` 失败的原因可能是暂时性的：系统资源不足、DLL 被占用、权限临时缺失。在这些情况下用户必须手动执行 `/plugin reload_hooks` 才能恢复钩子功能。更严重的是，如果 Python 进程因 segfault 或 `os._exit()` 等非正常方式终止，DLL 侧钩子可能残留（尽管 Windows 会在进程终止时回收 `WH_MOUSE_LL`/`WH_KEYBOARD_LL`，但同步事件对象、调试日志线程不做清理可能引发资源泄漏）。

**解决思路**

（1）在 `_install_hook` 中加入退避重试逻辑（500ms / 2s / 5s 共三次），仅在连续失败后上报给用户；（2）在 `hooks_mixin.py` 或 `tray_app.py` 的初始化点注册 `atexit.register(self._shutdown_runtime_components)`，确保 `PostThreadMessage(WM_QUIT)` 和句柄关闭在任何终止路径下都能执行；（3）利用 C++ `IsMouseHookInstalled`/`IsKeyboardHookInstalled` 做周期健康检查（与 `_process_check_timer` 合并），发现异常时自动触发 `_reinstall_hooks`。

---

## 36. C++ DLL 中鼠标/键盘 Install、Uninstall、ThreadProc 大面积重复代码

**问题**

`hooks_dll/hooks.cpp` 中 Mouse 和 Keyboard 的 Install/Uninstall/ThreadProc 函数几乎逐行对应：`InstallMouseHook`（`:883`）与 `InstallKeyboardHook`（`:978`）除变量名前缀（`g_mouse*`/`g_keyboard*`）和线程函数参数外完全一致；`UninstallMouseHook`（`:943`）与 `UninstallKeyboardHook`（`:1037`）同样如此；`MouseHookThread`（`:655`）与 `KeyboardHookThread`（`:840`）仅 `WH_MOUSE_LL` 和 `WH_KEYBOARD_LL` 的区别。

**问题分析**

复制粘贴式代码需要同时维护两套相同逻辑，修 bug 或加功能时容易遗漏一侧。历史上 `InstallMouseHook` 和 `InstallKeyboardHook` 都有 `EnsureCallbackThread()` 调用，如果某天只在一侧修改而忘记同步另一侧，就会产生微妙的时序 bug。函数总行数无谓膨胀，增加新人理解成本。注意 `MouseHookProc`/`KeyboardHookProc` 业务逻辑本质不同，不应合并。

**解决思路**

（1）定义 `struct HookContext { HHOOK* hook; DWORD* threadId; HANDLE* threadHandle; ... }`，将 Install/Uninstall/HookThread 改为对 HookContext 操作的统一函数；（2）或使用 C++ 宏模板/`template<auto HookType>` 统一，传入 `WH_MOUSE_LL`/`WH_KEYBOARD_LL` 和变量集合结构体指针；（3）HookProc 保持分离，但抽取公共工具函数（如 `GetTime`、`IsSpecialApp`、`CheckKeysPressed`）到独立辅助函数。

---

## 37. InvokeKeyboardCallbackAsync / InvokeMouseCallbackAsync 逻辑完全一致

**问题**

`hooks_dll/hooks.cpp:250-274` 中 `InvokeKeyboardCallbackAsync` 和 `InvokeMouseCallbackAsync` 除 CallbackEvent 构造参数不同（`Keyboard` vs `Mouse` + 坐标参数）外，逻辑完全一致：检查 callback 是否为空、调用 EnsureCallbackThread、加锁入队、SetEvent。共 24 行重复代码。

**问题分析**

重复代码增加了 CallbackEvent 类型扩展时的维护成本。若有第三种回调类型（如 TouchCallback），必须再复制一份。

**解决思路**

使用 `template<typename F, typename... Args>` 统一为 `InvokeCallbackAsync(CallbackEvent::Type type, F cb, Args... args)`，内部构造 CallbackEvent 并入队。

---

## 38. SafeInvokeCallback / SafeInvokeMouseCallback 模式相同

**问题**

`hooks_dll/hooks.cpp:183-197` 中 `SafeInvokeCallback` 和 `SafeInvokeMouseCallback` 仅函数签名不同，都是 `__try { cb(); } __except (EXCEPTION_EXECUTE_HANDLER) {}` 的相同模式。

**问题分析**

两个函数除参数类型和调用方式外完全一致，是典型的代码重复。

**解决思路**

定义宏 `SAFE_INVOKE(call_expr) __try { call_expr; } __except(EXCEPTION_EXECUTE_HANDLER) {}`，或用 `auto lambda + invoke` 统一两个安全调用包装。

---

## 39. 钩子暂停恢复模式在 4 个 Python 文件中重复实现

**问题**

`ui/utils/safe_file_dialog.py`（`:44-70`）、`ui/styles/themed_messagebox.py`（`:51-88, :454-475`，两次实现）、`ui/config_window/mouse_key_recorder.py`（`:77-99`）、`ui/config_window/input_trigger_recorder.py`（`:73-93`）均实现了相同的"保存 is_paused → set_paused(True) → 执行 → set_paused(prev_state)"模式，核心代码重复 4-5 次。

**问题分析**

每次打开文件对话框、消息框、按键录制器时都需要暂停钩子（防止钩子拦截对话框内的鼠标/键盘事件），这个暂停-执行-恢复的样板代码在多处重复，任何逻辑修改（如增加超时保护）都需要同步更新所有位置。

**解决思路**

在 `hooks/` 下使用 `contextlib.contextmanager` 定义统一的上下文管理器 `mouse_hook_paused()`，所有调用方改为 `with mouse_hook_paused(): ...`。项目已有 `hooks/hook_pause.py`，应确保所有使用点都通过此模块而非自行实现。

---

## 40. 按键到 VK 映射逻辑在 Python 和 C++ 侧各实现一份

**问题**

C++ DLL 热键解析 `ParseGlobalHotkey`（`hooks_dll/hooks.cpp:1074-1180`）和 `ParseVkList`（`:1248-1278`）实现了字符串到 VK 码的映射；Python 侧 `hooks/hooks_wrapper.py:416-458` 的 `_key_to_vk` 和 `core/hotkey_conflict_checker.py:191-248` 的 `_get_vk_code` 也各自实现了字符串到 VK 码的映射。`ui/config_window/input_trigger_recorder.py:149-178` 还有 Qt 键码到字符串的逆映射。

**问题分析**

`hooks_wrapper._key_to_vk` 和 `hotkey_conflict_checker._get_vk_code` 功能极其相似但独立维护，支持的按键集略有不同（后者多了多媒体键）。C++ 的 `ParseGlobalHotkey` 和 Python 的 `_key_to_vk` 逻辑重复且行为需要保持一致。如果 Python 侧新增了一个按键映射（如 `Pause`），C++ 侧不同步更新就会导致快捷键注册成功但触发失败。

**解决思路**

（1）在 `hooks/` 下创建 `key_map.py` 作为唯一映射来源，定义 `KEY_TO_VK: dict[str, int]` 和 `VK_TO_KEY: dict[int, str]`，所有 Python 模块从此引用；（2）编写 `test_key_map_consistency.py`，对 C++ 支持的每个按键调用 DLL `SetGlobalHotkey` 验证是否与 Python `key_map.py` 一致。

---

## 41. 插件权限模型仅为声明级，Python 原生 API 无法限制

**问题**

`PluginAPI._check_permission`（`plugin_manager.py:187-188`）仅在插件调用 API 方法时检查 `self._permissions`。插件可以直接 `import os; os.system(...)` 绕过，因为插件代码以与主进程相同的权限运行（`importlib.util.spec_from_file_location` + `exec_module`，`plugin_manager.py:1306-1312`）。`HIGH_RISK_PERMISSIONS`（`:60-66`）仅用于安装确认提示，无运行时隔离。

**问题分析**

权限声明具有误导性——用户看到"需要 process.run 权限"并批准，但插件实际可以不加限制地做任何事（直接 import os/subprocess/ctypes）。恶意插件可以从 `clipboard.read` 权限升级为任意代码执行。`settings_plugins_page.py:42-43` 自己也承认"插件声明权限为高风险提示，并非强权限隔离"。

**解决思路**

（1）长期方案：使用子进程 + IPC 或 Windows Job Object + 受限 token 运行插件，主进程通过 PluginAPI 代理调用；（2）中期方案：在 `exec_module` 前后猴子补丁 `__builtins__`，移除 `os.system`、`subprocess`、`open` 等危险函数，仅通过 PluginAPI 暴露受控接口；（3）短期方案：修改 `settings_plugins_page.py` 描述，明确声明当前权限是"声明+提示"模式而非"强制隔离"。

---

## 42. core/plugin_manager.py 达 1722 行，内聚性不足

**问题**

`core/plugin_manager.py` 包含多个不同职责：数据模型 `PluginManifest`/`PluginInfo`（104-156 行，53 行）、`PluginAPI` 面向插件的 API（163-951 行，789 行）、验证函数 `validate_manifest`（958-984 行，27 行）、`PluginManager` 插件生命周期管理（992-1722 行，731 行）、包安装 `_install_zip_archive`（1517-1685 行，169 行）。

**问题分析**

`PluginAPI`（789 行）是面向插件的接口，混杂在面向宿主的管理器中，两者职责和受众完全不同。`_install_zip_archive`（169 行压缩包解析 + 路径防穿越 + staging/commit/rollback）的复杂度足够独立成一个模块。整个文件过大导致导航困难、修改冲突频繁（多个开发者同时修改不同功能时容易产生合并冲突）。

**解决思路**

拆分为模块：`core/plugin/models.py`（PluginManifest, PluginInfo）、`core/plugin/api.py`（PluginAPI）、`core/plugin/manager.py`（PluginManager）、`core/plugin/installer.py`（_install_zip_archive + staging/rollback）、`core/plugin/constants.py`（权限常量、信任级别）。

---

## 43. settings_plugins_page.py 935 行，UI 与业务逻辑耦合较重

**问题**

`SettingsPluginsPageMixin`（`ui/config_window/settings_plugins_page.py`）将 UI 布局与控件创建（`_setup_plugins_page`）、插件安装流程（`_install_plugin_package`）、插件启用/禁用/删除操作、拖放安装处理、本地化字符串与消息框交互全部糅合在一个 mixin 类中。

**问题分析**

935 行的 mixin 类同时承担视图渲染和业务逻辑处理，任何 UI 调整都可能影响插件管理功能的正确性。拖放安装涉及文件验证、路径安全检查、ZIP 解压等复杂逻辑，与 UI 代码混杂增加了测试难度。

**解决思路**

（1）将安装、删除、启用/禁用等操作委托给 PluginManager 的控制器层，页面保持纯 UI 渲染 + 信号连接；（2）独立 `PluginListWidget`、`PluginInstallDropArea` 等可复用组件。

---

## 44. 更新检查 SSL 证书验证失败

**问题**

用户点击"检查更新"时弹出 `CERTIFICATE_VERIFY_FAILED` 错误。错误链路：`main_window.py:729` → `update_mixin.py:58` → `checker.py:105` → `base_client.py:55`（`urlopen(context=self._ssl_context)`）→ OpenSSL 证书验证失败。`base_client.py:29` 在 `verify_ssl=True` 时传递 `None` 给 urlopen，依赖 Python 全局默认 SSL 上下文。

**问题分析**

最可能的原因是 Nuitka 打包后 SSL 证书链缺失——编译的独立可执行文件可能无法正确读取 Windows 系统证书存储，`ssl.create_default_context()` 找不到 `api.github.com` 的签发 CA。代码层面的设计缺陷是 `verify_ssl=True` 时传递 `None` 作为 SSL 上下文，没有降级策略。此外 `UpdateConfig.verify_ssl` 仅可通过代码修改，未暴露到 UI 设置页面，用户无法自助绕过。

**解决思路**

（1）修改 `base_client.py`，在 `verify_ssl=True` 时显式创建 SSL 上下文：`ctx = ssl.create_default_context(); ctx.load_default_certs(ssl.Purpose.SERVER_AUTH)`；（2）在 UI 设置页面增加"启用 SSL 证书验证"复选框，允许用户自行关闭验证；（3）优化错误信息，对 SSL 错误提供中文提示（如"网络连接不安全，请检查系统日期或网络环境"）；（4）打包时引入 `certifi` 依赖，使用 `ssl.create_default_context(cafile=certifi.where())`。

---

## 45. 对话框主题继承缺陷：全局浅色主题下编辑面板强制深色

**问题**

用户在设置中切换为浅色主题后，所有编辑对话框（CommandDialog、ShortcutDialog、UrlDialog、HotkeyDialog、ChainDialog、BatchLaunchDialog 等 13 个）仍显示深色主题。根因链：`BaseDialog.__init__` 在 `base_dialog.py:60` 硬编码 `self.theme = "dark"` → `resolve_theme()` 在 `theme_controller.py:35-50` 检查 `self.theme` 发现非空值 `"dark"` 后立即返回 → 永远不看父窗口的实际主题。

**问题分析**

三个环节共同导致此 bug：（1）`base_dialog.py:60` 硬编码 `"dark"` 作为默认值，覆盖了父窗口传入的任何主题信息；（2）`resolve_theme()` 优先检查对话框自身的 `self.theme` 属性，找到 `"dark"` 后直接返回，从不降级检查父窗口；（3）`MainWindow` 没有 `_theme` 或 `theme` 属性（主题存储在 `data_manager.get_settings().theme` 中），即使 `resolve_theme` 检查到父窗口也找不到主题属性。`_get_theme_from_parent` 函数名暗示会从父窗口获取主题，但实际上只检查对话框自身。

**解决思路**

（1）将 `base_dialog.py:60` 的 `self.theme = "dark"` 改为 `self.theme = ""`；（2）修改 `resolve_theme()` 在检查完 owner 自身属性后进一步检查 `owner.parent()` 的主题属性及 `data_manager`；（3）重写 `_get_theme_from_parent` 使其实际遍历父级链；（4）在 MainWindow 中添加 `self._theme` 属性供快速查找。此外项目中还有大量 `theme = "dark"` 硬编码（`icon_grid.py` 9 处、`settings_panel.py` 5 处、`folder_panel.py` 2 处等），需要统一排查修复。

---

## 46. main.py 过度宽泛的异常捕获

**问题**

`main.py` 作为应用入口点，共包含 20 处 `except Exception`（未指定具体异常类型），部分仅记录 debug 日志后静默忽略。例如第 56 行（无日志记录）、第 151 行（`logger.debug("忽略异常")`）、第 430 行（`traceback.print_exc()`）等。

**问题分析**

虽然启动阶段的异常容错有一定合理性（避免因次要初始化失败导致应用崩溃），但过度宽泛的捕获可能隐藏配置损坏、资源泄漏等严重问题。偶发性失败（如"权限状态读取失败"）与结构性失败（如"合并应用列表失败"）被相同的 `logger.debug` 处理，无差异化告警。生产环境中 debug 日志默认不输出，严重问题完全不可见。

**解决思路**

（1）将 `except Exception` 替换为 `except (FileNotFoundError, PermissionError, json.JSONDecodeError)` 等具体类型；（2）结构性失败（配置文件损坏、系统服务注册失败）使用 `logger.error` + 用户可见通知，非 `logger.debug`；（3）对已稳定运行多年的初始化路径（如"清空图标缓存"），可直接移除 try/except 让异常自然传播。

---

## 47. 模块级全局可变状态模式

**问题**

代码库中广泛使用模块级 `global` 变量作为单例/共享状态容器，共 25+ 处 `global` 声明：`_tray_app`（`main.py`）、`_server`（`main.py`）、`_registry_initialized`（`core/__init__.py`）、`plugin_manager`（`core/__init__.py`）、`data_manager`（`core/__init__.py`）、`_search_history`（`core/search_history.py`）、`_global_executor`（`core/chain/graph_executor.py`）等。

**问题分析**

全局状态导致三方面问题：（1）测试困难——全局状态在测试间泄漏，导致测试隔离性差；（2）初始化顺序脆弱——模块导入顺序决定全局变量初始化时序，隐式依赖可能导致 `None` 引用崩溃；（3）并发安全隐患——多数全局变量在非线程安全的上下文中使用。`core/command_exec/output.py:108-110` 的注释直接证明了循环依赖问题的存在：`# Lazy import to avoid circular`。

**解决思路**

（1）建立依赖注入容器 `core/di_container.py`，统一管理应用级单例的生命周期；（2）为每个全局单例暴露 `_reset_for_testing()` 方法，在测试 teardown 中重置状态；（3）逐步迁移至 `QApplication.instance()` 的自定义属性存储共享实例。

---

## 48. C++ hooks.cpp 轮询忙等待模式

**问题**

`hooks_dll/hooks.cpp:894-900` 和 `:988-994` 在等待旧钩子线程退出时使用轮询+睡眠的忙等待方式：`while (g_mouseThreadAlive.load() && waitCount < 50) { sleep_for(10ms); waitCount++; }`，最坏情况下浪费 500ms。`CallbackThreadProc` 的 `WaitForSingleObject(g_callbackEvent, 500)` 也使用了类似模式。

**问题分析**

10ms 间隔的忙等待虽然对 CPU 影响较小，但存在理论响应延迟（旧线程恰好在第 49 次检查后退出仍需等下一个 10ms 周期），且 `50` 和 `10` 是未命名的魔数，含义不够明确。

**解决思路**

（1）在旧线程退出时设置 `SetEvent(g_threadExitedEvent)`，安装函数改为 `WaitForSingleObject(g_threadExitedEvent, 2000)`，实现 0 CPU 等待；（2）定义命名常量 `THREAD_JOIN_POLL_MS = 10` 和 `THREAD_JOIN_MAX_POLLS = 50` 替代魔数；（3）最佳方案是使用 `std::thread::join()` + `std::future::wait_for` 超时模式。

---

## 49. _install_zip_archive 惰性导入反模式

**问题**

`core/plugin_manager.py:1517-1528` 的 `_install_zip_archive` 方法在函数体内惰性导入多个标准库模块（`json`、`re`、`shutil`、`sys`、`uuid`、`zipfile`、`pathlib`），这些都不是需要延迟加载的重量级模块。

**问题分析**

每次安装插件时重复执行 import 操作（虽因 import 缓存影响不大），且读者需要滚动到函数体内部才能了解该方法的依赖项，违背顶层导入的约定俗成。同一文件中的其他方法未使用此模式，不一致性增加维护负担。

**解决思路**

将全部惰性导入移至 `plugin_manager.py` 文件顶部的标准导入块。如果确实需要延迟导入（如避免循环导入），应在函数头部加注释说明原因。

---

## 50. 鼠标中键双击刷新图标闪烁性能退化

**问题**

用户长时间运行后（4+ 小时），中键双击弹窗空白区域触发的图标闪烁动画（`IconFlashOverlay`）明显变慢、不流畅。根因包括：（1）`_snapshot_icons()` 每次调用重新遍历布局并创建覆盖 pixmap，无缓存（`popup_window_helpers.py:119-211`）；（2）`_flash_icons()` 在 `_run_blank_area_refresh` 和 `_refresh_after_folder_sync` 中被重复调用导致竞态（`popup_data_refresh.py:440-497`）；（3）`_blank_refresh_in_progress` 状态锁在异常路径可能永久保持 True 导致闪烁功能彻底失效（`:478-497`）；（4）弹窗实例长期不销毁导致 `_icon_pixmap_cache`（200 个）、`_icon_miss_cache`（200 个）、`_page_pixmap_cache`（24 个）持续膨胀。

**问题分析**

最关键的问题是 `_blank_refresh_in_progress` 永久锁死：如果 `FolderSyncWorker` 正常启动但其回调 `_refresh_after_folder_sync` 中的 `refresh_data()` 因弹窗已隐藏或 C++ 对象部分销毁而抛出异常，`_blank_refresh_in_progress` 将永久保持 True，后续所有空白区域双击都被 return 拦截。另一个关键问题是两个 `_flash_icons()` 调用几乎同时触发，第二个发生在 `refresh_data()` 的 `processEvents()` 之后，此时 `_icon_pixmap_cache` 可能已被清空，导致全部 cache miss。

**解决思路**

（1）P0：修复 `_blank_refresh_in_progress` 锁死——在 `_refresh_after_folder_sync` 的 except 路径也重置标志，或使用 try/finally 确保无条件重置；（2）P0：移除 `_refresh_after_folder_sync` 中的 `_flash_icons()` 重复调用；（3）P1：在 `IconFlashOverlay` 中缓存覆盖 pixmap（按 `pixmap.cacheKey()` 索引），避免每次闪烁重建；（4）P1：使用 `QTimer.singleShot(120, ...)` 延迟启动文件夹同步，确保 96ms 闪烁动画先完成；（5）P2：将 `_page_icon_warm_timer` 纳入 `_stop_lifecycle_timers()` 管理。

---

## 51. 启动初始化阶段 TrayApp 构造与配置写操作存在竞态窗口

**问题**

`main.py` 在 `_tray_app = TrayApp()`（`:255`）构造后，`TrayApp.__init__` 内部立即启动定时器（`_process_check_timer`、钩子初始化、后台线程 `IconCacheCleanThread` 等）。但在 TrayApp() 之后，`main.py` 继续执行版本标记写入（`:258-281`）和回调注册（`:283-305`）。在构造与回调注册完成之间的约 50-100ms 窗口内，定时器或 IPC 命令可能触发。

**问题分析**

如果 `_process_check_timer` 在此窗口触发，可能读取到未完全初始化的配置状态。如果 IPC 在此窗口收到 `show_config` 命令，`on_show_config` 回调为 None（尚未注册），命令被静默丢弃。特殊应用列表合并（`:264-279`）操作与 `TrayApp._sync_special_apps_to_hook()` 可能并发读写 `data.json`。

**解决思路**

（1）将 `_process_check_timer.start()`、钩子安装等非关键初始化移动到 TrayApp 显式的 `start()` 方法，在 `main.py` 所有初始化完成后调用；（2）在 `create_ipc_server` 中缓存等待期间到达的 IPC 请求，回调注册完成后批量重放。

---

## 52. 更新检查器 _do_check 整个检查流程被单一大 try 包裹

**问题**

`services/update/checker.py:103-145` 的 `_do_check()` 方法将 GitHub Release API 解析、自定义 API 解析、JSON 解析、版本比较、校验等所有步骤包裹在一个 `try: ... except Exception as exc:` 中。`downloader.py:71-168` 的 `_do_download()` 同样将整个下载流程（URL 校验、HTTP 流、哈希计算、文件移动）被一个大 try/except 包裹。

**问题分析**

网络错误、JSON 解析错误、校验错误全部被合并为一个 "check_failed" 通知。排查问题时需要检查日志才能区分是"GitHub API 超时"还是"更新包域名不被信任"。不同性质的错误需要不同的用户操作（网络问题重试、证书问题关闭验证、数据问题报告 bug），但当前设计无法区分。

**解决思路**

（1）将网络请求、JSON 解析、业务校验分离到各自 try 块，每个块抛出语义化异常（如 `UpdateNetworkError`、`UpdateValidationError`）；（2）细化 `_notify` 事件类型为 `check_network_error`/`check_parse_error`/`check_validation_error`。

---

## 53. folder_watcher.py 观察器停止时线程等待超时过短

**问题**

`core/folder_watcher.py:137-138` 在 `stop_all()` 中调用 `observer.join(timeout=1.5)`，仅等待 1.5 秒。如果 watchdog 的 Observer 线程在此时间内未退出（例如正在处理大文件夹的文件变更事件），线程变成悬挂线程。

**问题分析**

应用退出时悬挂的 watchdog 线程阻止 Python 进程正常终止（进程退出被延迟直到所有非 daemon 线程完成，或进程被强制 kill）。在卸载重装场景中（如更新流程），旧进程残留可能导致 DLL 文件锁定。

**解决思路**

（1）将 timeout 增加到 5 秒，超时后使用 `observer.unschedule_all()` 强制清空所有 watch 再重试 join；（2）在创建 `Observer()` 时设置 `daemon=True`，确保进程退出时不被阻塞。

---

## 54. QR 文件服务器硬编码 Google DNS (8.8.8.8) 获取本机 IP

**问题**

`core/commands.py:497-504` 的 `_qr_get_local_ip()` 通过 UDP 连接 `8.8.8.8:80` 来确定本机 IP。在企业防火墙/离线环境中此连接被拦截或超时，函数静默返回 `127.0.0.1`，QR 文件分享仅绑定 localhost，外部设备无法访问。

**问题分析**

`socket.connect()` 在 UDP 上不实际发包，但路由表查找和防火墙过滤规则因操作系统/网络配置而异。0.5 秒超时对部分企业环境可能不够。当返回 `127.0.0.1` 时用户不知道为什么其他设备无法连接。

**解决思路**

（1）使用 `socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)` 枚举所有非回环 IPv4 地址，`8.8.8.8` UDP connect 仅作为首选方法；（2）若有多个活跃网卡（有线 + 无线 + VPN），提供 UI 下拉选择本机 IP。

---

## 55. 事件日志写入失败使用 DEBUG 级别记录

**问题**

`core/event_log.py:50-53` 在 `log_event` 写入失败时使用 `logger.debug`。`core/commands.py` 中多处进程管理操作失败也使用 `logger.debug`（如 `:1382` explorer kill 失败）。

**问题分析**

`logger.debug` 在生产环境中默认不输出，导致事件日志写入失败（意味着潜在数据丢失）完全不可见。不同模块对相同严重级别（进程管理错误）的日志级别不统一：`commands.py` 用 `logger.debug`，`tray_app.py:349` 用 `logger.error`，`hooks_mixin.py:201` 用 `logger.error`。

**解决思路**

（1）定义项目级日志级别策略：写入失败/数据丢失 → ERROR；操作失败但可降级 → WARNING；调试诊断 → DEBUG；（2）`event_log.py` 的写入异常从 `logger.debug` 改为 `logger.warning`。

---

## 56. core/__init__.py 急切导入形成的隐式循环依赖链

**问题**

`core/__init__.py:1-26` 在模块级急切地从 5+ 个子模块导入（`clipboard_service`、`data_manager`、`data_models`、`interaction_context`、`selected_text_service`），而 `core/plugin_manager.py` 又通过 `command_registry`、`path_security` 等间接引用 `core`，形成循环依赖链。`core/command_exec/output.py:108-110` 的注释和 `services/update/checker.py:231-232` 的函数体内导入都是为了绕开此问题。

**问题分析**

任何在 `core/__init__.py` 被导入模块中新增 `from core import ...` 都可能触发 `ModuleNotFoundError`/`AttributeError`。惰性导入散布在各个函数体中形成隐藏依赖，使 import 链难以静态分析，新人修改导入顺序时可能无意中破坏启动流程。

**解决思路**

（1）将 `core/__init__.py` 的急切导入改为函数内部的惰性导入 + 缓存；（2）每个函数体内的惰性 import 上方添加标准化注释 `# Lazy: avoids circular import via core.__init__`；（3）长期目标：解耦 `core/__init__.py` 的导出职责，让各模块直接导入所需子模块。

---

## 57. IPC 连接处理大 try 块吞没单连接异常后丢弃剩余连接

**问题**

`bootstrap/ipc.py:12-38` 的 `_on_new_connection` 将整个连接处理循环（`while server.hasPendingConnections()` → `conn.waitForReadyRead` → 解码 → 分发）包裹在一个 `try/except Exception` 中。

**问题分析**

若某一次循环迭代中抛出异常（如 `conn.readAll()` 返回无法解码的垃圾数据导致 TypeError），该次及之后所有等待中的连接都被丢弃——不仅出错的连接被跳过，同一个 while 循环中尚未处理的连接也全部丢失。IPC 协议层没有给丢弃的连接任何回复，导致对端（另一个 QuickLauncher 实例）认为 `show_config` 成功发送但实际未被处理。

**解决思路**

（1）将 `try/except` 移到 while 循环内部，使单个连接失败不影响队列中后续连接；（2）在异常分支记录已处理/未处理的连接数，提供排查线索。

---

## 58. data_manager.batch_update 嵌套时异常路径可能出现提前刷盘

**问题**

`core/data_manager.py:468-510` 的 `batch_update()` 上下文管理器支持嵌套，通过 `_batch_depth` 计数器追踪。但在 except 块（`:478-486`）中先减了 `_batch_depth`，然后 raise，finally 块（`:487-510`）仍然会执行并再次递减 `_batch_depth`。

**问题分析**

在嵌套 batch_update 场景下：（1）外层 batch_update depth=1；（2）内层 batch_update depth=2 → 异常 → except 中 depth 从 2 减为 1，然后 raise；（3）finally 块执行 → depth 从 1 减为 0 → 触发 `should_flush = True` → 执行 `_do_save()`。结果：内层异常导致外层未完成的批量修改被提前刷盘，可能写入部分变更的数据。

**解决思路**

（1）将 except 块中的 `_batch_depth -= 1` 移除，让 finally 统一管理深度递减；在 except 中仅重置 dirty 和 pending 标志；（2）在 finally 中增加 `assert self._batch_depth >= 0` 防止计数下溢。
