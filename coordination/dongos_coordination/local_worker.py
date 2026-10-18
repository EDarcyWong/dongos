"""Owned subprocess, cancellable by the queue, without shell or agent tools."""
import json
from pathlib import Path
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dongos_coordination import local_model


def main():
    task = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    print(json.dumps({'type':'lmstudio.started','message':'正在处理简单任务；推理关闭、无工具调用。'},ensure_ascii=False),flush=True)
    answer = local_model.complete(task['provider'], [
        dict(role='system', content='完成一个简单、独立的小任务。只返回符合schema的JSON文件交付，不调用工具、不执行命令、不声称测试已运行或自行验收。'),
        dict(role='user', content=task['prompt'])], schema=local_model.SCHEMA)
    value = json.loads(answer)
    local_model.apply_files(Path.cwd(), task['allowed'], value)
    Path(sys.argv[1]).with_name('model-response.json').write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'type':'lmstudio.response','files':value['files']},ensure_ascii=False),flush=True)
    print(json.dumps({'result': '本地模型交付已收集，等待独立测试和源码审查。'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
