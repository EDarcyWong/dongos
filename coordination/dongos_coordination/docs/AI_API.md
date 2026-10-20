# Coordination：AI任务接口 v1

Claude Code、Cursor、LM Studio 和 DeepSeek Harness 客户端也可使用 MCP 任务接口，无需调用 AI CLI。MCP 指南在线地址 `/api/mcp/guide`，本地文件为同目录 `MCP.md`。MCP 仅封装下方现有 API 的查看/领取/释放/交付，继续执行相同的 rev、负责人、领取者、依赖和活动作业检查；Cursor 保持手动执行。

Codex另有MCP协调角色，通过既有网页管理API统一发布任务、返修、暂停/恢复、定向复验及登记验收/集成；每次显式项目，沿用同源令牌、rev与实物指纹检查，不改库。普通执行者的v1任务API仍不提供自行验收/集成。角色配置和独立复验要求详见MCP指南。

把这个入口交给AI即可自动发现能力：`GET http://127.0.0.1:8765/api/ai`。

- 本文在线地址：`/api/ai/guide`（UTF-8 Markdown）。
- OpenAPI 3.1：`/api/ai/openapi.json`。
- 服务：在协调项目目录运行 `python coordinate.py serve`；自定义端口时替换本文的8765。
- 本地Python客户端：`dongos_coordination.client.CoordinationClient`，仅依赖标准库。

## 先区分两个“提交”

**发布任务**：创建一项新工作，状态为 `todo`，等待领取。**提交交付**：领取者完成实现后提交报告，状态为 `submitted`，等待独立复验。二者都不会自动调用模型、运行测试或标记验收。

## AI执行约定

1. 读取 `/api/ai` 和项目列表，确认项目。不要依赖页面当前选中的项目。
2. 查询并领取分配给自己的 `owner` 或 `owner=null` 公共池中的 `todo` / `rework` 任务。领取前读取完整任务书、依赖、文件归属、上轮审查及最新 `rev`。
3. 用固定 `agent_id` 标识当前工作实例，例如 `claude-worker-1`。收到领取成功响应后才能工作；并发领取只有一个成功。保存响应中的 `claim_token`，后续提交、释放或停止确认须回传本轮令牌。
4. 源码路径相对于该项目的 `source_root`；`claude-works/...` 等路径映射到项目的 `works_root`。自动CLI使用组合后的独立副本，不覆盖原源码。外部AI必须遵守自己的任务范围和现有工作区契约。
5. 完成后提交真实交付说明、实际测试结果及证据路径。未执行的测试明确写“未执行”，不把模拟结果当作真实执行。
6. 遇到 `409` 先重新查询任务，确认是否已被别人领取、版本更新或依赖未完成；不要无限重试，也不要抢别人的任务。
7. 不手改SQLite/index.json，不自行验收或集成，不通过其它页面接口绕过这些约定。项目负责人负责独立复验与源码/契约审查。

`owner` 取 `codex / claude / cursor / deepseek / lmstudio`。`agent_id` 是协作归属标签，**不是独立身份认证**；这是面向本机可信AI的接口，没有远程多租户账号/权限系统。不要暴露到公网。

## 本机操作令牌

读取操作无需令牌，仍必须访问本机合法Host。写操作先 `GET /api/session`，获取JSON字段 `csrf`，然后同时发送：

```text
Content-Type: application/json
Origin: http://127.0.0.1:8765
X-Coordinator-CSRF: <csrf>
```

Origin的主机名和端口应与所用服务地址一致。服务重启会轮换令牌，遇到403可重新GET session并最多重试一次；409不能按令牌过期处理。Python客户端已实现这一流程。令牌不写进任务书、日志或仓库。

## 接口清单

