import re,os
print(len([m.group(1)for m in re.finditer(chr(34)+"(["+chr(34)+"]*[\u4e00-\u9fff]["+chr(34)+"]*)"+chr(34)+"\s*:",open("core/i18n.py",encoding="utf-8").read())]))
