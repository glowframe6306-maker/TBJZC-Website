// Minimal responsive navigation for the school-style page
(function(){
  const toggle = document.querySelector('.nav-toggle');
  const nav = document.querySelector('.site-nav');
  if (!toggle || !nav) return;

  toggle.addEventListener('click', () => {
    const isOpen = nav.classList.toggle('open');
    toggle.setAttribute('aria-expanded', isOpen);
    if (isOpen) {
      nav.style.display = 'flex';
    } else {
      nav.style.display = '';
    }
  });

  window.addEventListener('resize', () => {
    if (window.innerWidth > 760) {
      nav.classList.remove('open');
      nav.style.display = 'flex';
      toggle.setAttribute('aria-expanded', 'false');
    } else if (!nav.classList.contains('open')) {
      nav.style.display = 'none';
    }
  });
})();