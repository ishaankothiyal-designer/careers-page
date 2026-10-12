"""Real Chromium checks for the admin-to-applicant journey.
Requires installed Python Playwright and Chromium. Run: python tests/browser_check.py
No external service, production database, or real user credentials are touched.
"""
from pathlib import Path
import json
import sys
import os
import shutil
from playwright.sync_api import sync_playwright
from test_api import Server

ROOT = Path(__file__).resolve().parents[1]
WIDTHS = (320, 375, 414, 768, 1024, 1280, 1440)

def check(condition, description):
    if not condition: raise AssertionError(description)

def no_horizontal_overflow(page, width, surface):
    page.set_viewport_size({'width': width, 'height': 900})
    page.wait_for_timeout(120)
    overflow = page.evaluate('document.documentElement.scrollWidth > window.innerWidth + 1')
    check(not overflow, f'{surface} horizontal overflow at {width}px')

def reveal_page(page):
    page.evaluate('''async () => { for(let y=0; y<document.documentElement.scrollHeight; y+=600){window.scrollTo({top:y,behavior:'instant'}); await new Promise(r=>setTimeout(r,70));} window.scrollTo({top:0,behavior:'instant'}); history.replaceState(null,'',location.pathname+location.search); }''')
    page.wait_for_timeout(700)

