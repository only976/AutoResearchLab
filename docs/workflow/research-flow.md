# Research 流程

Research 是产品级工作单元，贯穿 refine → plan → execute → paper 四阶段。

## API 概览


| 方法     | 路径                                                 | 说明                                                  |
| ------ | -------------------------------------------------- | --------------------------------------------------- |
| GET    | `/api/research`                                    | 列出所有 Research                                       |
| POST   | `/api/research`                                    | 创建 Research（body: `{prompt}`）                       |
| GET    | `/api/research/{research_id}`                      | 获取 Research 详情（含 idea、plan、execution、outputs、paper） |
| DELETE | `/api/research/{research_id}`                      | 删除 Research（级联删除关联数据）                               |
| POST   | `/api/research/{research_id}/run`                  | 从 refine 开始全流程执行                                    |
| POST   | `/api/research/{research_id}/stop`                 | 中止当前运行                                              |
| POST   | `/api/research/{research_id}/retry`                | 从当前阶段重试                                             |
| POST   | `/api/research/{research_id}/stage/{stage}/run`    | 执行指定阶段（refine/plan/execute/paper）                   |
| POST   | `/api/research/{research_id}/stage/{stage}/resume` | 恢复指定阶段                                              |
| POST   | `/api/research/{research_id}/stage/{stage}/retry`  | 重试指定阶段                                              |
| POST   | `/api/research/{research_id}/stage/{stage}/stop`   | 中止指定阶段                                              |


## 阶段状态

- `idle`：未执行
- `running`：执行中
- `completed`：已完成
- `stopped`：用户中止
- `failed`：执行失败

## 实时事件（SSE）

事件流入口：`GET /api/events/stream?sessionId=...&sessionToken=...`

- `research-stage`：阶段状态变更（stage、status、error）
- `research-error`：Research 级错误

## 前置依赖

- Plan 需 Refine 完成
- Execute 需 Plan 完成
- Paper 需 Execute 完成
