/* The home screen, and moving between it and a showcase's chat screen.
 *
 * Navigation is hash-based, and that is a requirement rather than a
 * convenience: server.py serves static/ directly and 404s anything that is
 * not a real file, so a pushState path like /showcase/x would break on
 * refresh and on any link a presenter shared. A hash needs no server change.
 *
 * Note the vocabulary. "route" in this app means the model that served a
 * reply, and it keeps meaning only that -- what happens here is a *screen*
 * change between *showcases*.
 */
'use strict';

import { escapeHtml } from './markdown.js';
import {
  wordmark, brandProduct, cardsBox, statusEl, noticeBox, noticeTitle, noticeBody,
  cardWarning, cardWarningTitle, cardWarningBody, cardAbout, cardAboutHow, cardAboutSetup, clearCacheBtn,
  intro, introHead, introBody, introRefs, introChips, transcript, llmSelect,
  resetRoute, resetBudget, clearError, setBusy, setIdleStatus, input,
  showSpendMeter, signinBox, signinWho, signinLink, selectorBox, selectorLabel, selectorSelect,
  screenHome, scrollHint,
} from './dom.js';
import { buildRail, closeRail, showHeaders } from './rail.js';
import { setEmphasis, resetTurns } from './metrics.js';
import { configureSpend } from './spend.js';

/* Every chat screen opens on the same greeting, whichever capability is being
 * shown: a visitor sees an ordinary assistant while the gateway does the work
 * behind it. Under it, the OWASP risk or EU AI Act article the card answers,
 * for the presenter to frame the demo; it goes with the rest of the intro at
 * the first message. What the capability is, and whether it can run here, is
 * the rail's job and the notice strip's. */
const INTRO_HEADING = 'Hi, how can I help?';
/* The chat's welcome line comes with the business the demo plays. */
let introText = '';
export function setIntro(text) {
  introText = text;
  introBody.textContent = text;
}

export const showcases = new Map();

const STATUS_TITLE = 'The LLM proxy on the gateway this showcase talks to: each '
  + 'showcase has its own, with its policy attached, on a shared LLM provider.';

export let activeId = null;
export let activeShowcase = null;
/* The "Ask without the policy" button, with POLICY_COMPARISON_ENABLED=true (demo.env). */
export let policyComparison = false;

/* Per-viewer convenience only (which provider was last picked in this
 * browser) -- never state anything else depends on being read back
 * reliably, so a blocked/cleared localStorage just falls back to the
 * server's default. */
function readStoredProvider() {
  try { return localStorage.getItem('llmProvider') || ''; }
  catch (e) { return ''; }
}
function storeProvider(id) {
  try { localStorage.setItem('llmProvider', id); }
  catch (e) { /* private window, blocked storage, ... -- fine to lose this */ }
}

/* No provider id is ever assumed here -- only the server (its PROVIDERS
 * dict) knows which ones exist and which is the default. Until
 * loadProviders() resolves this against /api/providers, it is just
 * whatever this browser last picked, or "" (nothing chosen yet). */
export let activeProvider = readStoredProvider();

/* provider id -> {small, large} model ids, from /api/providers. A showcase
 * step names a role ("small"/"large"), never a literal model id, so it
 * grades and displays correctly under whichever provider is active --
 * including one added after the step was written. See rail.js's
 * resolveExpectModel(). */
const providerModels = new Map();

export function modelForRole(role) {
  const models = providerModels.get(activeProvider);
  return (models && models[role]) || null;
}

/* provider id -> its own spend-limit/cost-based-routing budget (per window: each
 * card's budget.duration in showcases.json), from
 * /api/providers -- see providers.json's costBudget and
 * scripts/python/provision_showcases.py's budget_for() for why this isn't
 * one flat number shared across providers. spend.js reads this instead of
 * a second copy in showcases.json, for the same reason modelForRole()
 * exists: one place, read by whichever provider is active. */
const providerCostBudget = new Map();

export function costBudgetFor(providerId) {
  return providerCostBudget.get(providerId) ?? null;
}

let defaultId = 'plain-chat';
let registryError = null;
let brand = '';
let onReset = null;

