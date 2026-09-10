(function () {
  const container = document.querySelector('[data-post-section]');
  if (!container) return;

  const section = container.dataset.postSection;
  const escapeText = value => String(value ?? '');
  const resolveImageUrl = image => {
    try {
      return new URL(image, window.location.origin).href;
    } catch {
      return image;
    }
  };
  const formatPublished = value => {
    if (!value) return '';
    const parsed = new Date(`${String(value).replace(' ', 'T')}Z`);
    if (Number.isNaN(parsed.getTime())) return String(value);
    return new Intl.DateTimeFormat(undefined, {
      day: 'numeric', month: 'long', year: 'numeric',
      hour: '2-digit', minute: '2-digit', hour12: true,
      timeZone: 'Asia/Colombo'
    }).format(parsed);
  };

  const galleryOverlay = document.createElement('div');
  galleryOverlay.className = 'posts-gallery-overlay';
  galleryOverlay.innerHTML = '<button class="posts-gallery-close" type="button" aria-label="Close gallery">&times;</button><div class="posts-gallery-grid"></div>';
  document.body.appendChild(galleryOverlay);
  const viewerOverlay = document.createElement('div');
  viewerOverlay.className = 'posts-viewer-overlay';
  viewerOverlay.innerHTML = '<button class="posts-viewer-close" type="button" aria-label="Close image viewer">&times;</button><img class="posts-viewer-image" alt="">';
  document.body.appendChild(viewerOverlay);
  const style = document.createElement('style');
  style.textContent = `
    .published-post-gallery-item { position: relative; border: 0; padding: 0; background: transparent; cursor: pointer; min-width: 0; }
    .published-post-gallery-item img { width: 100%; height: 180px; object-fit: contain; background: rgba(255,255,255,.06); border-radius: 8px; display: block; }
    .published-post-gallery-more { position: absolute; inset: 0; display: grid; place-items: center; border-radius: 8px; background: rgba(3,7,18,.68); color: #fff; font-size: 1.2rem; font-weight: 700; }
    .posts-gallery-overlay, .posts-viewer-overlay { position: fixed; inset: 0; z-index: 100; display: none; background: rgba(3,7,18,.95); padding: 6vh 5vw; overflow: auto; }
    .posts-gallery-overlay.show, .posts-viewer-overlay.show { display: block; }
    .posts-gallery-close, .posts-viewer-close { position: fixed; top: 16px; right: 24px; z-index: 101; border: 0; background: transparent; color: #fff; font-size: 2.4rem; cursor: pointer; }
    .posts-gallery-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 14px; max-width: 1100px; margin: 0 auto; }
    .posts-gallery-grid button { border: 0; padding: 0; background: transparent; cursor: pointer; }
    .posts-gallery-grid img { width: 100%; height: 190px; object-fit: contain; background: rgba(255,255,255,.06); border-radius: 8px; }
    .posts-viewer-overlay { display: none; place-items: center; padding: 48px; }
    .posts-viewer-overlay.show { display: grid; }
    .posts-viewer-image { max-width: 92vw; max-height: 86vh; object-fit: contain; }
  `;
  document.head.appendChild(style);
  const galleryGrid = galleryOverlay.querySelector('.posts-gallery-grid');
  const viewerImage = viewerOverlay.querySelector('.posts-viewer-image');

  const closeGallery = () => galleryOverlay.classList.remove('show');
  const closeViewer = () => {
    viewerOverlay.classList.remove('show');
    viewerImage.removeAttribute('src');
  };
  const openGallery = images => {
    galleryGrid.replaceChildren();
    images.forEach((image, index) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.imageIndex = String(index);
      const imageElement = document.createElement('img');
      imageElement.src = resolveImageUrl(image);
      imageElement.alt = `Gallery image ${index + 1}`;
      button.appendChild(imageElement);
      galleryGrid.appendChild(button);
    });
    galleryGrid.dataset.images = JSON.stringify(images);
    galleryOverlay.classList.add('show');
  };
  galleryOverlay.querySelector('.posts-gallery-close').addEventListener('click', closeGallery);
  viewerOverlay.querySelector('.posts-viewer-close').addEventListener('click', closeViewer);
  galleryOverlay.addEventListener('click', event => {
    if (event.target === galleryOverlay) closeGallery();
  });
  viewerOverlay.addEventListener('click', event => {
    if (event.target === viewerOverlay) closeViewer();
  });
  galleryGrid.addEventListener('click', event => {
    const button = event.target.closest('button');
    if (!button) return;
    const images = JSON.parse(galleryGrid.dataset.images || '[]');
    viewerImage.src = resolveImageUrl(images[Number(button.dataset.imageIndex)]);
    viewerOverlay.classList.add('show');
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      closeViewer();
      closeGallery();
    }
  });

  function render(posts) {
    container.replaceChildren();
    if (!posts.length) {
      const empty = document.createElement('p');
      empty.className = 'published-posts-empty';
      empty.textContent = 'No published posts in this section yet.';
      container.appendChild(empty);
      return;
    }

    posts.forEach(post => {
      const article = document.createElement('article');
      article.className = 'published-post';

      const heading = document.createElement('h3');
      heading.textContent = escapeText(post.title);
      article.appendChild(heading);

      const description = document.createElement('p');
      description.className = 'published-post-description';
      description.textContent = escapeText(post.content || post.short_description);
      article.appendChild(description);

      const images = post.images || [];
      const gallery = document.createElement('div');
      gallery.className = 'published-post-gallery';
      images.slice(0, 3).forEach((image, index) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'published-post-gallery-item';
        const imageElement = document.createElement('img');
        imageElement.src = resolveImageUrl(image);
        imageElement.alt = post.title || 'Published post image';
        imageElement.loading = 'lazy';
        button.appendChild(imageElement);
        if (index === 2 && images.length > 3) {
          const more = document.createElement('span');
          more.className = 'published-post-gallery-more';
          more.textContent = `+${images.length - 3}`;
          button.appendChild(more);
        }
        button.addEventListener('click', () => openGallery(images));
        gallery.appendChild(button);
      });
      if (gallery.children.length) article.appendChild(gallery);

      const meta = document.createElement('small');
      meta.className = 'published-post-meta';
      meta.textContent = formatPublished(post.publish_date || post.created_at);
      article.appendChild(meta);
      container.appendChild(article);
    });
  }

  fetch(`/api/posts?section=${encodeURIComponent(section)}`)
    .then(response => {
      if (!response.ok) throw new Error('Unable to load published posts.');
      return response.json();
    })
    .then(render)
    .catch(() => {
      container.replaceChildren();
      const error = document.createElement('p');
      error.className = 'published-posts-empty';
      error.textContent = 'Published posts are temporarily unavailable.';
      container.appendChild(error);
    });
})();
