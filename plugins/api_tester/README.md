# API Tester

## 插件定位

API Tester 是一个轻量 HTTP 请求工具，让你在 QuickLauncher 弹窗中直接发送 GET/POST/PUT/PATCH/DELETE 请求并查看格式化响应，无需打开浏览器或 Postman。

适合快速调试 REST API、验证接口连通性、查看响应格式。

## 命令

| 命令 ID | 常用输入 | 参数 | 说明 |
|---|---|---|---|
| `api_tester.get` | `api-get` | URL | 发送 GET 请求 |
| `api_tester.post` | `api-post` | URL + 请求体 | 发送 POST 请求 |
| `api_tester.put` | `api-put` | URL + 请求体 | 发送 PUT 请求 |
| `api_tester.delete` | `api-delete` | URL | 发送 DELETE 请求 |
| `api_tester.history` | `api-history` | 无 | 查看最近 30 条请求记录 |

## 示例

```text
api-get https://api.github.com/zen
api-post https://jsonplaceholder.typicode.com/posts {"title":"test","body":"hello"}
api-history
```

## 结果按钮

- 复制响应：复制格式化后的响应体
- 复制 curl：复制等价的 curl 命令

## 权限

| 权限 | 原因 |
|---|---|
| `network.request` | 发送 HTTP 请求到指定 URL |

## 注意事项

- 请求超时 8 秒，大响应会自动截断（64KB）
- 响应体自动识别 JSON 并缩进格式化
- 请求记录保存在插件数据目录 `api_tester/data/history.json`
- 不支持自定义请求头、Cookie 等高级功能