/* One home page per gateway: a card with an "mcp" block belongs to the MCP
 * Gateway page, one with an "a2a" block to the A2A Gateway page (only with
 * A2A_ENABLED in demo.env), every other card to the LLM Gateway page. */
const PAGES = ['llm', 'mcp', 'a2a'];
let activePage = 'llm';
let a2aEnabled = false;

function pageOf(showcase) { return showcase.a2a ? 'a2a' : showcase.mcp ? 'mcp' : 'llm'; }

const PAGE_NAMES = { llm: 'LLM Gateway', mcp: 'MCP Gateway', a2a: 'A2A Gateway' };

function setPage(page) {
  activePage = page;
  document.body.dataset.page = page;
  /* The breadcrumb's first step: this page, and the way back to it from a card. */
  const crumb = document.getElementById('crumb-page');
  crumb.textContent = PAGE_NAMES[page];
  crumb.href = '#/' + page;
}

/* Where the provider picker stands on the LLM page, the MCP and A2A pages
 * name the server or agent the cards use: the open card's, or every one on
 * the page. A card is written for it, so it is shown, not chosen. */
function showBackend() {
  const cards = activeShowcase ? [activeShowcase]
    : [...showcases.values()].filter((s) => pageOf(s) === activePage);
  const names = [...new Set(cards.map((s) => (s.a2a && s.a2a.agent) || (s.mcp && s.mcp.server)).filter(Boolean))];
  const kind = activePage === 'a2a' ? 'Agent' : 'MCP server';
  document.getElementById('backend-label').textContent = names.length > 1 ? kind + 's' : kind;
  backendBtn.textContent = names.join(', ');
  document.getElementById('backend').hidden = !names.length;
  backendBtn.title = activeShowcase ? 'What the gateway publishes for this card'
    : 'Each one as it is, with no gateway rule';
  closeBackend();
}

const backendBtn = document.getElementById('backend-name');
const backendPanel = document.getElementById('backend-panel');

function closeBackend() {
  backendPanel.hidden = true;
  backendBtn.setAttribute('aria-expanded', 'false');
}

/* One server or agent as a card: its name, the route it is read through,
 * and whether the gateway's policies apply on that route. */
function backendCardHtml(icon, name, aside, data, state, body) {
  return '<article class="bcard"><header class="bcard-head">' + iconHtml(icon, 'bcard-icon')
    + '<strong class="bcard-name">' + escapeHtml(name) + '</strong>'
    + (aside ? '<span class="bcard-aside">' + escapeHtml(aside) + '</span>' : '') + '</header>'
    + (data.via ? '<p class="bcard-meta"><code class="bcard-route">' + escapeHtml(data.via) + '</code><span class="bcard-state'
      + (state.policy ? ' is-policy' : '') + '">' + escapeHtml(state.text) + '</span></p>' : '')
    + body + '</article>';
}

const noAnswer = (data) => '<p class="bcard-note">The gateway did not answer: ' + escapeHtml(data.error || '') + '</p>';

/* The tools as the gateway lists them to the agent: a hidden tool is not
 * there, a renamed one shows its new name, a rewritten description its new
 * text. */
function mcpToolsHtml(data, name, state) {
  if (data.signinRequired) {
    return backendCardHtml('wrench', name, '', {}, state,
      '<p class="bcard-note">Sign in on this card first: the gateway lists these tools to a signed-in user only.</p>');
  }
  if (!data.tools) return backendCardHtml('wrench', name, '', {}, state, noAnswer(data));
  return backendCardHtml('wrench', data.server || name, data.tools.length + (data.tools.length === 1 ? ' tool' : ' tools'),
    data, state, '<ul class="bcard-list">' + data.tools.map((tool) => '<li><code class="bcard-tool">' + escapeHtml(tool.name)
      + '<span>(' + escapeHtml(tool.params.join(', ')) + ')</span></code><p>' + escapeHtml(tool.description) + '</p></li>').join('')
    + '</ul>');
}

/* The agent's card as the gateway serves it: every address points at the
 * gateway, so a client that discovers the agent comes back through it. */
