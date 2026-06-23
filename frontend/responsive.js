// responsive.js - minimal behavior: mobile nav toggle and reduced-motion friendly
(function(){
  const navToggle = document.querySelector('.nav-toggle');
  const nav = document.querySelector('.primary-nav');

  if (navToggle && nav) {
    navToggle.addEventListener('click', () => {
      const expanded = nav.getAttribute('data-open') === 'true';
      if (expanded) {
        nav.style.display = 'none';
        nav.setAttribute('data-open','false');
        navToggle.setAttribute('aria-expanded','false');
      } else {
        nav.style.display = 'flex';
        nav.style.flexDirection = 'column';
        nav.style.gap = '8px';
        nav.setAttribute('data-open','true');
        navToggle.setAttribute('aria-expanded','true');
      }
    });

    // Close nav on resize to desktop
    window.addEventListener('resize', () => {
      if (window.innerWidth >= 900) {
        nav.style.display = '';
        nav.setAttribute('data-open','false');
      } else {
        nav.style.display = 'none';
      }
    });

    // initialize
    if (window.innerWidth < 900) {
      nav.style.display = 'none';
      nav.setAttribute('data-open','false');
    }
  }

  // Gentle CPU-friendly logo pause while scrolling
  const logo = document.getElementById('siteLogo');
  if (logo) {
    let ticking = false;
    window.addEventListener('scroll', () => {
      if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
      if (!ticking) {
        window.requestAnimationFrame(() => {
          // lower animation when user scrolls by adding a reduced duration
          logo.style.animationDuration = '10s';
          clearTimeout(logo._scrollTimeout);
          logo._scrollTimeout = setTimeout(() => {
            logo.style.animationDuration = '';
          }, 250);
          ticking = false;
        });
        ticking = true;
      }
    }, {passive:true});
  }
})();