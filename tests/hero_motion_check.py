"""Check staged motion geometry and the real homepage's original hero artwork.
Run: python tests/hero_motion_check.py
Uses an isolated temporary server/database and installed Chromium.
"""
from pathlib import Path
import os
import re
import shutil
from playwright.sync_api import sync_playwright
from test_api import Server

ROOT = Path(__file__).resolve().parents[1]
WIDTHS = (320, 375, 414, 768, 1024, 1440, 1728)
ARTWORK = {'background': (1728,781), 'iceberg': (876,361), 'cloud-left': (488,315), 'cloud-right': (488,315)}

def check(value, message):
    if not value: raise AssertionError(message)

def settle(page):
    page.evaluate('() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))')

def scroll(page, value):
    page.evaluate('(y) => scrollTo({top:y,behavior:"instant"})', value)
    settle(page)

def geometry(page):
    return page.evaluate('''() => Object.fromEntries(['background','cloud-left','cloud-right','content','iceberg'].map(name=>{const r=document.querySelector('.hero-scene-'+name).getBoundingClientRect();return [name,{x:r.x,y:r.y,width:r.width,height:r.height}]}))''')

def motion_check(page, width, screenshot_dir=None):
    page.set_viewport_size({'width':width,'height':1000})
    scroll(page,0)
    start=geometry(page)
    background_image=page.locator('.hero-scene-mountains')
    initial_zoom=background_image.evaluate('(el)=>el.getBoundingClientRect().width') if background_image.count() else None
    check(not page.evaluate('document.documentElement.scrollWidth > innerWidth + 1'),f'Hero overflows at {width}px')
    scroll(page,200)
    moved=geometry(page)
    check(abs(moved['background']['y']-start['background']['y'])<1,f'Background moves in viewport at {width}px')
    check(abs((moved['content']['y']-start['content']['y'])+230)<1,f'Hero copy/button do not move slightly faster than document scroll at {width}px')
    check(abs((moved['iceberg']['y']-start['iceberg']['y'])+200)<1,f'Iceberg does not follow normal document scroll at {width}px')
    if initial_zoom:
        zoomed_in=background_image.evaluate('(el)=>el.getBoundingClientRect().width')
        check(zoomed_in>initial_zoom,f'Background does not gently zoom in at {width}px')
    check(moved['cloud-left']['x']<start['cloud-left']['x'],'Left cloud does not move outward')
    check(moved['cloud-right']['x']>start['cloud-right']['x'],'Right cloud does not move outward')
    scroll(page,201)
    adjacent=geometry(page)
    check(0<moved['cloud-left']['x']-adjacent['cloud-left']['x']<5,'Cloud motion snaps on a one-pixel scroll')
    height=page.locator('[data-parallax-hero]').evaluate('(el)=>el.getBoundingClientRect().height')
    scroll(page,height*.8)
    exited=geometry(page)
    check(exited['cloud-left']['x']+exited['cloud-left']['width']<=1,f'Left cloud remains inside viewport at 80% hero progress ({width}px)')
    check(exited['cloud-right']['x']>=width-1,f'Right cloud remains inside viewport at 80% hero progress ({width}px)')
    scroll(page,0)
    returned=geometry(page)
    if initial_zoom:
        check(abs(background_image.evaluate('(el)=>el.getBoundingClientRect().width')-initial_zoom)<1,f'Reverse scroll does not restore background zoom at {width}px')
    for name in ('background','cloud-left','cloud-right','content','iceberg'):
        check(abs(returned[name]['x']-start[name]['x'])<1 and abs(returned[name]['y']-start[name]['y'])<1,f'Reverse scroll fails to restore {name} at {width}px')
    if screenshot_dir and width in (375,1728):
        suffix='mobile' if width==375 else 'desktop'
        page.screenshot(path=str(screenshot_dir/f'hero-{suffix}.png'),full_page=False)
        scroll(page,200)
        page.screenshot(path=str(screenshot_dir/f'hero-{suffix}-scroll.png'),full_page=False)
        scroll(page,0)