function agentDetailHtml(data, name, state) {
  if (!data.name) return backendCardHtml('agents', name, '', {}, state, noAnswer(data));
  return backendCardHtml('agents', data.name, 'v' + (data.version || '?'), data, state,
    '<p class="bcard-desc">' + escapeHtml(data.description || '') + '</p>'
    + '<h4 class="bcard-label">Skills</h4><ul class="bcard-list">'
    + data.skills.map((skill) => '<li><strong>' + escapeHtml(skill.name) + '</strong><p>' + escapeHtml(skill.description) + '</p>'
      + skill.examples.map((example) => '<q>' + escapeHtml(example) + '</q>').join('') + '</li>').join('')
    + '</ul><h4 class="bcard-label">Addresses, all through the gateway</h4><ul class="bcard-addresses">'
    + data.interfaces.map((i) => '<li><span>' + escapeHtml(i.binding) + '</span><code>' + escapeHtml(i.url) + '</code></li>').join('')
    + '</ul>');
}

const NO_POLICY = { text: 'No gateway policy', policy: false };

/* One card's server or agent, as the gateway publishes it for that card. */
async function detailHtml(card, onCard) {
  /* The card's selector can choose which agent card is read: the details follow it. */
  const choice = card.a2a && !selectorBox.hidden ? '&choice=' + encodeURIComponent(selectorSelect.value) : '';
  const response = await fetch((card.a2a ? '/api/a2a/card' : '/api/mcp/tools') + '?showcase=' + encodeURIComponent(card.id) + choice);
  const data = await response.json();
  if (card.a2a) return agentDetailHtml(data, card.a2a.agent, onCard ? { text: 'Served by the gateway', policy: true } : NO_POLICY);
  return mcpToolsHtml(data, card.mcp.server, onCard ? { text: 'After the gateway\'s policies', policy: true } : NO_POLICY);
}

/* From a card: what the gateway publishes for it. From a page: each server or
 * agent as it is, through a card that puts no policy on it. */
backendBtn.addEventListener('click', async () => {
  if (!backendPanel.hidden) return closeBackend();
  const card = activeShowcase;
  backendPanel.innerHTML = '<p class="backend-note">Asking the gateway...</p>';
  backendPanel.hidden = false;
  backendBtn.setAttribute('aria-expanded', 'true');
  try {
    let html;
    if (card) {
      html = await detailHtml(card, true);
    } else {
      const cards = [...showcases.values()].filter((s) => pageOf(s) === activePage && (s.mcp || s.a2a));
      const backendOf = (s) => (s.a2a ? s.a2a.agent : s.mcp.server);
      const sections = [];
      /* A rate limit sits on the card's operations, not in its policies. */
      const noPolicy = (s) => !((s.a2a || s.mcp).policies || []).length && !(s.a2a || s.mcp).operations;
      for (const name of [...new Set(cards.map(backendOf))]) {
        const plain = cards.find((s) => backendOf(s) === name && noPolicy(s));
        sections.push(plain ? await detailHtml(plain, false)
          : backendCardHtml(activePage === 'a2a' ? 'agents' : 'wrench', name, '', {}, NO_POLICY,
            '<p class="bcard-note">Each of its cards puts a gateway policy on it: open one to see what the gateway publishes.</p>'));
      }
      html = sections.join('');
    }
    if (activeShowcase === card) backendPanel.innerHTML = html;
  } catch (error) {
    backendPanel.innerHTML = '<p class="backend-note">The gateway did not answer.</p>';
  }
});
document.addEventListener('click', (event) => {
  if (!backendPanel.hidden && !document.getElementById('backend').contains(event.target)) closeBackend();
});
document.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeBackend(); });

/* chat.js owns the transcript state, so it registers what to clear. */
export function onSessionReset(fn) { onReset = fn; }

/* ---------- boot ---------- */

/* Resolves activeProvider against the server's own list and, if present,
 * populates the provider <select> from it -- adding a provider
 * (scripts/provision_showcases.py's PROVIDERS + ai-chatbot/server.py's
 * PROVIDERS) needs no change here, it just shows up. */
