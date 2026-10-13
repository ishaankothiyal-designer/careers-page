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

def keyboard_focus_check(page):
    visible = page.evaluate('''() => {
        const active = document.activeElement;
        if (active === document.body) return true;
        const style = getComputedStyle(active);
        return active.matches(':focus-visible') &&
            ((style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) > 0) || style.boxShadow !== 'none');
    }''')
    check(visible, 'Keyboard focus has no visible indicator')

def product_copy_check(page, surface):
    annotations = page.locator('.demo-banner:visible, .draft-note:visible, .jobs-notice:visible, .access-help:visible')
    check(annotations.count()==0, f'{surface} exposes editorial annotations')
    visible_text = page.locator('body').inner_text().lower()
    for phrase in ('working prototype','internal prototype','demo opportunity','demo role','demo vacancies','draft culture content','design review','approval pending','policy confirmation pending','use test details','demo admin'):
        check(phrase not in visible_text, f'{surface} exposes editorial copy: {phrase}')

def reveal_page(page):
    page.evaluate('''async () => { for(let y=0; y<document.documentElement.scrollHeight; y+=600){window.scrollTo({top:y,behavior:'instant'}); await new Promise(r=>setTimeout(r,70));} window.scrollTo({top:0,behavior:'instant'}); history.replaceState(null,'',location.pathname+location.search); }''')
    page.wait_for_timeout(700)