def main():
    server = Server()
    errors = []
    screenshots = ROOT / 'tests' / 'artifacts'
    screenshots.mkdir(exist_ok=True)
    try:
        with sync_playwright() as p:
            executable = os.environ.get('CHROMIUM_EXECUTABLE_PATH') or shutil.which('chromium') or shutil.which('google-chrome')
            browser = p.chromium.launch(executable_path=executable, headless=True, args=['--no-sandbox'])
            admin_context = browser.new_context(viewport={'width':1280,'height':900})
            candidate_context = browser.new_context(viewport={'width':1280,'height':900})
            admin = admin_context.new_page(); candidate = candidate_context.new_page()
            for page in (admin, candidate):
                page.on('pageerror', lambda error: errors.append(str(error)))
            admin.goto(server.base + '/admin', wait_until='networkidle')
            # These controls use actual visible labels, so broken labeling fails the test too.
            admin.get_by_label('Email', exact=True).fill(server.email)
            admin.get_by_label('Password', exact=True).fill(server.password)
            admin.get_by_role('button',name='Sign in',exact=True).click()
            admin.locator('#new-job').wait_for()
            admin.locator('#new-job').click()
            admin.get_by_role('dialog').wait_for()
            admin.keyboard.press('Escape')
            check(admin.locator('#new-job').evaluate('(el) => el === document.activeElement'), 'Admin job dialog close did not restore trigger focus')
            admin.locator('#new-job').click()
            title='Browser journey builder'
            fields={'Job title':title,'Team':'Engineering','Location':'Gurugram','Country':'India','About the opportunity':'Build thoughtful tools with a collaborative team.','What they will build':'Own and deliver one useful product.','What they will bring':'Demonstrated ability to build useful software.','First 90 days':'Ship an improvement and learn from users.'}
            for label,value in fields.items(): admin.get_by_label(label,exact=True).fill(value)
            admin.get_by_label('Work mode').select_option('Hybrid')
            admin.get_by_label('Employment type').select_option('Full-time')
            for width in WIDTHS:
                no_horizontal_overflow(admin,width,'admin editor')
                check(admin.locator('#job-dialog').evaluate('(el) => el.scrollWidth <= el.clientWidth + 1'),'Admin editor content overflows')
            admin.set_viewport_size({'width':1280,'height':900})
            admin.get_by_role('button',name='Save draft',exact=True).click()
            role_card=admin.locator('[data-job-id]').filter(has_text=title)
            role_card.wait_for()
            role_card.get_by_role('button',name='Publish job',exact=True).click()
            candidate.goto(server.base,wait_until='networkidle')
            candidate.locator('#job-search').fill(title)
            candidate.locator('.job-row').filter(has_text=title).click()
            dialog=candidate.get_by_role('dialog')
            dialog.wait_for()
            for width in WIDTHS:
                no_horizontal_overflow(candidate,width,'candidate application dialog')
                check(dialog.evaluate('(el) => el.scrollWidth <= el.clientWidth + 1'),'Candidate dialog content overflows')
            candidate.set_viewport_size({'width':1280,'height':900})
            for _ in range(15):
                candidate.keyboard.press('Tab')
                check(candidate.evaluate('document.activeElement === document.body || document.querySelector("dialog[open]").contains(document.activeElement)'), 'Modal keyboard focus escaped')
            candidate.keyboard.press('Escape')
            dialog.wait_for(state='hidden')
            check(candidate.locator('.job-row').filter(has_text=title).evaluate('(el) => el === document.activeElement'), 'Dialog close did not restore trigger focus')
            candidate.locator('.job-row').filter(has_text=title).click()
            candidate.locator('#applicant-name').focus()
            candidate.get_by_role('textbox',name='Name',exact=True).fill('Browser Applicant')
            candidate.get_by_role('textbox',name='Email',exact=True).fill('browser@example.test')
            candidate.get_by_label('Portfolio or work link (optional)',exact=True).fill('https://example.test/project')
            candidate.get_by_role('textbox',name='Tell us about something you built',exact=True).fill('A scheduling tool my team used every week.')
            candidate.get_by_role('button',name='Send demo application').click()
            candidate.get_by_text('Something new starts here.',exact=True).wait_for()
            check(candidate.get_by_text('Something new starts here.',exact=True).is_visible(), 'Candidate did not receive a success receipt')
            admin.locator('#applications-tab').click()
            admin.locator('.application-row').filter(has_text='Browser Applicant').get_by_role('button',name='Review application').click()
            admin.keyboard.press('Escape')
            review_trigger=admin.locator('.application-row').filter(has_text='Browser Applicant').get_by_role('button',name='Review application')
            check(review_trigger.evaluate('(el) => el === document.activeElement'), 'Admin review dialog close did not restore trigger focus')
            review_trigger.click()
            admin.get_by_label('Application status').select_option('reviewing')
            admin.get_by_label('Internal note',exact=True).fill('Reviewed portfolio and project evidence.')
            admin.get_by_role('button',name='Save review',exact=True).click()
            admin.locator('#jobs-tab').click()
            role_card=admin.locator('[data-job-id]').filter(has_text=title)
            role_card.get_by_role('button',name='Close posting',exact=True).click()
            candidate.goto(server.base,wait_until='networkidle')
            candidate.locator('#job-search').fill(title)
            check(candidate.locator('.job-row').filter(has_text=title).count()==0, 'Closed job still visible to candidate')
            # Read the independently persisted server result, in addition to the UI feedback.
            admin_state=admin.evaluate("async () => (await fetch('/api/admin/applications')).json()")
            application=next(row for row in admin_state['applications'] if row['email']=='browser@example.test')
            check(application['status']=='reviewing','Admin review did not persist')
            for width in WIDTHS:
                no_horizontal_overflow(candidate,width,'candidate')
                no_horizontal_overflow(admin,width,'admin')
            candidate.set_viewport_size({'width':1440,'height':1000})
            candidate.locator('#job-search').fill('')
            reveal_page(candidate)
            candidate.screenshot(path=str(screenshots/'candidate-desktop.png'),full_page=True)
            candidate.set_viewport_size({'width':375,'height':812})
            reveal_page(candidate)
            candidate.screenshot(path=str(screenshots/'candidate-mobile.png'),full_page=True)
            admin.set_viewport_size({'width':1280,'height':900})
            admin.screenshot(path=str(screenshots/'admin-desktop.png'),full_page=True)
            reduced=browser.new_context(reduced_motion='reduce')
            reduced_page=reduced.new_page()
            reduced_page.on('pageerror', lambda error: errors.append(str(error)))
            reduced_page.goto(server.base,wait_until='networkidle')
            check(reduced_page.evaluate('matchMedia("(prefers-reduced-motion: reduce)").matches'),'Reduced motion not enabled')
            check(reduced_page.locator('#job-search').is_visible(),'Reduced-motion candidate flow unusable')
            check(not errors,'JavaScript errors: '+json.dumps(errors))
            browser.close()
        print('PASS: admin draft → publish → candidate details → application receipt → admin review → closed role.')
        print('PASS: separate sessions, keyboard focus trapping/Escape/restoration, persisted review, 28 responsive surface checks, reduced-motion flow, zero JavaScript errors.')
        print('Screenshots: tests/artifacts/candidate-desktop.png, candidate-mobile.png, admin-desktop.png')
    finally: server.close()

if __name__=='__main__': main()