export async function loadProviders() {
  try {
    const response = await fetch('/api/providers');
    const data = await response.json();
    const known = data.providers || [];
    if (known.length && !known.some((p) => p.id === activeProvider)) {
      activeProvider = data.default || known[0].id;
    }
    providerModels.clear();
    providerCostBudget.clear();
    for (const p of known) {
      providerModels.set(p.id, p.models || {});
      providerCostBudget.set(p.id, p.costBudget);
    }
    if (llmSelect) {
      llmSelect.innerHTML = known.map((p) =>
        '<option value="' + escapeHtml(p.id) + '"'
        + (p.id === activeProvider ? ' selected' : '') + '>'
        + escapeHtml(p.displayName) + '</option>').join('');
    }
  } catch (error) {
    registryError = 'could not load /api/providers: ' + error;
  }
  if (llmSelect) llmSelect.onchange = () => setProvider(llmSelect.value);
}

/* Switching providers mid-conversation talks to a different LlmProvider
 * entirely -- a carried-over transcript or budget reading would be showing
 * one provider's state on another's screen, same reasoning as Clear chat's
 * budget reset in resetSession(). */
export async function setProvider(id) {
  if (id === activeProvider) return;
  activeProvider = id;
  storeProvider(id);
  await loadRegistry();
  if (activeId && showcases.has(activeId)) {
    mountShowcase(showcases.get(activeId));
  }
  resetSession();
}

export async function loadRegistry() {
  try {
    const response = await fetch('/api/showcases?provider=' + encodeURIComponent(activeProvider));
    const data = await response.json();
    defaultId = data.defaultShowcase || defaultId;
    brand = data.brand || '';
    registryError = (data.registry && data.registry.error) || null;
    showcases.clear();
    for (const item of data.showcases || []) showcases.set(item.id, item);
    a2aEnabled = Boolean(data.a2a);
    policyComparison = data.policyComparison === true;
    document.getElementById('nav-a2a').hidden = !a2aEnabled;
    GROUPS = Object.fromEntries((data.groups || []).map((g) => [g.id, [g.title, g.icon, g.text, g.order]]));
  } catch (error) {
    registryError = 'could not load /api/showcases: ' + error;
  }
  renderCards();
}

/* ---------- home ---------- */

/* Only a card that cannot run gets a badge; the reason shows on hover, so no
 * setting name reaches the screen. */
function badge(showcase, needs) {
  const why = needs.length ? ' title="' + escapeHtml(needs.join(' ')) + '"' : '';
  if (showcase.status === 'disabled') {
    return '<span class="badge is-blocked"' + why + '>Disabled</span>';
  }
  if (showcase.status !== 'ready') {
    return '<span class="badge is-blocked"' + why + '>Not available yet</span>';
  }
  if (!showcase.configured) {
    return '<span class="badge is-unwired"' + why + '>Not configured</span>';
  }
  return '';
}

/* An EU AI Act article that binds high-risk systems only says so, plainly:
 * for a customer assistant it is good practice, not an obligation. */
function scopeBadge(ref) {
  return ref.scope === 'high-risk' ? '<span class="ref-scope">High-risk systems only</span> ' : '';
}

/* {brand} in a text becomes the operator's name, as in the system prompts. */
function branded(text) {
  return text.replaceAll('{brand}', brand);
}