| 操作 | 方法与路径 | 请求/响应 |
| --- | --- | --- |
| 查看项目 | `GET /api/v1/projects` | `{projects:[{id,name,source_root,works_root,...}]}` |
| 查看任务 | `GET /api/v1/projects/{project}/tasks?owner=claude&status=todo&q=关键词` | `{project,total,tasks:[...]}`；筛选可省略 |
| 查看单项 | `GET /api/v1/projects/{project}/tasks/{task_id}` | `{project,task}`，含最新rev |
| 读任务书 | `GET .../tasks/{task_id}/document?kind=task` | `{project,path,text,sha256,truncated}` |
| 读交付 | `GET .../tasks/{task_id}/document?kind=delivery` | 同上；自动执行的交付从候选副本读取 |
| 发布新任务 | `POST /api/v1/projects/{project}/tasks` | 创建成功201，返回 `{project,task}` |
| 领取 | `POST .../tasks/{task_id}/claim` | `{rev,owner,agent_id}` |
| 释放 | `POST .../tasks/{task_id}/release` | `{rev,owner,agent_id,claim_token}`；先停止外部工作；回到领取前的todo/rework，公共任务重新开放 |
| 提交交付 | `POST .../tasks/{task_id}/submit` | `{rev,owner,agent_id,claim_token,report?}`；进入submitted |

| 停止确认 | `POST .../tasks/{task_id}/acknowledge_pause` | `{rev,owner,agent_id,claim_token}`；原领取者确认确实已停止外部编辑/进程 |

`task_id` 是完整编号，例如 `claude:C7`，放在URL时可编码为 `claude%3AC7`。项目编号例如 `dongos`。URL项目是唯一定位依据，不受 `X-Coordination-Project` 页面头影响。

任务字段：`id`（完整编号）、`number`（短编号）、`owner`、`title`、`description`、`status`、`rev`、`write_paths`、`checks`、`depends_on`、`document`、`delivery`、`claimed_by`（领取后）、`review_note`、`candidate`、`verification`。`rev` 每次状态写入都会递增，动作必须使用最近响应中的版本。

## 发布任务

```json
{
  "id": "C20",
  "owner": "claude",
  "title": "一个独立的小组件",
  "description": "实现目标、明确接口、限制与验收条件。",
  "write_paths": ["claude-works/src/example.py", "claude-works/tests/test_example.py"],
  "checks": ["discover:claude-works/tests:test_example.py"],
  "depends_on": []
}
```

新任务不能指定status/rev/验收结果。短编号匹配 `[A-Z][A-Z0-9_-]{0,39}`，标题1～180字符，说明≤24000字符，可修改路径1～40项，依赖≤32项。`owner` 可省略或为null；公共任务使用稳定的 `pool:T1` 编号及 `pool-works/` 路径，所有符合任务范围的成员均可领取。系统自动增加对应命名空间的固定交付路径并生成任务书。编号重复或与未关闭任务的文件归属重叠会409。依赖必须引用当前项目中已存在的完整编号；领取前依赖须已验收或集成。

除Codex维护任务外，新组件写入自己的 `{owner}-works/`，验收后再由负责人集成。拒绝绝对路径、`..`、隐藏配置、build/esp等路径。LM Studio只接简单任务：说明≤3000字符、含交付最多3个明确文本文件，不允许通配符或修改测试/主线。

定向检查仅支持 `module:lang.tests.test_name`、`module:tests.test_name`，或 `discover:受支持目录:test_name.py`；当前支持目录为 tests、cursor-works/tests、claude-works/tests、deepseek-works/tests、codex-works/tests、lmstudio-works/tests、pool-works/tests。不接受shell命令。checks为空的任务可以发布，但不能以自动复验通过为依据验收。

## 领取、释放和交付

```json
{"rev": 1, "owner": "claude", "agent_id": "claude-worker-1"}
```

领取成功时状态in_progress，记录claimed_by/claimed_at及新的claim_token。领取时owner须为当前负责人，或在公共任务未指定负责人时成为实际领取成员。释放/提交还要求当前处于in_progress，agent_id等于领取者、claim_token等于本轮领取令牌；不能提交未领取或别人领取的任务，也不能用旧轮次结果覆盖转派后的任务。Web手动领取的旧任务没有AI领取标识，应由操作者先释放，再由AI领取。

提交交付可以附带 `report`：

```json
{
  "rev": 2,
  "owner": "claude",
  "agent_id": "claude-worker-1",
  "claim_token": "<本轮领取响应的claim_token>",
  "report": "实现范围：...\n实际测试：...\n证据路径：...\n限制：...\n待独立复验。"
}
```

report为1～24000字符的Markdown，仅写固定交付文件；已有交付会追加新段落保留历史，不覆盖旧内容。也可省略report，但必须已在固定交付路径写好文件。此接口不上传实现文件、不执行报告中的命令，也不运行测试；只能把交付状态变为submitted。候选副本/主目录的区别以任务字段为准，不要把未集成的候选源码当作已进入项目。