def artwork_check(page):
    for slot, (width,height) in ARTWORK.items():
        locator=page.locator(f'.hero-scene-{slot} img')
        check(locator.count()==1,f'{slot} must contain one supplied image')
        metadata=locator.evaluate('''img=>{const rect=img.getBoundingClientRect(), style=getComputedStyle(img);return {complete:img.complete,width:img.naturalWidth,height:img.naturalHeight,src:new URL(img.currentSrc).pathname,boxWidth:rect.width,boxHeight:rect.height,fit:style.objectFit};}''')
        check(metadata['complete'] and metadata['width']==width and metadata['height']==height,f'{slot} failed to load its original {width}×{height} export')
        check(metadata['src']==f'/images/hero/{slot}.png',f'{slot} uses the wrong source asset')
        check(metadata['boxWidth']>0 and metadata['boxHeight']>0,f'{slot} has no rendered artwork area')
        # contain/cover preserve bitmap proportions within a responsive box.
        # Any other fit must itself match the original aspect ratio.
        check(metadata['fit'] in ('contain','cover') or abs(metadata['boxWidth']/metadata['boxHeight']-width/height)<.01,f'{slot} stretches its supplied artwork')
        if slot != 'background':
            check(metadata['fit']!='cover',f'{slot} crops the supplied foreground artwork')

def staged_check(browser):
    fragment=(ROOT/'design/nav-hero-fragment.html').read_text()
    fragment=re.sub(r'<img\b[^>]*>','',fragment)
    styles='\n'.join((ROOT/'app'/name).read_text() for name in ('tokens.css','base.css','public.css','hero-scene.css'))
    controller=(ROOT/'app/hero-scene.js').read_text()
    html='<html><head><base href="http://hero.test/"><style>'+styles+'\nbody{margin:0}.test-tail{height:2500px}</style></head><body>'+fragment+'<div class="test-tail"></div></body></html>'
    page=browser.new_page(viewport={'width':1728,'height':1000})
    page.route('http://hero.test/fonts/**',lambda route:route.fulfill(path=str(ROOT/'app/fonts'/route.request.url.rsplit('/',1)[-1])))
    page.set_content(html)
    page.evaluate('document.fonts.ready')
    page.add_script_tag(content=controller)
    settle(page)
    motion_check(page,1728)
    page.close()


def main():
    server=Server(seed=True)
    artifacts=ROOT/'tests/artifacts'
    artifacts.mkdir(exist_ok=True)
    errors=[]
    try:
        with sync_playwright() as playwright:
            executable=os.environ.get('CHROMIUM_EXECUTABLE_PATH') or shutil.which('chromium') or shutil.which('google-chrome')
            browser=playwright.chromium.launch(executable_path=executable,headless=True,args=['--no-sandbox'])
            staged_check(browser)
            context=browser.new_context(viewport={'width':1728,'height':1000})
            page=context.new_page()
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(server.base,wait_until='networkidle')
            page.evaluate('document.fonts.ready')
            for width in WIDTHS:
                motion_check(page,width,artifacts)
                artwork_check(page)
            check(page.locator('.hero-scene-nav').get_by_role('link',name='Open roles').get_attribute('href')=='/jobs','Header CTA does not open the listings page')
            page.emulate_media(reduced_motion='reduce')
            settle(page)
            scroll(page,200)
            for name in ('background','cloud-left','cloud-right','content','iceberg'):
                check(page.locator('.hero-scene-'+name).evaluate('(el)=>getComputedStyle(el).transform')=='none',f'Reduced-motion transform active on {name}')
            check(page.locator('.hero-scene-mountains').evaluate('(el)=>getComputedStyle(el).transform')=='none','Reduced-motion zoom active on background artwork')
            scroll(page,0)
            page.locator('.hero-scene-nav').get_by_role('link',name='Open roles').click()
            page.wait_for_url('**/jobs')
            page.locator('#job-list .job-row').first.wait_for()
            page.locator('#job-list .job-row').first.click()
            page.locator('#role-content').wait_for(state='visible')
            page.get_by_role('textbox',name='Name',exact=True).fill('Hero Flow Applicant')
            page.get_by_role('textbox',name='Email',exact=True).fill('hero-flow@example.test')
            page.get_by_role('textbox',name='Tell us about something you built',exact=True).fill('Built a tool that improved a team handoff.')
            page.get_by_role('button',name='Send application').click()
            page.get_by_text('Something new starts here.',exact=True).wait_for()
            check(bool(page.locator('#application-reference').inner_text()),'Header-to-listings application has no receipt reference')
            check(not errors,'JavaScript errors: '+repr(errors))
            browser.close()
        print('PASS: staged controller and real-page original assets/source slots/aspect preservation.')
        print('PASS: anchored background zoom-in, faster copy/button, normal iceberg scroll, outward cloud exit at 80%, one-pixel continuity, reverse, seven widths, reduced motion, zero JavaScript errors.')
        print('PASS: real header CTA → dedicated listings → role details → application receipt.')
        print('Screenshots: tests/artifacts/hero-{desktop,mobile}{,-scroll}.png')
    finally:server.close()

if __name__=='__main__':main()