function cardHtml(showcase, group) {
  /* Anchors, not buttons: middle-click, keyboard activation, the back button
   * and "copy link" all work with no JavaScript of ours. */
  const needs = [];
  if (showcase.status !== 'ready') needs.push(...(showcase.blockedBy || []));
  if (showcase.status === 'ready' && !showcase.configured) {
    needs.push(showcase.unwiredReason || 'no provider configured');
  }

  /* The policies by name; their versions show on hover. */
  const caps = (showcase.capability || '').split(' + ').filter(Boolean);
  const policies = caps.map((c) => c.replace(/\s+v\d[\w.]*$/, '')).join(', ');
  /* In a group like OWASP or the EU AI Act: the risk or article it answers. */
  const ref = (showcase.refs || {})[group];

  /* A disabled card (DISABLED_CARDS in demo.env) stays on the home screen,
   * greyed out and not clickable, with its blockedBy reason. */
  const disabled = showcase.status === 'disabled';
  const status = badge(showcase, needs);
  return '<a class="card' + (disabled ? ' is-disabled" aria-disabled="true" tabindex="-1"' : '"')
    + ' href="#/' + encodeURIComponent(showcase.id) + '">'
    + '<div class="card-head">' + iconHtml((GROUPS[group] || [])[1], 'card-icon')
    + '<h3>' + (ref ? '<span class="ref-code">' + escapeHtml(ref.code) + '</span> ' : '')
    + escapeHtml(showcase.title || showcase.id)
    /* A policy that calls an outside service names that service. */
    + (showcase.vendor ? ' <span class="vendor" title="Third-party policy: calls ' + escapeHtml(showcase.vendor)
        + '">' + escapeHtml(showcase.vendor) + '</span>' : '')
    + (status ? ' ' + status : '')
    + '</h3></div>'
    + '<p>' + escapeHtml(showcase.tagline || '') + '</p>'
    + (ref ? '<p class="card-ref">' + scopeBadge(ref) + escapeHtml(branded(ref.text)) + '</p>' : '')
    + '<div class="card-foot">'
    + (policies ? '<span class="card-cap" title="' + escapeHtml(caps.join(', ')) + '">'
        + escapeHtml(policies) + '</span>' : '<span></span>')
    + (disabled ? '' : '<span class="card-try" aria-hidden="true">Try &rarr;</span>')
    + '</div>'
    + '</a>';
}

/* The groups come with the registry (showcases.json's "groups"), in the order
 * they show: id -> [title, icon, one line on what the group brings, and the
 * order of its cards when it sets one]. */
let GROUPS = {};
const ICONS = {
  route: '<path d="M16 3h5v5M4 20 21 3M21 16v5h-5M15 15l6 6M4 4l5 5"/>',
  gauge: '<path d="M12 14l4-4M3.3 18a9 9 0 1 1 17.4 0"/>',
  shield: '<path d="M12 3l8 3v6c0 5-3.4 8.4-8 9-4.6-.6-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  agents: '<circle cx="6" cy="12" r="3"/><circle cx="18" cy="6" r="3"/><circle cx="18" cy="18" r="3"/><path d="M8.7 10.6l6.6-3.2M8.7 13.4l6.6 3.2"/>',
  wrench: '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2.4-2.4z"/>',
  chat: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/>',
  alert: '<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17h.01"/>',
  scale: '<path d="M12 3v18M7 21h10M4 7h16M4 7l-2.5 6a2.5 2.5 0 0 0 5 0zM20 7l-2.5 6a2.5 2.5 0 0 0 5 0z"/>',
  plug: '<path d="M9 2v5M15 2v5M6 7h12v4a6 6 0 0 1-12 0zM12 17v5"/>',
};

/* A group's icon, on its header and on each of its cards. */
function iconHtml(icon, cls) {
  return '<span class="' + cls + '" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"'
    + ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + (ICONS[icon] || ICONS.chat) + '</svg></span>';
}

function groupHeadHtml(name) {
  const [title, icon, text] = GROUPS[name] || [name, 'chat', ''];
  return '<header class="group-head">'
    + iconHtml(icon, 'group-icon')
    + '<div><h2 class="group-title">' + escapeHtml(title) + '</h2>'
    + (text ? '<p class="group-desc">' + escapeHtml(branded(text)) + '</p>' : '') + '</div>'
    + '</header>';
}

/* "More below" shows while the home page has more to scroll. */
function updateScrollHint() {
  const left = screenHome.scrollHeight - screenHome.scrollTop - screenHome.clientHeight;
  scrollHint.classList.toggle('is-done', left < 24);
}
screenHome.addEventListener('scroll', updateScrollHint);
window.addEventListener('resize', updateScrollHint);
scrollHint.addEventListener('click', () =>
  screenHome.scrollBy({ top: screenHome.clientHeight * 0.8, behavior: 'smooth' }));

