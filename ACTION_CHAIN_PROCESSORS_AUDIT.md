# 动作链电池审计

> 版本：QuickLauncher 1.6.3.0 / Action Chain 0.1.0  
> 范围：当前内置 `core.chain_processors.PROCESSOR_DEFINITIONS`

## 审计结论

- 所有内置电池已具备 schema：分类、描述、输入/输出端口、参数控件、安全级别和示例。
- 文件写入、文件下载、图片写入、创建文件夹和脚本电池按高风险标记；HTTP、文件读取、图片转换按注意级标记。
- 端口契约已改为优先读取 processor definition，避免 UI、校验和实现各自维护端口类型。
- 运行快照已包含 `typed_inputs` / `typed_outputs`，列表、JSON、文件、数字、布尔等值可以在调试面板区分类型。
- 插件/外部电池注册已加入 schema 质量门槛：端口类型、参数类型、安全等级、端口唯一性、参数归属输入端口、capability 前缀都会校验，不合格定义不会进入电池注册表。

## 状态口径

| 状态 | 说明 |
| --- | --- |
| 稳定 | 已有基础执行测试或被链路测试覆盖，行为可作为常规电池使用。 |
| 注意 | 可用，但涉及文件、网络、图片处理或外部环境，运行前应展示风险提示。 |
| 高风险 | 会写文件、下载文件、执行代码或可能覆盖用户数据。 |
| 待补测试 | schema 已完整，但仍需要更细的边界/错误用例测试。 |

## 标准端口命名约定

内部端口 id 为了兼容旧动作链会继续保留，例如 `success`、`output`、`files.0`、`urls.0`；画布 UI 必须显示更明确的数据语义：

| 内部 id | UI 标签 | 数据类型 | 角色 | 说明 |
| --- | --- | --- | --- | --- |
| `success` | 成功状态 | bool | status | 成功为 `1/true`，失败为 `0/false`。 |
| `output` | 主输出 | text/any | primary | 电池或快捷方式的主结果，具体类型由端口 schema 决定。 |
| `error` | 错误信息 | text | diagnostic | 失败时的错误说明。 |
| `stdout` | 标准输出 | text | stream | 命令进程 stdout 字符串。 |
| `stderr` | 标准错误 | text | diagnostic | 命令进程 stderr 字符串。 |
| `exit_code` | 退出码 | number | status | 命令进程退出码，通常 `0` 表示成功。 |
| `files.0` | 结果文件[0] | file | collection | 结果文件集合的第 0 项，不再显示为“第一个文件”。 |
| `folders.0` | 结果文件夹[0] | folder | collection | 结果文件夹集合的第 0 项。 |
| `urls.0` | 结果 URL[0] | url | collection | 结果 URL 集合的第 0 项，不再显示为“第一个网址”。 |

## 电池清单

