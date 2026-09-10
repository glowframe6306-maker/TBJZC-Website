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

      const gallery = document.createElement('div');
      gallery.className = 'published-post-gallery';
      (post.images || []).forEach(image => {
        const imageElement = document.createElement('img');
        imageElement.src = resolveImageUrl(image);
        imageElement.alt = post.title || 'Published post image';
        imageElement.loading = 'lazy';
        gallery.appendChild(imageElement);
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