/* A card's group is one name, or a list when it belongs to several themes:
 * it then shows in each, and the first one is its home. */
function groupsOf(showcase) {
  return Array.isArray(showcase.group) ? showcase.group : [showcase.group || ''];
}

/* Cards are grouped by theme, groups in GROUPS order (others after them), so
 * the page reads as a story rather than a flat list. In its other groups, a
 * card comes after the group's own cards. */
function renderCards() {
  const items = [...showcases.values()].filter((s) => pageOf(s) === activePage);
  const groups = new Map();
  const add = (name, item) => {
    if (!groups.has(name)) groups.set(name, []);
    groups.get(name).push(item);
  };
  for (const item of items) add(groupsOf(item)[0], item);
  for (const item of items) groupsOf(item).slice(1).forEach((name) => add(name, item));
  const order = Object.keys(GROUPS);
  const rank = (name) => (order.includes(name) ? order.indexOf(name) : order.length);
  const sorted = [...groups].sort(([a], [b]) => rank(a) - rank(b));
  const code = (card, name) => ((card.refs || {})[name] || {}).code;
  for (const [name, cards] of sorted) {
    /* A group can list its cards in order ("order" in showcases.json); the
     * cards it does not list come after them. */
    const listed = (GROUPS[name] || [])[3] || [];
    const place = (card) => (listed.includes(card.id) ? listed.indexOf(card.id) : listed.length);
    if (cards.every((card) => code(card, name))) {
      const scope = (card) => (((card.refs || {})[name] || {}).scope === 'high-risk' ? 1 : 0);
      cards.sort((a, b) => place(a) - place(b) || scope(a) - scope(b)
        || code(a, name).localeCompare(code(b, name), 'en', { numeric: true }));
    } else if (listed.length) {
      cards.sort((a, b) => place(a) - place(b));
    }
  }
  cardsBox.innerHTML =
    (registryError
      ? '<div class="notice"><strong>The registry did not load cleanly</strong>'
        + '<p>' + escapeHtml(registryError) + '</p></div>'
      : '')
    + sorted.map(([name, cards]) => '<section class="card-group" data-group="' + escapeHtml(name) + '">'
        + (name ? groupHeadHtml(name) : '')
        + '<div class="card-grid">' + cards.map((card) => cardHtml(card, name)).join('') + '</div>'
        + '</section>').join('');
  requestAnimationFrame(updateScrollHint);
}

/* ---------- mounting a showcase ---------- */

function noticeFor(showcase) {
  const lines = [];
  if (showcase.status !== 'ready') {
    lines.push('<p>' + escapeHtml(showcase.title)
      + (showcase.status === 'disabled' ? ' is disabled.</p>' : ' cannot run on this gateway yet.</p>'));
    if ((showcase.blockedBy || []).length) {
      lines.push('<ul>' + showcase.blockedBy
        .map((b) => '<li>' + escapeHtml(b) + '</li>').join('') + '</ul>');
    }
  }
  if (!showcase.configured) {
    lines.push('<p>No provider is wired for this showcase, so the steps below '
      + 'will not send: <code>' + escapeHtml(showcase.unwiredReason || 'no provider configured')
      + '</code>.</p>');
  } else if (showcase.status !== 'ready' && showcase.status !== 'disabled') {
    /* Wired but the policy is not released: the card will answer normally and
     * prove nothing. That is the failure most likely to mislead an audience,
     * so it gets said out loud rather than left to be inferred. */
    lines.push('<p>A provider <em>is</em> wired at <code>'
      + escapeHtml(showcase.gatewayContext || '')
      + '</code>, so the steps will answer, but without the policy attached '
      + 'they prove nothing. This is what the demo looks like with the '
      + 'capability off.</p>');
  }
  return lines.join('');
}

/* The path of each message (assistant, gateway, what is behind it) is one
 * element: large under the title on the home page, in the bar on a card. */
