// Presentation only. The case viewer retains ownership of all evidence/state.
const motion = matchMedia('(prefers-reduced-motion: reduce)');
if (!motion.matches && 'IntersectionObserver' in window) {
  const reveal = new IntersectionObserver((entries) => {
    for (const entry of entries) if (entry.isIntersecting) {
      entry.target.classList.add('is-visible');
      reveal.unobserve(entry.target);
    }
  }, { threshold: 0.08 });
  document.querySelectorAll('.page-section > .section-heading, .trial-steps, .detector-explain, .project-film').forEach(el => {
    el.classList.add('will-reveal');
    reveal.observe(el);
  });
  motion.addEventListener('change', () => {
    if (motion.matches) {
      reveal.disconnect();
      document.querySelectorAll('.will-reveal').forEach(el => el.classList.add('is-visible'));
    }
  });
}
if ('IntersectionObserver' in window) {
  const links = [...document.querySelectorAll('.nav-links a')];
  const navigation = new IntersectionObserver((entries) => {
    for (const entry of entries) if (entry.isIntersecting) {
      for (const link of links) {
        if (link.hash === '#' + entry.target.id) link.setAttribute('aria-current', 'location');
        else link.removeAttribute('aria-current');
      }
    }
  }, { rootMargin: '-10% 0px -60% 0px', threshold: 0 });
  for (const link of links) {
    const target = document.querySelector(link.hash);
    if (target) navigation.observe(target);
  }
  const hero = document.querySelector('.landing-hero');
  if (hero) navigation.observe(hero);
}
