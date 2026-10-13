'use strict';
// One scroll timeline shared by both messages; native sticky layout pins the art.
(() => {
  const scene = document.querySelector('[data-underwater-scene]');
  if (!scene) return;
  const preference = matchMedia('(prefers-reduced-motion: reduce)');
  let frame = 0, top = 0, travel = 1;
  const smooth = (value, start, end) => {
    const t = Math.max(0, Math.min(1, (value - start) / (end - start)));
    return t * t * (3 - 2 * t);
  };
  function measure() {
    scene.classList.toggle('motion-enabled', !preference.matches);
    top = scene.getBoundingClientRect().top + scrollY;
    travel = Math.max(1, scene.offsetHeight - scene.querySelector('.underwater-stage').offsetHeight);
    schedule();
  }
  function render() {
    frame = 0;
    if (preference.matches) return;
    const progress = Math.max(0, Math.min(1, (scrollY - top) / travel));
    const out = smooth(progress, .25, .5);
    const incoming = smooth(progress, .45, .7);
    scene.style.setProperty('--underwater-first-opacity', String(1 - out));
    scene.style.setProperty('--underwater-first-y', `${-out * 80}px`);
    scene.style.setProperty('--underwater-second-opacity', String(incoming));
    scene.style.setProperty('--underwater-second-y', `${(1 - incoming) * 80}px`);
    scene.style.setProperty('--underwater-tint-opacity', String(1 - smooth(progress, .3, .75)));
  }
  function schedule() { if (!frame) frame = requestAnimationFrame(render); }
  addEventListener('scroll', schedule, {passive:true});
  addEventListener('resize', measure, {passive:true});
  addEventListener('pageshow', measure);
  preference.addEventListener('change', measure);
  measure();
})();