const flowEl = document.querySelector('.flow');
function placeFlow(home) {
  const target = home ? document.getElementById('hero-flow') : document.querySelector('.contextbar-inner');
  if (flowEl.parentElement !== target) target.appendChild(flowEl);
}

function mountShowcase(showcase) {
  const switching = showcase.id !== activeId;
  activeId = showcase.id;
  activeShowcase = showcase;
  document.body.dataset.screen = 'chat';
  placeFlow(false);
  setPage(pageOf(showcase));
  showBackend();
  closeRail();

  /* The tile shows the outside service as a label; here it follows the name,
   * so the two Content safety cards stay apart. */
  const name = (showcase.title || 'AI Assistant') + (showcase.vendor ? ' (' + showcase.vendor + ')' : '');
  brandProduct.textContent = name;
  document.title = name + ' - AI Gateway showcase';

  /* The gateway's tooltip gives this card's route on it, for the presenter;
   * the audience sees the path, not the plumbing. */
  statusEl.title = (showcase.a2a
    ? 'The agent proxy on the gateway this card\'s messages go through, with its policy attached.'
    : showcase.mcp
    ? 'The MCP proxy on the gateway this card\'s tool calls go through, with its policy attached.'
    : STATUS_TITLE) + (showcase.gatewayContext ? ' Route: ' + showcase.gatewayContext : '');
  setIdleStatus(showcase.gatewayContext ? '' : 'not wired');

  refreshSignin(showcase);

  /* A card whose gateway reads something about the customer from a header
   * (tier, region, id) gets a selector standing in for it. */
  const sel = showcase.selector;
  selectorBox.hidden = !sel;
  selectorBox.title = (sel && sel.hint) || '';
  selectorLabel.textContent = sel ? sel.label : '';
  /* What the selector stands in for: a card can say, the customer's token by default. */
  document.getElementById('selector-note').textContent = (sel && sel.note) || 'from the customer\'s token in production';
  selectorSelect.innerHTML = (sel ? sel.values : []).map((v) => '<option value="' + escapeHtml(v) + '">'
    + escapeHtml(v.charAt(0).toUpperCase() + v.slice(1)) + '</option>').join('');
  /* Its colour changes off the first value, so a switch shows from across the room. */
  const paint = () => { selectorSelect.dataset.alt = String(!!sel && selectorSelect.value !== sel.values[0]); };
  paint();
  selectorSelect.onchange = paint;

  const notice = noticeFor(showcase);
  noticeBox.hidden = !notice;
  noticeTitle.textContent = showcase.status === 'disabled'
    ? 'Disabled'
    : showcase.status === 'ready' && !showcase.configured
      ? 'Not wired on this environment'
      : 'Not available on this gateway yet';
  noticeBody.innerHTML = notice;

  /* What the presenter must know before running the card, such as the
   * provider to pick, and why. */
  const warning = showcase.warning;
  cardWarning.hidden = !warning;
  cardWarningTitle.textContent = warning ? warning.title : '';
  cardWarningBody.textContent = warning ? warning.text : '';
  /* A card that caches answers says so in showcases.json ("clearCache"): it
   * gets a button to empty the cache. */
  clearCacheBtn.hidden = !showcase.clearCache;
  /* How the card's policy works, and how it is set up on this card. */
  const about = showcase.about;
  cardAbout.hidden = !about;
  cardAboutHow.textContent = about ? about.how : '';
  cardAboutSetup.textContent = about ? about.setup : '';

  const introData = showcase.intro || {};
  introHead.textContent = INTRO_HEADING;
  introBody.textContent = introText;
  introRefs.innerHTML = Object.entries(showcase.refs || {}).map(([group, ref]) =>
    '<div class="intro-ref"><span class="ref-group">' + escapeHtml((GROUPS[group] || [group])[0]) + '</span>'
    + '<p><span class="ref-code">' + escapeHtml(ref.code) + '</span> ' + scopeBadge(ref)
    + escapeHtml(branded(ref.text)) + '</p></div>').join('');
  introChips.innerHTML = (introData.chips || []).map((chip) =>
    '<button type="button" class="chip" data-ask="' + escapeHtml(chip.ask || '')
    + '">' + escapeHtml(chip.label || chip.ask || '') + '</button>').join('');

  buildRail(showcase);
  setEmphasis(showcase.emphasis);

  /* Only a genuine change of showcase discards the conversation. Going home
   * and coming back leaves it intact -- the screen is display:none'd, never
   * destroyed. */
  if (switching) resetSession();

  /* Cost-based routing watches a budget the gateway does not report, so its
   * meter is shown from the registry's figures before the first call and
   * carries its running total across a trip home. Every other showcase leaves
   * the bar to the gateway's own headers, or has no budget at all. */
  showSpendMeter(configureSpend(showcase));
}