| id | 标题 | 分类 | 状态 | 输入端口 | 输出端口 | 风险 |
| --- | --- | --- | --- | --- | --- | --- |
| `python_cell` | 脚本电池 | 输入与调试 | 高风险 | input:any | output:text | 执行代码、需确认 |
| `panel_node` | 看板 | 输入与调试 | 稳定 | input:any, text:text | output:text, length:number, empty:bool | 安全 |
| `text_input` | 文本输入 | 通用 | 稳定 | text:text | output:text, length:number, empty:bool | 安全 |
| `assert_not_empty` | 检查非空 | 逻辑 | 稳定 | text:text, message:text | output:text, length:number, empty:bool | 安全 |
| `coalesce_value` | 空值兜底 | 逻辑 | 稳定 | value:any, fallback:text | output:text, length:number, empty:bool | 安全 |
| `type_convert` | 类型转换 | 逻辑 | 待补测试 | value:any, type:text | output:text, length:number, empty:bool | 安全 |
| `conditional_branch` | 条件分支 | 逻辑 | 待补测试 | value:any, compare:text, target:text | output:text, length:number, empty:bool | 安全 |
| `logger_node` | 日志输出 | 输入与调试 | 稳定 | text:text, level:text | output:text, length:number, empty:bool | 安全 |
| `sleep_node` | 等待 | 输入与调试 | 稳定 | input:any, ms:number | output:text, length:number, empty:bool, ms:number | 安全 |
| `bool_value` | 布尔值 | 输入与调试 | 稳定 | value:bool | output:bool, not:bool | 安全 |
| `bool_not` | 逻辑非 | 逻辑 | 稳定 | value:bool | output:bool, not:bool | 安全 |
| `bool_and` | 逻辑与 | 逻辑 | 稳定 | a:bool, b:bool | output:bool, not:bool | 安全 |
| `bool_or` | 逻辑或 | 逻辑 | 稳定 | a:bool, b:bool | output:bool, not:bool | 安全 |
| `bool_xor` | 逻辑异或 | 逻辑 | 稳定 | a:bool, b:bool | output:bool, not:bool | 安全 |
| `compare_value` | 比较判断 | 逻辑 | 稳定 | a:bool, operator:text, b:bool | output:bool, not:bool | 安全 |
| `if_else` | 条件选择 | 逻辑 | 稳定 | condition:bool, true_value:text, false_value:text | output:text, length:number, empty:bool | 安全 |
| `loop_repeat` | 循环重复 | 逻辑 | 稳定 | input:any, count:number, delimiter:text | output:text, length:number, empty:bool | 安全 |
| `loop_counter` | 计数循环 | 逻辑 | 稳定 | start:number, end:number, step:number, delimiter:text | output:list, count:number, first:text, last:text, items_json:list | 安全 |
| `text_template` | 文本模板 | 文本 | 稳定 | template:text, input:any, a:text, b:text, c:text | output:text, length:number, empty:bool | 安全 |
| `text_replace` | 文本替换 | 文本 | 稳定 | text:text, find:text, replace:text | output:text, length:number, empty:bool | 安全 |
| `text_slice` | 文本裁剪 | 文本 | 稳定 | text:text, start:number, end:number | output:text, length:number, empty:bool | 安全 |
| `regex_extract` | 正则提取 | 文本 | 稳定 | text:text, pattern:text, group:number | output:text, length:number, empty:bool | 安全 |
| `text_case` | 大小写转换 | 文本 | 稳定 | text:text, mode:text | output:text, length:number, empty:bool | 安全 |
| `text_join` | 文本合并 | 文本 | 稳定 | delimiter:text, a:text, b:text, c:text, d:text, e:text | output:text, length:number, empty:bool | 安全 |
| `text_len` | 文本长度 | 文本 | 稳定 | text:text | output:number | 安全 |
| `text_split` | 文本拆分 | 文本 | 稳定 | text:text, delimiter:text | output:list, count:number, first:text, last:text, items_json:list | 安全 |
| `text_lines` | 文本分行 | 文本 | 稳定 | text:text | output:list, count:number, first:text, last:text, items_json:list | 安全 |
| `img_resize` | 图片缩放 | 图像 | 高风险 | filepath:file, width:number, height:number | output:file, path:file, folder:folder, filename:text, exists:bool | 写文件、需确认 |
| `img_convert` | 图片转换 | 图像 | 注意 | filepath:file, format:text | output:file, path:file, folder:folder, filename:text, exists:bool | 读写文件 |
| `img_watermark` | 添加水印 | 图像 | 高风险 | filepath:file, text:text, position:text | output:file, path:file, folder:folder, filename:text, exists:bool | 写文件、需确认 |
| `img_crop` | 图片裁剪 | 图像 | 高风险 | filepath:file, x:number, y:number, width:number, height:number | output:file, path:file, folder:folder, filename:text, exists:bool | 写文件、需确认 |
| `img_rotate` | 图片旋转 | 图像 | 高风险 | filepath:file, angle:number | output:file, path:file, folder:folder, filename:text, exists:bool | 写文件、需确认 |
| `json_get` | 取结构化字段 | 网络与结构化 | 稳定 | json:json, path:text | output:any | 安全 |
| `json_set` | 设置结构化字段 | 网络与结构化 | 稳定 | json:json, path:text, value:any | output:json | 安全 |
| `http_get` | 网页请求 | 网络与结构化 | 注意 | url:url, headers:text | output:text, status_code:number, headers:json, length:number, empty:bool | 访问网络 |
| `http_post` | 提交请求 | 网络与结构化 | 注意 | url:url, data:text, headers:text | output:text, status_code:number, headers:json, length:number, empty:bool | 访问网络 |
| `url_encode` | 网址编解码 | 网络与结构化 | 稳定 | text:text, mode:text | output:text, length:number, empty:bool | 安全 |
| `json_parse` | 结构化文本校验格式化 | 网络与结构化 | 稳定 | json_str:json | output:json | 安全 |
| `json_template` | 结构化模板 | 网络与结构化 | 稳定 | json:json, template:text | output:text, length:number, empty:bool | 安全 |
| `http_download` | 文件下载 | 网络与结构化 | 高风险 | url:url, save_dir:folder | output:file, path:file, folder:folder, filename:text, exists:bool | 网络、写文件、需确认 |
| `num_input` | 数字输入 | 数学与列表 | 稳定 | number:number | output:number | 安全 |
| `math_add` | 加法 | 数学与列表 | 稳定 | a:number, b:number | output:number | 安全 |
| `math_sub` | 减法 | 数学与列表 | 稳定 | a:number, b:number | output:number | 安全 |
| `math_mul` | 乘法 | 数学与列表 | 稳定 | a:number, b:number | output:number | 安全 |
| `math_div` | 除法 | 数学与列表 | 稳定 | a:number, b:number | output:number | 安全 |
| `math_pow` | 幂运算 | 数学与列表 | 稳定 | base:number, exp:number | output:number | 安全 |
| `math_mod` | 取模 | 数学与列表 | 稳定 | a:number, b:number | output:number | 安全 |
| `series_arith` | 等差数列 | 数学与列表 | 稳定 | start:number, step:number, count:number | output:list, count:number, first:text, last:text, items_json:list | 安全 |
| `series_geom` | 等比数列 | 数学与列表 | 稳定 | start:number, ratio:number, count:number | output:list, count:number, first:text, last:text, items_json:list | 安全 |
| `list_create` | 列表创建 | 数学与列表 | 稳定 | a:text, b:text, c:text, d:text, e:text | output:list, count:number, first:text, last:text, items_json:list | 安全 |
| `list_item` | 获取元素 | 数学与列表 | 稳定 | list:list, index:number | output:text, length:number, empty:bool | 安全 |
| `list_len` | 列表长度 | 数学与列表 | 稳定 | list:list | output:number | 安全 |
| `list_rev` | 反转列表 | 数学与列表 | 稳定 | list:list | output:list, count:number, first:text, last:text, items_json:list | 安全 |
| `list_unique` | 列表去重 | 数学与列表 | 稳定 | list:list | output:list, count:number, first:text, last:text, items_json:list | 安全 |
| `list_sort` | 列表排序 | 数学与列表 | 稳定 | list:list, mode:text | output:list, count:number, first:text, last:text, items_json:list | 安全 |
| `list_filter` | 列表筛选 | 数学与列表 | 稳定 | list:list, contains:text, exclude:text | output:list, count:number, first:text, last:text, items_json:list | 安全 |
| `list_contains` | 列表包含 | 数学与列表 | 稳定 | list:list, value:any | output:bool, not:bool | 安全 |
| `list_template` | 列表套模板 | 数学与列表 | 稳定 | list:list, template:text, delimiter:text | output:list, count:number, first:text, last:text, items_json:list | 安全 |
| `list_concat` | 列表合并 | 数学与列表 | 稳定 | a:text, b:text, c:text, delimiter:text | output:list, count:number, first:text, last:text, items_json:list | 安全 |
| `list_slice` | 列表切片 | 数学与列表 | 稳定 | list:list, start:number, end:number | output:list, count:number, first:text, last:text, items_json:list | 安全 |
| `list_zip` | 列表配对 | 数学与列表 | 稳定 | a:text, b:text, template:text, delimiter:text | output:list, count:number, first:text, last:text, items_json:list | 安全 |
| `list_flatten` | 列表展开 | 数学与列表 | 稳定 | list:list, mode:text | output:list, count:number, first:text, last:text, items_json:list | 安全 |
| `list_join` | 列表转文本 | 数学与列表 | 稳定 | list:list, delimiter:text | output:text, length:number, empty:bool | 安全 |
| `base_convert` | 通用进制转换 | 数学与列表 | 稳定 | number:number, from_base:number, to_base:number | output:text, length:number, empty:bool | 安全 |
| `dec_to_hex` | 十进制转十六进制 | 数学与列表 | 稳定 | number:number | output:text, length:number, empty:bool | 安全 |
| `hex_to_dec` | 十六进制转十进制 | 数学与列表 | 稳定 | number:number | output:number | 安全 |
| `file_path_input` | 文件路径 | 文件与路径 | 注意 | path:file | output:file, path:file, folder:folder, filename:text, exists:bool | 读取路径状态 |
| `folder_path_input` | 文件夹路径 | 文件与路径 | 注意 | path:folder | output:folder, path:folder, exists:bool | 读取路径状态 |
| `path_join` | 路径拼接 | 文件与路径 | 稳定 | a:text, b:text, c:text | output:file, path:file, folder:folder, filename:text, exists:bool | 安全 |
| `path_split` | 拆分路径 | 文件与路径 | 注意 | path:file | output:file, folder:folder, filename:text, stem:text, extension:text, exists:bool | 读取路径状态 |
| `path_exists` | 路径存在 | 文件与路径 | 注意 | path:file | output:bool, not:bool, path:file | 读取路径状态 |
| `folder_create` | 创建文件夹 | 文件与路径 | 高风险 | path:folder | output:folder, path:folder, exists:bool | 写文件、需确认 |
| `file_read_text` | 读取文本文件 | 文件与路径 | 注意 | path:file, encoding:text | output:text, length:number, empty:bool, path:file, folder:folder, filename:text | 读文件 |
| `file_write_text` | 写入文本文件 | 文件与路径 | 高风险 | path:file, text:text, encoding:text, mode:text | output:file, path:file, folder:folder, filename:text, exists:bool, length:number | 写文件、需确认 |

## 待办

- 为图片处理、HTTP 请求和文件下载补充隔离环境测试或 mock 测试。
- 为 `type_convert`、`conditional_branch` 增加边界用例。
- 后续新增插件电池时，应通过同一套 schema/contract 测试，并在此表中补充状态。
