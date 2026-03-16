/* ═══════════════════════════════════════════════
   projects.js — shared data layer
   Fetches projects.json and exposes helpers
   used by heritage.html, film.html, immersive.html,
   and project.html
═══════════════════════════════════════════════ */

let _cache = null;

export async function getProjects() {
  if (_cache) return _cache;
  const res = await fetch('/projects.json');
  if (!res.ok) throw new Error('Could not load projects.json');
  _cache = await res.json();
  return _cache;
}

export async function getProjectsByTag(tag) {
  const all = await getProjects();
  return all.filter(p => p.tags.includes(tag));
}

export async function getProjectById(id) {
  const all = await getProjects();
  return all.find(p => p.id === id) || null;
}

/* ── Card renderer ──────────────────────────────
   Returns an <article> DOM element for a project.
   Used by the three category index pages.
─────────────────────────────────────────────── */
export function renderCard(project) {
  const card = document.createElement('article');
  card.className = 'proj-card-item';
  card.setAttribute('data-id', project.id);

  const tagHTML = project.tags
    .map(t => `<span class="proj-tag">${t}</span>`)
    .join('');

  card.innerHTML = `
    <a href="project.html?id=${project.id}" class="proj-card-link">
      <div class="proj-card-visual">
        ${project.coverImage
          ? `<img src="${project.coverImage}" alt="${project.coverAlt || project.title}" loading="lazy">`
          : `<div class="proj-card-placeholder">
               <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
                 <rect x="4" y="8" width="24" height="16" rx="1" stroke="currentColor" stroke-width="1" fill="none" opacity="0.4"/>
                 <circle cx="11" cy="14" r="2.5" stroke="currentColor" stroke-width="1" fill="none" opacity="0.4"/>
                 <path d="M4 20 L10 15 L16 19 L22 13 L28 18" stroke="currentColor" stroke-width="1" fill="none" opacity="0.4"/>
               </svg>
               <span>Image coming soon</span>
             </div>`
        }
        <div class="proj-card-hover-overlay"></div>
      </div>
      <div class="proj-card-meta">
        <div class="proj-card-top">
          <span class="proj-card-category">${project.category}</span>
          <span class="proj-card-year">${project.year}</span>
        </div>
        <h2 class="proj-card-title">${project.title}</h2>
        <p class="proj-card-summary">${project.summary}</p>
        <div class="proj-card-tags">${tagHTML}</div>
        <span class="proj-card-cta">View project <span class="proj-card-arrow">→</span></span>
      </div>
    </a>
  `;

  return card;
}

/* ── URL param helper ──────────────────────────── */
export function getParam(key) {
  return new URLSearchParams(window.location.search).get(key);
}
