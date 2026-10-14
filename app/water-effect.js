'use strict';
// Native SVG distortion: no controls, dependencies or frame-by-frame JS loop.
(() => {
  const svg = document.querySelector('[data-water-effect]');
  const stage = document.querySelector('.underwater-stage');
  if (!svg || !stage || !svg.pauseAnimations) return;
  const preference = matchMedia('(prefers-reduced-motion: reduce)');
  let visible = false;
  function sync() {
    if (visible && !document.hidden && !preference.matches) svg.unpauseAnimations();
    else svg.pauseAnimations();
  }
  svg.pauseAnimations();
  const observer = new IntersectionObserver(entries => {
    visible = entries.some(entry => entry.isIntersecting);
    sync();
  });
  observer.observe(stage);
  preference.addEventListener('change', sync);
  document.addEventListener('visibilitychange', sync);
  addEventListener('pageshow', sync);
})();
