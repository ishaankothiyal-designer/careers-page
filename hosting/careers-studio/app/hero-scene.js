'use strict';

// Each layer follows document scroll directly; one render per animation frame.
(() => {
  const scenes = [...document.querySelectorAll('[data-parallax-hero]')];
  if (!scenes.length) return;
  const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
  let frame = 0;
  let geometry = [];

  function measure() {
    geometry = scenes.map(scene => {
      const rect = scene.getBoundingClientRect();
      const cloud = scene.querySelector('[data-hero-cloud="left"]');
      return {
        scene, top: rect.top + window.scrollY, height: rect.height,
        distance: (rect.width + (cloud?.offsetWidth || rect.width * .28)) * .6
      };
    });
    schedule();
  }

  function render() {
    frame = 0;
    const scroll = window.scrollY;
    const viewport = window.innerHeight;
    for (const {scene, top, height, distance} of geometry) {
      if (preference.matches) {
        scene.style.removeProperty('--hero-background-offset');
        scene.style.removeProperty('--hero-cloud-left');
        scene.style.removeProperty('--hero-cloud-right');
        continue;
      }
      if (top - scroll > viewport || top + height - scroll < 0) continue;
      const progress = Math.max(0, Math.min(1, (scroll - top) / Math.max(1, height * .8)));
      // Continuous ease at the start and end, with no time-based catch-up or snapping.
      const travel = (1 - Math.cos(progress * Math.PI)) * .5 * distance;
      scene.style.setProperty('--hero-background-offset', scroll + 'px');
      scene.style.setProperty('--hero-cloud-left', -travel + 'px');
      scene.style.setProperty('--hero-cloud-right', travel + 'px');
    }
  }

  function schedule() {
    if (!frame) frame = window.requestAnimationFrame(render);
  }

  window.addEventListener('scroll', schedule, {passive: true});
  window.addEventListener('resize', measure, {passive: true});
  window.addEventListener('pageshow', measure);
  preference.addEventListener('change', schedule);
  measure();
})();