## Python最小示例

在协调项目目录运行（其它目录先把coordination加入Python模块搜索路径）：

```python
from dongos_coordination.client import CoordinationClient, APIError

c = CoordinationClient("http://127.0.0.1:8765")
print(c.projects())
project, owner, agent = "dongos", "claude", "claude-worker-1"
todo = c.tasks(project, owner=owner, status="todo")
if todo:
    task = c.task(project, todo[0]["id"])
    print(c.document(project, task["id"])["text"])
    try:
        task = c.claim_task(project, task["id"], rev=task["rev"], owner=owner, agent_id=agent)
    except APIError as e:
        if e.status == 409:
            print("状态变化，请重新查询，不要开始实现")
        raise
    # 按任务范围完成实现与实际测试；不要直接复制这行示例报告来宣称完成。
    # task = c.submit_task(project, task["id"], rev=task["rev"],
    #     owner=owner, agent_id=agent, report="真实范围、测试结果、证据和限制")
    # 放弃工作时：c.release_task(project, task["id"], rev=task["rev"], owner=owner, agent_id=agent)
```

## PowerShell最小示例

```powershell
$base = 'http://127.0.0.1:8765'
$session = Invoke-RestMethod "$base/api/session"
$headers = @{ Origin=$base; 'X-Coordinator-CSRF'=$session.csrf }
$list = Invoke-RestMethod "$base/api/v1/projects/dongos/tasks?owner=claude&status=todo"
if ($list.tasks.Count -gt 0) {
    $task = $list.tasks[0]
    $id = [uri]::EscapeDataString($task.id)
    $body = @{rev=$task.rev;owner='claude';agent_id='claude-worker-1'} | ConvertTo-Json
    Invoke-RestMethod "$base/api/v1/projects/dongos/tasks/$id/claim" -Method Post `
      -Headers $headers -ContentType 'application/json' -Body ([Text.Encoding]::UTF8.GetBytes($body))
}
```

## 状态与错误

`todo → in_progress → submitted → accepted → integrated`；返修为rework，可再次领取；释放in_progress回到该轮领取前的todo/rework。暂停、返修决定、运行独立复验、验收与集成由控制台负责人处理，v1 AI任务接口不提供自行关闭这些门禁的操作。

所有接口返回JSON，错误体为 `{error:"说明"}`。400参数/路径/依赖/报告错误；403同源校验失败；404项目/任务/文档不存在；409版本/状态/领取者/文件冲突；413请求超过64KiB；415请求不是application/json。重复发布不会覆盖原任务；重复领取/提交会409。网络超时可能已有操作成功：先GET任务核对status/rev/claimed_by及交付，再决定下一步，不盲目重放。

## 暂停、转派和计时

- 新任务可直接指定owner，也可不指定。已有todo/rework任务可通过网页或Codex协调MCP的`change_task(action="reassign", new_owner=...)`明确指派。任务编号、文件范围、交付位置及依赖保持不变；不移动或覆盖文件。
- 进行中的任务必须先暂停。协调器管理的CLI请求会取消作业，只有确认进程退出才标记暂停并允许转派。恢复是重新执行，不是恢复被终止的进程。
- 外部Cursor/MCP/手动进程无法由本服务停止。请求暂停后保留in_progress及`pause_requested_at`，拒绝新提交。原领取者先停止工作，再调用`acknowledge_pause`；或操作者在网页勾选明确确认并填写已停止依据。不能只改变状态就宣称进程已停止。
- 转派要求停止确认和交接说明；清除旧claim_token，新成员重新领取。`assignment_history`保留原成员、新成员、原领取者和交接说明。已交付任务先由协调者要求返修，再转派；验收/集成门禁不变。
- claimed_at为成功领取或CLI实际开始，completed_at为执行完成（提交），不是验收/集成。每次释放、停止或转派结束一个未提交轮次；重新领取另记一轮。经过时长包含暂停，办理时长扣除明确暂停。历史缺失事件不补造。
- Python客户端在同一实例中自动保留领取响应的claim_token；重建客户端后可在submit_task/release_task/acknowledge_pause显式传入本轮令牌。旧版本客户端须一起更新。
