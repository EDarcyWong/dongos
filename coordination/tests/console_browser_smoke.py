"""Optional browser QA: python coordination/tests/console_browser_smoke.py [output-directory].

Requires Playwright and Chromium. Uses disposable fixtures, never live task state,
never starts the runner and never invokes an AI CLI.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dongos_coordination.projects import Registry
from dongos_coordination.runner import Runner
from dongos_coordination.server import Console
from playwright.sync_api import sync_playwright


def main():
    output = Path(sys.argv[1] if len(sys.argv)>1 else tempfile.mkdtemp(prefix='console-screens-'))
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='console-browser-') as folder:
        root = Path(folder)
        source = root/'source'; source.mkdir()
        registry = Registry(root/'coordination')
        registry.add('demo', 'DongOS · 测试工作区', str(source))
        second = root/'second'; second.mkdir(); registry.add('empty', '空项目 · 测试', str(second))
        store = registry.store('demo')
        titles = ['完善模块导入的错误定位与诊断', '检查 bootstrap 后端的控制流边界', '补齐文件读取与输出管道测试',
                  '整理独立复验记录与组件契约', '为任务释放与重新领取补充回归测试', '完善窄整数运算的边界检查',
                  '核对短路表达式的源码集成', '验证符号表与跨模块引用', '修复语义诊断中的长文本换行',
                  '整理编译产物的可追溯信息', '补齐分配器测试中的错误分支', '完善自举构建的文档与测试说明']
        base = datetime.now(timezone.utc)-timedelta(hours=3)
        for i, title in enumerate(titles):
            owner = [None, 'cursor', 'claude', None, 'codex', 'deepseek', 'claude', 'cursor', None, 'lmstudio', 'codex', 'deepseek'][i]
            namespace = owner or 'pool'
            with patch('dongos_coordination.store.now', return_value=(base+timedelta(minutes=i*3)).isoformat(timespec='seconds')):
                task = store.create(dict(id='T'+str(i+1), owner=owner, title=title,
                    description='目标\n'+title+'，保留现有任务与交付历史。\n\n实现要求\n1. 仅修改声明的文件，遵守组件接口约定。\n2. 覆盖成功、失败和重复操作的边界情况。\n3. 交付时列明实际测试结果；等待独立复验后再集成。',
                    write_paths=[namespace+'-works/docs/T'+str(i+1)+'.md']))
            if i in (1,2,3,5,6,7,9,10,11):
                with patch('dongos_coordination.store.now', return_value=(base+timedelta(minutes=i*3+2)).isoformat(timespec='seconds')):
                    task=store.change(task['id'], task['rev'], 'claim', options={'owner':owner or 'cursor'})
            if i in (2,6,7,9,10,11):
                delivery=store.path(task['delivery']);delivery.parent.mkdir(parents=True,exist_ok=True);delivery.write_text('Fixture delivery. No model invoked.', encoding='utf-8')
                with patch('dongos_coordination.store.now', return_value=(base+timedelta(minutes=i*3+35)).isoformat(timespec='seconds')):
                    task=store.change(task['id'],task['rev'],'submit')
            if i==5:store.change(task['id'],task['rev'],'pause')
            if i==7:store.change(task['id'],task['rev'],'rework',note='补充空输入与重复调用边界。')
        runner = Runner(store, {})
        server = Console(('127.0.0.1',0), store, runner, registry=registry)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            if '--serve' in sys.argv:
                print('Isolated fixture preview: http://127.0.0.1:'+str(server.server_port), flush=True)
                thread.join()
                return
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
                page=browser.new_page(viewport={'width':1440,'height':1080},device_scale_factor=1)
                errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto('http://127.0.0.1:'+str(server.server_port))
                page.wait_for_selector('#task-rows tr')
                assert page.locator('#task-rows tr').count()==12
                assert not page.locator('#progress-board').is_visible()
                assert page.locator('#owner-filter').is_visible()
                page.screenshot(path=str(output/'console-desktop.png'),full_page=True)
                page.get_by_role('button',name='待领取',exact=True).click()
                assert page.locator('#task-rows tr').count()==3
                page.locator('#owner-filter').select_option('unassigned')
                assert page.locator('#task-rows tr').count()==3
                page.locator('#search').fill('错误定位')
                assert page.locator('#task-rows tr').count()==1
                page.locator('#task-rows tr').click()
                assert page.locator('#detail-dialog').is_visible()
                assert page.locator('.task-metrics').inner_text().count('暂无记录')==1
                page.get_by_role('button',name='领取公共任务',exact=True).click()
                page.wait_for_selector('#detail-dialog .badge.in_progress')
                claimed=store.get('pool:T1');assert claimed['owner']=='cursor'
                assert page.locator('.elapsed-metric').inner_text().find('秒')>=0
                page.get_by_role('button',name='请求暂停',exact=True).click()
                page.wait_for_selector('.stop-confirm-label')
                page.locator('.stop-confirm-label input').check()
                page.get_by_label('外部停止确认依据').fill('隔离测试，无外部执行进程')
                page.get_by_role('button',name='确认已停止',exact=True).click()
                page.wait_for_selector('#detail-dialog .badge.paused')
                page.get_by_role('button',name='释放回公共任务池',exact=True).click()
                page.wait_for_selector('#detail-dialog .badge.todo')
                assert store.get('pool:T1')['owner'] is None
                page.locator('#close-detail').click()
                page.locator('#progress-reset').click()
                page.locator('#task-rows tr').filter(has_text='完善模块导入').click()
                page.get_by_role('button',name='领取公共任务',exact=True).click()
                page.wait_for_selector('#detail-dialog .badge.in_progress')
                page.screenshot(path=str(output/'console-task-detail.png'),full_page=True)
                page.locator('#close-detail').click()
                page.locator('#new-task').click()
                assert page.locator('select[name=owner]').input_value()==''
                assert page.locator('input[name=dispatch]').is_disabled()
                page.locator('input[name=title]').fill('浏览器发布与领取回归')
                page.locator('textarea[name=description]').fill('隔离测试；不操作用户任务。')
                page.get_by_role('button',name='发布任务',exact=True).click()
                page.wait_for_selector('#detail-dialog[open]')
                assert store.get('pool:T2')['owner'] is None
                page.locator('#close-detail').click()
                page.locator('#view-board').click()
                assert page.locator('#progress-board').is_visible()
                assert not page.locator('.workspace').is_visible()
                page.locator('#view-list').click()
                page.locator('#search').fill('nothing matches this fixture')
                assert page.locator('#empty').is_visible()
                page.locator('#progress-reset').click()
                page.locator('#project-select').select_option('empty')
                page.wait_for_function("document.getElementById('total').textContent==='0'")
                assert page.locator('#task-rows tr').count()==0
                page.locator('#project-select').select_option('demo')
                page.wait_for_selector('#task-rows tr')
                page.set_viewport_size({'width':390,'height':844})
                page.screenshot(path=str(output/'console-mobile.png'),full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                assert page.locator('#owner-filter').is_visible()
                page.locator('#task-rows tr').first.click()
                assert page.locator('#detail-dialog').is_visible()
                page.screenshot(path=str(output/'console-mobile-detail.png'),full_page=True)
                page.keyboard.press('Escape')
                assert not page.locator('#detail-dialog').is_visible()
                assert not errors, errors
                browser.close()
                print('PASS: create, public claim/release/reclaim, filters, empty state, view switching, project switching, desktop/mobile layout, dialog dismissal; no JS errors.')
                print('Screenshots:', output)
        finally:
            server.shutdown();server.server_close();thread.join(timeout=5)


if __name__=='__main__':main()
