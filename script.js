const roles = [
  { title: 'Senior Product Designer', team: 'Design', location: 'Remote', type: 'Full-time', description: 'Help shape thoughtful digital experiences, from the first sketch to the final detail. Partner with engineers and product teammates to turn complex problems into clear, useful solutions.' },
  { title: 'Frontend Engineer', team: 'Engineering', location: 'Bengaluru / Hybrid', type: 'Full-time', description: 'Build accessible, responsive interfaces that feel great to use. Collaborate across disciplines and help develop a reliable foundation for the next generation of products.' },
  { title: 'Brand Designer', team: 'Design', location: 'Remote', type: 'Full-time', description: 'Bring a distinctive visual point of view to our sample brand. Explore identity, storytelling, and communication across digital touchpoints.' },
  { title: 'Product Marketing Manager', team: 'Marketing', location: 'Remote', type: 'Full-time', description: 'Connect product ideas with the people who need them. Develop clear stories, thoughtful launch plans, and a deep understanding of our audience.' },
];

const search = document.querySelector('#search');
const team = document.querySelector('#team');
const list = document.querySelector('#job-list');
const dialog = document.querySelector('#role-dialog');
let trigger;

function openRole(role, button) {
  trigger = button;
  document.querySelector('#dialog-title').textContent = role.title;
  document.querySelector('#dialog-team').textContent = role.team;
  document.querySelector('#dialog-meta').textContent = `${role.location} · ${role.type}`;
  document.querySelector('#dialog-description').textContent = role.description;
  dialog.showModal();
}

function renderRoles() {
  const query = search.value.trim().toLowerCase();
  const matches = roles.filter(role =>
    (team.value === 'all' || role.team === team.value) &&
    `${role.title} ${role.team} ${role.location} ${role.type}`.toLowerCase().includes(query)
  );
  list.replaceChildren();
  matches.forEach(role => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'job-row';
    button.setAttribute('aria-haspopup', 'dialog');
    button.setAttribute('aria-label', `View ${role.title}, ${role.team}, ${role.location}`);
    const details = document.createElement('span');
    const title = document.createElement('span');
    title.className = 'job-title';
    title.textContent = role.title;
    const meta = document.createElement('span');
    meta.className = 'role-meta';
    meta.textContent = `${role.location} · ${role.type}`;
    details.append(title, meta);
    const side = document.createElement('span');
    side.className = 'job-side';
    const pill = document.createElement('span');
    pill.className = 'team-pill';
    pill.textContent = role.team;
    const arrow = document.createElement('span');
    arrow.className = 'arrow';
    arrow.textContent = '→';
    arrow.setAttribute('aria-hidden', 'true');
    side.append(pill, arrow);
    button.append(details, side);
    button.addEventListener('click', () => openRole(role, button));
    list.append(button);
  });
  document.querySelector('#result-count').textContent = `${matches.length} sample ${matches.length === 1 ? 'role' : 'roles'}`;
  document.querySelector('#empty-state').hidden = matches.length > 0;
}

search.addEventListener('input', renderRoles);
team.addEventListener('change', renderRoles);
document.querySelector('#reset').addEventListener('click', () => {
  search.value = '';
  team.value = 'all';
  renderRoles();
  search.focus();
});
document.querySelector('#close-dialog').addEventListener('click', () => dialog.close());
dialog.addEventListener('close', () => trigger?.focus());
renderRoles();
