"""Geometry checks for the staged hero controller; artwork is not simulated."""
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
fragment=(ROOT/'design/nav-hero-fragment.html').read_text()
# The fixture tests layer movement only, without missing or substituted image assets.
import re
fragment=re.sub(r'<img\b[^>]*>','',fragment)
styles='\n'.join((ROOT/'app'/name).read_text() for name in ('tokens.css','base.css','public.css','hero-scene.css'))
controller=(ROOT/'app/hero-scene.js').read_text()
html='<html><head><base href="http://hero.test/"><style>'+styles+'\nbody{margin:0}.test-tail{height:2500px}</style></head><body>'+fragment+'<div class="test-tail"></div></body></html>'
def settle(page): page.evaluate('() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))')
def geometry(page):
 return page.evaluate('''() => Object.fromEntries(['background','cloud-left','cloud-right','content','iceberg'].map(name=>{const r=document.querySelector('.hero-scene-'+name).getBoundingClientRect();return [name,{x:r.x,y:r.y,width:r.width,height:r.height}]}))''')
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':1728,'height':1000})
 page.route('http://hero.test/fonts/**',lambda route:route.fulfill(path=str(ROOT/'app/fonts'/route.request.url.rsplit('/',1)[-1])))
 page.set_content(html);page.evaluate('document.fonts.ready');page.add_script_tag(content=controller);settle(page)
 start=geometry(page)
 page.evaluate('scrollTo({top:200,behavior:"instant"})');settle(page);scrolled=geometry(page)
 assert abs(scrolled['background']['y']-start['background']['y'])<1,'Background moved in viewport'
 for layer in ('content','iceberg'):
  assert abs((scrolled[layer]['y']-start[layer]['y'])+200)<1,layer+' does not scroll with document'
 assert scrolled['cloud-left']['x']<start['cloud-left']['x'],'Left cloud does not move left'
 assert scrolled['cloud-right']['x']>start['cloud-right']['x'],'Right cloud does not move right'
 page.evaluate('scrollTo({top:201,behavior:"instant"})');settle(page);next_frame=geometry(page)
 assert 0<scrolled['cloud-left']['x']-next_frame['cloud-left']['x']<5,'Cloud motion snaps on a one-pixel scroll'
 page.evaluate('scrollTo({top:0,behavior:"instant"})');settle(page);restored=geometry(page)
 assert abs(restored['cloud-left']['x']-start['cloud-left']['x'])<1,'Reverse scroll does not restore clouds'
 for width in (320,375,768,1440,1728):
  page.set_viewport_size({'width':width,'height':1000});settle(page)
  assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),'Hero overflows at '+str(width)
 page.emulate_media(reduced_motion='reduce');settle(page)
 page.evaluate('scrollTo({top:200,behavior:"instant"})');settle(page)
 assert page.locator('.hero-scene-cloud-left').evaluate('el=>getComputedStyle(el).transform')=='none','Reduced-motion cloud transform active'
 assert page.locator('.hero-scene-background').evaluate('el=>getComputedStyle(el).transform')=='none','Reduced-motion background transform active'
 browser.close()
print('PASS fixed background, document-flow foreground, outward clouds, one-pixel continuity, reverse scroll, five widths, reduced motion. Artwork verification pending original assets.')