/* MCP cards whose proxy runs mcp-auth: who is signed in for this card, and
 * the link to sign in or out. The token itself never reaches the page. */
async function refreshSignin(showcase) {
  const needs = ((showcase.mcp || {}).policies || []).some((p) => p.name === 'mcp-auth');
  signinBox.hidden = !needs;
  signinBox.classList.remove('is-attention');
  if (!needs) return;
  const card = encodeURIComponent(showcase.id);
  let session = { signedIn: false };
  try { session = await (await fetch('/api/session?card=' + card)).json(); }
  catch (e) { /* shown as signed out */ }
  signinBox.classList.toggle('is-signed-in', Boolean(session.signedIn));
  signinWho.textContent = session.signedIn
    ? 'Signed in as ' + session.user + (session.scopes.length ? ' (' + session.scopes.join(', ') + ')' : '')
    : 'Signed out';
  signinLink.textContent = session.signedIn ? 'Sign out' : 'Sign in';
  signinLink.href = (session.signedIn ? '/oauth/logout?card=' : '/oauth/login?card=') + card;
}

export function resetSession() {
  clearError();
  transcript.innerHTML = '';
  transcript.appendChild(intro);
  resetRoute();
  /* Each showcase is a different provider, and llm-cost-based-ratelimit counts
   * per provider -- so a balance carried across a switch would be showing one
   * provider's budget on another's screen. Clear chat deliberately does NOT do
   * this, because there the provider has not changed. */
  resetBudget();
  resetTurns();
  showHeaders({});
  if (onReset) onReset();
  setBusy(false);
}

function mountHome(page) {
  /* Each page starts at its top, not where the other one was left. */
  if (page !== activePage) screenHome.scrollTop = 0;
  setPage(page);
  renderCards();
  setIdleStatus();
  statusEl.title = 'Every message of these cards goes through the WSO2 AI Gateway.';
  activeId = null;
  activeShowcase = null;
  showBackend();
  document.body.dataset.screen = 'home';
  placeFlow(true);
  document.body.dataset.rail = '';
  brandProduct.textContent = 'AI Assistant';
  document.title = 'AI Gateway showcases';
  closeRail();
}

/* ---------- the hash ---------- */

export function applyHash() {
  /* A hand-edited or copy-truncated fragment (e.g. a trailing "%") throws
   * URIError here -- every hash this app itself generates comes from
   * encodeURIComponent and can't do this, but an outside link can. */
  let id;
  try { id = decodeURIComponent(location.hash.replace(/^#\/?/, '')).trim(); }
  catch (e) { return mountHome('llm'); }
  const showcase = showcases.get(id);
  if (!showcase) {
    mountHome(PAGES.includes(id) && (id !== 'a2a' || a2aEnabled) ? id : 'llm');
    return;
  }
  mountShowcase(showcase);
  if (!showcase.configured) return;
  if (!window.matchMedia('(max-width: 1023px)').matches) input.focus();
}

window.addEventListener('hashchange', applyHash);

/* The page links are plain anchors, so they need no handler -- except when
 * the hash is already theirs (a card opened from a stale entry), where no
 * hashchange fires, so nudge it. */
for (const page of PAGES) {
  document.getElementById('nav-' + page).addEventListener('click', () => {
    if (location.hash === '#/' + page) mountHome(page);
  });
}
wordmark.addEventListener('click', () => { if (location.hash === '#/') mountHome('llm'); });

export function defaultShowcaseId() { return defaultId; }
