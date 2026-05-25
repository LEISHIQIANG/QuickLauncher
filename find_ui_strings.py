import re, os

c = open("core/i18n.py", encoding="utf-8").read()
en = set()
for m in re.finditer(chr(34)+"(["+chr(34)+"]*[\\u4e00-\\u9fff]["+chr(34)+"]*)"+chr(34)+"\\s*:", c):
    en.add(m.group(1))

ui = set()
skip = {"__pycache__",".git","venv",".idea",".pytest_cache",".ruff_cache",".claude"}
markers = ["tr(","add_group(","_create_label(","QLabel(","QPushButton(","QGroupBox(","QCheckBox(","QRadioButton(","QAction(",".setText(",".setToolTip(",".setPlaceholderText(",".setTitle(",".setWindowTitle("]

for r,d,fs in os.walk("."):
    d[:]=[x for x in d if x not in skip and not x.startswith(".")]
    for fn in fs:
        if not fn.endswith(".py"): continue
        try:
            txt = open(os.path.join(r,fn), encoding="utf-8").read()
            for line in txt.split(chr(10)):
                if not any(m in line for m in markers): continue
                for m in re.finditer(chr(34)+"(["+chr(34)+"]*[\\u4e00-\\u9fff]["+chr(34)+"]*)"+chr(34), line):
                    ui.add(m.group(1))
                for m in re.finditer(chr(39)+"(["+chr(39)+"]*[\\u4e00-\\u9fff]["+chr(39)+"]*)"+chr(39), line):
                    ui.add(m.group(1))
        except: pass

with open("ui_strings.txt","w",encoding="utf-8") as f:
    for s in sorted(ui):
        f.write(s+chr(10))
with open("en_us_keys.txt","w",encoding="utf-8") as f:
    for s in sorted(en):
        f.write(s+chr(10))

missing = sorted(ui - en)
with open("missing_strings.txt","w",encoding="utf-8") as f:
    for s in missing:
        f.write(s+chr(10))

print("EN_US:", len(en))
print("UI:", len(ui))
print("Missing:", len(missing))
