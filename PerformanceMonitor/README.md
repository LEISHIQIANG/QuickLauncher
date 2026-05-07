# 性能监视器

监控 QuickLauncher 进程的 CPU、内存和磁盘使用情况。

## 安装依赖
```bash
pip install -r requirements.txt
```

## 运行
```bash
python monitor.py
```

或双击 `run.bat`

## 修改监控目标
编辑 `monitor.py` 第 95 行，修改进程名称：
```python
monitor = PerformanceMonitor("你的进程名")
```
