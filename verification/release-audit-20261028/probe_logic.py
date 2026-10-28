"""Read-only application audit with synthetic fixtures in a NEW isolated directory.
Does not contact running service or external APIs. Never deletes existing data.
"""
import io
import json
import os
import secrets
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DATA = HERE / 'probe-data'
if DATA.exists():
    raise SystemExit('Refusing to reuse an existing probe database')
os.environ['DILIGENCE_DATA_DIR'] = str(DATA)
os.environ['DILIGENCE_SECRET'] = secrets.token_hex(32)
os.environ['DILIGENCE_ADMIN_PASSWORD'] = 'synthetic-audit-password'
os.environ['DEEPSEEK_API_KEY'] = ''
os.environ['DILIGENCE_MOCK_STEP_DELAY'] = '0'
sys.path.insert(0, str(ROOT / 'backend'))
from app import agents, scoring, subject, parsers
from app.main import app
from app.db import connect, now
from fastapi.testclient import TestClient
from pypdf import PdfWriter
import docx

results = {}
rubric = scoring.load_rubric()
results['rubric_sum'] = {'declared_total': rubric['total'], 'sum_dimensions': sum(d['points'] for d in rubric['dimensions'])}
base = dict(analyzed=True, board='all', findings=[], external_findings=[], external_present=False,
            required_materials=[], present_materials=[], missing_count=10,
            versions={'groups': 0, 'versions': 0}, qc=None)
s = scoring.score_project(rubric, **base)
results['missing_boards_score'] = {d['id']: {'earned': d['earned'], 'applicable': d['applicable']} for d in s['dimensions']}
ext = scoring.score_project(rubric, **{**base, 'external_present': True})
results['search_only_external_score'] = next(d for d in ext['dimensions'] if d['id'] == 'D')['items'][0]

rules = agents.load_rules('asset')
f = {'code':'AST-01','title':'synthetic','risk_level':'low','rule_id':'AST-01','rule_ref':None,
     'citations':[{'document_id':1,'filename':'synthetic.txt','page':999,'quote':'exact phrase'}]}
results['wrong_page_qc'] = agents.qc({}, [f], [{'id':1,'text':'[[PAGE 1]]\nexact phrase'}], rules)
fixture = [{'field':'出租方','value':'虚构房东甲','document_id':1,'filename':'synthetic.txt','page':1,'quote':'出租方：虚构房东甲'}]
lease = agents.analyze({'board':'asset','subject_name':'虚构租户乙'}, {'items':fixture,'conflicts':[]}, rules)
results['normal_different_lessor'] = [x['title'] for x in lease if x['code']=='AST-04']
names = ' '.join(k for typ, _ in agents.BOARD_REQUIRED['asset'] for k in agents.MATERIAL_KEYWORDS[typ][:1])
spec = agents.build_task_spec({'board':'asset'}, [], rules)
results['empty_body_filename_materials'] = agents.check_missing(spec, [{'filename':names+'.pdf','text':'','status':'needs_ocr'}])

HERE.mkdir(exist_ok=True)
pdf = HERE / 'synthetic-blank-10-pages.pdf'
w = PdfWriter()
for _ in range(10): w.add_blank_page(width=100, height=100)
w.write(str(pdf))
body, pages, status = parsers.parse_pdf(pdf)
results['blank_pdf'] = {'pages':pages,'status':status,'non_marker_text':__import__('re').sub(r'\[\[PAGE \d+\]\]','',body).strip()}
word = HERE / 'synthetic-explicit-pagebreak.docx'
d = docx.Document(); d.add_paragraph('Synthetic page one content'); d.add_page_break(); d.add_paragraph('Synthetic page two content'); d.save(word)
results['docx_pages'] = {'explicit_page_breaks':1,'parser_pages':parsers.parse_docx(word)[1]}

captured = {}
old_run = agents._run_json
def capture(system, user, cfg=None):
    captured['tail_present'] = 'SYNTHETIC_END_MARKER' in user
    return {'items':[]}
agents._run_json = capture
agents._llm_extract({'id':1,'filename':'long.txt','text':'A'*12001+'SYNTHETIC_END_MARKER'}, {'board':'asset','checks':[]})
agents._run_json = old_run
results['long_document_truncation'] = captured

with TestClient(app) as c:
    c.post('/api/auth/login', json={'email':'admin','password':'synthetic-audit-password'}).raise_for_status()
    pid = c.post('/api/projects', json={'title':'SYNTHETIC audit fixture','subject_name':'虚构审查主体','board':'all','is_demo':True}).json()['id']
    with connect() as conn:
        conn.execute("UPDATE projects SET status='done' WHERE id=?", (pid,))
        p = dict(conn.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone())
        subj = subject.score_subject(conn, p['subject_name'], [p])
    results['all_project_subject'] = {d['id']: d['applicable'] for d in subj['dimensions']}
    before = c.get(f'/api/projects/{pid}').json()['project']['status']
    up = c.post(f'/api/projects/{pid}/documents', files={'files':('synthetic.txt',b'Synthetic evidence content only','text/plain')})
    after = c.get(f'/api/projects/{pid}').json()['project']['status']
    results['upload_after_done'] = {'before':before,'upload_status':up.status_code,'after':after}
    groups = c.get(f'/api/projects/{pid}/versions').json()['groups']
    with connect() as conn: conn.execute("UPDATE projects SET status='running' WHERE id=?",(pid,))
    version = c.post(f'/api/projects/{pid}/versions', data={'group_id':groups[0]['id']},files={'file':('new.txt',b'Synthetic changed evidence','text/plain')})
    results['version_while_running'] = {'http_status':version.status_code}
    with connect() as conn:
        rid=conn.execute('INSERT INTO review_requests(project_id,triggers,status,created_at) VALUES (?,?,?,?)',
            (pid,json.dumps([{'code':'A4','detail':'synthetic blocked evidence'}]),'pending',now())).lastrowid
    approval=c.post(f'/api/reviews/{rid}/decision',json={'decision':'approved','comment':'synthetic probe'})
    results['approve_blocker_without_resolution'] = {'http_status':approval.status_code,'result':approval.json()}
    c.post('/api/auth/register',json={'email':'synthetic@example.invalid','password':'synthetic-old'}).raise_for_status()
    old_cookie=c.cookies.get('diligence_sid')
    c.post('/api/auth/password',json={'old_password':'synthetic-old','new_password':'synthetic-new'}).raise_for_status()
    c.cookies.clear(); c.cookies.set('diligence_sid',old_cookie)
    results['old_session_after_password_change']={'http_status':c.get('/api/auth/me').status_code}

out = HERE / 'probe-results.json'
out.write_text(json.dumps({'fixture_notice':'All identities, files, inputs and states are synthetic test fixtures, not real business facts.','results':results},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(results,ensure_ascii=False,indent=2))
