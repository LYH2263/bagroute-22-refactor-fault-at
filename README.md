# BagRoute

投递装袋：按路线订户顺序装袋，重量与体积双约束，超限拒收。

## 启动

```bash
docker compose up --build
```

| 服务 | 地址 |
| --- | --- |
| 前端 | http://localhost:4300 |
| API | http://localhost:9300 |
| API 文档 | http://localhost:9300/docs |
| Postgres | localhost:5444 |

健康检查：`GET http://localhost:9300/api/health`

## 页面

- `/routes` — 路线
- `/stops` — 订户点
- `/pack` — 装袋
- `/bags` — 袋明细
- `/rejects` — 拒收
- `/weights` — 袋重

## 使用说明

1. 查看路线与订户点顺序。
2. 在装袋页选择路线执行双约束装袋。
3. 袋明细与袋重查看结果，拒收页查看超限订户。

## 装袋失败响应

`POST /api/pack` 失败时统一返回 `{"fault", "detail", "at"}` 三个键，`at` 只取 `route` / `stop` / `pack`：

| fault | at | 含义 | 状态码 |
| --- | --- | --- | --- |
| `route_not_found` | `route` | 路线找不到 | 404 |
| `invalid_stop` | `stop` | 订户点字段不合法 | 422 |
| `pack_rejected` | `pack` | 装袋过程业务拒绝 | 409 |

同类失败连续两次，`fault` 与 `at` 相同；装袋页会把三个键展示给操作员。

## 开发与测试

```bash
docker compose exec api pytest -q
```
