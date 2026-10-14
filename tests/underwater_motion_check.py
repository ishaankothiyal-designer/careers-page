"""Check shared underwater scroll scene, reversible text motion and reduced-motion fallback."""
import sys,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_api import Server
from playwright.sync_api import sync_playwright
s=Server(seed=True)
try:
 with sync_playwright() as p:
  b=p.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox']);page=b.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.goto(s.base,wait_until='networkidle');page.evaluate('document.fonts.ready')
  for w in [320,375,414,768,1024,1440,1728]:
   page.set_viewport_size({'width':w,'height':900})
   assert page.locator('[data-underwater-scene]').count()==1
   assert page.locator('.underwater-art').count()==1
   top,travel=page.locator('.underwater').evaluate('(e)=>[e.getBoundingClientRect().top+scrollY,e.offsetHeight-e.querySelector(".underwater-stage").offsetHeight]')
   def state(t):
    page.evaluate('(y)=>scrollTo({top:y,behavior:"instant"})',top+travel*t);page.evaluate('()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');return page.evaluate('()=>[...document.querySelectorAll(".underwater-copy")].map(e=>({opacity:+getComputedStyle(e).opacity,y:e.getBoundingClientRect().y}))')
   a=state(0);mid=state(.4);z=state(1);rev=state(0)
   assert a[0]['opacity']==1 and a[1]['opacity']==0
   assert 0<mid[0]['opacity']<1 and mid[0]['y']<a[0]['y']
   assert z[0]['opacity']==0 and z[1]['opacity']==1
   assert abs(rev[0]['y']-a[0]['y'])<1
   assert page.locator('.underwater-stage').evaluate('(e)=>Math.abs(e.getBoundingClientRect().top)<2')
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
   assert page.locator('.underwater img').evaluate_all('(a)=>a.every(i=>i.complete&&i.naturalWidth>0)')
   if w in [375,1728]:
    state(0);page.screenshot(path=f'/workspace/careers-page-repo/tests/artifacts/underwater-motion-{w}-first.png');state(1);page.screenshot(path=f'/workspace/careers-page-repo/tests/artifacts/underwater-motion-{w}-second.png')
  page.emulate_media(reduced_motion='reduce');page.wait_for_function('()=>!document.querySelector(".underwater").classList.contains("motion-enabled")');page.evaluate('()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');assert not page.locator('.underwater').evaluate('(e)=>e.classList.contains("motion-enabled")');page.wait_for_function('()=>[...document.querySelectorAll(".underwater-copy")].every(e=>+getComputedStyle(e).opacity===1)')
  page.emulate_media(reduced_motion='no-preference');page.wait_for_function('()=>document.querySelector(".underwater").classList.contains("motion-enabled")');assert page.locator('.underwater').evaluate('(e)=>e.classList.contains("motion-enabled")')
  assert not errors
  print('PASS: one shared scene, both scroll-driven text phases, pinned artwork, reverse scroll, seven widths, loaded assets, live reduced-motion toggle, zero JS errors.')
  b.close()
finally:s.close()
