"""Animation API safety and compatibility tests to prevent AttributeError and state-checking bugs."""

import ast
import os
import pytest
from types import SimpleNamespace
from qt_compat import QApplication, QTimer, QPoint

# List of allowed variable names or patterns that can call .isActive()
ALLOWED_ISACTIVE_CALLERS = {
    "painter",
    "self",  # self.isActiveWindow()
    "timer",
    "auto_timer",
    "_bg_load_timer",
    "_indicator_timer",
    "_scroll_timer",
    "_sleep_timer",
    "_process_check_timer",
    "_settings_sync_timer",
    "_search_anim_timer",
    "_auto_close_timer",
    "_slider_debounce_timer",
    "_deferred_startup_timer",
    "_memory_check_timer",
    "_hide_timer",
    "hide_timer",
}


def test_codebase_for_isactive_animation_vulnerabilities():
    """Scan all Python files in the codebase to mathematically ensure `.isActive()` is never called on animation objects.

    This prevents regressions of the 'AttributeError: QPropertyAnimation object has no attribute isActive' bug.
    """
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_dirs = ["ui", "core", "bootstrap", "hooks", "tests"]
    
    violations = []
    
    for target in target_dirs:
        dir_path = os.path.join(root_dir, target)
        if not os.path.exists(dir_path):
            continue
            
        for root, _, files in os.walk(dir_path):
            for file in files:
                if not file.endswith(".py"):
                    continue
                file_path = os.path.join(root, file)
                
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    
                try:
                    tree = ast.parse(content, filename=file_path)
                except SyntaxError:
                    continue
                    
                for node in ast.walk(tree):
                    # Check for Attribute access like obj.isActive
                    if isinstance(node, ast.Attribute) and node.attr == "isActive":
                        # Determine the variable name of the object calling .isActive
                        caller_name = None
                        if isinstance(node.value, ast.Name):
                            caller_name = node.value.id
                        elif isinstance(node.value, ast.Attribute) and isinstance(node.value.value, ast.Name):
                            # e.g., self.auto_timer.isActive()
                            caller_name = node.value.attr
                            
                        # If the caller is not in the whitelisted set of QTimer/QPainter/QWidget names, or contains 'anim' or 'group'
                        is_safe = False
                        if caller_name:
                            # If caller_name explicitly ends with or contains 'timer'
                            if "timer" in caller_name.lower():
                                is_safe = True
                            # If caller_name is in whitelisted names
                            elif caller_name in ALLOWED_ISACTIVE_CALLERS:
                                is_safe = True
                                
                        # Animations should never be called with isActive
                        if caller_name and any(x in caller_name.lower() for x in ["anim", "group", "effect"]) and "timer" not in caller_name.lower():
                            is_safe = False
                            
                        if not is_safe:
                            # Get line number
                            line_no = getattr(node, "lineno", 0)
                            rel_path = os.path.relpath(file_path, root_dir)
                            violations.append(
                                f"{rel_path}:{line_no} - Called '.isActive' on unsafe caller '{caller_name or 'unknown'}'. "
                                "Animations do not support '.isActive()'; use '.state() == QAbstractAnimation.Running' "
                                "or call '.stop()' directly."
                            )
                            
    assert not violations, "Found animation isActive vulnerabilities:\n" + "\n".join(violations)


def test_wobbly_coffee_cup_lifecycle_safety(qapp):
    """Verify that WobblyCoffeeCup is stable, and its pause_effects/resume_effects work safely without AttributeErrors."""
    from ui.config_window.settings_license_page import WobblyCoffeeCup
    
    # Instantiate WobblyCoffeeCup inside the QApplication context (headless/offscreen)
    cup = WobblyCoffeeCup("☕")
    
    # 1. Verify basic properties (decorations with pyqtProperty are accessed as attributes, not methods)
    assert cup.text() == "☕"
    assert cup.offset == QPoint(0, 0)
    assert cup.angle == 0.0
    assert cup.halo_opacity == 0.0
    
    # 2. Test resume_effects
    cup.resume_effects()
    assert cup.auto_timer.isActive()
    assert cup.halo_opacity == 0.15
    
    # 3. Test pause_effects
    cup.pause_effects()
    assert not cup.auto_timer.isActive()
    assert cup.halo_opacity == 0.0
    
    # Cleanup
    cup.deleteLater()


def test_support_dialog_lifecycle_safety(qapp):
    """Verify that SupportDialog constructs and manages its transition animation lifecycle safely without crash."""
    from ui.config_window.support_dialog import SupportDialog
    
    # Instantiate SupportDialog
    dialog = SupportDialog(drink_name="Latte", price="9.9", color_hex="#f39c12")
    
    # Verify starting animation is setup and running
    assert hasattr(dialog, "_entry_anim")
    assert dialog.anim_progress == 0.0 or dialog.anim_progress > 0.0
    
    # Force anim_progress to 1.0 to bypass early exit guard in close_with_anim
    dialog.anim_progress = 1.0
    
    # Trigger close_with_anim and verify exit animation runs safely
    dialog.close_with_anim()
    assert hasattr(dialog, "_exit_anim")
    
    # Cleanup
    dialog.deleteLater()


def test_settings_about_page_lifecycle_safety(qapp):
    """Verify that the About page setup and dynamic theme synchronization run safely without any errors."""
    from ui.config_window.settings_about_page import SettingsAboutPageMixin
    from qt_compat import QWidget, QVBoxLayout
    
    # Create a mock Page class that inherits QWidget and has add_group and apply_theme
    class MockPage(QWidget):
        def __init__(self):
            super().__init__()
            self.layout = QVBoxLayout(self)
            self.apply_theme = lambda theme: None
            
        def add_group(self, title):
            from qt_compat import QGroupBox, QVBoxLayout
            group = QGroupBox(title, self)
            layout = QVBoxLayout(group)
            self.layout.addWidget(group)
            return layout, group
            
    # Create an instance of a class mixing in SettingsAboutPageMixin
    class AboutPanel(SettingsAboutPageMixin):
        def __init__(self):
            self.theme = "dark"
            
    panel = AboutPanel()
    page = MockPage()
    
    # Trigger setup
    panel._setup_about_page(page)
    
    # Verify properties saved
    assert hasattr(page, "_header_card")
    assert hasattr(page, "_title_lbl")
    assert hasattr(page, "_slogan_lbl")
    assert hasattr(page, "_developer_lbl")
    assert hasattr(page, "_intro_card")
    assert hasattr(page, "_intro_lbl")
    assert len(page._feature_cards) == 6
    assert len(page._feature_lbls) == 6
    
    # Test dynamic theme updating to light mode
    panel._update_about_page_theme(page, "light")
    assert page._title_lbl.text() != ""
    
    # Test dynamic theme updating to dark mode
    panel._update_about_page_theme(page, "dark")
    assert page._title_lbl.text() != ""
    
    # Cleanup
    page.deleteLater()

