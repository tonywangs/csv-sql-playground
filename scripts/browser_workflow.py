"""Real Chromium acceptance workflow; starts its own loopback server."""
import json, os, socket, subprocess, sys, tempfile, time, urllib.request, hashlib
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
ROOT=Path(__file__).resolve().parents[1]

def main():
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    server=subprocess.Popen([sys.executable,str(ROOT/'server.py'),'--port',str(port)],stdout=subprocess.DEVNULL)
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'fixtures').glob('*.xlsx')}
    try:
        for _ in range(100):
            try:urllib.request.urlopen(base,timeout=1);break
            except Exception:time.sleep(.05)
        with sync_playwright() as p, tempfile.TemporaryDirectory(prefix='formula-browser-') as tmp:
            browser=p.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1440,'height':1050},accept_downloads=True)
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(base);page.locator('#workbook').set_input_files(ROOT/'fixtures/Valuation.xlsx')
            expect(page.locator('#workspace')).to_be_visible()
            expect(page.locator('#coverage')).to_contain_text('1026 supported')
            page.locator('#sheet').select_option('Valuation');page.locator('#address').fill('H57');page.locator('#go button').click()
            expect(page.locator('#detail')).to_contain_text("'Financial Model'!$D$263")
            expect(page.locator('#trace')).to_contain_text("'Financial Model'!D263")
            expect(page.locator('#traceStatus')).to_contain_text('INCOMPLETE')
            page.locator('#transitive').uncheck()
            page.locator('#trace').get_by_role('button',name="'Financial Model'!D263",exact=True).click()
            expect(page.locator('#detail')).to_contain_text("'Financial Model'!D263")
            page.locator('#direction').select_option('dependents')
            expect(page.locator('#trace')).to_contain_text("'Valuation'!H57")
            note='Review model inputs before relying on valuation. <script>alert("escaped")</script>'
            page.locator('#note').fill(note)
            expect(page.locator('#saved')).to_contain_text('Saved in this browser')
            page.reload();expect(page.locator('#status')).to_contain_text('Saved review recovered')
            page.locator('#workbook').set_input_files(ROOT/'fixtures/Loan.xlsx')
            expect(page.locator('#status')).to_contain_text('hash mismatch')
            page.locator('#workbook').set_input_files(ROOT/'fixtures/Valuation.xlsx')
            expect(page.locator('#workspace')).to_be_visible();expect(page.locator('#note')).to_have_value(note)
            expect(page.locator('#detail')).to_contain_text("'Financial Model'!D263")
            with page.expect_download() as download:page.locator('#json').click()
            project=Path(tmp)/'project.json';download.value.save_as(project)
            data=json.loads(project.read_text());assert data['state']['notes']["'Financial Model'!D263"]==note
            page.locator('#reset').click();page.locator('#project').set_input_files(project)
            expect(page.locator('#status')).to_contain_text('Reconnect')
            page.locator('#workbook').set_input_files(ROOT/'fixtures/Valuation.xlsx')
            expect(page.locator('#workspace')).to_be_visible()
            expect(page.locator('#status')).to_contain_text('Workbook connected')
            expect(page.locator('#note')).to_have_value(note)
            page.locator('#transitive').check()
            page.screenshot(path=str(ROOT/'results/browser.png'),full_page=True)
            with page.expect_download() as download:page.locator('#html').click()
            report=ROOT/'results/sample-report.html';download.value.save_as(report)
            # Standalone reopening with the browser context offline.
            page.context.set_offline(True);page.goto(report.as_uri());expect(page.locator('h1')).to_contain_text('offline review')
            expect(page.get_by_role('cell',name=note,exact=True)).to_be_visible()
            assert page.locator('script').count()==0
            assert data['model']['source']['sha256'] in page.locator('body').inner_text()
            page.context.set_offline(False);page.goto(base);page.locator('#reset').click()
            for name,coverage in [('Loan.xlsx','96 supported'),('CashFlowCompany.xlsx','4 supported')]:
                page.get_by_role('button',name={'Loan.xlsx':'Loan repayments','CashFlowCompany.xlsx':'Company cash flow'}[name],exact=True).click()
                expect(page.locator('#coverage')).to_contain_text(coverage)
                expect(page.locator('#traceStatus')).to_contain_text('Complete within')
                page.locator('#reset').click()
            assert not errors,errors
            browser.close()
        assert before=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'fixtures').glob('*.xlsx')}
        result={'browser':'Chromium via Playwright 1.55.0','checks':['real workbook file import','cross-sheet direct and transitive tracing','dependent navigation','incomplete coverage label','annotation','reload recovery','wrong-hash rejection','matching-hash reconnection','JSON export/import','offline HTML reopening with escaped note','all three real demo buttons','source bytes unchanged'],'passed':True}
        (ROOT/'results/browser.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
    finally:server.terminate();server.wait(timeout=10)
if __name__=='__main__':main()
