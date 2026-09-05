const body = document.body;
const header = document.querySelector('#siteHeader');
const progress = document.querySelector('.progress');
const backTop = document.querySelector('.back-top');
const drawer = document.querySelector('.mobile-drawer');
const menuButton = document.querySelector('.menu-toggle');
const search = document.querySelector('.search-overlay');

const setPanel = (panel, open) => {
  panel?.classList.toggle('open', open);
  panel?.setAttribute('aria-hidden', String(!open));
  body.classList.toggle('locked', open);
};

menuButton?.addEventListener('click', () => {
  setPanel(drawer, true);
  menuButton.setAttribute('aria-expanded', 'true');
});
document.querySelector('.drawer-close')?.addEventListener('click', () => {
  setPanel(drawer, false);
  menuButton?.setAttribute('aria-expanded', 'false');
});
document.querySelector('.search-toggle')?.addEventListener('click', () => {
  setPanel(search, true);
  setTimeout(() => document.querySelector('#global-search')?.focus(), 100);
});
document.querySelector('.search-close')?.addEventListener('click', () => setPanel(search, false));
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') {
    setPanel(drawer, false);
    setPanel(search, false);
  }
});

const onScroll = () => {
  const top = window.scrollY;
  const max = document.documentElement.scrollHeight - innerHeight;
  if (progress) progress.style.width = `${max ? (top / max) * 100 : 0}%`;
  header?.classList.toggle('scrolled', top > 40);
  backTop?.classList.toggle('show', top > 700);
  if (!matchMedia('(prefers-reduced-motion: reduce)').matches && innerWidth > 780) {
    document.querySelectorAll('[data-parallax]').forEach(section => {
      const rect = section.getBoundingClientRect();
      section.style.setProperty('--parallax', `${rect.top * -0.08}px`);
    });
  }
};
addEventListener('scroll', onScroll, { passive: true });
onScroll();
backTop?.addEventListener('click', () => scrollTo({ top: 0, behavior: 'smooth' }));

const observer = new IntersectionObserver(entries => {
  entries.forEach(entry => entry.target.classList.toggle('visible', entry.isIntersecting));
}, { threshold: 0.08 });
document.querySelectorAll('.reveal').forEach(element => observer.observe(element));

const filterButton = document.querySelector('.filter-toggle');
const filters = document.querySelector('.filters');
filterButton?.addEventListener('click', () => {
  filters?.classList.toggle('open');
  body.classList.toggle('locked');
});

document.querySelectorAll('.flash button').forEach(button => button.addEventListener('click', () => button.parentElement.remove()));
setTimeout(() => document.querySelectorAll('.flash').forEach(item => item.remove()), 6000);

if (matchMedia('(pointer:fine)').matches && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
  const cursor = document.createElement('div');
  cursor.className = 'custom-cursor';
  document.body.appendChild(cursor);
  addEventListener('mousemove', event => cursor.style.transform = `translate(${event.clientX}px,${event.clientY}px)`);
  document.querySelectorAll('a,button,input,select').forEach(item => {
    item.addEventListener('mouseenter', () => cursor.classList.add('active'));
    item.addEventListener('mouseleave', () => cursor.classList.remove('active'));
  });
}