def geography_checks(browser, errors, screenshots):
    seeded = Server(seed=True)
    try:
        context = browser.new_context(viewport={'width':1280,'height':900})
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(seeded.base, wait_until='networkidle')
        page.wait_for_function("() => document.querySelector('#job-status').textContent === '6 of 120 matching roles'")
        check(page.locator('#job-list .job-row').count()==6,'Homepage should preview six roles')
        check(page.evaluate("document.querySelector('#jobs').previousElementSibling.classList.contains('operating') && document.querySelector('#jobs').nextElementSibling.id === 'builders'"),'Homepage roles are not between the operating introduction and builders')
        page.locator('#job-country').select_option('India')
        page.locator('#job-state').select_option('Maharashtra')
        page.wait_for_function("() => document.querySelector('#job-list').getAttribute('aria-busy') === 'false'")
        transfer_city=page.locator('#job-location option').evaluate_all('(els) => els.map(el => el.value).filter(Boolean)')[0]
        page.locator('#job-location').select_option(transfer_city)
        page.wait_for_function("() => document.querySelector('#job-list').getAttribute('aria-busy') === 'false'")
        page.get_by_role('link',name='Show more listings').click()
        page.wait_for_url('**/jobs?*')
        page.locator('#job-list .job-row').first.wait_for()
        check(page.locator('#job-country').input_value()=='India','Listing navigation lost selected country')
        check(page.locator('#job-state').input_value()=='Maharashtra','Listing navigation lost selected state')
        check(page.locator('#job-location').input_value()==transfer_city,'Listing navigation lost selected city')
        check(all(transfer_city in text and 'Maharashtra' in text for text in page.locator('#job-list .job-row').all_text_contents()),'Transferred filters do not constrain listing results')
        page.goto(seeded.base + '/jobs', wait_until='networkidle')
        page.wait_for_function("() => document.querySelector('#job-status').textContent === '12 of 120 matching roles'")
        product_copy_check(page, 'candidate careers page')
        check(page.locator('#job-list .job-row').count()==12,'Initial seed pagination does not show 12 roles')
        page.locator('#load-more-jobs').click()
        check(page.locator('#job-list .job-row').count()==24,'Load more did not expose next 12 roles')
        page.locator('#job-country').select_option('India')
        page.wait_for_function("() => document.querySelector('#job-status').textContent === '12 of 72 matching roles'")
        regions=page.locator('#job-state option').evaluate_all('(els) => els.map(el => el.value).filter(Boolean)')
        check(len(regions)==36,'India does not offer all 28 states and 8 union territories')
        page.locator('#job-state').select_option('Maharashtra')
        page.wait_for_function("() => document.querySelector('#job-list').getAttribute('aria-busy') === 'false'")
        check(page.locator('#job-list .job-row').count()>0,'Maharashtra selection yielded no roles')
        check(all('Maharashtra' in text and 'India' in text for text in page.locator('#job-list .job-row').all_text_contents()),'State filter shows roles outside selected geography')
        cities=page.locator('#job-location option').evaluate_all('(els) => els.map(el => el.value).filter(Boolean)')
        check(bool(cities),'State did not cascade into city choices')
        page.locator('#job-location').select_option(cities[0])
        page.wait_for_function("() => document.querySelector('#job-list').getAttribute('aria-busy') === 'false'")
        check(page.locator('#job-list .job-row').count()>0,'City selection yielded no roles')
        check(all(cities[0] in text for text in page.locator('#job-list .job-row').all_text_contents()),'City filter shows unrelated roles')
        page.locator('#job-filters').scroll_into_view_if_needed()
        page.screenshot(path=str(screenshots/'role-filters.png'),full_page=False)
        page.locator('#job-country').select_option('Australia')
        page.wait_for_function("() => document.querySelector('#job-status').textContent === '12 of 24 matching roles'")
        check(page.locator('#job-state').input_value()=='' and page.locator('#job-location').input_value()=='','Country change did not clear dependent state/city selections')
        check(page.locator('#job-state option').count()==9,'Australia region choices incorrect')
        page.locator('#job-country').select_option('UAE')
        page.wait_for_function("() => document.querySelector('#job-status').textContent === '12 of 24 matching roles'")
        check(page.locator('#job-state option').count()==8,'UAE emirate choices incorrect')
        check(page.locator('#job-state-label').inner_text()=='Emirate','UAE state label should say Emirate')
        page.locator('#job-country').select_option('')
        page.wait_for_function("() => document.querySelector('#job-status').textContent === '12 of 120 matching roles'")
        for width in WIDTHS: no_horizontal_overflow(page,width,'dedicated listings page')
        page.set_viewport_size({'width':1440,'height':1000})
        reveal_page(page)
        page.screenshot(path=str(screenshots/'listings-desktop.png'),full_page=True)
        page.set_viewport_size({'width':375,'height':812})
        page.screenshot(path=str(screenshots/'listings-mobile.png'),full_page=True)
        page.goto(seeded.base,wait_until='networkidle')
        page.wait_for_function("() => document.querySelector('#job-status').textContent === '6 of 120 matching roles'")
        for width in WIDTHS: no_horizontal_overflow(page,width,'homepage role preview')
        page.set_viewport_size({'width':1440,'height':1000})
        reveal_page(page)
        page.screenshot(path=str(screenshots/'candidate-desktop.png'),full_page=True)
        page.screenshot(path=str(screenshots/'candidate-first-screen.png'),full_page=False)
        page.set_viewport_size({'width':375,'height':812})
        reveal_page(page)
        page.screenshot(path=str(screenshots/'candidate-mobile.png'),full_page=True)
        page.screenshot(path=str(screenshots/'candidate-mobile-first-screen.png'),full_page=False)
        context.close()
    finally: seeded.close()

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
            product_copy_check(admin, 'admin sign-in')
            # These controls use actual visible labels, so broken labeling fails the test too.
            admin.get_by_label('Email', exact=True).fill(server.email)
            admin.get_by_label('Password', exact=True).fill(server.password)
            admin.get_by_role('button',name='Sign in',exact=True).click()
            admin.locator('#new-job').wait_for()
            product_copy_check(admin, 'admin workspace')
            admin.locator('#new-job').click()
            admin.get_by_role('dialog').wait_for()
            admin.keyboard.press('Escape')
            check(admin.locator('#new-job').evaluate('(el) => el === document.activeElement'), 'Admin job dialog close did not restore trigger focus')
            admin.locator('#new-job').click()
            title='Browser journey builder'
            fields={'Job title':title,'Team':'Engineering','Location':'Gurugram','State / region':'Haryana','About the opportunity':'Build thoughtful tools with a collaborative team.','What they will build':'Own and deliver one useful product.','What they will bring':'Demonstrated ability to build useful software.','First 90 days':'Ship an improvement and learn from users.'}
            admin.get_by_label('Country').select_option('India')
            for label,value in fields.items(): admin.get_by_label(label,exact=True).fill(value)
            admin.get_by_label('Work mode').select_option('Hybrid')
            admin.get_by_label('Employment type').select_option('Full-time')
            for width in WIDTHS:
                no_horizontal_overflow(admin,width,'admin editor')
                check(admin.locator('#job-dialog').evaluate('(el) => el.scrollWidth <= el.clientWidth + 1'),'Admin editor content overflows')
            admin.set_viewport_size({'width':1280,'height':900})
            admin.locator('#job-dialog').evaluate('(el) => {el.scrollTop = 0;}')
            admin.screenshot(path=str(screenshots/'admin-editor.png'),full_page=True)
            admin.get_by_role('button',name='Save draft',exact=True).click()
            role_card=admin.locator('[data-job-id]').filter(has_text=title)
            role_card.wait_for()
            role_card.get_by_role('button',name='Publish job',exact=True).click()
            candidate.goto(server.base + '/jobs',wait_until='networkidle')
            candidate.locator('#job-search').fill(title)
            candidate.locator('.job-row').filter(has_text=title).click()
            dialog=candidate.get_by_role('dialog')
            dialog.wait_for()
            candidate.locator('#role-content').wait_for(state='visible')
            product_copy_check(candidate, 'candidate role dialog')
            for width in WIDTHS:
                no_horizontal_overflow(candidate,width,'candidate application dialog')
                check(dialog.evaluate('(el) => el.scrollWidth <= el.clientWidth + 1'),'Candidate dialog content overflows')
            candidate.set_viewport_size({'width':1280,'height':900})
            for _ in range(15):
                candidate.keyboard.press('Tab')
                check(candidate.evaluate('document.activeElement === document.body || document.querySelector("dialog[open]").contains(document.activeElement)'), 'Modal keyboard focus escaped')
                keyboard_focus_check(candidate)
            candidate.keyboard.press('Escape')
            dialog.wait_for(state='hidden')
            check(candidate.locator('.job-row').filter(has_text=title).evaluate('(el) => el === document.activeElement'), 'Dialog close did not restore trigger focus')
            candidate.locator('.job-row').filter(has_text=title).click()
            candidate.locator('#role-content').wait_for(state='visible')
            application_requests = []
            candidate.on('request', lambda request: application_requests.append(request) if request.method == 'POST' and request.url.endswith('/applications') else None)
            candidate.get_by_role('button',name='Send application').click()
            check(candidate.locator('#applicant-name').evaluate('(el)=>el.validity.valueMissing && el === document.activeElement'),'Empty application does not identify and focus the required name field')
            check(not application_requests,'Invalid form sent an application request')
            candidate.get_by_role('textbox',name='Name',exact=True).fill('Browser Applicant')
            candidate.get_by_role('textbox',name='Email',exact=True).fill('invalid-email')
            candidate.get_by_role('button',name='Send application').click()
            check(candidate.locator('#applicant-email').evaluate('(el)=>el.validity.typeMismatch && el === document.activeElement'),'Invalid email does not identify and focus the email field')
            check(not application_requests,'Invalid email sent an application request')
            candidate.get_by_role('textbox',name='Email',exact=True).fill('browser@example.test')
            candidate.get_by_label('Portfolio or work link (optional)',exact=True).fill('https://example.test/project')
            candidate.get_by_role('textbox',name='Tell us about something you built',exact=True).fill('A scheduling tool my team used every week.')
            pending_submissions = []
            candidate.route('**/api/jobs/*/applications',lambda route:pending_submissions.append(route))
            candidate.get_by_role('button',name='Send application').click()
            candidate.wait_for_function('() => document.querySelector("#submit-application").disabled')
            check(candidate.locator('#close-dialog').is_disabled(),'Role close remains enabled while the application is saving')
            check(len(pending_submissions)==1,'Submitting should create exactly one pending application request')
            pending_submissions[0].continue_()
            candidate.get_by_text('Something new starts here.',exact=True).wait_for()
            candidate.unroute('**/api/jobs/*/applications')
            check(candidate.get_by_text('Something new starts here.',exact=True).is_visible(), 'Candidate did not receive a success receipt')
            product_copy_check(candidate, 'candidate submission receipt')
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
            candidate.goto(server.base + '/jobs',wait_until='networkidle')
            candidate.locator('#job-search').fill(title)
            check(candidate.locator('.job-row').filter(has_text=title).count()==0, 'Closed job still visible to candidate')
            # Read the independently persisted server result, in addition to the UI feedback.
            admin_state=admin.evaluate("async () => (await fetch('/api/admin/applications')).json()")
            application=next(row for row in admin_state['applications'] if row['email']=='browser@example.test')
            check(application['status']=='reviewing','Admin review did not persist')
            for width in WIDTHS:
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
            reduced_page.goto(server.base + '/jobs',wait_until='networkidle')
            check(reduced_page.evaluate('matchMedia("(prefers-reduced-motion: reduce)").matches'),'Reduced motion not enabled')
            check(reduced_page.locator('#job-search').is_visible(),'Reduced-motion candidate flow unusable')
            geography_checks(browser,errors,screenshots)
            check(not errors,'JavaScript errors: '+json.dumps(errors))
            browser.close()
        print('PASS: admin draft → publish → candidate details → application receipt → admin review → closed role.')
        print('PASS: separate sessions, keyboard focus trapping/Escape/restoration, persisted review, 35 responsive surface checks, reduced-motion flow, visible keyboard focus, native form errors, pending-submit disabled controls, zero JavaScript errors.')
        print('PASS: 120 seeded roles, load-more pagination, country/state/city cascade across India/Australia/UAE, dependent selection reset, homepage six-role preview and filter-preserving listings navigation.')
        print('Screenshots: tests/artifacts/candidate-desktop.png, candidate-mobile.png, listings-desktop.png, listings-mobile.png, admin-desktop.png')
    finally: server.close()

if __name__=='__main__': main()
