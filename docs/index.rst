QuickLauncher 文档
==================

QuickLauncher 是一款 Windows 平台的鼠标中键快速启动工具。

.. toctree::
   :maxdepth: 2
   :caption: 目录:

   architecture
   api/index

快速开始
--------

安装依赖::

    pip install -r requirements.txt

运行程序::

    python main.py

开发指南
--------

安装开发依赖::

    pip install -r requirements-dev.txt
    pre-commit install

运行测试::

    pytest --cov

代码检查::

    ruff check .
    black .
    mypy core ui bootstrap

索引
====

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
