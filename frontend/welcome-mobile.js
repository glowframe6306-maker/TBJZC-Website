// Mobile welcome helper: makes sure mobile layout gets initialized and tweaks logo for sharpness
(function(){
  if (!document.documentElement.classList.contains('mobile-layout')) return;

  // Create a mobile-only welcome card if not present
  const hero = document.querySelector('.hero');
  if (!hero) return;

  // If a mobile card already exists skip
  if (hero.querySelector('.mobile-welcome-card')) return;

  const card = document.createElement('div');
  card.className = 'mobile-welcome-card';

  // Logo element
  const logoWrap = document.createElement('div');
  logoWrap.className = 'mobile-logo';
  const logoImg = document.querySelector('.logo-wrapper img') || document.querySelector('.intro-logo') || document.querySelector('#siteLogo');
  const img = document.createElement('img');
  if (logoImg && logoImg.getAttribute) {
    img.src = logoImg.getAttribute('src');
    img.alt = logoImg.getAttribute('alt') || 'Logo';
    img.decoding = 'async';
  } else {
    img.src = '../images/LOGO.png';
    img.alt = 'Logo';
  }
  logoWrap.appendChild(img);

  // Heading and subtext
  const heading = document.createElement('div');
  heading.className = 'mobile-heading';
  heading.textContent = 'Welcome to T.B. Jayah Zahira College';

  const sub = document.createElement('div');
  sub.className = 'mobile-sub';
  sub.textContent = 'A place of learning, character and service. Explore our site or share feedback.';

  const actions = document.createElement('div');
  actions.className = 'mobile-actions';
  const cta = document.createElement('a');
  cta.className = 'mobile-cta';
  cta.href = 'feedback.html';
  cta.textContent = 'Give Feedback';
  actions.appendChild(cta);

  card.appendChild(logoWrap);
  card.appendChild(heading);
  card.appendChild(sub);
  card.appendChild(actions);

  // Insert at top of hero-inner
  const heroInner = hero.querySelector('.hero-inner') || hero;
  heroInner.insertBefore(card, heroInner.firstChild);

  // Reduce animation during scroll to preserve CPU on low-end devices
  let scrollTimeout = null;
  window.addEventListener('scroll', () => {
    const logo = card.querySelector('.mobile-logo');
    if (!logo) return;
    logo.style.animationPlayState = 'paused';
    clearTimeout(scrollTimeout);
    scrollTimeout = setTimeout(() => {
      logo.style.animationPlayState = '';
    }, 180);
  }, {passive:true});

})();