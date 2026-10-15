// The page: home, decks, status and settings, set-up, a new deck, one deck with the gate it
// waits at, and what the workspace has published.
// It draws what the server says and sends back only what the person decides. Every value
// from the server is placed as text, so nothing in a deck's files or its record can ever be
// read as markup. Documents are drawn by markdown.js, which keeps the same rule. A slide's
// picture, and the deck itself, are fetched as bytes and held in memory, never at an address.
'use strict';

const TOKEN_HEADER = 'X-Presentation-Studio-Token';
const POLL_SHOWN = 5000;
const POLL_HIDDEN = 20000;
const POLL_RUN = 2000; // while a deck is working and its own screen is open
// Where set-up is read each time. It carries what was found of the skills, for home and status.
const SET_UP_SHOWN = ['home', 'status', 'settings', 'setup', 'new'];
const DRAWING = 'http://www.w3.org/2000/svg'; // the name of the SVG language; nothing is fetched
const COUNTED = ['Nothing needs', 'One thing needs', 'Two things need', 'Three things need',
  'Four things need', 'Five things need', 'Six things need', 'Seven things need',
  'Eight things need', 'Nine things need', 'Ten things need'];
const NOTICES = {
  stopped: 'This page has lost touch with Presentation Studio, so it cannot read or save '
    + 'anything. Run the studio command again in your terminal and use the new link.',
  refused: 'This link does not match the page that is running. '
    + 'Run the studio command again in your terminal and use the link it prints, whole.',
};
// Every icon is drawn here, on a 24 by 24 grid, in one weight of line.
const ICONS = {
  home: ['M4 11.5 12 4.5l8 7', 'M6.5 10.5V19.5h11V10.5'],
  decks: ['M4 6.5h16v10H4z', 'M9 20h6', 'M12 16.5V20'],
  status: ['M3 12.5h4l2.5-6.5 4.5 12 2.5-5.5H21'],
  settings: ['M4.5 7.5h7', 'M16.5 7.5h3', 'M14 5.5a2 2 0 1 0 0 4 2 2 0 0 0 0-4z', 'M4.5 16.5h3',
    'M12.5 16.5h7', 'M10 14.5a2 2 0 1 0 0 4 2 2 0 0 0 0-4z'],
  back: ['M14.5 5.5 8 12l6.5 6.5'],
  check: ['M5.5 12.5 10 17l8.5-10'],
  eye: ['M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z',
    'M12 9.2a2.8 2.8 0 1 0 0 5.6 2.8 2.8 0 0 0 0-5.6z'],
  warn: ['M12 6v7.5', 'M12 17.5h.01'],
  minus: ['M6.5 12h11'],
  slash: ['M7 17 17 7'],
};
const BEAD_ICONS = { done: 'check', review: 'eye', late: 'warn', out: 'minus', off: 'slash' };
const COMPUTER_WORDS = {
  ok: ['done', 'Ready'], missing: ['off', 'Not installed'], problem: ['late', 'Needs attention'],
};
const NAV = [['go-home', 'home', 'home'], ['go-decks', 'decks', 'decks'],
  ['go-status', 'status', 'status'], ['go-settings', 'settings', 'settings']];
// The screen in the sidebar that each other screen belongs to.
const PARENTS = { deck: 'decks', new: 'decks', published: 'decks', setup: 'settings' };

// A deck says where it is in these words, as a bead's shape and a few words.
const RUN_WORDS = {
  working: ['current', 'Working on its own'],
  waiting: ['review', 'Waiting for you'],
  paused: ['out', 'Paused'],
  stopped: ['off', 'Stopped'],
  failed: ['late', 'Stopped: something went wrong'],
  finished: ['done', 'Finished'],
  // A deck a teammate's computer runs: only what was last shared is known here.
  elsewhere: ['none', 'Run from another computer'],
};
// Each step of a deck, and each stage, as the timeline says it.
const STEP_WORDS = {
  done: ['done', 'Done'], current: ['current', 'Now'], upcoming: ['none', 'Still to come'],
  later: ['out', 'Coming later'],
};
const STAGES = [['intake', 'Intake'], ['classify', 'Classify'], ['research', 'Research'],
  ['outline', 'Outline'], ['look', 'Brand'], ['build', 'Build'], ['deliver', 'Deliver'],
  ['rehearse', 'Rehearse with Yoodli']];
const STEERED = {
  pause: 'Paused. Nothing more is started until you resume it.',
  resume: 'Carrying on.',
  stop: 'Stopped. Everything made so far is kept.',
  retry: 'Trying again.',
  undo: 'The last step was undone. It carries on from there.',
};
const AGENTS = ['claude', 'codex'];
const AGENT_NAMES = { claude: 'Claude Code', codex: 'Codex' };
// The first choice of a model and of a reasoning level, which leaves it to the agent.
const OWN_CHOICE = 'The agent’s own choice';
// Where "Another model…" is in the list of models. No name an agent takes has a space.
const OTHER_MODEL = ' other';
const LEVEL_NAMES = { none: 'None', minimal: 'Minimal', low: 'Low', medium: 'Medium',
  high: 'High', xhigh: 'Extra high', max: 'Maximum', ultra: 'Ultra' };
const MODELS_AGAIN = 60000; // a list of models that could not be made is asked for again after
const SHARE = ['each-decision', 'when-asked'];
// What the folder and the workspace are called become names of folders, so they are plain.
const PLAIN_NAME = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
const PLAIN_SAYS = 'Use letters, digits, dots, hyphens and underscores, with no spaces, '
  + 'starting with a letter or a digit: field-decks, for example.';
const SHARE_SAYS = [
  'After each decision: your team sees the outline, your decisions and each deck as soon as '
    + 'you decide a stage, finished or not.',
  'Only when I ask: everything stays on this computer, and your team sees nothing new, '
    + 'until you press “Share now”.',
];
const OUTPUTS = [['google', 'Google Slides'], ['pptx', 'PowerPoint (.pptx)']];
const OUTPUT_SAYS = [
  'Google Slides: the finished deck is a new presentation in your Google Drive.',
  'PowerPoint: the finished deck is a .pptx file kept on this computer, to download.',
];
// How a deck begins. Each card opens a short form with only that route's questions.
const ROUTES = [
  ['scratch', 'Start from scratch', 'Say what it is about and who it is for. It is '
    + 'researched if you like, outlined, designed and built.'],
  ['document', 'Start from a document', 'A script, notes or a write-up. It is read first, '
    + 'and you confirm whether it is a finished script for the slides or material to build '
    + 'from.'],
  ['existing', 'Redesign an existing deck', 'A .pptx or a Google Slides deck. The original '
    + 'is never changed: a new copy is made.'],
];
// How much of an existing deck changes. Each says in one line what it does.
const LEVELS = [
  ['brand-only', 'Brand only', 'Same slides in your brand’s look: colors, fonts, logo, '
    + 'master layouts.'],
  ['polish', 'Polish', 'Brand plus tidier layouts, spacing and overflow fixes. Words stay.'],
  ['redesign', 'Redesign, keep content', 'Rebuilt with your brand’s layouts, icons and diagrams. '
    + 'Same message per slide.'],
  ['rework', 'Full rework', 'We may tighten, split, merge or reorder content, then redesign.'],
  ['selected', 'Selected changes', 'Tell us which slides and what to fix.'],
];
// Each route's steps, by name. The last is where it starts.
const NEW_STEPS = {
  scratch: ['What it is about', 'How it looks, and starting it'],
  document: ['Your document', 'What it is about', 'How it looks, and starting it'],
  existing: ['Your deck and what changes', 'What it is about', 'How it looks, and starting it'],
};
const DOCUMENT_TYPES = ['.txt', '.md', '.html', '.htm', '.docx', '.pdf'];
const DOCUMENT_BYTES = 8000000;      // the largest document the runner reads
const DECK_BYTES = 85000000;         // the largest deck the page sends, as base64 it is larger
const SOURCE_KINDS = {
  document: [['upload', 'Upload a file'], ['paste', 'Paste the text'],
    ['google', 'A Google Docs link']],
  existing: [['upload', 'Upload a .pptx'], ['google', 'A Google Slides link']],
};
// A document is a finished script, or material to build from: the two kinds classify knows.
const KINDS = { spec: 'a finished script for the slides', material: 'material to build from' };
const KIND_SAYS = {
  spec: 'Its slides are taken as it lays them out: the outline is read from it.',
  material: 'An outline is drafted from it' + ', researched first if you asked for research.',
};
const WEB_LINK = /^https?:\/\/\S+$/i;
// How the pictures of a deck's slides are made while it is drawn. What each way means is
// said under the choice.
const PREVIEWS = ['local', 'drive'];
const PREVIEW_NAMES = ['LibreOffice', 'Google Drive'];
const PREVIEW_SAYS = [
  'LibreOffice: the pictures are made on this computer, and nothing leaves it.',
  'Google Drive: each deck keeps one presentation named “Preview: …” in your Drive, written '
    + 'again at each render. Presentation Studio never deletes it.',
];
const PREVIEW_ABSENT = [
  'LibreOffice was not found on this computer, so Google Drive is the one way there is.',
  'Google access on this computer does not reach Drive, so LibreOffice is the one way there '
    + 'is.',
];
const PREVIEW_WORDS = { local: 'made with LibreOffice, on this computer',
  drive: 'made through Google Drive' };
const SEVERITIES = { critical: ['late', 'Critical'], major: ['late', 'Major'],
  minor: ['none', 'Minor'] };
const SERIOUS = ['critical', 'major'];
// What a finding is about, where drawing again would not put it right.
const ABOUT_TAGS = { content: 'About what it says', concept: 'About how it was designed' };
const CLOSE = 'You can close this page; it says when it needs you again.';
// What a team adds. Each of these is confirmed in the sheet before anything is sent.
const TEAM_SHEETS = ['take', 'hand-over', 'publish'];
const READ_ONLY = 'You can read everything here: the steps, the outline and the slides. '
  + 'Nothing here can be paused, stopped, decided or answered from this computer.';
const PUBLISH_SAYS = 'Publishing marks this deck, exactly as it stands now, as its next '
  + 'numbered revision in the workspace. Nothing is copied anywhere.';
const PUBLISH_KEPT = 'A revision is never moved afterwards. If the deck changes later, '
  + 'publish it again, and that is the next revision. What it was made from, and its '
  + 'previews, are not part of it.';
const NOTIFY_SAYS = 'When no page is open and a deck needs you, this computer tells you '
  + 'through its own notifications. It says only the deck’s title and that it needs a '
  + 'decision, once for each thing that needs you.';
const NOTIFY_DIFFERS = 'This is not the browser’s notification above. That one works only '
  + 'while this page is open in a tab; this one is for when no page is open at all.';
// Deleting a deck: what the card offers, and what its confirmation says. The runner says
// what goes and what stays for each deck; these are the words around it.
const DELETE_SAYS = 'If you no longer want this deck, delete it. It goes from this '
  + 'computer and from your team’s workspace.';
const DELETE_STOPS = 'It is working now. Deleting it stops it first, and ends everything it '
  + 'is running.';
const DELETE_SHARED = { decision: 'Your team sees it gone straight away.',
  asked: 'Your team sees it gone the next time you press Share now.' };
const DELETE_UNDO = 'This cannot be undone from this page. Its history stays in git, where '
  + 'someone who knows git can bring it back.';
const DELETE_DRIVE = 'Presentation Studio never deletes anything in your Google Drive. Remove '
  + 'these yourself if you no longer want them:';
const UPDATE_SAYS = 'Each is fetched from its own repository at the one revision this '
  + 'Presentation Studio was made with, and checked file for file before any of it is run. '
  + 'Then its own installer is run with Node, and registers the skill for every assistant it '
  + 'knows.';
const UPDATE_WAITS = 'It takes a few minutes, while you carry on. The Status screen says how '
  + 'it goes.';
const LOOK_SAYS = 'Once a day, Presentation Studio asks where it and its skills are kept which '
  + 'releases there are, and says on Home when a newer one is out. It only reads their names: '
  + 'nothing is downloaded or run, and nothing is installed without your yes.';
const BRAND_SAYS = 'Your brand skill is released from a repository of its own. Name it here, '
  + 'and Presentation Studio installs and upgrades the brand skill from it, with your own git '
  + 'access and only after your yes. A brand skill you installed yourself is still found and '
  + 'used. Every studio on this computer shares the repository and release named here, so '
  + 'saving changes them for all of them.';
const BRAND_STEPS = ['The release is fetched with your own access: its ZIP through gh, where '
  + 'gh is signed in, or else the tag with git.',
'Its own installer is run, and told to leave harness-research alone. Where it would put in '
  + 'its own harness-slides in place of the one Presentation Studio uses, nothing is run, and '
  + 'you are told.',
'Then this computer is checked again, so that new decks can use it.'];
const BRAND_TRUST = 'The repository is your choice, so the release is not checked against '
  + 'anything Presentation Studio knows. Install only from a repository you trust.';
const BRAND_WAITS = 'It takes a few minutes, while you carry on. Nothing is changed while a '
  + 'deck is working.';
const UPGRADE_KEEPS = 'The version you have now is kept beside it, so decks carry on where '
  + 'they are, and nothing of yours is touched.';
const UPGRADE_WAITS = 'It takes a minute or two, while you carry on. Nothing is changed while a '
  + 'deck is working.';
// How each row of the versions is said: its bead and its words.
const VERSION_STATES = { current: ['done', 'Up to date'], update: ['review', 'Update available'],
  missing: ['late', 'Missing'], unknown: ['none', 'Not known'] };
const COME_BACK_TRIES = 90;   // one a second, while the runner opens its newer version
const SETUP_HIDDEN = 600000;  // how often a tab nobody looks at reads what was found of versions
const OWN_NAME = 'presentation-studio';
// The decisions that take a note. `needed` is what the page says when one is missing.
const FORMS = {
  changes: {
    title: 'Ask for changes',
    label: 'What should change?',
    hint: 'Say it in your own words. Presentation Studio makes the change and brings it back '
      + 'here for your decision.',
    needed: 'Say what should change first.',
    send: 'Send for changes',
  },
};

const view = {
  token: '', screen: 'home', path: null, decks: null, listing: null, needs: 0,
  computer: undefined, known: null, sheet: '', opener: '', after: null,
  drawn: '', named: '', pushed: 0, timer: 0, turn: 0, busy: false, checking: false,
  setup: null, form: null, draft: null, run: null, agents: null, looking: false,
  unlooked: '', sharing: false, steered: '', barred: '', answers: {}, notes: {},
  // Each agent's models as the runner listed them, by agent, and the choice of a model on
  // the screen: what it is held in, and how it is drawn again once a list comes.
  models: {}, picking: null,
  // The slide the open deck's pager shows, and the way to turn to another, and the pictures
  // this screen holds: each by what it is of, those still to fetch, and what says when one
  // comes into view.
  slide: 0, viewer: null, pictures: new Map(), wanted: [], fetching: false, watcher: null,
  // What the person has chosen at the gate of the open deck, before it is sent: whether the
  // classification is wrong, the outline as edited, the slides marked for changes, another
  // brand, and the marks at a stop reviewed item by item. Each is kept for its deck and its
  // gate's round, so a refresh loses nothing.
  chosen: {},
  // What a team adds: every run and who runs what, what is published, what publishing just
  // answered, and a look for teammates' work and what it brought.
  status: null, shelf: null, issued: null, noticed: {}, looked: false, found: null,
  // What deleting the open deck would do, as the runner said when its sheet was opened.
  leaving: null,
  // Looking online for newer releases, while it is switched, and why switching it was refused.
  turningLook: false, lookRefused: '',
  // The brand skill's repository as it is typed in Settings, while it is saved, and why
  // saving it was refused.
  brandForm: null, savingBrand: false, brandRefused: '',
  // Set-up is to start from the team repository every studio now shares.
  joining: false,
  // The versions Home last told of, when set-up was last read, and the restart in hand.
  versionsTold: undefined, setupAt: 0, restarting: false, comingBack: null,
  notifying: false, unnotified: '', downloading: false, delivering: false,
  // The refresh in hand, and whether another was asked for while it was.
  refreshing: null, again: false,
  // What the decks screen is narrowed to.
  search: { text: '' },
};
// Each part of a screen that is drawn in parts, and what it was drawn from.
const PARTS = new WeakMap();
// Each place a picture goes, and which picture that is.
const PLACES = new WeakMap();

const byId = (id) => document.getElementById(id);
const main = () => byId('main');

// --- small builders ---------------------------------------------------------------

function make(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function add(parent, ...children) {
  for (const child of children) {
    if (child) parent.append(child);
  }
  return parent;
}

function count(number, one, many) {
  return number + ' ' + (number === 1 ? one : many);
}

function list(value) {
  return Array.isArray(value) ? value : [];
}

// Several things named in a row: "one, two and three".
function series(items) {
  return items.length < 2 ? items.join('')
    : items.slice(0, -1).join(', ') + ' and ' + items[items.length - 1];
}

function ago(then) {
  const minutes = Math.round((Date.now() - then) / 60000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return count(minutes, 'minute', 'minutes') + ' ago';
  const hours = Math.round(minutes / 60);
  if (hours < 24) return count(hours, 'hour', 'hours') + ' ago';
  const days = Math.round(hours / 24);
  if (days < 30) return count(days, 'day', 'days') + ' ago';
  return new Date(then).toLocaleDateString(undefined,
    { year: 'numeric', month: 'short', day: 'numeric' });
}

function when(stamp) {
  const then = Date.parse(stamp);
  if (Number.isNaN(then)) return make('span', 'quiet', 'not recorded');
  const node = make('time', '', ago(then));
  node.dateTime = new Date(then).toISOString();
  node.title = new Date(then).toLocaleString();
  return node;
}

// A limit, in the round numbers a limit is set in: 8,000,000 bytes is 8 MB.
function megabytes(bytes) {
  return String(Math.round(bytes / 100000) / 10) + ' MB';
}

function pathInto(node, path) {
  String(path).split('/').forEach((part, index) => {
    if (index) add(node, '/', document.createElement('wbr'));
    add(node, part);
  });
  return node;
}

function icon(name) {
  const node = document.createElementNS(DRAWING, 'svg');
  node.setAttribute('class', 'icon');
  node.setAttribute('viewBox', '0 0 24 24');
  node.setAttribute('aria-hidden', 'true');
  node.setAttribute('focusable', 'false');
  for (const line of ICONS[name]) {
    const path = document.createElementNS(DRAWING, 'path');
    path.setAttribute('d', line);
    node.append(path);
  }
  return node;
}

function button(label, className, action, key) {
  const node = make('button', className, label);
  node.type = 'button';
  if (key) node.dataset.key = key;
  node.addEventListener('click', action);
  return node;
}

// A capsule of glass. The highlight on it follows the pointer.
function capsule(label, kind, action, key) {
  return button(label, 'button shine' + (kind ? ' button-' + kind : ''), action, key);
}

// The filled button of a form. Pressing it, or Enter in one of the form's boxes, sends it.
function submitButton(label, key) {
  const node = make('button', 'button shine button-filled', label);
  node.type = 'submit';
  node.dataset.key = key;
  return node;
}

// A form in the page's narrow column. The browser checks nothing in it: `sent` does, and
// says what is wrong beside each box.
function pageForm(sent) {
  const node = make('form', 'narrow');
  node.noValidate = true;
  node.addEventListener('submit', (event) => {
    event.preventDefault();
    sent();
  });
  return node;
}

// A link out of the page: only to a web address the server gave, in a new tab that is
// never handed this page. Anything else is shown as the text it is.
function outLink(address, words, label) {
  if (!WEB_LINK.test(String(address || ''))) return make('span', '', words);
  const node = make('a', 'link', words);
  node.href = address;
  node.rel = 'noopener noreferrer';
  node.target = '_blank';
  node.setAttribute('aria-label', (label || words) + ', in a new tab');
  return node;
}

// A bead that says a state by its shape. The words beside it say the same thing.
function bead(kind) {
  const node = make('span', 'bead');
  node.dataset.state = kind;
  node.setAttribute('aria-hidden', 'true');
  if (BEAD_ICONS[kind]) node.append(icon(BEAD_ICONS[kind]));
  return node;
}

function state(kind, text) {
  return add(make('span', 'state'), bead(kind), make('span', '', text));
}

function card(title, className) {
  const node = make('section', 'card shine' + (className ? ' ' + className : ''));
  return add(node, make('h2', 'card-title', title));
}

function bullets(items, className) {
  const node = make('ul', className || 'plain');
  for (const item of items) node.append(make('li', '', item));
  return node;
}

function callout(kind, ...children) {
  const node = make('div', 'paper callout');
  if (kind) node.dataset.kind = kind;
  return add(node, ...children);
}

// A control with two answers, or three. Its glass thumb slides to the one that is chosen.
function segmented(label, options, at, choose, key) {
  const node = make('div', 'segmented');
  node.setAttribute('role', 'group');
  node.setAttribute('aria-label', label);
  node.dataset.at = String(at);
  node.dataset.count = String(options.length);
  const thumb = make('span', 'seg-thumb');
  thumb.setAttribute('aria-hidden', 'true');
  node.append(thumb);
  options.forEach((text, index) => {
    const option = button(text, 'seg-option', () => {
      if (index !== Number(node.dataset.at)) choose(index, node);
    }, key + ' ' + index);
    option.setAttribute('aria-pressed', String(index === at));
    node.append(option);
  });
  return node;
}

function slide(node, at) {
  node.dataset.at = String(at);
  node.querySelectorAll('.seg-option').forEach((option, index) => {
    option.setAttribute('aria-pressed', String(index === at));
  });
}

// A line beside a control that says why it was refused. It is read out when it appears.
function alertLine(id) {
  const node = make('p', 'problem');
  node.id = id;
  node.setAttribute('role', 'alert');
  node.hidden = true;
  return node;
}

function say(problem, text) {
  problem.textContent = text;
  problem.hidden = !text;
}

// A labelled box to type in. What is typed is kept in `held[name]` as it is typed, so a
// screen that is drawn again still has it. With `picked` it is the browser's own file picker
// instead: nothing of it is kept, and what is chosen is handed to `picked`. With `options`,
// each a value and its name, it is the browser's own list to choose one from. An option
// with a third word, a group's name, is put in that group with the options next to it
// that name it too.
function field(id, label, held, name, about) {
  const spec = about || {};
  const title = make('label', 'field-label', label);
  title.htmlFor = id;
  const input = make(spec.long ? 'textarea' : spec.options ? 'select' : 'input',
    'input' + (spec.short ? ' input-short' : ''));
  input.id = id;
  if (spec.long) input.rows = spec.rows || 3;
  else if (!spec.options) input.type = spec.picked ? 'file' : 'text';
  if (spec.picked) {
    input.multiple = Boolean(spec.multiple);
    input.accept = spec.accept || '';
    input.addEventListener('change', () => spec.picked(input));
  } else {
    let group = null;
    for (const [value, text, under] of spec.options || []) {
      const option = make('option', '', text);
      option.value = value;
      if (!under) group = null;
      else if (!group || group.label !== under) {
        group = make('optgroup');
        group.label = under;
        input.append(group);
      }
      (group || input).append(option);
    }
    input.value = held[name] || '';
    input.maxLength = spec.limit || (spec.long ? 4000 : 400);
    input.autocomplete = 'off';
    input.spellcheck = Boolean(spec.long);
    input.addEventListener('input', () => {
      held[name] = input.value;
      // A box that is being put right no longer says it is wrong.
      if (input.getAttribute('aria-invalid')) refuse(id, '');
      if (spec.typed) spec.typed();
    });
  }
  if (spec.mode) input.inputMode = spec.mode;
  input.dataset.key = id;
  const hint = spec.hint ? make('p', 'quiet field-hint', spec.hint) : null;
  if (hint) hint.id = id + '-hint';
  input.setAttribute('aria-describedby', (hint ? id + '-hint ' : '') + id + '-problem');
  if (spec.changed) input.addEventListener('change', spec.changed);
  const problem = alertLine(id + '-problem');
  // Drawn again after it was refused, it still says why.
  if (spec.refused) {
    say(problem, spec.refused);
    input.setAttribute('aria-invalid', 'true');
  }
  return add(make('div', 'field'), title, input, hint, problem);
}

// Refuse what is in a field, beside it, before anything is sent. Returns the field.
function refuse(id, text) {
  const input = byId(id);
  say(byId(id + '-problem'), text);
  if (text) input.setAttribute('aria-invalid', 'true');
  else input.removeAttribute('aria-invalid');
  return input;
}

// One choice among two or three, with its name above it and what it means below.
function choice(label, options, at, choose, key, hint) {
  const control = segmented(label, options, at, (index, node) => {
    slide(node, index);
    choose(index);
  }, key);
  return add(make('div', 'field'), make('p', 'field-label', label), control,
    hint ? make('p', 'quiet field-hint', hint) : null);
}

// A choice with what each of its answers means spelled out under it. The one that is chosen
// is marked there too.
function explained(label, options, says, at, choose, key) {
  const meanings = make('ul', 'reasons meanings');
  const mark = (chosen) => Array.from(meanings.children).forEach((item, index) => {
    if (index === chosen) item.dataset.chosen = 'true';
    else delete item.dataset.chosen;
  });
  for (const text of says) meanings.append(make('li', '', text));
  mark(at);
  return [choice(label, options, at, (index) => {
    choose(index);
    mark(index);
  }, key), meanings];
}

// A capsule that is on or off. A tick says it is on, so it does not rest on colour.
function chip(label, on, flip, key) {
  const node = button('', 'chip', () => {
    const now = node.getAttribute('aria-pressed') !== 'true';
    node.setAttribute('aria-pressed', String(now));
    flip(now);
  }, key);
  node.setAttribute('aria-pressed', String(Boolean(on)));
  return add(node, icon('check'), make('span', '', label));
}

// A card that is a button: one of several to pick from, with what it means under its name.
// The one that is picked says so by its tick and its words, not by colour alone.
function pickCard(title, says, picked, action, key) {
  const node = button('', 'pick-card shine', action, key);
  node.setAttribute('aria-pressed', String(Boolean(picked)));
  return add(node, add(make('span', 'pick-top'), icon('check'),
    make('span', 'pick-title', title)), says ? make('span', 'pick-says', says) : null);
}

// One thing chosen from several, in the browser's own list. Where there is only one, there
// is nothing to choose, and it is said in a line.
function oneOf(id, label, options, held, name, changed) {
  if (options.length > 1) return field(id, label, held, name, { options, changed });
  return add(make('div', 'field'), make('p', 'field-label', label),
    make('p', '', options.length ? options[0][1] : 'None'));
}

function money(dollars) {
  return '$' + Number(dollars).toFixed(2);
}

function lasted(seconds) {
  const whole = Math.round(Number(seconds));
  if (whole < 60) return count(whole, 'second', 'seconds');
  const minutes = Math.round(whole / 60);
  if (minutes < 60) return count(minutes, 'minute', 'minutes');
  return count(Math.floor(minutes / 60), 'hour', 'hours') + ' '
    + count(minutes % 60, 'minute', 'minutes');
}

function lower(text) {
  return String(text).charAt(0).toLowerCase() + String(text).slice(1);
}

function capital(text) {
  return String(text).charAt(0).toUpperCase() + String(text).slice(1);
}

// A word the runner uses for a kind or a state, as a person would write it.
function spoken(word) {
  return capital(String(word).replace(/[-_]+/g, ' '));
}

function given(value) {
  return value !== null && value !== undefined;
}

function cell(label, ...children) {
  const node = make('td');
  node.dataset.label = label;
  return add(node, ...children);
}

// --- talking to the server ---------------------------------------------------------

class PageError extends Error {
  constructor(kind, message, status) {
    super(message);
    this.kind = kind;
    this.status = status || 0;
  }
}

// One request to the server. With no answer at all, the page has lost touch with it.
async function reach(endpoint, options) {
  try {
    return await fetch('/api/' + endpoint, options);
  } catch (failure) {
    throw new PageError('stopped', NOTICES.stopped);
  }
}

// What an answer says, where it can be read, and the refusal an answer that says no makes.
async function saidBy(response) {
  try {
    return await response.json();
  } catch (failure) {
    return null;
  }
}

function refusal(response, body) {
  const said = body && body.error ? String(body.error)
    : 'Presentation Studio gave no answer this page can read.';
  return new PageError(response.status === 403 ? 'refused' : 'failed', said, response.status);
}

async function call(endpoint, options) {
  const response = await reach(endpoint, options);
  const body = await saidBy(response);
  if (response.ok && body) return body;
  throw refusal(response, body);
}

function ask(endpoint, params) {
  const query = params ? '?' + new URLSearchParams(params).toString() : '';
  return call(endpoint + query, { headers: { [TOKEN_HEADER]: view.token }, cache: 'no-store' });
}

// Bytes the server sends, read with the key in the header, which an address written into
// the page could not send.
async function bytes(response, kind) {
  if (!response.ok) throw refusal(response, await saidBy(response));
  let held = null;
  try {
    held = await response.blob();
  } catch (failure) {
    held = null;
  }
  if (!held) throw new PageError('failed', 'It did not arrive whole.');
  if (kind && !kind.test(held.type)) {
    throw new PageError('failed', 'What came back is not a picture.');
  }
  return held;
}

// One slide's picture, as its bytes.
async function picture(params) {
  return bytes(await reach('slide?' + new URLSearchParams(params).toString(),
    { headers: { [TOKEN_HEADER]: view.token }, cache: 'no-store' }), /^image\/png\b/);
}

// The rendered deck, as its bytes.
async function deckFile(path) {
  return bytes(await reach('download?' + new URLSearchParams({ path }).toString(),
    { headers: { [TOKEN_HEADER]: view.token }, cache: 'no-store' }));
}

function send(endpoint, body) {
  return call(endpoint, {
    method: 'POST',
    headers: { [TOKEN_HEADER]: view.token, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    cache: 'no-store',
  });
}

function notify(text) {
  byId('notice').textContent = text;
  byId('notice').hidden = !text;
}

function calm() {
  return Boolean(window.matchMedia
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
}

// A short message that slides in at the bottom right, is read out, and leaves by itself.
// It is kept clear of the toolbar, so it never covers the main thing to do.
function toast(text) {
  const node = make('p', 'toast glass', text);
  byId('toasts').append(node);
  window.setTimeout(() => {
    node.classList.add('toast-leaving');
    window.setTimeout(() => node.remove(), calm() ? 0 : 260);
  }, 4200);
}

// --- copying ----------------------------------------------------------------------

function copyBySelection(text) {
  const holder = make('textarea', 'offscreen');
  holder.value = text;
  holder.readOnly = true;
  holder.setAttribute('aria-hidden', 'true');
  document.body.append(holder);
  holder.select();
  let copied = false;
  try {
    copied = document.execCommand('copy');
  } catch (failure) {
    copied = false;
  }
  holder.remove();
  return copied;
}

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (failure) {
    return copyBySelection(text);
  }
}

function copyButton(label, done, text, key) {
  return capsule(label, '', async () => {
    toast(await copy(text) ? done : 'Not copied. Select the text instead.');
  }, key);
}

// --- pictures of slides ------------------------------------------------------------------
// Each picture is fetched as bytes, kept in memory, and shown from there under an address
// that only this page holds. They are fetched one at a time: the one being looked at first,
// and each of the others when its place comes into view. Leaving the screen lets go of all.

// What says when a picture's place comes into view.
function watcher() {
  if (!view.watcher) {
    view.watcher = new IntersectionObserver((seen) => {
      for (const found of seen) {
        if (!found.isIntersecting) continue;
        view.watcher.unobserve(found.target);
        wantPicture(PLACES.get(found.target), false);
      }
    }, { rootMargin: '200px' });
  }
  return view.watcher;
}

// Put a picture in line to be fetched. `first` puts it at the head of the line.
function wantPicture(place, first) {
  let held = view.pictures.get(place.key);
  if (!held) {
    held = { state: 'wanted', where: place.where, url: '', says: '' };
    view.pictures.set(place.key, held);
  }
  if (held.state !== 'wanted') return;
  const at = view.wanted.indexOf(place.key);
  if (at >= 0 && !first) return;
  if (at >= 0) view.wanted.splice(at, 1);
  if (first) view.wanted.unshift(place.key);
  else view.wanted.push(place.key);
  fetchPictures();
}

async function fetchPictures() {
  if (view.fetching) return;
  view.fetching = true;
  try {
    while (view.wanted.length) {
      const key = view.wanted.shift();
      const held = view.pictures.get(key);
      if (!held) continue;
      held.state = 'fetching';
      let found = null;
      try {
        found = await picture(held.where);
      } catch (failure) {
        held.says = failure.message;
      }
      // The screen was left meanwhile, or this picture is no longer on it: it is not kept.
      if (view.pictures.get(key) !== held) continue;
      held.state = found ? 'here' : 'failed';
      if (found) held.url = URL.createObjectURL(found);
      for (const node of document.querySelectorAll('.frame')) {
        if (PLACES.get(node).key === key) fillFrame(node);
      }
    }
  } finally {
    view.fetching = false;
  }
}

// What a picture's place shows: the picture once it is here, and words until then. A picture
// that cannot be had says so in its place, and never leaves a gap.
function fillFrame(node) {
  const place = PLACES.get(node);
  const held = view.pictures.get(place.key);
  const says = (className, text) => add(make('span', 'frame-says ' + className),
    make('span', 'offscreen', place.alt + '. '), text);
  if (held && held.state === 'here') {
    const image = make('img', 'picture');
    image.alt = place.alt;
    image.src = held.url;
    image.addEventListener('error', () => {
      node.replaceChildren(says('problem', 'What was fetched cannot be shown as a picture.'));
    });
    node.replaceChildren(image);
  } else if (held && held.state === 'failed') {
    const again = place.again ? button('Try this picture again', 'link', () => {
      view.pictures.delete(place.key);
      wantPicture(place, true);
      fillFrame(node);
      node.focus({ preventScroll: true });
    }, 'picture-again') : null;
    node.replaceChildren();
    add(node, says('problem', 'Its picture could not be fetched. ' + held.says
      + (again ? ' The deck itself is as it was.' : '')), again);
  } else {
    node.replaceChildren(says('quiet', 'Its picture is on its way.'));
  }
}

// What the server names a picture by, as it is asked for: a deck, the kind of picture, and
// a slide's number or a name.
function pictureOf(path, named) {
  const where = { path, kind: named.kind };
  if (typeof named.ref === 'number') where.number = String(named.ref);
  else where.name = String(named.ref);
  return where;
}

// The place a picture goes. `where` is what it is of, `alt` says so in words, and `mark`
// changes when a newer picture of the same thing is made. `about.first` is for the one being
// looked at, and `about.again` offers another try where one could not be fetched.
function pictureAt(where, alt, mark, about) {
  const spec = about || {};
  const node = make('span', 'frame');
  const place = { key: JSON.stringify([where, mark || '']), where, alt,
    again: Boolean(spec.again) };
  PLACES.set(node, place);
  if (place.again) node.tabIndex = -1;
  fillFrame(node);
  // A browser that cannot say when a place comes into view is asked for each in turn.
  if (spec.first || typeof IntersectionObserver === 'undefined') wantPicture(place, spec.first);
  else if (!view.pictures.has(place.key)) watcher().observe(node);
  return node;
}

// A picture that nothing on the screen shows any more, such as one of an earlier round, is
// let go.
function tidyPictures() {
  const shown = new Set(Array.from(document.querySelectorAll('.frame'))
    .map((node) => PLACES.get(node).key));
  for (const [key, held] of Array.from(view.pictures)) {
    if (shown.has(key)) continue;
    if (held.url) URL.revokeObjectURL(held.url);
    view.pictures.delete(key);
  }
  view.wanted = view.wanted.filter((key) => shown.has(key));
}

// Leaving a screen lets go of every picture it held, and stops waiting for the rest.
function letGo() {
  for (const held of view.pictures.values()) {
    if (held.url) URL.revokeObjectURL(held.url);
  }
  view.pictures = new Map();
  view.wanted = [];
  if (view.watcher) view.watcher.disconnect();
}

// --- the window: sidebar, toolbar, sheet ------------------------------------------------

function show(screen, where, replace) {
  const next = { screen, path: (where && where.path) || null };
  if (replace) {
    window.history.replaceState(next, '');
  } else {
    window.history.pushState(next, '');
    view.pushed += 1;
  }
  open(next);
}

function back() {
  if (view.pushed > 0) {
    window.history.back();
    return;
  }
  const up = { new: 'home', setup: 'settings', published: 'decks' };
  show(up[view.screen] || 'decks', null, true);
}

// Change screens with the browser's own transition where it has one, and a fade where not.
function swap(update) {
  if (document.startViewTransition && !calm()) {
    const moving = document.startViewTransition(update);
    // A transition that is overtaken by the next one is dropped; the screen is drawn anyway.
    moving.ready.catch(() => {});
    moving.finished.catch(() => {});
    return moving.updateCallbackDone;
  }
  const done = update();
  const holder = main();
  holder.classList.remove('arrive');
  holder.classList.add('arrive');
  return done;
}

function open(next) {
  view.screen = unset() ? 'setup' : next.screen || 'home';
  view.path = next.path || null;
  view.sheet = '';
  view.drawn = '';
  view.run = null;
  view.form = null;
  view.steered = '';
  view.barred = '';
  view.leaving = null;
  view.slide = 0;
  view.viewer = null;
  letGo();
  view.turn += 1;
  frame();
  const current = PARENTS[view.screen] || view.screen;
  for (const [id, screen] of NAV) {
    if (current === screen) byId(id).setAttribute('aria-current', 'page');
    else byId(id).removeAttribute('aria-current');
  }
  drawSheet();
  swap(() => draw(true));
}

// The toolbar: where you are, the way back, and the main thing to do here.
function toolbar(spec) {
  setTitle(spec.name === undefined ? spec.title : spec.name);
  byId('title').textContent = spec.title;
  // A title too long for two lines is cut there. Its whole text is a pointer away.
  byId('title').title = spec.title;
  const above = byId('above');
  above.replaceChildren(...list(spec.above).filter(Boolean));
  above.hidden = !above.childNodes.length;
  const lead = byId('toolbar-lead');
  lead.replaceChildren();
  if (spec.back) {
    const node = button('', 'button button-round shine', back, 'back');
    node.setAttribute('aria-label', 'Back');
    add(lead, add(node, icon('back')));
  }
  byId('actions').replaceChildren(...list(spec.actions).filter(Boolean));
}

// Put a screen in place. A screen drawn again, because something changed, keeps the
// reader's place: what had the focus has it again, and what was open stays open.
function place(spec, nodes, fresh) {
  const holder = main();
  const active = document.activeElement;
  const focused = !fresh && active && active.dataset ? active.dataset.key : '';
  const opened = fresh ? [] : Array.from(holder.querySelectorAll('details'))
    .filter((node) => node.open).map((node) => node.dataset.key);
  toolbar(spec);
  holder.replaceChildren(...nodes.filter(Boolean));
  for (const node of holder.querySelectorAll('details')) {
    if (opened.includes(node.dataset.key)) node.open = true;
  }
  if (fresh) {
    window.scrollTo(0, 0);
    byId('title').focus({ preventScroll: true });
    return;
  }
  if (focused) focusKey(focused);
}

function focusKey(key) {
  for (const node of document.querySelectorAll('[data-key]')) {
    if (node.dataset.key === key && !node.disabled) {
      node.focus({ preventScroll: true });
      return true;
    }
  }
  return false;
}

// The tab's title leads with how many things need the person, so it shows from another tab.
// Versions Home tells of count as one more thing.
function setTitle(name) {
  if (name !== undefined) view.named = name;
  const needs = view.needs + (versionsNotice() ? 1 : 0);
  const waiting = needs ? '(' + needs + ') ' : '';
  document.title = waiting + (view.named ? view.named + ' · ' : '') + 'Presentation Studio';
  const badge = byId('needs-count');
  badge.replaceChildren(String(needs), make('span', 'offscreen',
    needs === 1 ? ' thing needs you' : ' things need you'));
  badge.hidden = !needs;
}

// Everything a list screen is drawn from. When none of it has changed, nothing is redrawn.
function signature() {
  return JSON.stringify([view.decks, view.search, ...around()]);
}

// What a list screen's parts are drawn from, apart from the decks themselves.
function around() {
  return [view.computer, view.checking, alerts(), view.setup, view.sharing, view.status,
    view.unnotified, view.looked, view.found, view.lookRefused, view.brandRefused,
    view.savingBrand];
}

// Put parts in a holder in order. A part is [name, what it is drawn from, how it is built],
// and a node already there that was built from the same is kept where it is, untouched.
// A fourth item fills a part, whether it was kept or built: a list inside it is fitted
// the same way, one item at a time.
function fit(holder, parts, fresh) {
  const kept = new Map();
  for (const node of fresh ? [] : Array.from(holder.children)) {
    if (PARTS.has(node)) kept.set(PARTS.get(node), node);
  }
  const nodes = [];
  for (const [name, from, build, fill] of parts.filter(Boolean)) {
    const mark = name + '\n' + JSON.stringify(from);
    let node = kept.get(mark);
    if (!node) {
      node = build();
      if (!node) continue;
      PARTS.set(node, mark);
    }
    kept.delete(mark);
    if (fill) fill(node);
    nodes.push(node);
  }
  let at = holder.firstChild;
  for (const node of nodes) {
    if (node === at) at = at.nextSibling;
    else holder.insertBefore(node, at);
  }
  while (at) {
    const next = at.nextSibling;
    at.remove();
    at = next;
  }
}

function placeParts(spec, parts, fresh) {
  const holder = main();
  const active = document.activeElement;
  const focused = !fresh && active && active.dataset ? active.dataset.key : '';
  const opened = fresh ? [] : Array.from(holder.querySelectorAll('details'))
    .filter((node) => node.open).map((node) => node.dataset.key);
  const bar = JSON.stringify(spec.mark);
  if (fresh || bar !== view.barred) toolbar(spec);
  view.barred = bar;
  fit(holder, parts, fresh);
  for (const node of holder.querySelectorAll('details')) {
    if (opened.includes(node.dataset.key)) node.open = true;
  }
  if (fresh) {
    window.scrollTo(0, 0);
    byId('title').focus({ preventScroll: true });
  } else if (focused && !document.body.contains(active) && !focusKey(focused)) {
    byId('title').focus({ preventScroll: true });
  }
}

function draw(fresh) {
  if (view.screen === 'deck') return drawDeck(fresh);
  if (view.screen === 'published') return drawPublished(fresh);
  if (view.screen === 'setup' && view.setup) return drawSetup(fresh);
  const titles = { home: 'Home', decks: 'Decks', status: 'Status', settings: 'Settings',
    setup: 'Set-up', new: 'New deck' };
  if (!view.decks) {
    place({ title: titles[view.screen] || 'Home' },
      [make('p', 'quiet', 'Reading your decks.')], fresh);
    return undefined;
  }
  if (view.screen === 'new') return drawNew(fresh);
  view.drawn = signature();
  if (view.screen === 'decks') return drawDecks(fresh);
  if (view.screen === 'status') return drawStatus(fresh);
  if (view.screen === 'settings') return drawSettings(fresh);
  return drawHome(fresh);
}

// A screen that could not be read says why, and the way back, where it was being opened. One
// already on the screen stays as it is. Where the page has lost touch, the notice says so too.
function unopened(failure, shown, fresh, about) {
  const spec = about || {};
  if (failure.kind === 'stopped') notify(failure.message);
  if (shown) return;
  place({ title: spec.title || 'This cannot be opened', back: true },
    [make('p', 'problem', failure.message), spec.said ? make('p', 'quiet', spec.said) : null,
      capsule(spec.back || 'Back to home', 'filled', spec.to || (() => show('home')), 'home')],
    fresh);
}

// --- the sheet: it drops from the toolbar, and a decision is confirmed in it ---------------

function sheetTitle(text) {
  const node = make('h2', 'sheet-title', text);
  node.id = 'sheet-title';
  return node;
}

function openSheet(kind, opener) {
  return () => {
    view.sheet = kind;
    view.opener = opener;
    drawSheet();
    if (view.screen === 'deck' && view.run) paintDeck(false);
    const box = byId('note-text');
    (box || byId('sheet')).focus();
  };
}

function closeSheet() {
  const opener = view.opener;
  view.sheet = '';
  view.leaving = null;
  drawSheet();
  if (view.screen === 'deck' && view.run) paintDeck(false);
  if (!focusKey(opener)) byId('title').focus({ preventScroll: true });
}

function problemLine() {
  const node = make('p', 'problem');
  node.id = 'sheet-problem';
  node.setAttribute('role', 'alert');
  node.hidden = true;
  return node;
}

// A note is kept for the deck, its gate and the decision it was typed for.
function noteKey(kind) {
  const gate = view.run && view.run.gate ? view.run.gate.name : 'deliver';
  return [view.path, gate, kind].join('\n');
}

function noteSheet(kind) {
  const spec = FORMS[kind];
  const form = make('form', 'note');
  form.noValidate = true;
  const label = make('label', 'note-label', spec.label);
  label.htmlFor = 'note-text';
  const box = make('textarea', 'note-field');
  box.id = 'note-text';
  box.rows = 3;
  box.maxLength = 4000;
  box.dataset.key = 'note';
  box.setAttribute('aria-describedby', 'note-hint sheet-problem');
  // What was typed before the sheet was put away is here again.
  const key = noteKey(kind);
  box.value = view.notes[key] || '';
  box.addEventListener('input', () => {
    view.notes[key] = box.value;
  });
  const marked = markedSlides();
  // At a stop reviewed item by item, what is marked in its list goes with the note too.
  const gate = view.run && view.run.gate;
  const listed = !gate || !REVIEWED.includes(gate.name) || !reviewOf(gate).extra ? ''
    : gate.name === 'gate:outline' ? ' What you marked or edited in the outline goes with '
      + 'your note.' : ' What you marked in the list goes with your note.';
  const hint = make('p', 'quiet', spec.hint + (marked.length ? ' The parts of the deck '
    + 'that hold ' + slidesNamed(marked) + ', which you marked, are drawn again.' : '')
    + listed);
  hint.id = 'note-hint';
  const problem = problemLine();
  const submit = submitButton(spec.send, 'send');
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const text = box.value.trim();
    if (spec.needed && !text) {
      // Refused here, beside the control, before anything is sent.
      problem.textContent = spec.needed;
      problem.hidden = false;
      box.setAttribute('aria-invalid', 'true');
      box.focus();
      return;
    }
    decide('changes', text, problem, submit);
  });
  add(form, label, box, hint, problem,
    add(make('div', 'bar'), submit, capsule('Cancel', 'quiet', closeSheet, 'cancel')));
  return [sheetTitle(spec.title), form];
}

function drawSheet() {
  const holder = byId('sheet');
  const shown = Boolean(view.sheet && (view.run || ['companions', 'upgrade', 'brand']
    .includes(view.sheet)));
  holder.hidden = !shown;
  // While a sheet is open it holds the one filled button, so the toolbar's are put away.
  byId('actions').hidden = Boolean(shown);
  // And it is the only thing that can be reached: everything behind it is inert until it is
  // put away, by its own buttons or by Escape.
  for (const id of ['main', 'sidebar', 'toolbar']) byId(id).inert = Boolean(shown);
  if (!shown) {
    holder.replaceChildren();
    return;
  }
  let body;
  if (view.sheet === 'delete') body = deleteSheet();
  else if (view.sheet === 'companions') body = updateSheet();
  else if (view.sheet === 'upgrade') body = upgradeSheet();
  else if (view.sheet === 'brand') body = brandSheet();
  else if (TEAM_SHEETS.includes(view.sheet)) body = teamSheet(view.sheet);
  else if (FORMS[view.sheet]) body = noteSheet(view.sheet);
  else if (view.sheet === 'rebrand') body = rebrandSheet();
  else body = undoSheet();
  holder.replaceChildren(...body);
}

// --- home -------------------------------------------------------------------------

function greeting() {
  const hour = new Date().getHours();
  const hello = hour < 12 ? 'Good morning.' : hour < 18 ? 'Good afternoon.' : 'Good evening.';
  const things = view.needs < COUNTED.length ? COUNTED[view.needs]
    : view.needs + ' things need';
  return hello + ' ' + things + ' you' + (view.needs ? '.' : ' right now.');
}

function openDeck(brief) {
  return () => show('deck', { path: brief.path });
}

// How a deck began, in a few words.
function routeWords(brief) {
  const level = LEVELS.find((one) => one[0] === brief.level);
  if (brief.route === 'existing') return 'An existing deck' + (level ? ' · ' + level[1] : '');
  if (brief.route === 'document') return 'From a document';
  if (brief.route === 'scratch') return 'From scratch';
  return '';
}

function runWords(found) {
  return RUN_WORDS[found.state] || RUN_WORDS.working;
}

// Where a deck stands, as a shape and words. What a teammate runs is never said to be
// working or waiting: that is not known here.
function standingOf(brief) {
  if (elsewhere(brief)) return ['none', 'Run by ' + nameOf(brief.driver)];
  return runWords(brief);
}

function newButton(kind) {
  return capsule('New deck', kind, () => show('new'), 'new');
}

// The contact sheet of a deck, small: one picture of all its slides.
function sheetThumb(brief) {
  if (!brief.contactSheet) return null;
  return add(make('div', 'thumb'), pictureAt(pictureOf(brief.path,
    { kind: 'build', ref: 'contact-sheet' }), 'Every slide of ' + (brief.title || 'the deck'),
  brief.revision));
}

// Where a finished deck can be had: in Google Slides, or as a .pptx from its own screen.
function deliveredLine(brief) {
  if (!brief.link && !brief.pptx) return null;
  const node = make('p', 'foot-line');
  if (brief.revision) add(node, make('span', 'quiet', 'Revision ' + brief.revision));
  if (brief.link) {
    add(node, outLink(brief.link, 'Open in Google Slides',
      'Open ' + (brief.title || 'the deck') + ' in Google Slides'));
  } else {
    add(node, make('span', 'quiet', 'A .pptx, to download from its own screen.'));
  }
  return node;
}

function deckRow(brief, kind) {
  const title = brief.title || 'Untitled';
  const text = add(make('div', 'row-text'), make('h3', 'row-title', title));
  const route = routeWords(brief);
  if (route) add(text, make('p', 'quiet', route));
  if (kind !== 'needs' && kind !== 'finished') add(text, state(...standingOf(brief)));
  add(text, elsewhere(brief) ? lastLine(brief.last_shared, 'row-says')
    || make('p', 'row-says', brief.sentence || '') : make('p', 'row-says', brief.sentence || ''),
  whoLine(brief), noticeLine(brief));
  if (kind === 'finished') add(text, deliveredLine(brief), sheetThumb(brief));
  const go = capsule(kind === 'needs' ? 'Review' : 'Open', kind === 'needs' ? '' : 'quiet',
    openDeck(brief), 'open ' + brief.path);
  go.setAttribute('aria-label', go.textContent + ' ' + title);
  const row = make('li', 'row' + (kind === 'needs' ? ' row-needs' : '')
    + (brief.state === 'working' && !elsewhere(brief) ? ' working' : ''));
  const shape = kind === 'needs' ? (brief.state === 'failed' ? 'late' : 'review')
    : kind === 'finished' ? 'done' : null;
  return add(row, shape ? bead(shape) : null, text, go);
}

// A card with a row for each deck, as a part of its screen. A row is built again only when
// what it is drawn from has changed, so the others keep their place and their focus.
function rows(title, found, kind, className) {
  if (!found.length) return null;
  return ['rows ' + title, [className], () => add(card(title, className), make('ul', 'rows')),
    (node) => fit(node.querySelector('.rows'), found.map((brief) => [
      'row ' + brief.path, [brief, kind], () => deckRow(brief, kind)]))];
}

function invitation() {
  return add(make('section', 'card shine invite'),
    make('h2', 'invite-title', 'Start your first deck'),
    make('p', '', 'Start from scratch, from a document, or from a deck you already have. '
      + 'Presentation Studio researches, outlines, designs and builds it on its own, and '
      + 'stops each time it needs your decision.'),
    add(make('div', 'bar'), newButton('filled')),
    make('p', 'quiet', 'It takes two or three short steps, and this page tells you each time '
      + 'it needs you.'));
}

function alerts() {
  return typeof Notification === 'undefined' ? 'none' : Notification.permission;
}

function computerLine() {
  const node = make('p', 'foot-line');
  const result = view.computer;
  if (!result) {
    add(node, make('span', '', 'This computer has not been checked yet.'));
  } else if (result.ready) {
    add(node, state('done', 'This computer is ready.'));
  } else {
    add(node, state('late', count(list(result.wrong).length, 'thing needs', 'things need')
      + ' putting right on this computer.'));
  }
  return add(node, button(result ? 'See the details' : 'Check it on the status screen',
    'link', () => show('status'), 'computer'));
}

function every() {
  const found = view.decks || {};
  return [...list(found.needs), ...list(found.working), ...list(found.finished),
    ...list(found.elsewhere)];
}

function drawHome(fresh) {
  const found = view.decks;
  const first = list(found.needs)[0];
  const lead = first ? capsule('Review ' + (first.title || 'Untitled'), 'filled',
    openDeck(first), 'lead') : null;
  // With no deck yet, the invitation holds the one way to start one.
  const start = every().length ? newButton(lead ? '' : 'filled') : null;
  const said = greeting();
  const parts = [['greeting', [said], () => make('p', 'large-title', said)],
    ['updates', [upkeepOf()], updatesCard]];
  if (!every().length) {
    parts.push(['invite', [], invitation]);
  } else {
    parts.push(
      rows('Needs you', list(found.needs), 'needs', 'card-needs'),
      rows('In progress', list(found.working), 'working'),
      rows('Finished', list(found.finished), 'finished'),
      rows('Run by your teammates', list(found.elsewhere), 'elsewhere'));
  }
  parts.push(['foot', around(),
    () => add(make('footer', 'foot'), computerLine(), sharingLine(), fetchLine())]);
  placeParts({ title: 'Home', name: '', actions: [start, lead],
    mark: ['Home', first ? [first.path, first.title] : null, Boolean(lead)] }, parts, fresh);
  tidyPictures();
}

// --- decks ------------------------------------------------------------------------
// Every deck in the workspace, narrowed by what is typed in the search box.

function deckCard(brief) {
  const node = make('li', 'card shine' + (brief.state === 'working' && !elsewhere(brief)
    ? ' working' : ''));
  const title = brief.title || 'Untitled';
  add(node, make('h2', 'row-title', title));
  const route = routeWords(brief);
  if (route) add(node, make('p', 'quiet', route));
  add(node, state(...standingOf(brief)), make('p', 'row-says', brief.sentence || ''),
    whoLine(brief), noticeLine(brief), brief.state === 'finished' ? deliveredLine(brief) : null,
    sheetThumb(brief));
  const go = capsule('Open', '', openDeck(brief), 'open ' + brief.path);
  go.setAttribute('aria-label', 'Open ' + title);
  return add(node, add(make('div', 'bar'), go));
}

function matching() {
  const words = view.search.text.trim().toLowerCase().split(/\s+/).filter(Boolean);
  return every().filter((brief) => {
    const said = [brief.title, routeWords(brief), brief.sentence,
      brief.driver && brief.driver.name].join(' ').toLowerCase();
    return words.every((word) => said.includes(word));
  });
}

function drawDecks(fresh) {
  const all = every();
  const shown = matching();
  const parts = [];
  if (!all.length) {
    parts.push(['invite', [], invitation]);
  } else {
    parts.push(['search', [], () => add(make('div', 'narrow'),
      field('decks-search', 'Find a deck', view.search, 'text', {
        typed: () => draw(false),
        hint: 'By its title, how it began, where it stands or who runs it.' }))]);
    parts.push(['found', [shown.length, all.length], () => make('p', 'quiet',
      shown.length === all.length ? count(all.length, 'deck', 'decks') + '.'
        : shown.length + ' of ' + count(all.length, 'deck', 'decks') + ' match.')]);
    parts.push(['grid', [], () => make('ul', 'grid'), (node) => fit(node,
      shown.map((brief) => ['deck ' + brief.path, brief, () => deckCard(brief)]))]);
  }
  placeParts({ title: 'Decks', actions: [newButton('filled'),
    capsule('Published', 'quiet', () => show('published'), 'published')],
  mark: ['Decks'] }, parts, fresh);
  tidyPictures();
}

// --- status -----------------------------------------------------------------------

function fact(found, optional) {
  const shape = found.state === 'ok' ? 'done'
    : found.state === 'problem' && !optional ? 'late' : 'none';
  const words = found.label + (found.detail ? ': ' + found.detail : '')
    + (found.state === 'ok' && !found.detail ? ': yes' : '');
  return add(make('li', 'fact'), bead(shape), make('span', '', words));
}

// What can put a missing companion skill right from here: the update the runner offers.
function fixable(item) {
  const upkeep = upkeepOf();
  return Boolean(item.state !== 'ok' && upkeep && upkeep.update && upkeep.update.offered
    && wantedCompanions(upkeep).some((one) => one.name === item.id));
}

function computerItem(item) {
  const [shape, words] = COMPUTER_WORDS[item.state] || COMPUTER_WORDS.problem;
  const node = make('li', 'computer-item');
  const said = item.state !== 'ok' && item.optional ? words + ' (optional)' : words;
  add(node, add(make('div', 'computer-top'), make('h3', 'row-title', item.name),
    state(item.state !== 'ok' && item.optional ? 'none' : shape, said)));
  const facts = make('ul', 'facts');
  for (const found of list(item.facts)) facts.append(fact(found, item.optional));
  add(node, facts);
  if (item.fix) add(node, make('p', item.optional ? 'fix fix-optional' : 'fix', item.fix));
  if (fixable(item)) {
    const go = capsule('Fix it', '', openSheet('companions', 'fix ' + item.id), 'fix ' + item.id);
    go.setAttribute('aria-label', 'Fix it: bring ' + item.name);
    add(node, add(make('div', 'bar'), go));
  }
  return node;
}

async function checkComputer() {
  if (view.checking) return;
  view.checking = true;
  if (view.screen === 'setup') paintComputerSetup();
  else draw(false);
  try {
    view.computer = (await send('computer', {})).computer;
    toast(view.computer.ready ? 'This computer is ready.'
      : 'This computer needs something put right.');
  } catch (failure) {
    notify(failure.message);
  }
  view.checking = false;
  if (view.screen === 'setup') paintComputerSetup();
  else draw(false);
}

function checkButton(kind) {
  const node = capsule(view.checking ? 'Checking…' : view.computer
    ? 'Check this computer again' : 'Check this computer', kind, checkComputer,
  'check-computer');
  node.disabled = view.checking;
  return node;
}

function computerCard() {
  const node = card('This computer');
  const result = view.computer;
  if (!result) {
    return add(node, make('p', '', 'See whether this computer has what a deck needs: an '
      + 'assistant that is installed and can be reached from this network, Node, the '
      + 'research and slides skills, a brand skill, a way to make previews, and the programs '
      + 'that turn a render into pictures. It asks each one for its version and nothing '
      + 'more.'));
  }
  const summary = make('p', 'foot-line');
  if (result.ready) add(summary, state('done', 'This computer is ready.'));
  else {
    add(summary, state('late', 'Not ready yet. To put right: '
      + list(result.wrong).join(', ') + '.'));
  }
  add(summary, add(make('span', 'quiet'), 'Checked ', when(result.checked_at), '.'));
  const items = make('ul', 'computer-items');
  for (const item of list(result.items)) items.append(computerItem(item));
  return add(node, summary, items);
}

function drawStatus(fresh) {
  placeParts({ title: 'Status', actions: [checkButton('filled')],
    mark: ['Status', view.checking, Boolean(view.computer)] }, [
    ['runs', [view.status], runsCard],
    ['teammates', [view.status, teamSpace(), view.looked, view.found], teammatesCard],
    ['versions', [upkeepOf(), view.restarting], versionsCard],
    ['skills', [upkeepOf()], skillsCard],
    ['studios', studiosMark(), studiosCard],
    ['computer', [view.computer, upkeepOf()], computerCard]], fresh);
  // Every run and who runs what is asked for as the screen opens.
  if (fresh) {
    const turn = view.turn;
    readStatus().then(() => {
      if (turn === view.turn && view.drawn !== signature() && !view.checking) draw(false);
    });
  }
}

// --- settings ---------------------------------------------------------------------

function alertsCard() {
  const node = card('Notifications');
  const allowed = alerts();
  if (allowed === 'none') {
    return add(node, make('p', '', 'This browser cannot show notifications. The count beside '
      + 'Home, and in the tab title, still shows what needs you.'));
  }
  if (allowed === 'granted') {
    return add(node, state('done', 'On. This browser tells you when something needs you, '
      + 'while this page is open in a tab.'));
  }
  if (allowed === 'denied') {
    return add(node, make('p', '', 'Notifications are turned off for this page in your '
      + 'browser’s own settings. The count beside Home, and in the tab title, still shows '
      + 'what needs you.'));
  }
  return add(node, make('p', '', 'Be told when a deck needs you, even when this tab is '
    + 'behind another.'), add(make('div', 'bar'), capsule('Turn on notifications', 'filled',
    async () => {
      try {
        await Notification.requestPermission();
      } catch (failure) {
        // Older browsers answer through a callback; the next draw reads the result.
      }
      draw(false);
    }, 'alerts')));
}

// What a new deck starts with: whose it is, its brand, and where it is delivered.
function defaultsCard() {
  const held = view.setup;
  if (!held || !held.configured) return null;
  const brand = (held.brand && held.brand.default) || {};
  const output = OUTPUTS.find((one) => one[0] === held.output);
  return add(card('What a new deck starts with'),
    about([['Your name', (held.person && held.person.name) || 'not given yet'],
      ['Brand', brand.brand ? brand.brand + (brand.variant ? ', ' + brand.variant : '') : ''],
      ['Delivered as', output ? output[1] : '']]),
    add(make('div', 'bar'), capsule('Change them', 'quiet', () => show('setup'),
      'defaults')));
}

function drawSettings(fresh) {
  placeParts({ title: 'Settings', mark: ['Settings'] }, [
    ['workspace', around(), workspaceCard], ['studios', studiosMark(), studiosCard],
    ['defaults', [view.setup], defaultsCard],
    ['alerts', [alerts()], alertsCard], ['notify', around(), notifyCard],
    ['look', [view.setup && view.setup.updates, view.lookRefused], lookCard],
    ['brand-source', [view.setup && view.setup.brand && [view.setup.brand.repository,
      view.setup.brand.release], view.brandRefused, view.savingBrand], brandSourceCard],
    ['page', [], () => add(card('This page'),
      make('p', '', 'It runs on this computer and answers only to the link that opened it. '
        + 'The page sends what you read and decide nowhere else. The agent that does the '
        + 'drafting is sent what it needs for each step, by its own service.'))]], fresh);
}

// --- with the runner behind the page ---------------------------------------------------

// Nobody has said where the decks are kept. Until they have, set-up is the only screen there is.
function unset() {
  return Boolean(view.setup && !view.setup.configured);
}

function frame() {
  const alone = unset();
  byId('sidebar').hidden = alone;
  if (alone) document.body.classList.add('alone');
  else document.body.classList.remove('alone');
}

// Whether the team can see the work yet, and the way to share it when they cannot.
function sharingLine() {
  const space = view.setup ? view.setup.workspace : null;
  if (!space) return null;
  const node = make('p', 'foot-line');
  if (!space.repository) {
    return add(node, make('span', '', 'Your decks are kept in a folder on this computer, '
      + 'and are not shared with anyone.'));
  }
  if (space.shared) {
    return add(node, state('done', 'Shared: your team can see everything decided so far.'));
  }
  add(node, state(space.notice ? 'late' : 'none', space.notice
    ? 'Not shared with your team yet. ' + space.notice
      + ' The work is kept on this computer until it is.'
    : 'Not shared with your team yet: the latest work is on this computer only.'));
  const go = capsule(view.sharing ? 'Sharing…' : 'Share now', '', shareNow, 'share');
  if (view.sharing) go.setAttribute('aria-busy', 'true');
  return add(node, go);
}

// What teammates have shared is looked for every few minutes. This looks now, and says in
// a sentence what came back.
function fetchLine() {
  if (!teamSpace()) return null;
  const node = make('p', 'foot-line');
  const found = view.found;
  add(node, found ? state(found.shape, found.says) : make('span', '', 'What your teammates '
    + 'share is looked for every few minutes.'));
  const go = capsule(view.looked ? 'Looking…' : 'Look now', 'quiet', fetchNow, 'fetch');
  go.setAttribute('aria-label', view.looked ? 'Looking for what your teammates shared'
    : 'Look now for what your teammates shared');
  if (view.looked) go.setAttribute('aria-busy', 'true');
  return add(node, go);
}

async function fetchNow() {
  if (view.looked) return;
  view.looked = true;
  draw(false);
  try {
    const found = await send('fetch', {});
    const received = Number(found.received) || 0;
    if (found.reached === false) {
      view.found = { shape: 'late', says: 'Nothing new could be brought in. '
        + (found.notice || 'Your team’s repository could not be reached.') };
    } else if (found.notice) {
      view.found = { shape: 'late', says: found.notice };
    } else {
      view.found = { shape: 'done', says: received ? 'Brought in '
        + count(received, 'change', 'changes') + ' your team shared.'
        : 'Nothing new from your team since the last look.' };
    }
  } catch (failure) {
    view.found = { shape: 'late', says: failure.message + ' Nothing was changed.' };
  }
  view.looked = false;
  draw(false);
  if (!focusKey('fetch')) byId('title').focus({ preventScroll: true });
  refresh();
}

async function shareNow() {
  if (view.sharing) return;
  view.sharing = true;
  draw(false);
  let found;
  try {
    found = await send('share', {});
    toast(found.shared ? 'Shared. Your team can see it now.'
      : 'It is not shared yet. The work is still kept on this computer.');
  } catch (failure) {
    found = { shared: false, notice: failure.message };
    toast('It could not be shared. The work is still kept on this computer.');
  }
  // The set-up may have been read again meanwhile; the answer goes on the one that is held now.
  if (view.setup && view.setup.workspace) {
    view.setup.workspace.shared = Boolean(found.shared);
    view.setup.workspace.notice = found.notice || null;
  }
  view.sharing = false;
  draw(false);
  if (!focusKey('share')) byId('title').focus({ preventScroll: true });
}

function about(pairs) {
  const node = make('dl', 'about');
  for (const [name, value] of pairs) {
    if (given(value) && value !== '') add(node, make('dt', '', name), make('dd', '', value));
  }
  return node;
}

function limitsSays(limits) {
  const says = [];
  if (limits.step_seconds) says.push('A step may take up to ' + lasted(limits.step_seconds) + '.');
  if (given(limits.deck_dollars)) {
    says.push('A deck stops and asks you once it has spent ' + money(limits.deck_dollars)
      + '.');
  }
  if (limits.parallel) {
    says.push(limits.parallel === 1 ? 'One deck runs at a time.'
      : 'Up to ' + limits.parallel + ' decks run at once.');
  }
  return says.join(' ');
}

// Settings: where the decks are kept, who can see them, and the way in to change any of it.
function workspaceCard() {
  const held = view.setup;
  const space = held && held.workspace;
  if (!space) return null;
  const node = card('Workspace');
  const agent = held.agent || {};
  add(node, make('p', 'row-title', space.name || 'Your decks'),
    about([[space.repository ? 'Repository' : 'Folder on this computer',
      space.repository || space.path],
    [space.repository ? 'This computer’s copy' : '', space.repository ? space.path : ''],
    ['Folder inside it', space.folder], ['Branch', space.branch],
    ['Shared', space.repository ? lower(SHARE_SAYS[space.share_when === 'when-asked' ? 1 : 0])
      : ''],
    ['Drafting is done by', (AGENT_NAMES[agent.default] || agent.default || 'no agent yet')
      + modelWords(agent.model, agent.effort, true)],
    ['Limits', limitsSays(held.limits || {})],
    ['Slide previews', held.previews ? previewsSays(held.previews) : '']]),
    sharingLine(), fetchLine(),
    add(make('div', 'bar'), capsule('Change the set-up', '', () => show('setup'), 'setup')));
  return node;
}

// The file every studio shares, said where there is something to say: that it could not be
// read, so the built-in defaults are used; that it names another team repository than the one
// this computer works in, with the way to join it; and what moving to it left as it was.
// Nothing waits on any of them.
function studiosCard() {
  const held = view.setup;
  if (!held) return null;
  const parts = [];
  if (held.shared_problem) parts.push(make('p', 'problem', held.shared_problem));
  const moved = held.team_moved;
  if (moved && moved.says) {
    parts.push(make('p', '', moved.says), add(make('div', 'bar'),
      capsule('Join it', '', joinShared, 'join-shared')));
  }
  if (held.shared_notice) {
    parts.push(make('p', '', held.shared_notice), add(make('div', 'bar'),
      capsule('Got it', 'quiet', sharedSeen, 'shared-seen')));
  }
  return parts.length ? add(card('Your other studios'), ...parts) : null;
}

function studiosMark() {
  const held = view.setup || {};
  return [held.shared_problem, (held.team_moved || {}).says, held.shared_notice];
}

// Set-up, filled in with the team repository every studio now shares.
function joinShared() {
  view.joining = true;
  show('setup');
}

async function sharedSeen() {
  try {
    tookSetup(await send('shared', { seen: true }));
  } catch (failure) {
    toast(failure.message);
    return;
  }
  draw(false);
}

// How previews are made, as it can be on this computer now: the way that was chosen, or
// else the first way there is, or nothing where there is none. Drive is not asked about
// while LibreOffice makes them, and a way not asked about is still offered.
function previewsNow(found) {
  const can = PREVIEWS.filter((how) => found[how] || found[how] === null);
  return can.includes(found.how) ? found.how : can[0] || null;
}

// How previews are made as it is set now, in a few words for Settings.
function previewsSays(found) {
  if (found.how) {
    return PREVIEW_WORDS[found.how] + (found[found.how] ? ''
      : ', which this computer cannot do now');
  }
  return found.drive || found.local ? 'not chosen yet: choose how in the set-up'
    : 'cannot be made on this computer yet';
}

// --- set-up ------------------------------------------------------------------------
// Shown first where nothing is set up yet, and from Settings afterwards: this computer, the
// workspace, and the defaults. Each answer about where the decks are kept is checked as it is
// given, and nothing is changed until Save. Until this computer has saved settings of its own,
// what the studios on it share is what is offered.

function setupForm() {
  const held = view.setup;
  // Joining the team repository every studio now shares starts from it, not from the
  // workspace this computer has.
  const joining = view.joining ? held.team_moved : null;
  view.joining = false;
  const space = (!joining && held.workspace) || {};
  // Where nothing is set up, the team repository the studios share is offered.
  const offered = joining || (held.configured ? null : held.suggested);
  const limits = held.limits || {};
  const agent = held.agent || {};
  const local = !joining && Boolean(held.workspace) && !space.repository;
  const seconds = Number(limits.step_seconds) || 0;
  const brand = (held.brand && held.brand.default) || {};
  const shared = (offered && offered.share_when) || (held.workspace || {}).share_when;
  return settleBrand({
    where: local ? 1 : 0,
    repository: space.repository || (offered && offered.repository) || '',
    path: local ? space.path || '' : '',
    folder: space.folder || '',
    branch: space.branch || (offered && offered.branch) || '',
    name: space.name || '',
    touched: { folder: Boolean(space.folder),
      branch: Boolean(space.branch || (offered && offered.branch)), name: Boolean(space.name) },
    share: shared === 'when-asked' ? 1 : 0,
    // The values every studio shares as this form was shown them, sent back with it so
    // that one another studio changes meanwhile is never written over.
    seen: 'shared' in held ? held.shared : null,
    agent: agent.default === 'codex' ? 'codex' : 'claude',
    model: agent.model || '', other: false, effort: agent.effort || '',
    person: (held.person && held.person.name) || '',
    brand: brand.brand || '', variant: brand.variant || '',
    output: held.output === 'pptx' ? 1 : 0,
    minutes: seconds ? String(Math.round(seconds / 6) / 10) : '', seconds,
    dollars: given(limits.deck_dollars) ? String(limits.deck_dollars) : '',
    parallel: given(limits.parallel) ? String(limits.parallel) : '',
    previews: previewsNow(held.previews || {}),
    brandSkill: (brandSkills().find((skill) => skill.chosen) || brandSkills()[0] || {}).path
      || '',
    check: null, checked: '', checking: false, unchecked: '', existing: false, turn: 0,
    saving: false,
  });
}

// What is asked of the check: exactly where the decks would be kept, and nothing else.
// A folder or a branch that nobody has chosen is not asked about: the check says what it found.
function placeAsked(form) {
  const text = (value) => String(value).trim() || null;
  const chosen = (name) => (form.touched[name] || form.existing ? text(form[name]) : null);
  return { repository: form.where ? null : text(form.repository),
    path: form.where ? text(form.path) : null,
    folder: chosen('folder'), branch: chosen('branch') };
}

// A different place was named. What was found in the last one says nothing about this one.
function forgetFound(form) {
  for (const name of ['folder', 'branch', 'name']) {
    if (!form.existing && form.touched[name]) continue;
    form[name] = '';
    form.touched[name] = false;
  }
  form.existing = false;
  form.check = null;
}

function checkItem(found) {
  const item = add(make('li', 'check-item'), add(make('p', 'fact'),
    bead(found.ok ? 'done' : 'late'),
    make('span', '', capital(found.what) + (found.ok ? ': yes' : ': no'))));
  if (!found.ok && found.fix) add(item, make('p', 'fix', found.fix));
  return item;
}

function paintChecks() {
  const form = view.form;
  const holder = byId('setup-checks');
  if (!form || !holder) return;
  const nodes = [];
  if (form.checking) {
    nodes.push(make('p', 'quiet', 'Checking…'));
  } else if (form.unchecked) {
    nodes.push(make('p', 'problem', 'This could not be checked. ' + form.unchecked),
      make('p', 'quiet', 'Nothing was changed. Try “Check again”.'));
  } else if (form.check) {
    const checks = list(form.check.checks);
    const wrong = checks.filter((found) => !found.ok).length;
    const items = make('ul', 'plain check-items');
    for (const found of checks) items.append(checkItem(found));
    nodes.push(items, form.check.ok
      ? state('done', 'This is ready to use.')
      : state('late', (wrong ? count(wrong, 'thing needs', 'things need') : 'Something needs')
        + ' putting right before this can be saved. Then choose “Check again”.'));
  } else {
    nodes.push(make('p', 'quiet', form.where
      ? 'It is checked as soon as you say which folder.'
      : 'It is checked as soon as you give the address.'));
  }
  holder.replaceChildren(...nodes);
}

// What the check found is filled in. Where the team has already set Presentation Studio up in
// the repository, its folder, branch and name are theirs, and are not asked for again.
function fillFound(found) {
  const form = view.form;
  form.existing = Boolean(found.existing);
  for (const name of ['folder', 'branch', 'name']) {
    const box = byId('setup-' + name);
    if (found[name] && (form.existing || !form.touched[name])) form[name] = String(found[name]);
    if (!box) continue;
    box.value = form[name];
    box.readOnly = form.existing;
  }
  const note = byId('setup-found');
  if (!note) return;
  note.hidden = !form.existing;
  note.replaceChildren(...(form.existing ? [make('p', '', 'Presentation Studio is already set '
    + 'up here' + (found.name ? ', as “' + found.name + '”' : '') + '. Its '
    + 'folder, branch and name are read from the hub.json your team keeps there, so there is '
    + 'nothing to choose here.')] : []));
}

async function checkSetup() {
  const form = view.form;
  const asked = placeAsked(form);
  form.turn += 1;
  const turn = form.turn;
  form.unchecked = '';
  if (!asked.repository && !asked.path) {
    form.check = null;
    form.checking = false;
    fillFound({});
    paintChecks();
    return false;
  }
  form.checking = true;
  paintChecks();
  try {
    const found = await send('setup/check', asked);
    if (view.form !== form || turn !== form.turn) return false;
    form.check = found;
    fillFound(found.found || {});
  } catch (failure) {
    if (view.form !== form || turn !== form.turn) return false;
    form.check = null;
    form.unchecked = failure.message;
  }
  form.checked = JSON.stringify(placeAsked(form));
  form.checking = false;
  paintChecks();
  return Boolean(form.check && form.check.ok);
}

// An agent, as the runner found it: installed, signed in, reachable from this network.
function agentItem(found) {
  const yes = (value, unknown) => (value === true ? ['ok', ''] : value === false
    ? ['problem', 'no'] : ['unknown', unknown]);
  const facts = [{ label: 'Installed', state: found.installed ? 'ok' : 'problem',
    detail: found.installed ? found.version || '' : 'not found' }];
  if (found.installed) {
    const [signed, signedSays] = yes(found.signed_in, 'cannot be asked');
    const [reached, reachedSays] = yes(found.reachable, 'not known');
    facts.push({ label: 'Signed in', state: signed, detail: signedSays },
      { label: 'Reachable from this network', state: reached, detail: reachedSays });
  }
  const usable = found.installed && found.signed_in !== false && found.reachable !== false
    && !found.problem;
  return computerItem({ id: found.agent, name: AGENT_NAMES[found.agent] || found.agent,
    state: usable ? 'ok' : found.installed ? 'problem' : 'missing', facts,
    fix: found.problem || '' });
}

function paintAgents() {
  const holder = byId('agents');
  if (!holder) return;
  const nodes = [];
  if (view.looking && !view.agents) {
    nodes.push(make('p', 'quiet', 'Looking for the agents on this computer…'));
  } else if (view.unlooked) {
    nodes.push(make('p', 'problem', 'The agents could not be looked for. ' + view.unlooked),
      make('p', 'quiet', 'Nothing was changed. Try “Look again”.'));
  } else if (view.agents) {
    const items = make('ul', 'computer-items');
    for (const found of view.agents) items.append(agentItem(found));
    nodes.push(items);
    if (!view.agents.length) {
      nodes.push(make('p', 'problem', 'No agent was found on this computer. Install Claude '
        + 'Code or Codex, sign in to it, then choose “Look again”.'));
    }
  }
  holder.replaceChildren(...nodes);
}

async function readAgents() {
  if (view.looking) return;
  view.looking = true;
  paintAgents();
  try {
    view.agents = list((await ask('agents')).agents);
    view.unlooked = '';
  } catch (failure) {
    view.unlooked = failure.message;
  }
  view.looking = false;
  paintAgents();
}

// A reasoning level as a person would say it.
function levelName(level) {
  return LEVEL_NAMES[level] || spoken(level);
}

// The model and the reasoning level, in words that follow an agent's name. With `own`, a
// model left to the agent is said so.
function modelWords(model, effort, own) {
  const level = effort ? 'reasoning set to ' + lower(levelName(effort)) : '';
  if (model || own) {
    return ', with the model ' + (model || 'it chooses itself') + (level ? ' and ' + level : '');
  }
  return level ? ', with ' + level : '';
}

// What the runner listed for an agent: its models, and the levels a model it does not list
// may be given. Nothing while it is being asked, or where it could not be listed.
function listedFor(agent) {
  const found = view.models[agent];
  return found && found.models ? found : null;
}

// The levels the chosen model takes, or null while that is not known.
function levelsFor(held) {
  const found = listedFor(held.agent);
  if (!found) return null;
  const model = held.other ? null : found.models.find((one) => one.name === held.model);
  return list(model ? model.levels : found.levels);
}

// Hold a choice to what the agent listed: a model it does not list is typed in as another,
// and a level the model does not take is left to the agent again.
function settlePick(held) {
  const found = listedFor(held.agent);
  if (!found) return;
  if (held.model && !found.models.some((one) => one.name === held.model)) held.other = true;
  if (held.effort && !levelsFor(held).includes(held.effort)) held.effort = '';
}

// Ask the runner which models an agent has. It is asked apart from the page's refresh and
// holds nothing up: the choice is drawn again when the list comes. A list is asked for once,
// and one that could not be made again a minute later, or at once with `again`.
async function readModels(agent, again) {
  const known = view.models[agent];
  if (known && (known.asking || known.models
    || (!again && Date.now() - known.at < MODELS_AGAIN))) return;
  view.models[agent] = { asking: true };
  paintPick();
  let found;
  try {
    found = await ask('models', { agent });
  } catch (failure) {
    found = { problem: failure.message };
  }
  view.models[agent] = found.problem ? { problem: String(found.problem), at: Date.now() }
    : { models: list(found.models).filter((one) => one && typeof one.name === 'string'),
      levels: list(found.levels), source: found.source || '' };
  paintPick();
}

function paintPick() {
  if (!view.picking) return;
  settlePick(view.picking.held);
  view.picking.fill();
}

// The model, from the agent's own list, and how hard it reasons, from the levels that model
// takes. Models of one family are a group, and what the agent says of a model follows its
// name. "Another model…" is for a name the list does not have, and stays where the list
// could not be made. A model that takes no level is offered none.
function modelFields(held, prefix, fill, told) {
  const name = AGENT_NAMES[held.agent] || held.agent;
  const known = view.models[held.agent] || { asking: true };
  const found = listedFor(held.agent);
  const listed = found ? found.models : [];
  const model = held.other ? null : listed.find((one) => one.name === held.model);
  const options = [['', OWN_CHOICE], ...listed.map((one) => [one.name,
    (one.label || one.name) + (one.about ? ': ' + one.about : ''), one.family || ''])];
  // Until the list comes, a model already chosen is offered as it is.
  if (!found && held.model && !held.other) options.push([held.model, held.model]);
  options.push([OTHER_MODEL, 'Another model…']);
  const pick = { model: held.other ? OTHER_MODEL : held.model };
  const nodes = [field(prefix + '-model', 'Its model', pick, 'model', { options,
    changed: () => {
      if (pick.model === OTHER_MODEL) {
        if (!held.other && found) held.model = '';
        held.other = true;
      } else {
        held.other = false;
        held.model = pick.model;
      }
      settlePick(held);
      fill();
    },
    hint: 'As ' + (found && found.source ? 'the ' + found.source + ',' : name) + ' lists '
      + 'them. Its own choice is the model it uses when none is named.' })];
  if (known.asking) {
    nodes.push(make('p', 'quiet', 'Asking ' + name + ' which models it has…'));
  } else if (!found) {
    const problem = make('p', 'problem', name + '’s models could not be listed. '
      + known.problem);
    problem.setAttribute('role', 'status');
    nodes.push(problem, make('p', 'quiet', 'Choose “Another model…” to give one by its name, '
      + 'or try “Look again”.'));
  }
  if (held.other) {
    nodes.push(field(prefix + '-model-name', 'The model’s name', held, 'model', { typed: told,
      hint: 'As ' + name + ' knows it, with no spaces.' }));
  }
  const levels = levelsFor(held);
  if (model && !list(model.levels).length) {
    nodes.push(make('p', 'quiet', (model.label || model.name) + ' takes no reasoning level.'));
    return nodes;
  }
  const usual = model && model.default_level
    ? ' (' + lower(levelName(model.default_level)) + ')' : '';
  const choices = [['', OWN_CHOICE + usual], ...list(levels).map((level) => [level,
    levelName(level)])];
  if (!levels && held.effort) choices.push([held.effort, levelName(held.effort)]);
  nodes.push(field(prefix + '-effort', 'Its reasoning level', held, 'effort', {
    options: choices, changed: told,
    hint: 'How much it thinks before it answers: more is slower, and costs more. Only the '
      + 'levels this model takes are offered.' }));
  return nodes;
}

// Which agent, which of its models, and how hard it reasons. The same questions are asked at
// set-up, for the default, and at the last step of a new deck, for that deck.
// `told` is called whenever the answer changes.
function agentFields(held, prefix, label, told) {
  const found = make('div', 'agents');
  found.id = 'agents';
  found.setAttribute('role', 'status');
  const picks = make('div', 'fields');
  settlePick(held);
  const fill = () => {
    const active = document.activeElement;
    const focused = active && active.dataset && picks.contains(active) ? active.dataset.key : '';
    picks.replaceChildren(...modelFields(held, prefix, fill, told));
    if (focused) focusKey(focused);
    if (told) told();
  };
  view.picking = { held, fill };
  fill();
  return [found,
    add(make('div', 'bar'), capsule('Look again', 'quiet', () => {
      readAgents();
      readModels(held.agent, true);
    }, 'agents-again')),
    choice(label, AGENTS.map((name) => AGENT_NAMES[name]), AGENTS.indexOf(held.agent),
      (index) => {
        held.agent = AGENTS[index];
        held.model = '';
        held.other = false;
        settlePick(held);
        fill();
        readModels(held.agent);
      }, prefix + '-agent'),
    picks];
}

// The first part of set-up: whether this computer has what a deck needs, and a way to put
// right what the runner itself can bring.
function computerSetupCard() {
  const node = computerCard();
  node.id = 'setup-computer';
  node.querySelector('.card-title').textContent = 'Check this computer';
  return add(node, add(make('div', 'bar'), checkButton('quiet')));
}

// Set-up is drawn once, under the person filling it in: only its check of this computer is
// drawn again, as a look at it goes.
function paintComputerSetup() {
  const held = byId('setup-computer');
  if (!held) return;
  const focused = held.contains(document.activeElement);
  const node = computerSetupCard();
  held.parentNode.insertBefore(node, held);
  held.remove();
  if (focused) focusKey('check-computer');
}

function placeCard(form) {
  const node = card('Workspace: where your decks are kept');
  const again = () => {
    checkSetup();
  };
  const moved = () => {
    forgetFound(form);
    checkSetup();
  };
  add(node, choice('Kept in', ['Join our team repository', 'Just this computer'], form.where,
    (index) => {
      form.where = index;
      forgetFound(form);
      paintSetup(false);
      checkSetup();
    }, 'where'));
  if (form.where) {
    add(node, field('setup-path', 'The folder', form, 'path', { changed: moved,
      hint: 'A folder on this computer, for trying things out. Nothing in it is shared with '
        + 'anyone.' }));
  } else {
    add(node, field('setup-repository', 'The repository’s address', form, 'repository', {
      changed: moved,
      hint: 'The address you would clone it from. Presentation Studio keeps a copy of its own '
        + 'on this computer, and writes inside one folder of the repository, beside whatever '
        + 'is there, and nowhere else.' }));
  }
  const found = make('div', 'paper callout');
  found.id = 'setup-found';
  found.hidden = true;
  const touch = (name) => () => {
    form.touched[name] = true;
  };
  add(node, found,
    field('setup-folder', 'The folder inside it', form, 'folder', { changed: again,
      typed: touch('folder'), hint: 'Everything Presentation Studio writes goes in this '
        + 'folder: presentations, unless you say otherwise.' }),
    field('setup-branch', 'The branch', form, 'branch', { changed: again,
      typed: touch('branch') }),
    field('setup-name', 'A name for this workspace', form, 'name', { typed: touch('name'),
      hint: 'What your team calls this collection of decks: a short name with no spaces, '
        + 'such as field-decks.' }));
  const checks = make('div', 'checks');
  checks.id = 'setup-checks';
  checks.setAttribute('role', 'status');
  return add(node, make('h3', 'row-title', 'Checked for you'), checks,
    add(make('div', 'bar'), capsule('Check again', 'quiet', again, 'check-again')));
}

function shareCard(form) {
  return add(card('When your team sees the work'), ...explained('Share',
    ['After each decision', 'Only when I ask'], SHARE_SAYS, form.share, (index) => {
      form.share = index;
    }, 'share-when'));
}

function limitsCard(form) {
  const node = card('Limits');
  return add(node, make('p', '', 'These keep a deck from running away with your time or '
    + 'your money. A deck that reaches one stops and asks you.'),
  field('setup-minutes', 'The longest a step may take, in minutes', form, 'minutes',
    { short: true, mode: 'decimal' }),
  field('setup-dollars', 'The most a deck may spend, in dollars', form, 'dollars',
    { short: true, mode: 'decimal', hint: 'Counted where the agent says what it spends.' }),
  field('setup-parallel', 'How many decks may run at once', form, 'parallel',
    { short: true, mode: 'numeric' }));
}

// The brand skills found on this computer, each as the runner names it and where it is.
function brandSkills() {
  return list(((view.setup || {}).brand || {}).skills).filter((skill) => skill && skill.path);
}

// The brands a deck can be made in, as the brand skill on this computer lists them.
function brandsFound() {
  const found = (view.setup && view.setup.brand) || {};
  return found.found ? list(found.brands) : [];
}

// Hold a choice to a brand the brand skill has, and one of that brand's variants.
function settleBrand(held) {
  const brands = brandsFound();
  const chosen = brands.find((brand) => brand.brand === held.brand) || brands[0];
  const variants = list(chosen && chosen.variants);
  held.brand = chosen ? chosen.brand : '';
  held.variant = variants.includes(held.variant) ? held.variant : variants[0] || '';
  return held;
}

// The brand a deck is made in, and which of its variants: both as the brand skill on this
// computer lists them. Choosing another brand offers that brand's variants.
function brandFields(held, prefix) {
  const found = (view.setup && view.setup.brand) || {};
  const brands = brandsFound();
  const node = make('div', 'fields');
  if (!brands.length) {
    return add(node, make('p', 'fix', 'No brand skill is installed on this computer yet, so '
      + 'there is no brand to choose. A deck can still be started: it is made up to the '
      + 'point it needs your brand, and waits there. Name the brand skill’s repository in '
      + 'Settings to install it.'));
  }
  const fill = () => {
    const chosen = brands.find((brand) => brand.brand === held.brand) || {};
    const variants = list(chosen.variants);
    node.replaceChildren();
    add(node, oneOf(prefix + '-brand', 'The brand',
      brands.map((brand) => [brand.brand, brand.name || brand.brand]), held, 'brand', () => {
        settleBrand(held);
        fill();
        focusKey(prefix + '-brand');
      }),
    variants.length ? oneOf(prefix + '-variant', 'The brand’s variant',
      variants.map((variant) => [variant, variant]), held, 'variant') : null,
    make('p', 'quiet field-hint', 'A deck is always made in a brand. '
      + (found.name ? 'These are what ' + found.name + ', the brand skill on this computer, '
        + 'offers.' : 'These are what the brand skill on this computer offers.')));
  };
  fill();
  return node;
}

// What a new deck starts with. Each can still be changed for one deck as it is started.
// Where the brand skill is installed from is Settings' own card (brandSourceCard).
function defaultsSetupCard(form) {
  const held = view.setup;
  return add(card('Defaults'),
    make('p', '', 'What every new deck starts with. You can change any of it for one deck as '
      + 'you start it.'),
    held.shared_problem ? make('p', 'fix', held.shared_problem) : null,
    field('setup-person', 'Your name', form, 'person',
      { hint: 'How your teammates see who runs a deck and who decided what.' }),
    brandFields(form, 'setup'),
    ...explained('Delivered as', OUTPUTS.map((one) => one[1]), OUTPUT_SAYS, form.output,
      (index) => {
        form.output = index;
      }, 'setup-output'),
    make('p', 'quiet', 'Your team’s repository, when to share, your name, the agent, the '
      + 'brand and the output are shared by every studio on this computer, so saving them '
      + 'here changes them for all of them.'));
}

// Which brand skill decks are made with. It is a choice only where more than one was found.
// Two with one name are told apart by where each is.
function brandSkillCard(form) {
  const skills = brandSkills();
  if (skills.length < 2) return null;
  const twice = (name) => skills.filter((skill) => skill.name === name).length > 1;
  return add(card('The brand skill decks are made with'),
    make('p', '', 'A slide deck is always made in a brand, and a brand skill holds the '
      + 'brands. More than one was found on this computer.'),
    oneOf('setup-brand-skill', 'Use this brand skill', skills.map((skill) => [skill.path,
      (skill.name || skill.path) + (twice(skill.name) ? ' (' + skill.path + ')' : '')]),
    form, 'brandSkill'),
    make('p', 'quiet field-hint', 'A new deck offers the brands of the one chosen here.'));
}

// How the pictures of a deck's slides are made. Each way says what it means, and a way this
// computer cannot do says so and cannot be chosen.
function previewsCard(form) {
  const found = view.setup.previews;
  if (!found) return null;
  const node = card('How slide previews are made');
  add(node, make('p', '', 'At every decision after the first, you see the slides themselves: '
    + 'each slide is turned into a picture. A deck cannot be made without them.'));
  if (!form.previews) {
    return add(node, state('late', 'This computer cannot make them yet.'),
      make('p', 'fix', 'It needs LibreOffice, or Google access that reaches Drive. The Status '
        + 'screen says what a deck needs.'));
  }
  const [control, meanings] = explained('Make them with', PREVIEW_NAMES, PREVIEW_SAYS,
    PREVIEWS.indexOf(form.previews), (index) => {
      form.previews = PREVIEWS[index];
    }, 'previews');
  add(node, control, meanings);
  PREVIEWS.forEach((how, index) => {
    if (found[how] || found[how] === null) return;
    const option = control.querySelectorAll('.seg-option')[index];
    option.disabled = true;
    option.classList.add('seg-absent');
    add(node, make('p', 'fix', PREVIEW_ABSENT[index]));
  });
  if (found.how && found.how !== form.previews) {
    add(node, make('p', 'problem', PREVIEW_NAMES[PREVIEWS.indexOf(found.how)] + ' was chosen '
      + 'before, and this computer cannot use it now. Save to use the other way.'));
  }
  return node;
}

function paintSetup(fresh) {
  const form = view.form;
  const first = !view.setup.configured;
  view.drawn = 'setup';
  const problem = alertLine('setup-problem');
  const save = submitButton(first ? 'Save and go on' : 'Save', 'save');
  const intro = add(make('div', 'intro'),
    first ? make('p', 'large-title', 'Welcome. Let’s get you set up.') : null,
    make('p', 'lede', 'Check this computer, say where your team keeps its decks, and choose '
      + 'what a new deck starts with. Each answer is checked as you give it, and nothing is '
      + 'changed until you save.' + (first ? ' Then you can start your first deck.' : '')));
  // The set-up is a form, so Enter in a box saves as the filled button does.
  const body = add(pageForm(() => saveSetup(save)), intro,
    first ? computerSetupCard() : null, placeCard(form),
    form.where ? null : shareCard(form),
    add(card('The agent that does the drafting'),
      make('p', '', 'An agent is the AI that drafts each stage for you to decide on. It has '
        + 'to be installed on this computer and signed in.'),
      ...agentFields(form, 'setup', 'Use by default')),
    defaultsSetupCard(form), brandSkillCard(form), previewsCard(form), limitsCard(form),
    add(make('div', 'form-foot'), problem, add(make('div', 'bar'), save,
      first ? null : capsule('Cancel', 'quiet', back, 'cancel'))));
  place({ title: first ? 'Set up Presentation Studio' : 'Set-up', name: 'Set-up',
    above: first ? [] : [make('span', '', 'Settings')], back: !first }, [body], fresh);
  fillFound((form.check && form.check.found) || (form.existing ? { existing: true } : {}));
  paintChecks();
  paintAgents();
}

function drawSetup(fresh) {
  if (!fresh && view.drawn === 'setup') return;
  if (!view.form) view.form = setupForm();
  paintSetup(true);
  checkSetup();
  readAgents();
  readModels(view.form.agent);
}

// A limit as a number, or nothing when what was typed is not one that can be used.
function limit(id, text, whole) {
  const value = Number(String(text).trim());
  const fine = String(text).trim() !== '' && Number.isFinite(value) && value > 0
    && (!whole || Number.isInteger(value));
  refuse(id, fine ? '' : whole ? 'Give a whole number, 1 or more.'
    : 'Give a number greater than 0.');
  return fine ? value : null;
}

async function saveSetup(pressed) {
  const form = view.form;
  if (form.saving) return;
  const problem = byId('setup-problem');
  say(problem, '');
  const asked = placeAsked(form);
  const where = form.where ? 'setup-path' : 'setup-repository';
  const missing = [];
  const need = (id, value, text) => {
    if (!refuse(id, value ? '' : text).getAttribute('aria-invalid')) return;
    missing.push(id);
  };
  need(where, asked.repository || asked.path, form.where ? 'Say which folder first.'
    : 'Give the repository’s address first.');
  const minutes = limit('setup-minutes', form.minutes, false);
  const dollars = limit('setup-dollars', form.dollars, false);
  const parallel = limit('setup-parallel', form.parallel, true);
  for (const [id, value] of [['setup-minutes', minutes], ['setup-dollars', dollars],
    ['setup-parallel', parallel]]) {
    if (value === null) missing.push(id);
  }
  if (missing.length) {
    say(problem, 'Something above is missing. Nothing was saved.');
    byId(missing[0]).focus();
    return;
  }
  form.saving = true;
  pressed.disabled = true;
  const done = (text) => {
    form.saving = false;
    pressed.disabled = false;
    say(problem, text);
    if (text) pressed.focus();
  };
  // Never save a place that has not been checked as it now stands.
  if (form.checking || !form.check || form.checked !== JSON.stringify(asked)) await checkSetup();
  if (view.form !== form) return;
  if (!form.check || !form.check.ok) {
    done('Where your decks are kept needs putting right first: see “Checked for you” '
      + 'above. Nothing was saved.');
    return;
  }
  for (const [name, text] of [['folder', 'Say which folder inside it.'],
    ['branch', 'Say which branch.'], ['name', 'Give it a name.']]) {
    need('setup-' + name, form[name].trim(), text);
  }
  // What the repository already says is taken as it is. What was typed here has to be plain.
  for (const name of form.existing ? [] : ['folder', 'name']) {
    const id = 'setup-' + name;
    if (missing.includes(id) || PLAIN_NAME.test(form[name].trim())) continue;
    refuse(id, PLAIN_SAYS);
    missing.push(id);
  }
  if (missing.length) {
    done('Something above is missing or cannot be used. Nothing was saved.');
    byId(missing[0]).focus();
    return;
  }
  // Minutes are shown to the nearest tenth. A time nobody changed is saved as it was.
  const kept = form.seconds && minutes === Math.round(form.seconds / 6) / 10;
  const body = { folder: form.folder.trim(), branch: form.branch.trim(),
    name: form.name.trim(), share_when: form.where ? SHARE[1] : SHARE[form.share],
    agent: form.agent, model: form.model.trim() || null, effort: form.effort || null,
    person: form.person.trim() || null, output: OUTPUTS[form.output][0],
    limits: { step_seconds: kept ? form.seconds : Math.max(1, Math.round(minutes * 60)),
      deck_dollars: dollars, parallel } };
  if (form.where) body.path = asked.path;
  else body.repository = asked.repository;
  if (form.brand) {
    body.brand = form.brand;
    body.variant = form.variant || null;
  }
  // Where this computer can make previews in neither way, there is no choice to send.
  if (form.previews) body.previews = form.previews;
  // With one brand skill, or none, there is nothing to choose and nothing to send.
  if (brandSkills().length > 1 && form.brandSkill) body.brand_skill = form.brandSkill;
  // The computer's own notification is switched in Settings, and is saved as it stands.
  if (view.setup.notify) body.notify = Boolean(view.setup.notify.on);
  if (form.seen) body.shared_seen = form.seen;
  const first = !view.setup.configured;
  let saved;
  try {
    saved = await send('setup', body);
  } catch (failure) {
    done(failure.message + ' Nothing was saved, and your answers are still here: change what '
      + 'it names and save again.');
    return;
  }
  tookSetup(saved);
  form.saving = false;
  frame();
  toast(first ? 'You are set up. Now start your first deck.' : 'The set-up is saved.');
  if (first || view.pushed === 0) show(first ? 'home' : 'settings', null, true);
  else back();
}

// --- a new deck ------------------------------------------------------------------------
// Three cards, one for each way a deck begins. Each opens two or three short steps with only
// that route's questions, and a default for every choice. Nothing is sent until the last one.

function newDraft() {
  const agent = (view.setup && view.setup.agent) || {};
  const brand = (view.setup && view.setup.brand && view.setup.brand.default) || {};
  return settleBrand({ route: null, step: 0, title: '', audience: '', goal: '', minutes: '',
    research: false, level: null, selected: '', source: 0, link: '', text: '', upload: null,
    reading: false, brand: brand.brand || '', variant: brand.variant || '',
    output: view.setup && view.setup.output === 'pptx' ? 1 : 0,
    agent: agent.default === 'codex' ? 'codex' : 'claude', model: agent.model || '',
    other: false, effort: agent.effort || '', starting: false });
}

function stepsOf(draft) {
  return NEW_STEPS[draft.route] || [];
}

function sourceKind(draft) {
  const kinds = SOURCE_KINDS[draft.route] || [];
  return (kinds[draft.source] || kinds[0] || [''])[0];
}

// The three ways to begin, as cards. Choosing one opens its first step.
function routeStep() {
  const node = make('div', 'pick-cards');
  node.setAttribute('role', 'group');
  node.setAttribute('aria-label', 'How the deck begins');
  for (const [route, title, says] of ROUTES) {
    add(node, pickCard(title, says, view.draft.route === route, () => {
      view.draft.route = route;
      view.draft.step = 0;
      view.draft.research = false;
      paintNew(true);
    }, 'route ' + route));
  }
  return [make('p', 'lede', 'How does this deck begin?'), node];
}

// Why a file cannot be used, or nothing when it can.
function unfit(file, draft) {
  const at = String(file.name).lastIndexOf('.');
  const ending = at < 0 ? '' : String(file.name).slice(at).toLowerCase();
  const deck = draft.route === 'existing';
  const types = deck ? ['.pptx'] : DOCUMENT_TYPES;
  const most = deck ? DECK_BYTES : DOCUMENT_BYTES;
  if (!types.includes(ending)) {
    return file.name + ' cannot be used: only ' + series(types) + ' files are taken.';
  }
  if (file.size > most) {
    return file.name + ' cannot be used: it is ' + megabytes(file.size) + ', and '
      + (deck ? 'a deck' : 'a document') + ' can be at most ' + megabytes(most) + '.';
  }
  if (!file.size) return file.name + ' is empty. Choose another file.';
  return '';
}

// A file as the runner takes it, in base64. The browser reads it, and puts a few words about
// its kind in front, up to a comma, which are left off.
function base64Of(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const read = String(reader.result);
      const at = read.indexOf(',');
      resolve(at < 0 ? '' : read.slice(at + 1));
    };
    reader.onerror = () => reject(new Error('This browser could not read it.'));
    reader.readAsDataURL(file);
  });
}

// A file was chosen. It is read here at once, so that nothing waits on it when the deck
// starts, and what was chosen is said beside the picker.
async function pickFile(input) {
  const draft = view.draft;
  const file = Array.from(input.files || [])[0];
  if (!file) return;
  const wrong = unfit(file, draft);
  if (wrong) {
    draft.upload = null;
    refuse('new-file', wrong);
    paintChosen();
    return;
  }
  refuse('new-file', '');
  draft.reading = true;
  paintChosen();
  try {
    draft.upload = { name: file.name, size: file.size, encoded: await base64Of(file) };
  } catch (failure) {
    draft.upload = null;
    refuse('new-file', file.name + ' could not be read. ' + failure.message);
  }
  draft.reading = false;
  if (view.draft === draft) paintChosen();
}

function paintChosen() {
  const holder = byId('new-chosen');
  const draft = view.draft;
  if (!holder || !draft) return;
  if (draft.reading) holder.replaceChildren(make('p', 'quiet', 'Reading the file…'));
  else paintChosenLater(holder);
}

// Where the document or the deck comes from: a file, pasted text, or a Google link.
function sourceFields(draft) {
  const kinds = SOURCE_KINDS[draft.route];
  const deck = draft.route === 'existing';
  const holder = make('div', 'fields');
  const fill = () => {
    const kind = sourceKind(draft);
    holder.replaceChildren();
    if (kind === 'upload') {
      const chosen = make('div', '');
      chosen.id = 'new-chosen';
      chosen.setAttribute('role', 'status');
      add(holder, field('new-file', deck ? 'The deck, as a .pptx' : 'The document', {}, 'file',
        { picked: pickFile, accept: deck ? '.pptx' : DOCUMENT_TYPES.join(','),
          hint: deck ? 'At most ' + megabytes(DECK_BYTES) + '. It stays on this computer, '
            + 'and is never changed.' : series(DOCUMENT_TYPES) + ', at most '
            + megabytes(DOCUMENT_BYTES) + '. It stays on this computer and is never shared.' }),
      chosen);
      paintChosenLater(chosen);
    } else if (kind === 'paste') {
      add(holder, field('new-text', 'The text', draft, 'text', { long: true, rows: 8,
        limit: 200000, hint: 'Paste it whole. It stays on this computer and is never '
          + 'shared.' }));
    } else {
      add(holder, field('new-link', deck ? 'The Google Slides link' : 'The Google Docs link',
        draft, 'link', { hint: 'The address of the ' + (deck ? 'presentation' : 'document')
          + ', or its ID. It is read with your own Google access on this computer.' }));
    }
  };
  fill();
  return [choice(deck ? 'Where the deck is' : 'Where the document is',
    kinds.map((one) => one[1]), draft.source, (index) => {
      draft.source = index;
      fill();
    }, 'new-source'), holder];
}

// The picker says what was chosen as soon as it is on the screen.
function paintChosenLater(node) {
  const draft = view.draft;
  node.replaceChildren(draft && draft.upload ? state('done', 'Chosen: ' + draft.upload.name
    + ', ' + megabytes(draft.upload.size) + '.') : make('p', 'quiet', 'Nothing chosen yet.'));
}

function documentStep(draft) {
  return [add(card('Your document'), make('p', '', 'A script, notes, a write-up or a '
    + 'transcript. It is read first, and you confirm whether it is a finished script for the '
    + 'slides or material to build from.'), ...sourceFields(draft))];
}

// How much of an existing deck changes, as five cards with what each does.
function levelCards(draft) {
  const node = make('div', 'pick-cards');
  node.setAttribute('role', 'group');
  node.setAttribute('aria-label', 'How much changes');
  for (const [level, title, says] of LEVELS) {
    add(node, pickCard(title, says, draft.level === level, () => {
      draft.level = level;
      say(byId('new-level-problem'), '');
      for (const other of node.querySelectorAll('.pick-card')) {
        other.setAttribute('aria-pressed', String(other.dataset.key === 'level ' + level));
      }
      byId('new-selected-part').hidden = level !== 'selected';
    }, 'level ' + level));
  }
  const selected = add(make('div', ''), field('new-selected', 'Which slides, and what to fix',
    draft, 'selected', { long: true, hint: 'For example: “Slides 3 and 7: the chart is '
      + 'unreadable. Slide 12: shorten the bullets.” Only those slides change.' }));
  selected.id = 'new-selected-part';
  selected.hidden = draft.level !== 'selected';
  return [make('p', 'field-label', 'How much changes'), node, alertLine('new-level-problem'),
    selected];
}

function deckStep(draft) {
  return [add(card('Your deck'), make('p', '', 'The original is never changed: what you get '
    + 'is always a new copy.'), ...sourceFields(draft)),
  add(card('What changes'), ...levelCards(draft))];
}

function aboutStep(draft) {
  const research = draft.route !== 'existing' ? chip('Research it first', draft.research,
    (on) => {
      draft.research = on;
    }, 'research') : null;
  return [add(card('About it'),
    field('new-title', 'A short title', draft, 'title',
      { limit: 120, hint: 'What it is called in every list, for example “Rolling restarts”.' }),
    field('new-audience', 'Who is it for?', draft, 'audience', { long: true, limit: 2000,
      hint: 'Their role, and what they already know.' }),
    field('new-goal', 'What should they take away?', draft, 'goal', { long: true, limit: 2000,
      hint: 'A sentence or two is enough.' }),
    field('new-minutes', 'About how long, in minutes (optional)', draft, 'minutes',
      { short: true, mode: 'numeric' }),
    research ? add(make('div', 'field'), research, make('p', 'quiet field-hint',
      draft.route === 'document' ? 'Only where your document turns out to be material to '
        + 'build from. You approve the research plan, then the findings, before the outline '
        + 'is drafted.' : 'You approve the research plan, then the findings, before the '
        + 'outline is drafted.')) : null)];
}

// The decisions a deck will ask for, in the order it asks.
function asksFor(draft) {
  const asks = [];
  if (draft.route !== 'scratch') {
    asks.push(draft.route === 'document' ? 'what kind of document it is' : 'the slides read '
      + 'from your deck');
  }
  if (draft.research && draft.route !== 'existing') asks.push('the research plan',
    'the research');
  const level = draft.route === 'existing' ? draft.level : null;
  if (!level || level === 'rework') asks.push('the outline');
  if (!level || ['redesign', 'rework'].includes(level)) asks.push('the brand, on your cover');
  asks.push('the deck itself');
  return asks;
}

function startStep(draft) {
  const drafted = make('p', '');
  const told = () => {
    drafted.textContent = 'It is drafted by ' + AGENT_NAMES[draft.agent]
      + modelWords(draft.model.trim(), draft.effort, true) + '.';
  };
  const limits = (view.setup && view.setup.limits) || {};
  return [add(card('How it looks'), brandFields(draft, 'new'),
    ...explained('Delivered as', OUTPUTS.map((one) => one[1]), OUTPUT_SAYS, draft.output,
      (index) => {
        draft.output = index;
      }, 'new-output')),
  add(card('The agent that does the drafting'),
    ...agentFields(draft, 'new', 'For this deck', told)),
  add(card('Limits'), make('p', '', limitsSays(limits)
    || 'No limits are set for this computer.'),
  make('p', 'quiet', 'A deck that reaches a limit stops and asks you. The limits are changed '
    + 'in Settings.')),
  add(callout('', make('h2', 'aside-title', 'What happens when you start')),
    make('p', '', 'It starts at once and works on its own. It stops and asks for your '
      + 'decision on ' + series(asksFor(draft)) + '. From the first decision on, you see the '
      + 'slides themselves.'),
    drafted, make('p', 'quiet', 'This page tells you each time. In between, you can close '
      + 'it.'))];
}

function paintNew(fresh) {
  const draft = view.draft;
  view.drawn = 'new';
  const problem = alertLine('new-problem');
  if (!draft.route) {
    place({ title: 'New deck', back: true }, [add(make('div', 'narrow'), ...routeStep())],
      fresh);
    return;
  }
  const steps = stepsOf(draft);
  const builders = { scratch: [aboutStep, startStep],
    document: [documentStep, aboutStep, startStep],
    existing: [deckStep, aboutStep, startStep] }[draft.route];
  const last = draft.step === steps.length - 1;
  const go = submitButton(last ? 'Start the deck' : 'Continue', 'continue');
  const earlier = capsule(draft.step ? 'Back a step' : 'Another way to begin', 'quiet', () => {
    if (draft.step) draft.step -= 1;
    else draft.route = null;
    paintNew(true);
  }, 'earlier');
  // Each step is a form, so Enter in a box goes on as the filled button does.
  const body = add(pageForm(() => (last ? startDeck(go) : nextStep())),
    ...builders[draft.step](draft),
    add(make('div', 'form-foot'), problem, add(make('div', 'bar'), earlier, go)));
  const route = ROUTES.find((one) => one[0] === draft.route);
  place({ title: steps[draft.step], name: 'New deck', back: true,
    above: [make('span', '', route[1] + ' · Step ' + (draft.step + 1) + ' of '
      + steps.length)] }, [body], fresh);
  if (last) paintAgents();
}

function drawNew(fresh) {
  if (!fresh && view.drawn === 'new') return;
  if (!view.draft) view.draft = newDraft();
  paintNew(true);
  if (view.draft.route && view.draft.step === stepsOf(view.draft).length - 1) {
    readAgents();
    readModels(view.draft.agent);
  }
}

// What is missing on the step on the screen, said beside each box. True when nothing is.
function stepReady(draft) {
  const name = stepsOf(draft)[draft.step];
  const missing = [];
  const need = (id, wanted, text) => {
    if (refuse(id, wanted ? '' : text).getAttribute('aria-invalid')) missing.push(id);
  };
  if (name === 'Your document' || name === 'Your deck and what changes') {
    const kind = sourceKind(draft);
    if (kind === 'upload') {
      need('new-file', draft.upload && !draft.reading, draft.reading
        ? 'Wait a moment: the file is still being read.' : 'Choose the file first.');
    } else if (kind === 'paste') {
      need('new-text', draft.text.trim(), 'Paste the text first.');
    } else {
      need('new-link', draft.link.trim(), 'Give the link first.');
    }
    if (draft.route === 'existing') {
      if (!draft.level) {
        say(byId('new-level-problem'), 'Choose how much changes.');
        missing.push('level ' + LEVELS[0][0]);
      } else if (draft.level === 'selected') {
        need('new-selected', draft.selected.trim(), 'Say which slides, and what to fix.');
      }
    }
  }
  if (name === 'What it is about') {
    need('new-title', draft.title.trim(), 'Give it a title first.');
    const minutes = draft.minutes.trim();
    const number = Number(minutes);
    need('new-minutes', !minutes || (Number.isInteger(number) && number >= 1 && number <= 240),
      'Give a whole number of minutes, from 1 to 240, or leave it empty.');
  }
  say(byId('new-problem'), missing.length ? 'Something above is missing.' : '');
  if (missing.length && !focusKey(missing[0])) byId(missing[0]).focus();
  return !missing.length;
}

function nextStep() {
  const draft = view.draft;
  if (!stepReady(draft)) return;
  draft.step += 1;
  paintNew(true);
  if (draft.step === stepsOf(draft).length - 1) {
    readAgents();
    readModels(draft.agent);
  }
}

// The form as the runner reads it, and what was uploaded with it.
function formOf(draft) {
  const minutes = draft.minutes.trim();
  const form = { route: draft.route, title: draft.title.trim(),
    audience: draft.audience.trim(), goal: draft.goal.trim(),
    minutes: minutes ? Number(minutes) : null, brand: draft.brand,
    variant: draft.variant || null, output: OUTPUTS[draft.output][0],
    research: draft.route !== 'existing' && draft.research,
    agent: draft.agent, model: draft.model.trim() || null, effort: draft.effort || null };
  const uploads = {};
  if (draft.route === 'existing') {
    form.level = draft.level;
    if (draft.level === 'selected') form.selected = draft.selected.trim();
  }
  if (draft.route !== 'scratch') {
    const kind = sourceKind(draft);
    if (kind === 'upload') {
      form.source = { kind, name: draft.upload.name };
      uploads[draft.upload.name] = draft.upload.encoded;
    } else if (kind === 'paste') {
      form.source = { kind, text: draft.text };
    } else {
      form.source = { kind, link: draft.link.trim() };
    }
  }
  return [form, uploads];
}

async function startDeck(pressed) {
  const draft = view.draft;
  if (draft.starting) return;
  const problem = byId('new-problem');
  if (!draft.brand && brandsFound().length) {
    say(problem, 'Choose the brand the deck is made in.');
    return;
  }
  const [form, uploads] = formOf(draft);
  draft.starting = true;
  pressed.disabled = true;
  say(problem, '');
  let started;
  try {
    started = await send('decks', { form, uploads });
  } catch (failure) {
    draft.starting = false;
    pressed.disabled = false;
    say(problem, failure.message + (failure.kind === 'stopped' ? ''
      : ' Nothing was started.') + ' Your answers are still here.');
    pressed.focus();
    return;
  }
  view.draft = null;
  toast('Started. It is working on its own now.');
  show('deck', { path: started.path }, true);
  refresh();
}

// --- one deck ------------------------------------------------------------------------------
// Where a deck stands on its stages, what it is doing, and the gate it waits at, with the
// slides themselves from the first decision on. It is drawn in parts, and a part that has not
// changed is left exactly as it is, so a choice being made stays under the cursor while the
// rest of the screen keeps up with the run.

// What the person has chosen at a gate and not sent yet: kept for the deck, the gate and its
// round, so that a refresh, or a gate that comes round again, starts from what is true.
function chosenFor(gate) {
  const key = [view.path, gate ? gate.name : 'deliver', gate ? gate.round : ''].join('\n');
  if (!view.chosen[key]) view.chosen[key] = { wrong: false, work: null, edited: false,
    marked: [], adding: '', brand: '', variant: '', dropped: [], reword: {}, again: {},
    leftOut: null, added: [], asking: '', slideNotes: {} };
  return view.chosen[key];
}

function forget(gate) {
  delete view.chosen[[view.path, gate ? gate.name : 'deliver', gate ? gate.round : '']
    .join('\n')];
}

// The slides marked for changes at the deck's gate, by number, in order.
function markedSlides() {
  const gate = view.run && view.run.gate;
  if (!gate || gate.name !== 'gate:build') return [];
  return chosenFor(gate).marked.slice().sort((one, other) => one - other);
}

function slideName(slide) {
  return 'Slide ' + slide.number + (slide.title ? ': ' + slide.title : '');
}

// Slides by their numbers: "slide 3", "slides 3 to 5", or "slides 3, 5 and 8".
function slidesNamed(numbers) {
  const held = list(numbers);
  if (held.length < 2) return held.length ? 'slide ' + held[0] : 'no slide';
  const row = held.length > 2 && held.every((number, index) => !index
    || number === held[index - 1] + 1);
  return 'slides ' + (row ? held[0] + ' to ' + held[held.length - 1]
    : series(held.map(String)));
}

// A deck someone else's computer runs, or nobody does, is read here and never changed.
function theirs(run) {
  return run.mine === false;
}

function deckStanding(run) {
  if (theirs(run)) return run.driver ? RUN_WORDS.elsewhere : ['off', 'Nobody is running it'];
  if (queued(run)) return ['none', 'Waiting its turn'];
  return runWords(run);
}

function deckIntro(run) {
  const node = add(make('div', 'intro'), state(...deckStanding(run)),
    make('p', 'lede run-says', run.sentence));
  const stands = theirs(run) ? '' : run.state;
  if (queued(run) && stands) add(node, make('p', '', queueSays(run.queue)));
  if (stands === 'working') {
    add(node, make('p', 'quiet', 'Nothing is needed from you right now. It carries on by '
      + 'itself, and this page tells you when it needs you.'));
  } else if (stands === 'paused') {
    add(node, make('p', 'quiet', 'Nothing more is started until you resume it. Everything '
      + 'made so far is kept.'));
  } else if (stands === 'stopped' && !run.problem) {
    add(node, make('p', 'quiet', 'Everything made so far is kept. Resume, and it carries on '
      + 'from where it stopped.'));
  }
  if (view.steered) {
    const problem = make('p', 'problem', view.steered);
    problem.setAttribute('role', 'alert');
    add(node, problem);
  }
  return node;
}

// --- one deck: its stages ------------------------------------------------------------------

// Each stage of the deck, as the steps it has say: done, the one it is at, still to come,
// or, for rehearsing with Yoodli, coming later.
function stagesOf(run) {
  const rows = list(run.timeline);
  const found = [];
  for (const [stage, name] of STAGES) {
    const own = rows.filter((row) => row.stage === stage);
    if (!own.length && stage !== 'rehearse') continue;
    let at = 'upcoming';
    if (stage === 'rehearse') at = 'later';
    else if (own.every((row) => row.state === 'done')) at = 'done';
    else if (own.some((row) => row.state === 'current')) at = 'current';
    const failed = own.some((row) => row.failed);
    found.push({ stage, name, at, failed,
      waiting: at === 'current' && run.gate && own.some((row) => row.name === run.gate.name) });
  }
  return found;
}

function stageBead(found) {
  if (found.failed) return ['late', 'Stopped here'];
  if (found.waiting) return ['review', 'Waiting for you'];
  return STEP_WORDS[found.at];
}

function timelinePart(run) {
  const row = make('ol', 'beads timeline');
  row.setAttribute('aria-label', 'Its stages');
  for (const found of stagesOf(run)) {
    const [shape, words] = stageBead(found);
    const item = make('li', 'bead-stage');
    item.dataset.state = found.waiting ? 'review' : found.at;
    add(item, bead(shape), make('span', 'bead-name', found.name),
      make('span', found.at === 'later' ? 'bead-later' : 'offscreen',
        (found.at === 'later' ? '' : ': ') + words));
    row.append(item);
  }
  return add(make('section', 'card shine'), make('h2', 'card-title', 'Where it is'), row);
}

// What a step has taken so far.
function stepFacts(step) {
  const facts = [];
  if (String(step.name).startsWith('gate:')) facts.push('Your decision');
  if (step.attempts > 1) facts.push(count(step.attempts, 'try', 'tries'));
  if (given(step.seconds)) facts.push(lasted(step.seconds));
  if (given(step.dollars)) facts.push(money(step.dollars));
  return facts.join(' · ');
}

function stepItem(step) {
  const later = step.state === 'later';
  const [shape, words] = step.failed ? ['late', 'Stopped here'] : STEP_WORDS[step.state]
    || STEP_WORDS.upcoming;
  const facts = make('p', 'quiet step-facts', stepFacts(step));
  facts.hidden = !facts.textContent;
  const label = later ? 'Rehearse with Yoodli' : step.label;
  const text = add(make('div', 'row-text'), make('p', 'step-name', label), facts);
  if (step.error) add(text, make('p', step.failed ? 'problem' : 'quiet', step.error));
  const item = make('li', 'row step' + (step.state === 'current' ? ' working' : ''));
  item.dataset.state = step.state;
  return add(item, bead(shape), text, make('span', 'step-words', words));
}

function stepsCard(run) {
  const node = make('details', 'card shine steps');
  node.dataset.key = 'steps';
  const items = make('ol', 'rows');
  for (const step of list(run.timeline)) items.append(stepItem(step));
  return add(node, make('summary', 'card-title', 'Every step'), items);
}

// --- one deck: what it asks ----------------------------------------------------------------

// What went wrong, what was kept, and the one thing to do about it.
function problemPart(run, lead) {
  const found = run.problem;
  const label = found.action === 'retry' ? 'Try again' : 'Resume';
  const go = found.action && !theirs(run)
    ? capsule(label, lead ? 'filled' : '', () => steer(found.action, go), 'problem-action')
    : null;
  const title = found.state === 'failed' ? (theirs(run) ? 'It has stopped'
    : 'It has stopped, and needs you') : found.state === 'paused' ? 'It is paused'
    : 'It is stopped';
  return callout(found.state === 'failed' ? 'late' : '', make('h2', 'aside-title', title),
    add(make('p', ''), make('strong', '', 'What happened: '), found.why || ''),
    found.kept ? add(make('p', ''), make('strong', '', 'What was kept: '), found.kept) : null,
    go ? add(make('div', 'bar'), go) : null);
}

// A question from a worker, with a box to answer in. What is typed is kept as it is typed.
function questionPart(run, title) {
  const question = run.question;
  const key = view.path + '\n' + question.id;
  const label = add(make('label', 'field-label', 'Your answer'),
    make('span', 'offscreen', ' for ' + title));
  label.htmlFor = 'answer-run';
  const box = make('textarea', 'input');
  box.id = 'answer-run';
  box.rows = 3;
  box.maxLength = 4000;
  box.value = view.answers[key] || '';
  box.dataset.key = 'answer ' + key;
  box.setAttribute('aria-describedby', 'answer-run-problem');
  box.addEventListener('input', () => {
    view.answers[key] = box.value;
  });
  const problem = alertLine('answer-run-problem');
  const go = capsule('Send answer', 'filled', () => sendAnswer(question, box, problem, go),
    'send ' + key);
  return add(card('Needs you', 'card-needs'), add(make('div', 'answer'),
    make('p', 'row-says', (question.from || 'A worker') + ' asks:'),
    make('p', 'row-quote', question.text), label, box, problem, add(make('div', 'bar'), go)));
}

async function sendAnswer(question, box, problem, pressed) {
  const text = box.value.trim();
  if (!text) {
    // Refused here, beside the box, before anything is sent.
    say(problem, 'Write your answer first.');
    box.setAttribute('aria-invalid', 'true');
    box.focus();
    return;
  }
  if (view.busy) return;
  const turn = view.turn;
  const path = view.path;
  view.busy = true;
  pressed.disabled = true;
  try {
    const run = await send('answer', { path, id: question.id, answer: text });
    delete view.answers[path + '\n' + question.id];
    view.busy = false;
    toast('Your answer is sent. It carries on from here.');
    if (turn === view.turn) {
      view.run = run;
      paintDeck(false);
      window.scrollTo(0, 0);
      byId('title').focus({ preventScroll: true });
    }
    refresh();
  } catch (failure) {
    say(problem, failure.message + ' Your answer is still here, and nothing was sent.');
    pressed.disabled = false;
  }
  view.busy = false;
}

// --- one deck: the slides ------------------------------------------------------------------
// One slide at full size with the way to the next and the one before, and all of them in a
// strip to jump by. What is said of the slide on the stage is drawn under it by `about`.

function pager(slides, about) {
  const node = make('section', 'slides');
  node.id = 'slides';
  node.setAttribute('aria-label', 'The slides');
  if (!slides.some((one) => one.number === view.slide)) view.slide = slides[0].number;
  const at = () => slides.findIndex((one) => one.number === view.slide);
  const stage = make('div', 'paper stage');
  stage.id = 'slide-stage';
  stage.tabIndex = -1;
  stage.dataset.key = 'slide-stage';
  const now = make('p', 'slide-now');
  now.setAttribute('role', 'status');
  const earlier = capsule('Previous', '', () => view.viewer.move(-1), 'slide-previous');
  const later = capsule('Next', '', () => view.viewer.move(1), 'slide-next');
  earlier.setAttribute('aria-label', 'Previous slide');
  later.setAttribute('aria-label', 'Next slide');
  const said = make('div', 'slide-about');
  const strip = make('ol', 'strip');
  strip.setAttribute('aria-label', 'Every slide');
  const items = slides.map((one) => {
    const item = button('', 'strip-item', () => view.viewer.go(one.number),
      'slide ' + one.number);
    item.setAttribute('aria-label', slideName(one) + (one.changed ? ', changed' : ''));
    add(strip, add(make('li'), add(item, pictureAt(one.where, slideName(one), one.mark),
      make('span', 'strip-number', String(one.number)),
      make('span', 'strip-title', one.title || ''),
      one.changed ? make('span', 'tag', 'Changed') : null)));
    return item;
  });
  // Turning to a slide changes only what is in the stage, so nothing else loses its place.
  const turn = () => {
    const index = at();
    const shown = slides[index];
    // Where the focus was on what is about to go, it stays on the stage, not nowhere.
    const within = stage.contains(document.activeElement)
      || said.contains(document.activeElement);
    stage.replaceChildren(pictureAt(shown.where, slideName(shown), shown.mark,
      { first: true, again: true }));
    said.replaceChildren(...(about ? about(shown) : []).filter(Boolean));
    if (within) stage.focus({ preventScroll: true });
    now.textContent = 'Slide ' + shown.number + ' of ' + slides.length
      + (shown.title ? ': ' + shown.title : '') + (shown.changed ? ' (changed)' : '');
    // At either end the control stays where the keyboard can find it, and says it is off.
    earlier.setAttribute('aria-disabled', String(index === 0));
    later.setAttribute('aria-disabled', String(index === slides.length - 1));
    items.forEach((item, other) => {
      if (other === index) item.setAttribute('aria-current', 'true');
      else item.removeAttribute('aria-current');
    });
    // The strip follows the slide that is shown, sideways only: the page itself stays put.
    const held = items[index].parentNode;
    const past = held.offsetLeft + held.offsetWidth - strip.clientWidth;
    if (held.offsetLeft < strip.scrollLeft) strip.scrollLeft = held.offsetLeft;
    else if (past > strip.scrollLeft) strip.scrollLeft = past;
  };
  view.viewer = {
    move(by) {
      const next = slides[at() + by];
      if (next) this.go(next.number);
    },
    go(number, look) {
      if (slides.some((one) => one.number === number)) {
        view.slide = number;
        turn();
      }
      // Reached from a finding, the slide itself is where the reader is taken.
      if (look) stage.focus();
    },
  };
  turn();
  return add(node, stage, add(make('div', 'bar slide-moves'), earlier, later, now), said, strip);
}

// --- one deck: the gate it waits at --------------------------------------------------------

// A document drawn from markdown, by the page's own renderer.
function documentPart(label, text) {
  const node = make('article', 'paper doc');
  node.setAttribute('aria-label', label);
  if (!String(text || '').trim()) {
    return add(node, make('p', 'quiet', 'Nothing has been written here yet.'));
  }
  return add(node, window.TrainingStudioMarkdown.render(String(text), { files: false }));
}

// What the worker said of its work, and what the person asked for last time round.
function gateSaid(gate) {
  const parts = [];
  if (gate.round > 1 && gate.note) {
    parts.push(add(make('p', ''), make('strong', '', 'You asked for: '), gate.note));
  }
  if (typeof gate.said === 'string' && gate.said.trim()) {
    parts.push(add(make('p', 'quiet'), make('strong', '', 'It says of its work: '), gate.said));
  }
  return parts;
}

// The classification of a document: a finished script, or material, with the way to say it
// is wrong. Of a deck: its slides as they are, with what the inventory found.
function classifyPanel(gate, readonly) {
  const node = card('What you gave us');
  if (gate.kind === 'deck') {
    const slides = list(gate.inventory);
    const pictured = new Set(list(gate.pictures).map((one) => one.ref));
    add(node, make('p', '', 'Your deck has ' + count(slides.length, 'slide', 'slides') + '.'
      + (gate.source ? ' It was read from ' + gate.source + '.' : '')),
    make('p', 'quiet', 'These are its slides as they are now. Approve, and it carries on from '
      + 'them; nothing in the original is ever changed.'));
    const shown = slides.filter((one) => pictured.has(one.number)).map((one) => ({
      number: one.number, title: one.title || '', words: one.words, hidden: one.hidden,
      where: pictureOf(view.path, { kind: 'original', ref: one.number }), mark: 'original' }));
    if (shown.length) {
      add(node, pager(shown, (one) => [make('p', 'quiet', count(Number(one.words) || 0,
        'word', 'words') + ' on it.' + (one.hidden ? ' It is hidden in the deck.' : ''))]));
    } else {
      add(node, make('p', 'quiet', 'There are no pictures of its slides on this computer.'));
    }
    return add(node, ...gateSaid(gate));
  }
  const verdict = KINDS[gate.verdict] ? gate.verdict : 'material';
  const other = verdict === 'spec' ? 'material' : 'spec';
  const held = chosenFor(gate);
  add(node, make('p', 'lede', 'It reads as ' + KINDS[verdict] + '.'),
    gate.reason ? make('p', '', gate.reason) : null,
    gate.slides ? make('p', 'quiet', 'Slides it lays out: ' + gate.slides) : null,
    gate.corrected ? make('p', 'quiet', 'You corrected this before.') : null,
    make('p', 'quiet', KIND_SAYS[verdict]));
  const documents = list(gate.documents);
  if (documents.length) {
    add(node, make('h3', 'row-title', 'Read from'), bullets(documents.map((one) => (one.title
      || one.name) + (one.readable === false ? ' (it could not be read)' : ''))));
  }
  if (!readonly) {
    const then = make('p', '');
    const tell = () => {
      then.textContent = held.wrong ? 'It will be taken as ' + KINDS[other] + ' instead. '
        + KIND_SAYS[other] : '';
      then.hidden = !held.wrong;
    };
    tell();
    add(node, add(make('div', 'field'), chip('That’s wrong', held.wrong, (on) => {
      held.wrong = on;
      tell();
    }, 'wrong'), make('p', 'quiet field-hint', 'Press it if this is really '
      + KINDS[other] + '. Your word is taken: it is not asked again.')), then);
  }
  return add(node, ...gateSaid(gate));
}

// The research plan: each question with the way to drop or reword it, and a box for one
// more. Drops go with Approve; rewording and new questions go back to be redrafted.
function researchPlanPanel(gate, readonly) {
  const node = card('The research plan');
  const questions = list(gate.questions);
  const searched = questions.filter((item) => item.search).length;
  add(node, reviewCounts([[questions.length, questions.length === 1 ? 'question'
    : 'questions'], [searched, 'searched on the web']]));
  if (!readonly) {
    add(node, make('p', '', 'Drop a question, or reword it. A drop takes effect when you '
      + 'approve; rewording and new questions go back to be redrafted, and come back here.'));
  }
  const items = make('ol', 'plain review-list');
  items.id = 'plan-list';
  add(node, items);
  paintPlan(gate, items, readonly);
  if (!readonly) add(node, addedPart(gate), reviewBar(gate));
  return add(node, fullText('Read the full plan', 'The research plan', gate.text, 'plan-text'),
    ...gateSaid(gate));
}

// The plan's questions. They are drawn again together, since dropping one can leave
// another the last, which cannot be dropped.
function paintPlan(gate, holder, readonly) {
  if (!holder) return;
  holder.replaceChildren(...list(gate.questions).map((item) => planRow(gate, item,
    readonly)));
}

function planRow(gate, item, readonly) {
  const held = chosenFor(gate);
  const title = item.title || item.id;
  const dropped = held.dropped.includes(item.id);
  const rewording = !dropped && owns(held.reword, item.id);
  // The runner refuses a plan with every question dropped: research needs one to look up.
  const last = !dropped && list(gate.questions)
    .filter((one) => !held.dropped.includes(one.id)).length < 2;
  const row = make('li', 'review-row' + (dropped ? ' review-off' : ''));
  add(row, make('p', 'row-title', title), make('p', '', item.question),
    item.search ? make('p', 'quiet', 'Searched for: ' + item.search) : null);
  if (readonly) return row;
  if (dropped) add(row, make('p', 'quiet', 'Dropped: it is not researched.'));
  if (rewording) {
    add(row, field('reword-' + item.id, 'New wording for “' + title + '”', held.reword,
      item.id, { long: true, limit: 1000, typed: () => reviewChanged(gate) }));
  }
  const redraw = (key) => {
    paintPlan(gate, byId('plan-list'), false);
    reviewChanged(gate);
    focusKey(key);
  };
  const drop = capsule(dropped ? 'Keep' : 'Drop', 'quiet', () => {
    held.dropped = dropped ? held.dropped.filter((id) => id !== item.id)
      : [...held.dropped, item.id];
    delete held.reword[item.id];
    redraw('drop ' + item.id);
  }, 'drop ' + item.id);
  drop.setAttribute('aria-label', (dropped ? 'Keep “' : 'Drop “') + title + '”');
  let why = null;
  if (last) {
    drop.disabled = true;
    why = make('p', 'quiet', 'The last question left cannot be dropped: research needs '
      + 'something to look up.');
    why.id = 'drop-why-' + item.id;
    drop.setAttribute('aria-describedby', why.id);
  }
  const reword = dropped ? null : capsule(rewording ? 'Keep the wording' : 'Reword', 'quiet',
    () => {
      if (rewording) delete held.reword[item.id];
      else held.reword[item.id] = item.question;
      redraw(rewording ? 'reword ' + item.id : 'reword-' + item.id);
    }, 'reword ' + item.id);
  if (reword) {
    reword.setAttribute('aria-label', (rewording ? 'Keep the wording of “' : 'Reword “')
      + title + '”');
  }
  return add(row, why, add(make('div', 'bar'), drop, reword));
}

function researchPanel(gate) {
  const node = card('What the research found');
  const verdicts = Object.values(gate.verdicts || {});
  if (verdicts.length) {
    const counted = {};
    for (const said of verdicts) counted[said] = (counted[said] || 0) + 1;
    add(node, make('p', '', series(Object.entries(counted).map(([said, number]) => number
      + ' ' + lower(spoken(said))))));
  }
  return add(node, documentPart('The research report', gate.text), ...gateSaid(gate));
}

// The outline as it stands here: the server's, or the person's edit of it.
function outlineWork(gate) {
  const held = chosenFor(gate);
  if (!held.work) held.work = JSON.parse(JSON.stringify(list(gate.slides)));
  return held.work;
}

function outlineEdited(gate) {
  chosenFor(gate).edited = true;
  paintOutline(gate, byId('outline-list'), byId('outline-said'));
}

// A name for a slide that is added, unlike every other slide's.
function newSlideId(title, slides) {
  const base = 'added-' + (String(title).toLowerCase().replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '').slice(0, 28).replace(/-+$/, '') || 'slide');
  let ident = base;
  for (let number = 2; slides.some((one) => one.id === ident); number += 1) {
    ident = base + '-' + number;
  }
  return ident;
}

function outlineRow(gate, slides, index, readonly) {
  const one = slides[index];
  const title = one.title || 'Untitled slide';
  const node = make('li', 'outline-slide');
  add(node, make('p', 'outline-top', 'Slide ' + (index + 1)
    + (one.kind ? ' · ' + spoken(one.kind) : '')));
  if (readonly) add(node, make('p', 'outline-title', title));
  else {
    add(node, field('outline-title-' + index, 'Title of slide ' + (index + 1), one, 'title',
      { limit: 300, typed: () => {
        chosenFor(gate).edited = true;
        paintOutlineSaid(gate, byId('outline-said'));
      } }));
  }
  for (const text of [one.subtitle, one.understand]) {
    if (text) add(node, make('p', 'outline-said', text));
  }
  const points = list(one.points).filter((point) => point && (point.label || point.text));
  if (points.length) {
    add(node, bullets(points.map((point) => (point.label && point.text
      ? point.label + ': ' + point.text : point.label || point.text)), 'outline-points'));
  }
  if (one.notes) add(node, make('p', 'outline-notes quiet', 'Notes: ' + one.notes));
  if (readonly) return node;
  const move = (by) => () => {
    const [taken] = slides.splice(index, 1);
    slides.splice(index + by, 0, taken);
    outlineEdited(gate);
    focusKey('outline ' + (by < 0 ? 'up ' : 'down ') + taken.id);
  };
  const up = capsule('Move up', 'quiet', move(-1), 'outline up ' + one.id);
  const down = capsule('Move down', 'quiet', move(1), 'outline down ' + one.id);
  const remove = capsule('Remove', 'quiet', () => {
    slides.splice(index, 1);
    outlineEdited(gate);
    if (!focusKey('outline-add')) byId('title').focus({ preventScroll: true });
  }, 'outline remove ' + one.id);
  up.setAttribute('aria-label', 'Move “' + title + '” up');
  down.setAttribute('aria-label', 'Move “' + title + '” down');
  remove.setAttribute('aria-label', 'Remove “' + title + '”');
  up.disabled = index === 0;
  down.disabled = index === slides.length - 1;
  remove.disabled = slides.length < 2;
  return add(node, add(make('div', 'bar'), up, down, remove));
}

// Whether the outline here differs from the one the deck holds, in a line.
function paintOutlineSaid(gate, holder) {
  if (!holder) return;
  const held = chosenFor(gate);
  holder.replaceChildren(...(held.edited ? [state('review', 'Edited here. Your edits are sent '
    + 'with your approval, and checked first.'), capsule('Put it back as drafted', 'quiet', () => {
    held.work = null;
    held.edited = false;
    paintOutline(gate, byId('outline-list'), holder);
    focusKey('outline-add');
  }, 'outline-reset')] : []));
}

function paintOutline(gate, holder, said) {
  if (!holder) return;
  const readonly = holder.dataset.readonly === 'true';
  const slides = readonly ? list(gate.slides) : outlineWork(gate);
  const active = document.activeElement;
  const focused = active && active.dataset && holder.contains(active) ? active.dataset.key : '';
  holder.replaceChildren(...slides.map((one, index) => outlineRow(gate, slides, index,
    readonly)));
  if (focused) focusKey(focused);
  paintOutlineSaid(gate, said);
}

function outlinePanel(gate, readonly) {
  const node = card('The outline');
  const slides = list(gate.slides);
  add(node, make('p', '', count(slides.length, 'slide', 'slides') + ', each with its title, '
    + 'what it says and its notes.' + (readonly ? '' : ' Retitle, move, add or remove '
    + 'slides here; your edits are sent with your approval.')));
  const said = make('div', 'bar');
  said.id = 'outline-said';
  said.setAttribute('role', 'status');
  const items = make('ol', 'plain outline');
  items.id = 'outline-list';
  items.dataset.readonly = String(Boolean(readonly));
  add(node, said, items);
  paintOutline(gate, items, said);
  if (!readonly) {
    const held = chosenFor(gate);
    const live = gate.delivery === 'live';
    if (held.addingNotes === undefined) held.addingNotes = '';
    const go = capsule('Add the slide', '', () => {
      const title = held.adding.trim();
      const notes = held.addingNotes.trim();
      refuse('outline-add', '');
      refuse('outline-add-notes', '');
      if (!title) {
        refuse('outline-add', 'Give the new slide a title first.');
        byId('outline-add').focus();
        return;
      }
      if (live && !notes) {
        refuse('outline-add-notes', 'A deck presented live needs what the presenter says '
          + 'on each slide.');
        byId('outline-add-notes').focus();
        return;
      }
      const work = outlineWork(gate);
      // A content slide as the outline contract has it: the person's request is what it
      // rests on, and its points are left for the build to fill. It is light, so it does
      // not make a long run of dense slides.
      work.push({ id: newSlideId(title, work), kind: 'content', title, understand: title,
        relation: 'none', rhythm: 'breathing', points: [], sources: ['request'],
        ...(notes ? { notes } : {}) });
      held.adding = '';
      held.addingNotes = '';
      byId('outline-add').value = '';
      byId('outline-add-notes').value = '';
      outlineEdited(gate);
    }, 'outline-add-go');
    add(node, add(make('div', 'paper callout'), field('outline-add', 'A new slide’s title',
      held, 'adding', { limit: 300, hint: 'It is added at the end. Move it where it belongs.' }),
    field('outline-add-notes', 'What the presenter says on it', held, 'addingNotes',
      { long: true, limit: 2000, hint: live ? 'Needed: this deck is presented live.'
        : 'Optional. These are its speaker notes.' }),
    add(make('div', 'bar'), go)));
  }
  if (!slides.length) add(node, documentPart('The outline', gate.text));
  return add(node, ...gateSaid(gate));
}

// The brand: the deck's cover drawn in the brand it is made in, so the person can see it is
// the one they meant. No layout is chosen here: each slide is designed on its own as it is
// built.
function lookPanel(gate, readonly) {
  const node = card('The brand');
  const made = gate.made_in || 'your brand';
  add(node, make('p', 'lede', 'Made in ' + made + '.'),
    make('p', '', readonly ? 'Its cover, drawn in that brand.' : 'This is your cover, drawn '
      + 'in that brand, so you can see it is the one you meant. If it is not, choose another '
      + 'brand.'),
    gate.picture ? pictureAt(pictureOf(view.path, gate.picture), 'The cover in ' + made,
      gate.round) : make('p', 'quiet', 'There is no picture of it on this computer.'),
    make('p', 'quiet', 'No layout is chosen here. When the deck is built, each slide is '
      + 'designed on its own from what it says.'));
  return add(node, ...gateSaid(gate));
}

// What the review still finds on one slide, the most serious first.
function findingItems(findings) {
  const order = Object.keys(SEVERITIES);
  const rank = (finding) => (order.includes(finding.severity) ? order.indexOf(finding.severity)
    : order.length);
  const items = make('ul', 'look findings');
  for (const finding of findings.slice().sort((one, other) => rank(one) - rank(other))) {
    const [shape, words] = SEVERITIES[finding.severity]
      || ['none', spoken(finding.severity || 'finding')];
    add(items, add(make('li', 'finding'),
      add(make('p', 'foot-line'), state(shape, words),
        ABOUT_TAGS[finding.about] ? make('span', 'tag', ABOUT_TAGS[finding.about]) : null),
      make('p', '', finding.note || finding.question || ''),
      finding.fix ? make('p', 'quiet', 'Suggested: ' + finding.fix) : null));
  }
  return items;
}

// The brand's own check of the deck: its word, and each error and warning in its words.
function auditPart(gate) {
  const audit = gate.audit;
  const node = add(make('div', 'audit'), make('h3', 'row-title', 'The brand’s own check'));
  if (!audit) {
    return add(node, make('p', 'quiet', gate.auditNote || 'It has not been run on this '
      + 'deck.'));
  }
  const errors = Number(audit.errors) || 0;
  const warnings = Number(audit.warnings) || 0;
  if (!errors && !warnings) {
    return add(node, state('done', 'It raised nothing about the brand’s rules'
      + (audit.status ? ', and answered “' + audit.status + '”.' : '.')));
  }
  add(node, state('late', [errors ? count(errors, 'error', 'errors') : '',
    warnings ? count(warnings, 'warning', 'warnings') : ''].filter(Boolean).join(' and ')));
  add(node, bullets(list(audit.messages).map(String), 'look'));
  return add(node, make('p', 'quiet', 'Approving is still yours to decide. Weigh these first.'));
}

function buildPanel(gate, readonly) {
  const node = card('The deck');
  const held = chosenFor(gate);
  const changed = list(gate.changed);
  const pairs = new Map(list(gate.pairs).map((pair) => [pair.number, pair]));
  const slides = list(gate.slides).map((one) => ({ number: one.number, title: one.title,
    findings: list(one.findings), changed: changed.includes(one.number),
    note: typeof one.note === 'string' ? one.note : null,
    where: pictureOf(view.path, one.image || { kind: 'build', ref: one.number }),
    mark: gate.round }));
  const findings = slides.reduce((all, one) => all + one.findings.length, 0);
  const serious = slides.reduce((all, one) => all + one.findings.filter((finding) => SERIOUS
    .includes(finding.severity)).length, 0);
  add(node, make('p', '', count(slides.length, 'slide', 'slides') + '. ' + (findings
    ? count(findings, 'finding remains', 'findings remain') + ' from the review, each shown '
      + 'with its slide.' : 'The review has nothing left to raise. Whether the deck is good '
      + 'is still yours to judge.')),
  serious ? state('late', count(serious, 'serious finding', 'serious findings')
    + ' still listed.') : null,
  changed.length ? make('p', 'quiet', 'Built again after your changes: '
    + slidesNamed(changed) + '. They are marked “Changed”.') : null);
  const marked = make('p', 'quiet');
  marked.setAttribute('role', 'status');
  const tellMarked = () => {
    const numbers = markedSlides();
    marked.textContent = numbers.length ? 'Marked for changes: ' + slidesNamed(numbers)
      + '. Ask for changes, and the parts of the deck that hold them are drawn again.' : '';
    marked.hidden = !numbers.length;
  };
  tellMarked();
  const about = (one) => {
    const parts = [];
    const pair = pairs.get(one.number);
    if (pair && pair.before) {
      parts.push(add(make('div', 'pair'),
        add(make('div', ''), make('p', 'quiet', 'Before'), pictureAt(pictureOf(view.path,
          pair.before), 'Slide ' + one.number + ' before', 'original')),
        add(make('div', ''), make('p', 'quiet', 'After'), pair.after
          ? pictureAt(pictureOf(view.path, pair.after), 'Slide ' + one.number + ' after',
            gate.round) : make('p', 'quiet', 'There is no picture of it after yet.'))));
    }
    if (one.note) parts.push(make('p', 'quiet', one.note));
    if (one.findings.length) parts.push(findingItems(one.findings));
    else parts.push(make('p', 'quiet', 'The review found nothing on this slide.'));
    if (!readonly) {
      parts.push(chip('Ask for changes to this slide', held.marked.includes(one.number),
        (on) => {
          held.marked = held.marked.filter((number) => number !== one.number);
          if (on) held.marked.push(one.number);
          tellMarked();
        }, 'mark ' + one.number));
    }
    return parts;
  };
  if (slides.length) add(node, pager(slides, about), marked);
  else add(node, make('p', 'quiet', 'There are no pictures of its slides on this computer.'));
  if (gate.contactSheet) {
    const sheet = make('details', 'card-part');
    sheet.dataset.key = 'contact-sheet';
    add(node, add(sheet, make('summary', '', 'Every slide at once'),
      pictureAt(pictureOf(view.path, gate.contactSheet), 'Every slide of the deck',
        gate.round)));
  }
  return add(node, auditPart(gate), ...gateSaid(gate));
}

function gatePanel(run) {
  const gate = run.gate;
  const readonly = theirs(run);
  if (gate.name === 'gate:classify') return classifyPanel(gate, readonly);
  if (gate.name === 'gate:research-plan') return researchPlanPanel(gate, readonly);
  if (gate.name === 'gate:research') return researchPanel(gate, readonly);
  if (gate.name === 'gate:outline') return outlinePanel(gate, readonly);
  if (gate.name === 'gate:look') return lookPanel(gate, readonly);
  return buildPanel(gate, readonly);
}

// What approving each gate does, said before Approve is pressed: it acts at once.
const APPROVING = {
  'gate:classify': 'Approve, and it carries on from what you gave us. Or ask for changes and '
    + 'say what should change.',
  'gate:research-plan': 'Approve, and each question in the plan is researched; the findings '
    + 'come back to you before anything is written from them. Or ask for changes.',
  'gate:research': 'Approve, and the outline is drafted from these findings. Or ask for '
    + 'changes.',
  'gate:outline': 'Approve, and every slide is designed and built from this outline, with '
    + 'any edits you made here. Or ask for changes.',
  'gate:look': 'Approve, and every slide is designed in this brand, each on its own. Or '
    + 'choose another brand.',
  'gate:build': 'Approve, and the deck is delivered as it is. Or mark slides and ask for '
    + 'changes.',
};

// What waits, in a line above the gate: what is to decide, and how.
function gateLine(run) {
  const gate = run.gate;
  if (theirs(run)) {
    return callout('', make('p', '', (run.driver ? nameOf(run.driver) + ' decides this, on '
      + 'the computer that runs it.' : 'Nobody is running this deck, so it cannot be decided '
      + 'until someone takes it.') + ' Here you can read it.'));
  }
  return callout('yours', make('p', '', capital(gate.label) + '.'),
    make('p', 'quiet', APPROVING[gate.name] || 'Approve it, or ask for changes and say what '
      + 'should change.'));
}

// --- one deck: delivered -------------------------------------------------------------------

function deliverPart(run) {
  const found = run.deliver;
  const node = card('Delivered');
  add(node, state('done', 'Revision ' + (found.revision || 1) + '.'),
    found.at ? add(make('p', 'quiet'), 'Delivered ', when(found.at), '.') : null);
  const bar = make('div', 'bar');
  if (found.url) {
    add(bar, outLink(found.url, 'Open in Google Slides', 'Open ' + run.title
      + ' in Google Slides'));
  }
  if (found.download) {
    const go = capsule(view.downloading ? 'Downloading…' : 'Download .pptx', '',
      () => downloadDeck(run, go), 'download');
    add(bar, go);
  }
  add(node, bar);
  if (found.notice) add(node, make('p', 'fix', found.notice));
  if (found.to_google && !theirs(run)) {
    const google = capsule(view.delivering ? 'Delivering…' : 'Deliver to Google Slides', '',
      () => deliverToGoogle(run, google), 'deliver-google');
    add(node, make('p', 'quiet', 'Once you are signed in to Google with gcloud on this '
      + 'computer, the same deck goes to Google Slides as the next revision. Nothing in it '
      + 'is built again.'), add(make('div', 'bar'), google));
  }
  const revisions = list(found.revisions);
  if (revisions.length > 1) {
    const items = make('ul', 'rows');
    for (const one of revisions.slice().reverse()) {
      add(items, add(make('li', 'row'), add(make('div', 'row-text'),
        make('p', 'step-name', 'Revision ' + one.revision),
        add(make('p', 'quiet'), 'Delivered ', when(one.at), '.'),
        one.url ? add(make('p', ''), outLink(one.url, 'Open revision ' + one.revision
          + ' in Google Slides')) : null)));
    }
    add(node, make('h3', 'row-title', 'Every revision'), items);
  }
  if (run.contactSheet) {
    add(node, add(make('div', 'thumb'), pictureAt(pictureOf(view.path,
      { kind: 'build', ref: 'contact-sheet' }), 'Every slide of the deck', found.revision)));
  }
  if (!theirs(run)) {
    add(node, make('p', 'quiet', 'To change it, ask for changes: the parts that draw the '
      + 'slides you name are drawn again, and it is delivered as the next revision. The one '
      + 'before is kept.'),
    add(make('div', 'bar'), capsule('Ask for changes', '', openSheet('changes', 'changes'),
      'changes')));
  }
  return node;
}

// The deck, fetched with the key and handed to the browser to keep, from memory.
// A deck made as a PowerPoint file because Google was not connected, sent to Google Slides.
async function deliverToGoogle(run, pressed) {
  if (view.delivering || view.busy) return;
  const turn = view.turn;
  view.delivering = true;
  pressed.disabled = true;
  try {
    const shown = await send('deliver', { path: run.path });
    view.delivering = false;
    toast('The deck is in Google Slides now.');
    if (turn === view.turn) {
      view.run = shown;
      paintDeck(false);
    }
    refresh();
  } catch (failure) {
    view.delivering = false;
    pressed.disabled = false;
    toast(failure.message + ' Nothing was sent.');
  }
}

async function downloadDeck(run, pressed) {
  if (view.downloading) return;
  view.downloading = true;
  pressed.disabled = true;
  try {
    const found = await deckFile(run.path);
    const held = URL.createObjectURL(found);
    const node = make('a', 'offscreen', 'Download');
    node.href = held;
    node.download = (run.id || 'deck') + '.pptx';
    document.body.append(node);
    node.click();
    node.remove();
    window.setTimeout(() => URL.revokeObjectURL(held), 60000);
    toast('The deck is downloaded.');
  } catch (failure) {
    toast(failure.message + ' Nothing was downloaded.');
  }
  view.downloading = false;
  pressed.disabled = false;
}

// --- one deck: cost and workers ------------------------------------------------------------

function workerItem(worker) {
  const lines = list(worker.lines);
  const item = add(make('li', 'worker'), add(make('div', 'computer-top'),
    make('h3', 'row-title', worker.label),
    add(make('span', 'quiet'), 'Started ', when(worker.started_at))));
  if (!lines.length) return add(item, make('p', 'quiet', 'Just starting.'));
  add(item, make('p', 'worker-now', lines[lines.length - 1]));
  if (lines.length > 1) {
    const before = make('details', 'worker-before');
    before.dataset.key = 'worker ' + worker.id;
    add(item, add(before, make('summary', '', 'What it did just before'),
      bullets(lines.slice(0, -1).reverse(), 'reasons')));
  }
  return item;
}

function workersCard(run) {
  const items = make('ul', 'plain workers');
  for (const worker of list(run.workers)) items.append(workerItem(worker));
  return add(card('Working now'), items);
}

function costCard(run) {
  const node = card('What it has cost');
  const spent = run.spent || {};
  const limits = (view.setup && view.setup.limits) || {};
  const agent = AGENT_NAMES[run.agent] || run.agent || 'an agent';
  add(node, make('p', 'cost', given(spent.dollars) ? money(spent.dollars) : 'Not reported'));
  const says = [];
  const silent = !given(spent.dollars) && given(spent.tokens);
  if (given(spent.dollars)) says.push('So far.');
  else if (silent) says.push(agent + ' says how many tokens it uses, not what they cost.');
  else says.push('Nothing has been reported yet. An agent says what it used as each step ends.');
  if (given(spent.tokens)) says.push(Number(spent.tokens).toLocaleString() + ' tokens used.');
  if (given(limits.deck_dollars)) {
    says.push(silent ? 'So the limit of ' + money(limits.deck_dollars)
      + ' cannot stop it: watch the steps instead.'
      : 'It stops and asks you at ' + money(limits.deck_dollars) + '.');
  }
  return add(node, make('p', 'quiet', says.join(' ')),
    make('p', 'quiet', 'Drafted by ' + agent + modelWords(run.model, run.effort) + '.'));
}

// --- one deck: a stop reviewed item by item -------------------------------------------------
// The research plan, the research and the outline are shown as items the person marks one
// by one: what needs them first, the rest a line each, and one button that says what it
// will do. Marks are kept with the stop's other choices (`chosenFor`), so a refresh loses
// nothing, and nothing is sent until the button is pressed.

const REVIEWED = ['gate:research-plan', 'gate:research', 'gate:outline'];
const ADDED = 10; // questions added at once: the runner takes no more
const FINDING_WORDS = { supported: ['done', 'Answered'], insufficient: ['late', 'Not settled'],
  unavailable: ['late', 'Not found'], contradicted: ['review', 'Contradicted'],
  pending: ['out', 'Not answered'] };

function sized(value) {
  return Array.isArray(value) ? value.length : Object.keys(value || {}).length;
}

function owns(object, key) {
  return Object.prototype.hasOwnProperty.call(object, key);
}

// A line with its spaces made single, as the runner keeps it.
function spaced(text) {
  return String(text || '').trim().split(/\s+/).join(' ');
}

// A text cut to about `size` characters, to name a control by.
function clipped(text, size) {
  const said = spaced(text);
  return said.length > size ? said.slice(0, size - 1).trimEnd() + '…' : said;
}

// The lines typed against items, as the runner keeps them, keeping those that say
// something. `unchanged` leaves out a line that is what the item says already.
function filled(lines, unchanged) {
  const kept = {};
  for (const [id, text] of Object.entries(lines || {})) {
    const said = spaced(text);
    if (said && (!unchanged || said !== spaced(unchanged(id)))) kept[id] = said;
  }
  return kept;
}

// The findings the runner leaves out now.
function leftBefore(gate) {
  return list(gate.items).filter((item) => item.left_out).map((item) => item.id);
}

// The findings the person leaves out: as the runner has them until they change it here.
function leftOut(gate) {
  const held = chosenFor(gate);
  if (!held.leftOut) held.leftOut = leftBefore(gate);
  return held.leftOut;
}

// How many findings are left out or brought back here, against what the runner has.
function movedOut(gate, ids) {
  const before = leftBefore(gate);
  return ids.filter((id) => !before.includes(id)).length
    + before.filter((id) => !ids.includes(id)).length;
}

// What the person has marked at a reviewed stop, as the runner takes it.
function marksOf(gate) {
  const held = chosenFor(gate);
  if (gate.name === 'gate:research-plan') {
    const asked = new Map(list(gate.questions).map((item) => [item.id, item.question]));
    return { dropped: held.dropped.slice(),
      reword: filled(held.reword, (id) => asked.get(id)), add: held.added.slice() };
  }
  if (gate.name === 'gate:research') {
    const again = {};
    for (const [id, text] of Object.entries(held.again)) again[id] = spaced(text);
    return { left_out: leftOut(gate).slice(), again, add: held.added.slice() };
  }
  if (gate.name === 'gate:outline') {
    const here = new Set(outlineWork(gate).map((one) => one.id));
    const slides = filled(held.slideNotes);
    for (const id of Object.keys(slides)) if (!here.has(id)) delete slides[id];
    return { slides };
  }
  return {};
}

// What a request for changes at a reviewed stop carries, whether its button or the sheet
// sends it: the marks, the findings left out only when that changed here, so one left out
// in an earlier round is not asked for again, and the outline as edited.
function changesOf(gate) {
  const held = chosenFor(gate);
  const marks = marksOf(gate);
  if (gate.name === 'gate:research' && !movedOut(gate, marks.left_out)) {
    return { again: marks.again, add: marks.add };
  }
  if (gate.name === 'gate:outline' && held.edited) return { ...marks, edited: held.work };
  return marks;
}

// What a reviewed stop's button does now: its words, whether it approves, what goes with
// it, and a tally of the marks. What goes with it is nothing only where nothing is marked.
function reviewOf(gate) {
  const held = chosenFor(gate);
  const marks = marksOf(gate);
  if (gate.name === 'gate:research-plan') {
    const dropped = sized(marks.dropped);
    const asked = sized(marks.reword) + sized(marks.add);
    const tally = [count(dropped, 'dropped', 'dropped'),
      count(sized(marks.reword), 'reworded', 'reworded'),
      count(sized(marks.add), 'added', 'added')].join(' · ');
    if (asked) {
      return { label: 'Send ' + count(asked + dropped, 'change', 'changes'), approve: false,
        extra: changesOf(gate), tally };
    }
    if (dropped) {
      return { label: 'Approve without ' + count(dropped, 'question', 'questions'),
        approve: true, extra: { dropped: marks.dropped }, tally };
    }
    return { label: 'Approve', approve: true, extra: null, tally };
  }
  if (gate.name === 'gate:research') {
    const moved = movedOut(gate, marks.left_out);
    const asked = sized(marks.again) + sized(marks.add);
    const tally = [count(sized(marks.again), 'to research again', 'to research again'),
      count(marks.left_out.length, 'left out', 'left out'),
      count(sized(marks.add), 'added', 'added')].join(' · ');
    if (asked) {
      return { label: 'Send ' + count(asked + moved, 'change', 'changes'), approve: false,
        extra: changesOf(gate), tally };
    }
    if (moved) {
      return { label: marks.left_out.length ? 'Approve, leaving out '
        + count(marks.left_out.length, 'finding', 'findings') : 'Approve with every finding',
      approve: true, extra: { left_out: marks.left_out }, tally };
    }
    return { label: 'Approve', approve: true, extra: null, tally };
  }
  const slides = sized(marks.slides);
  const edited = held.edited ? { edited: held.work } : null;
  const tally = count(slides, 'slide to change', 'slides to change')
    + (held.edited ? ' · edited here' : '');
  if (slides) {
    return { label: 'Send ' + count(slides, 'change', 'changes'), approve: false,
      extra: changesOf(gate), tally };
  }
  return { label: 'Approve', approve: true, extra: edited, tally };
}

// Do what a reviewed stop's button says. What refuses it is said in `problem` where one is
// given, or else at the head of the deck.
function sendReview(gate, pressed, problem) {
  const made = reviewOf(gate);
  decide(made.approve ? 'approve' : 'changes', '', problem || null, pressed, made.extra);
}

// Two to four numbers in a row, each with what it counts.
function reviewCounts(pairs) {
  const node = make('div', 'review-counts');
  for (const [number, words] of pairs) {
    add(node, add(make('p', 'review-count'), make('span', 'review-number', String(number)),
      ' ', make('span', 'quiet', words)));
  }
  return node;
}

// The full text a stop was drawn from, folded.
function fullText(summary, label, text, key) {
  const node = make('details', 'card-part');
  node.dataset.key = key;
  return add(node, make('summary', '', summary), documentPart(label, text));
}

// The tally of the marks and the button that sends them, at the foot of the items. The
// tally is made once and only its words change, so what it says is read out as it changes.
// What refuses the decision is said beside the button.
function reviewBar(gate) {
  const node = make('div', 'review-bar');
  node.id = 'review-bar';
  const tally = make('p', 'quiet');
  tally.id = 'review-tally';
  tally.setAttribute('role', 'status');
  add(node, tally, alertLine('review-problem'), make('div', 'bar'));
  paintReviewBar(gate, node);
  return node;
}

function paintReviewBar(gate, node) {
  if (!node) return;
  const made = reviewOf(gate);
  const problem = node.querySelector('#review-problem');
  node.querySelector('#review-tally').textContent = made.tally;
  // What was refused before is not what the marks say now.
  say(problem, '');
  const go = capsule(made.label, '', () => sendReview(gate, go, problem), 'review-send');
  node.querySelector('.bar').replaceChildren(go);
}

// A mark changed: the tally, this button and the toolbar's say so at once.
function reviewChanged(gate) {
  paintReviewBar(gate, byId('review-bar'));
  if (view.screen === 'deck' && view.run) paintDeck(false);
}

// New questions the person adds, each with the way to take it back, and a box for one more.
function addedPart(gate) {
  const node = make('div', 'review-added');
  node.id = 'review-added';
  paintAdded(gate, node);
  return node;
}

function paintAdded(gate, node) {
  if (!node) return;
  const held = chosenFor(gate);
  const items = make('ul', 'plain review-list');
  held.added.forEach((text, index) => {
    const take = capsule('Take it back', 'quiet', () => {
      held.added.splice(index, 1);
      paintAdded(gate, byId('review-added'));
      reviewChanged(gate);
      focusKey('added-question');
    }, 'unadd ' + index);
    take.setAttribute('aria-label', 'Take it back: “' + clipped(text, 60) + '”');
    items.append(add(make('li', 'review-row'), make('p', '', text),
      add(make('div', 'bar'), take)));
  });
  // The runner refuses more than ADDED at once, so no more are taken here.
  const full = held.added.length >= ADDED;
  const box = field('added-question', 'A question to add', held, 'asking',
    { long: true, limit: 1000, hint: full ? 'You have added ' + ADDED + ', as many as can '
      + 'be added at once. Send these, and add more next time round.' : '' });
  const go = capsule('Add the question', 'quiet', () => {
    const text = String(held.asking || '').trim();
    if (!text) {
      refuse('added-question', 'Write the question first.');
      focusKey('added-question');
      return;
    }
    held.added.push(text);
    held.asking = '';
    paintAdded(gate, byId('review-added'));
    reviewChanged(gate);
    focusKey('added-question');
  }, 'add-question');
  go.disabled = full;
  node.replaceChildren(...(held.added.length ? [make('h3', 'row-title', 'Questions you added'),
    items] : []), box, add(make('div', 'bar'), go));
}

// --- one deck: deciding and steering -------------------------------------------------------

// What comes with a decision at the gate, from what the person chose there.
function extraFor(gate, decision) {
  const held = chosenFor(gate);
  if (REVIEWED.includes(gate.name)) {
    return decision === 'approve' ? reviewOf(gate).extra : changesOf(gate);
  }
  if (gate.name === 'gate:classify' && decision === 'approve' && held.wrong
      && gate.kind === 'document') {
    return { kind: gate.verdict === 'spec' ? 'material' : 'spec' };
  }
  if (gate.name === 'gate:look' && decision === 'changes') {
    return { brand: held.brand, variant: held.variant || null };
  }
  if (gate.name === 'gate:build' && decision === 'changes' && held.marked.length) {
    return { slides: markedSlides() };
  }
  return null;
}

// Another brand, or another variant of it, chosen at the brand's gate. The cover is drawn
// again in it and comes back here.
function rebrandSheet() {
  const gate = view.run.gate;
  const cancel = capsule('Cancel', 'quiet', closeSheet, 'cancel');
  const title = sheetTitle('Choose another brand');
  if (!gate || gate.name !== 'gate:look') {
    return [title, make('p', '', 'This deck has moved on from its brand.'),
      add(make('div', 'bar'), cancel)];
  }
  const held = chosenFor(gate);
  if (!held.brand) {
    held.brand = gate.brand || '';
    held.variant = gate.variant || '';
  }
  const form = make('form', 'note');
  form.noValidate = true;
  const problem = problemLine();
  const submit = submitButton('Use this brand', 'send');
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    if (held.brand === (gate.brand || '') && (held.variant || '') === (gate.variant || '')) {
      say(problem, 'It is made in ' + (gate.made_in || 'this brand') + ' already. Choose '
        + 'another brand or variant.');
      return;
    }
    decide('changes', '', problem, submit);
  });
  add(form, brandFields(held, 'rebrand'), make('p', 'quiet', 'Your cover is drawn again in '
    + 'the one you choose and comes back here for your decision.'), problem,
  add(make('div', 'bar'), submit, cancel));
  return [title, form];
}

function undoSheet() {
  const problem = problemLine();
  const confirm = capsule('Undo it', 'filled', () => steer('undo', confirm, problem), 'send');
  return [sheetTitle('Undo the last step?'),
    make('p', '', 'The last thing done to this deck is taken back, and it carries on from '
      + 'there. Only the last step can be undone, and only while it has not been shared with '
      + 'your team.'),
    problem, add(make('div', 'bar'), confirm, capsule('Cancel', 'quiet', closeSheet,
      'cancel'))];
}

async function decide(decision, note, problem, pressed, extra) {
  if (view.busy) return;
  const turn = view.turn;
  const run = view.run;
  const gate = run.gate;
  const noted = noteKey(decision);
  const body = { path: view.path, gate: gate ? gate.name : 'gate:build', decision };
  if (note) body.note = note;
  const more = extra !== undefined ? extra : gate ? extraFor(gate, decision) : null;
  if (more) body.extra = more;
  view.busy = true;
  pressed.disabled = true;
  let answered;
  try {
    answered = await send('decide', body);
  } catch (failure) {
    view.busy = false;
    pressed.disabled = false;
    if (problem) {
      say(problem, failure.message + ' Nothing was decided.');
      return;
    }
    // A decision pressed in the toolbar has no sheet, whether it approves or sends what was
    // marked: what refused it is said at the head of the deck.
    if (turn !== view.turn) return;
    view.steered = failure.message + ' Nothing was decided.';
    paintDeck(false);
    return;
  }
  // A note that was sent is not offered again, nor what was chosen with it.
  delete view.notes[noted];
  forget(gate);
  view.busy = false;
  if (turn !== view.turn) return;
  view.sheet = '';
  view.run = answered;
  view.steered = '';
  drawSheet();
  view.barred = '';
  paintDeck(false);
  toast(decision === 'approve' ? 'Approved. It carries on by itself. ' + CLOSE
    : 'Your changes are noted. Once they are made, it comes back to you.');
  window.scrollTo(0, 0);
  byId('title').focus({ preventScroll: true });
  refresh();
}

async function steer(action, pressed, problem) {
  if (view.busy) return;
  const turn = view.turn;
  const key = pressed.dataset.key;
  view.busy = true;
  pressed.disabled = true;
  try {
    const run = await send('run', { path: view.path, action });
    view.busy = false;
    if (turn !== view.turn) return;
    view.run = run;
    view.steered = '';
    toast(STEERED[action]);
  } catch (failure) {
    view.busy = false;
    if (turn !== view.turn) return;
    if (problem) {
      say(problem, failure.message + ' Nothing was changed.');
      pressed.disabled = false;
      return;
    }
    view.steered = failure.message + ' Nothing was changed.';
  }
  if (view.sheet) {
    view.sheet = '';
    drawSheet();
  }
  view.barred = '';
  paintDeck(false);
  // The control that was pressed may be gone. Focus goes to the one that undoes it, or to
  // the head of the screen, never to nowhere.
  const undo = { pause: 'resume', resume: 'pause', stop: 'resume' }[action];
  if (!focusKey(key) && !(undo && focusKey(undo))) byId('title').focus({ preventScroll: true });
  refresh();
}

// The toolbar's side of a deck: the decision at its gate, and pause, stop, resume and undo.
function deckActions(run, lead) {
  if (theirs(run)) return [];
  const actions = [];
  const press = (label, kind, action) => {
    const node = capsule(label, kind, () => steer(action, node), action);
    actions.push(node);
  };
  if (run.gate && !run.question) {
    // Approve acts at once: what it does is said beside the gate before it is pressed. At
    // a stop reviewed item by item it says what it will do with the marks. Pressed, it
    // acts on the gate as it is then, as `decide` does.
    const approve = capsule(REVIEWED.includes(run.gate.name) ? reviewOf(run.gate).label
      : 'Approve', lead === 'approve' ? 'filled' : '', () => {
      const gate = view.run.gate;
      if (gate && REVIEWED.includes(gate.name)) sendReview(gate, approve);
      else decide('approve', '', null, approve);
    }, 'approve');
    const brand = run.gate.name === 'gate:look';
    actions.push(approve, capsule(brand ? 'Choose another brand' : 'Ask for changes', '',
      openSheet(brand ? 'rebrand' : 'changes', 'changes'), 'changes'));
  }
  const offered = run.problem && run.problem.action;
  if (run.state === 'working') press('Pause', '', 'pause');
  if (['working', 'waiting', 'paused'].includes(run.state)) press('Stop', 'quiet', 'stop');
  if (['paused', 'stopped'].includes(run.state) && !offered) {
    press('Resume', lead === 'resume' ? 'filled' : '', 'resume');
  }
  if (run.state !== 'working') {
    actions.push(capsule('Undo the last step', 'quiet', openSheet('undo', 'undo'), 'undo'));
  }
  return actions;
}

function paintDeck(fresh) {
  const run = view.run;
  const title = run.title || 'Untitled';
  const read = theirs(run);
  const driver = run.driver || null;
  const finished = run.state === 'finished';
  // One filled button on the screen, for the first thing that is needed. While a sheet is
  // open it holds that button, so nothing under it is filled.
  const lead = view.sheet ? '' : read ? (!driver && !finished ? 'take' : '')
    : run.question ? 'answer' : run.problem && run.problem.action ? 'problem'
      : run.gate ? 'approve' : ['paused', 'stopped'].includes(run.state) ? 'resume' : '';
  const route = routeWords(run);
  const runs = !read ? (driver ? 'Runs on this computer' : '') : driver
    ? 'Run by ' + nameOf(driver) : finished ? 'Finished' : 'Nobody is running it';
  const above = [make('span', '', [route, runs].filter(Boolean).join(' · '))];
  const published = view.issued && view.issued.path === view.path ? view.issued : null;
  const gate = run.gate;
  placeParts({ title, above, back: true, actions: deckActions(run, lead),
    mark: [title, route, run.state, lead, gate && [gate.name, gate.round], read, driver,
      Boolean(run.question), run.problem,
      gate && REVIEWED.includes(gate.name) && !read ? reviewOf(gate).label : ''] }, [
    ['intro', [run.state, run.sentence, run.queue, view.steered, read, Boolean(run.problem)],
      () => deckIntro(run)],
    ['timeline', [run.timeline, gate && gate.name], () => timelinePart(run)],
    read && (driver || !finished) ? ['theirs', [driver, lead, run.taken, run.notice,
      run.last_shared, run.kept, title], () => theirsPart(run, lead === 'take')] : null,
    !read && run.notice ? ['notice', [run.notice, run.clash, run.kept],
      () => noticePart(run)] : null,
    run.problem ? ['problem', [run.problem, lead, read],
      () => problemPart(run, lead === 'problem')] : null,
    run.question && read ? ['asked', [run.question, driver], () => askedPart(run)] : null,
    run.question && !read ? ['question', [run.question, title],
      () => questionPart(run, title)] : null,
    gate ? ['gate-line', [gate.name, gate.label, read, driver], () => gateLine(run)] : null,
    gate ? ['gate', [gate, read], () => gatePanel(run)] : null,
    run.deliver ? ['deliver', [run.deliver, run.contactSheet, read, view.downloading],
      () => deliverPart(run)] : null,
    list(run.workers).length ? ['workers', run.workers, () => workersCard(run)] : null,
    finished && (!read || !driver) ? ['publish', [published, teamSpace()],
      () => publishCard(run, published)] : null,
    read && !driver && finished ? ['free', [title], () => finishedFreePart()] : null,
    ['cost', [run.spent, run.agent, run.model, run.effort, view.setup && view.setup.limits],
      () => costCard(run)],
    ['steps', [run.timeline], () => stepsCard(run)],
    // What this computer runs for a team can be handed over, for anyone to take.
    !read && driver && driver.here ? ['mine', [driver, title, run.kept],
      () => minePart(driver, run.kept)] : null,
    deletable(run) ? ['delete', [title], () => deleteCard()] : null,
  ], fresh);
  tidyPictures();
}

async function drawDeck(fresh) {
  const turn = view.turn;
  if (fresh) {
    place({ title: 'Opening', back: true }, [make('p', 'quiet', 'Reading the deck.')], true);
  }
  try {
    const run = await ask('run', { path: view.path });
    if (turn !== view.turn) return;
    const first = fresh || !view.run;
    const same = !first && JSON.stringify(run) === JSON.stringify(view.run);
    view.run = run;
    // Someone is in the middle of deciding: the screen waits until they are done.
    if (!view.busy && !view.sheet && !same) paintDeck(first);
    if (first) later();
  } catch (failure) {
    if (turn !== view.turn) return;
    unopened(failure, !fresh && view.run, fresh,
      { said: 'Nothing was changed. The deck itself is as it was.' });
  }
}

// --- with a team ---------------------------------------------------------------------
// A shared workspace has one driver for each deck: the computer that runs it. Everyone else
// reads. The runner names the driver; where it names none, which is every workspace that is
// a folder on one computer, none of this is ever shown.

function nameOf(driver) {
  return String((driver && driver.name) || '').trim() || 'A teammate';
}

// A deck that someone else's computer runs.
function elsewhere(brief) {
  return Boolean(brief && brief.mine === false && brief.driver && brief.driver.here === false);
}

function teamSpace() {
  const space = view.setup ? view.setup.workspace : null;
  return Boolean(space && space.repository);
}

// Who runs a deck and since when, in a sentence.
function whoSays(driver, className) {
  const node = make('p', className);
  const who = driver.here ? 'This computer runs it'
    : nameOf(driver) + ' runs it from another computer';
  if (Number.isNaN(Date.parse(driver.since))) return add(node, who + '.');
  return add(node, who + ', and took it ', when(driver.since), '.');
}

function whoLine(brief) {
  if (teamSpace() && brief && brief.mine === false && !brief.driver
      && brief.state !== 'finished') {
    return make('p', 'quiet who', 'Nobody is running it. Anyone on your team may take it.');
  }
  return brief && brief.driver ? whoSays(brief.driver, 'quiet who') : null;
}

// What this computer knows of a deck a teammate runs: when it was last shared and where it
// stood then. It never says what is happening now, because that is not known here.
function lastLine(last, className) {
  if (!last) return null;
  const node = make('p', className);
  if (!Number.isNaN(Date.parse(last.at))) add(node, 'Last shared ', when(last.at), '. ');
  return add(node, (last.says ? String(last.says).trim() + ' ' : '')
    + 'It may have moved on since: this computer knows only what was shared.');
}

// What the runner says about who has a deck: that it was taken from this computer, or that
// it was changed on two computers at once.
function noticeLine(brief) {
  return brief && brief.notice ? make('p', 'fix', brief.notice) : null;
}

// Where what this computer set aside is kept, for someone who brings it back with git. The
// sentence beside it has already said, in plain words, that it is kept and can come back.
function keptLine(names) {
  const kept = list(names).filter(Boolean);
  if (!kept.length) return null;
  const space = view.setup && view.setup.workspace;
  const node = make('p', 'quiet', 'A detail for whoever brings it back: it is in this '
    + 'computer’s copy of the workspace' + (space && space.path ? ' (' + space.path + ')' : '')
    + ', where git keeps it under the name' + (kept.length > 1 ? 's ' : ' '));
  kept.forEach((name, index) => add(node, index ? ', ' : '', pathInto(make('code'), name)));
  return add(node, '. It is on this computer only, and is never sent to your team.');
}

// A deck that waits for its turn, and how many are ahead of it.
function queued(run) {
  return Boolean(run && run.queue && given(run.queue.ahead));
}

function queueSays(queue) {
  const ahead = Number(queue.ahead) || 0;
  return (ahead ? 'It is waiting its turn: ' + count(ahead, 'deck is', 'decks are')
    + ' ahead of it.' : 'It is waiting its turn, and is next.')
    + ' Decks take turns in the order they became ready, and it starts by itself when its '
    + 'turn comes.';
}

// On a deck this computer does not drive: who does and since when, what was last shared,
// that it is read here, and the way to take it. Where it was this computer's until it was
// taken, the runner's own sentence says so first.
function theirsPart(run, lead) {
  const driver = run.driver;
  if (!driver) {
    return callout('yours', make('h2', 'aside-title', 'Nobody is running this deck'),
      make('p', '', 'It was handed over, so anyone on your team may take it. Once you take '
        + 'it, it runs from this computer and carries on from where it stands.'),
      make('p', 'quiet', 'Until someone does, nothing more happens to it. ' + READ_ONLY),
      add(make('div', 'bar'), capsule('Take it', lead ? 'filled' : '',
        openSheet('take', 'take'), 'take')));
  }
  const name = nameOf(driver);
  const lost = run.taken || null;
  const kept = lost ? (list(run.kept).length ? run.kept : [lost.kept]) : [];
  return callout(lost ? 'late' : '', make('h2', 'aside-title', lost
    ? (String(lost.by || '').trim() || name) + ' took this deck over'
    : name + ' is running this deck'),
  lost ? make('p', '', run.notice || 'This computer stopped working on it, and nothing '
    + 'was deleted.') : null,
  keptLine(kept), whoSays(driver, ''), lastLine(run.last_shared, ''),
  make('p', 'quiet', READ_ONLY),
  add(make('div', 'bar'), capsule('Take it over', '', openSheet('take', 'take'), 'take')));
}

// A finished deck in a shared workspace is nobody's. It is read and published as it stands;
// to ask for changes, someone takes it first.
function finishedFreePart() {
  return callout('', make('h2', 'aside-title', 'Nobody is running this deck'),
    make('p', '', 'It is finished, so no computer runs it. It can be read, and published as '
      + 'it stands, from any computer on your team.'),
    make('p', '', 'To ask for changes, take it first. It then runs from this computer.'),
    add(make('div', 'bar'), capsule('Take it', '', openSheet('take', 'take'), 'take')));
}

// What the runner says about a deck this computer runs: that it was changed on two computers
// at once, which is put right by carrying on from the shared version, or that it has been.
function noticePart(run) {
  if (!run.clash) {
    return callout('', make('p', '', run.notice), keptLine(run.kept));
  }
  return callout('late', make('h2', 'aside-title', 'Changed on two computers at once'),
    make('p', '', run.notice),
    add(make('div', 'bar'), capsule('Carry on from the shared version', '',
      openSheet('take', 'take-shared'), 'take-shared')));
}

// A question that only the computer running the deck can answer, shown to be read.
function askedPart(run) {
  const name = run.driver ? nameOf(run.driver) : '';
  return add(card('A question is waiting'),
    make('p', 'row-says', (run.question.from || 'A worker') + ' asks:'),
    make('p', 'row-quote', run.question.text),
    make('p', 'quiet', name ? 'Only ' + name + ' can answer it, on the computer that runs '
      + 'this deck.' : 'It can be answered once someone takes this deck.'));
}

function minePart(driver, kept) {
  const aside = keptLine(kept);
  return add(card('Who runs this deck'), whoSays(driver, ''),
    make('p', 'quiet', 'Your teammates can read it, and only this computer can change it. '
      + 'If someone else should carry it on, hand it over: anyone on your team may then '
      + 'take it.'),
    aside ? make('p', 'quiet', 'Some of what this computer made for this deck was set aside, '
      + 'because it had not been shared when the deck carried on from the shared version. It '
      + 'is kept on this computer, and can be brought back.') : null, aside,
    add(make('div', 'bar'), capsule('Hand over', '', openSheet('hand-over', 'hand-over'),
      'hand-over')));
}

// A finished deck is published from its own screen. Once it is, the card says which revision
// that made, and whether the team can see it yet.
function publishCard(run, published) {
  const node = add(card('Publish it'), make('p', '', PUBLISH_SAYS));
  if (published) {
    add(node, state('done', 'Published as revision ' + published.revision + '.'));
    const notice = published.notice ? ' ' + published.notice : '';
    add(node, published.shared ? state('done', 'Shared: your team can see this revision.'
      + notice)
      : state(notice ? 'late' : 'none', (teamSpace() ? 'Not shared with your team yet.'
        : 'Kept on this computer: this workspace is not shared with anyone.') + notice));
  }
  return add(node, add(make('div', 'bar'),
    capsule(published ? 'Publish again' : 'Publish', '', openSheet('publish', 'publish'),
      'publish'),
    capsule('See what is published', 'quiet', () => show('published'), 'see-published')));
}

// What each confirmation says before anything is sent, and what its button is called.
function teamAsks(kind, title) {
  const run = view.run || {};
  if (kind === 'take' && run.clash && run.mine !== false) {
    return { title: 'Carry on with ' + title + ' from the shared version?',
      send: 'Carry on from it',
      says: [make('p', '', 'It was changed on this computer and on another at the same '
        + 'time. From then on it carries on from the version your team shares, and runs '
        + 'from this computer.'),
      make('p', '', 'What this computer made and never shared is set aside. It is kept on '
        + 'this computer and can be brought back; nothing is deleted.')] };
  }
  if (kind === 'take' && run.driver) {
    const name = nameOf(run.driver);
    const dated = !Number.isNaN(Date.parse(run.driver.since));
    return { title: 'Take ' + title + ' over from ' + name + '?', send: 'Take it over',
      says: [dated ? add(make('p', ''), 'It is ' + name + '’s: ' + name + ' took it ',
        when(run.driver.since), ', and runs it from another computer.')
        : make('p', '', 'It is ' + name + '’s, and runs from another computer.'),
      make('p', '', 'If you take it over, ' + name + '’s runner stops working on it and '
        + 'keeps what it had. From then on it runs from this computer, and only this '
        + 'computer can change it.'),
      make('p', 'quiet', name + ' is told who took it and when.')] };
  }
  if (kind === 'take') {
    return { title: 'Take ' + title + '?', send: 'Take it',
      says: [make('p', '', 'Nobody is running it. From then on it runs from this computer, '
        + 'and carries on from where it stands.'),
      run.state === 'finished' ? make('p', 'quiet', 'It is finished, so nothing more is made '
        + 'until you ask for changes. When you are done, hand it over, so that nobody is '
        + 'shown as running it.') : null] };
  }
  if (kind === 'hand-over') {
    return { title: 'Hand ' + title + ' over?', send: 'Hand it over',
      says: [make('p', '', 'This computer stops working on it, and keeps everything made so '
        + 'far.'),
      make('p', '', 'Anyone on your team may then take it and carry it on. Until someone '
        + 'does, nothing more happens to it.')] };
  }
  return { title: 'Publish ' + title + '?', send: 'Publish it',
    says: [make('p', '', PUBLISH_SAYS), make('p', '', PUBLISH_KEPT),
      run.state === 'finished' ? null : state('late', 'This deck is not delivered yet. It '
        + 'can still be published, and the revision will say so.')] };
}

function teamSheet(kind) {
  const title = (view.run || {}).title || 'Untitled';
  const spec = teamAsks(kind, title);
  const problem = problemLine();
  const confirm = capsule(spec.send, 'filled', () => settleTeam(kind, problem, confirm),
    'send');
  return [sheetTitle(spec.title), ...spec.says.filter(Boolean), problem,
    add(make('div', 'bar'), confirm, capsule('Cancel', 'quiet', closeSheet, 'cancel'))];
}

// Send what was confirmed. A refusal is said in the sheet, in the runner's own words, with
// what it means for the deck: nothing was changed.
async function settleTeam(kind, problem, pressed) {
  if (view.busy) return;
  const turn = view.turn;
  const path = view.path;
  const to = kind === 'publish' ? 'publish' : 'drive';
  const body = to === 'drive' ? { path, action: kind } : { path };
  view.busy = true;
  pressed.disabled = true;
  let found;
  try {
    found = await send(to, body);
  } catch (failure) {
    view.busy = false;
    if (turn !== view.turn) return;
    say(problem, failure.message + (kind === 'publish' ? ' Nothing was published.'
      : ' Nothing was changed.'));
    pressed.disabled = false;
    pressed.focus();
    return;
  }
  view.busy = false;
  if (turn !== view.turn) return;
  view.sheet = '';
  if (kind === 'publish') {
    view.issued = { path, revision: found.revision, ready: found.ready !== false,
      shared: Boolean(found.shared), notice: found.notice || '' };
    toast('Published as revision ' + found.revision + '.');
  } else {
    view.run = found;
    toast(kind === 'take' ? found.notice || 'It runs from this computer now.'
      : 'Handed over. Anyone on your team may take it now.');
  }
  drawSheet();
  view.barred = '';
  paintDeck(false);
  if (!(kind === 'publish' && focusKey('publish'))) {
    window.scrollTo(0, 0);
    byId('title').focus({ preventScroll: true });
  }
  refresh();
}

// --- deleting a deck -------------------------------------------------------------------
// A deck this computer runs, or a finished one nobody runs, can be deleted. What goes and
// what stays is the runner's to say, so the sheet asks it first; nothing is sent until the
// person presses the button that names the deck.

// Whether the open deck may be offered for deletion here. The runner decides; this only
// keeps the card off a deck someone else runs.
function deletable(run) {
  return Boolean(run && (run.mine !== false || (run.state === 'finished' && !run.driver)));
}

function deleteCard() {
  return add(card('Delete this deck'), make('p', 'quiet', DELETE_SAYS),
    add(make('div', 'bar'), capsule('Delete this deck', 'quiet', askDelete('delete'),
      'delete')));
}

function askDelete(opener) {
  return async () => {
    const turn = view.turn;
    view.leaving = null;
    openSheet('delete', opener)();
    let found;
    try {
      found = await ask('delete', { path: view.path });
    } catch (failure) {
      found = { failed: failure.message };
    }
    if (turn !== view.turn || view.sheet !== 'delete') return;
    view.leaving = found;
    drawSheet();
    byId('sheet').focus();
  };
}

// One file left in Google Drive, as a link that opens in a new tab.
function driveItem(found) {
  const words = found.what + ': ' + (found.name || 'untitled');
  return add(make('li'), outLink(found.url, words));
}

function deleteSheet() {
  const title = (view.run || {}).title || 'Untitled';
  const found = view.leaving;
  const head = sheetTitle('Delete ' + title + '?');
  const cancel = capsule('Cancel', 'quiet', closeSheet, 'cancel');
  if (!found) {
    return [head, make('p', 'quiet', 'Reading what would go.'), add(make('div', 'bar'), cancel)];
  }
  if (found.failed || !found.may) {
    return [head, make('p', '', (found.failed || found.why || 'It cannot be deleted from '
      + 'here.') + ' Nothing was deleted.'), add(make('div', 'bar'), cancel)];
  }
  const documents = Number(found.documents) || 0;
  const revisions = Number(found.revisions) || 0;
  const drive = list(found.drive);
  const goes = [['Its folder in your workspace, with every file in it.',
    DELETE_SHARED[found.share] || ''].filter(Boolean).join(' '),
  'What only this computer kept for it: ' + (documents ? count(documents,
    'document you gave it', 'documents you gave it') + ', ' : '')
    + 'what it was made from, its previews and its work in progress.'];
  const stays = [revisions ? count(revisions, 'published revision', 'published revisions')
    + '. ' + (revisions === 1 ? 'It stays' : 'They stay') + ' in your workspace’s history, '
    + 'and the page no longer lists ' + (revisions === 1 ? 'it.' : 'them.') : null,
  DELETE_UNDO].filter(Boolean);
  const problem = problemLine();
  const confirm = capsule('Delete ' + title, 'danger', () => settleDelete(title, problem,
    confirm), 'send');
  return [head,
    found.stops ? state('late', DELETE_STOPS) : null,
    make('h3', 'sheet-part', 'What goes'), bullets(goes),
    make('h3', 'sheet-part', 'What stays'), bullets(stays),
    drive.length ? make('p', '', DELETE_DRIVE) : null,
    drive.length ? add(make('ul', 'plain'), ...drive.map(driveItem)) : null,
    problem, add(make('div', 'bar'), confirm, cancel)].filter(Boolean);
}

// Send the deletion. A refusal is said in the sheet, in the runner's own words. Once it is
// done the deck is gone, so the page goes home, in place of the screen it was on.
async function settleDelete(title, problem, pressed) {
  if (view.busy) return;
  const turn = view.turn;
  view.busy = true;
  pressed.disabled = true;
  let found;
  try {
    found = await send('delete', { path: view.path, title });
  } catch (failure) {
    view.busy = false;
    if (turn !== view.turn) return;
    say(problem, failure.message + (/\bdeleted\b/.test(failure.message) ? ''
      : ' Nothing was deleted.'));
    pressed.disabled = false;
    pressed.focus();
    return;
  }
  view.busy = false;
  if (turn !== view.turn) return;
  view.sheet = '';
  view.leaving = null;
  toast('Deleted ' + title + '.' + (found && found.notice ? ' ' + found.notice : ''));
  show('home', null, true);
  refresh();
}

// --- with a team: every run at once ----------------------------------------------------

async function readStatus() {
  try {
    view.status = await ask('status');
  } catch (failure) {
    view.status = null;
  }
}

function spentSays(spent) {
  if (given(spent.dollars)) return money(spent.dollars);
  return given(spent.tokens) ? Number(spent.tokens).toLocaleString() + ' tokens'
    : 'Not reported yet';
}

// Every deck on this computer: what each is doing, and what it has cost.
function runsCard() {
  if (!view.status) return null;
  const runs = list(view.status.runs);
  const node = card('Running on this computer');
  const most = Number(view.status.limit) || 0;
  // How many work at once is this computer's own limit, set where the set-up is changed.
  const turns = most ? make('p', 'quiet', 'Up to ' + count(most, 'deck works',
    'decks work') + ' at once on this computer. Any more wait their turn.') : null;
  if (!runs.length) {
    return add(node, make('p', 'quiet', 'There are no decks on this computer yet.'),
      turns, backgroundLine());
  }
  const table = make('table', 'table');
  const head = make('tr');
  for (const title of ['Deck', 'What it is doing', 'Cost so far', '']) {
    const top = make('th', '', title);
    top.scope = 'col';
    if (!title) add(top, make('span', 'offscreen', 'Open'));
    head.append(top);
  }
  const body = make('tbody');
  for (const found of runs) {
    const name = make('th');
    name.scope = 'row';
    add(name, make('span', 'row-title', found.title || 'Untitled'));
    const go = capsule('Open', 'quiet', () => show('deck', { path: found.path }),
      'run ' + found.path);
    go.setAttribute('aria-label', 'Open ' + (found.title || 'Untitled'));
    add(body, add(make('tr'), name,
      cell('What it is doing', state(...(queued(found) ? ['none', 'Waiting its turn']
        : runWords(found))),
      // A question, a problem or a gate: it does nothing more until you come.
      found.needs ? add(make('p', ''), make('strong', '', 'It needs you.')) : null,
      found.sentence ? make('p', 'quiet', found.sentence) : null,
      queued(found) ? make('p', 'quiet', queueSays(found.queue)) : null,
      noticeLine(found)),
      cell('Cost so far', spentSays(found.spent || {})), cell('', go)));
  }
  return add(node, turns, backgroundLine(), add(table, add(make('thead'), head), body));
}

// What last went wrong in what the runner does by itself in the background, in its own
// words, and when. It is said until that work goes right again.
function backgroundLine() {
  const wrong = view.status && view.status.background;
  if (!wrong || !wrong.says) return null;
  const node = add(make('p', 'fix'), String(wrong.says));
  if (!Number.isNaN(Date.parse(wrong.at))) add(node, ' This was ', when(wrong.at), '.');
  return node;
}

// The decks teammates run, apart from this computer's own.
function teammatesCard() {
  const found = view.status ? list(view.status.elsewhere) : list((view.decks || {}).elsewhere);
  if (!found.length && !teamSpace()) return null;
  const node = card('Run by your teammates');
  if (!found.length) {
    return add(node, make('p', 'quiet', 'No teammate is running a deck right now, as far as '
      + 'this computer has been told.'), fetchLine());
  }
  const items = make('ul', 'rows');
  for (const one of found) {
    const title = one.title || 'Untitled';
    const go = capsule('Open', 'quiet', () => show('deck', { path: one.path }),
      'theirs ' + one.path);
    go.setAttribute('aria-label', 'Open ' + title + ', to read it');
    add(items, add(make('li', 'row'), add(make('div', 'row-text'),
      make('h3', 'row-title', title),
      one.driver ? whoSays(one.driver, 'who') : null,
      lastLine(one.last_shared, 'row-says')
        || (one.sentence ? make('p', 'row-says', one.sentence) : null),
      noticeLine(one)), go));
  }
  return add(node, make('p', 'quiet', 'Each can be opened and read here. Only the computer '
    + 'that runs a deck can change it.'), items, fetchLine());
}

// --- with a team: the computer's own notification ----------------------------------------

async function setNotify(index, node) {
  if (view.notifying) return;
  view.notifying = true;
  view.unnotified = '';
  slide(node, index);
  try {
    tookSetup(await send('setup', { notify: Boolean(index) }));
    toast(index ? 'On. This computer tells you when no page is open.'
      : 'Off. This computer says nothing when no page is open.');
  } catch (failure) {
    // The thumb slides home again: the card is not built again when it says what it said.
    slide(node, index ? 0 : 1);
    view.unnotified = failure.message + ' Nothing was changed.';
  }
  view.notifying = false;
  if (view.screen === 'settings') draw(false);
}

// Settings: the notification for when no page is open. It is the computer's own, and is kept
// apart from the browser's, which is the card above.
function notifyCard() {
  const found = view.setup ? view.setup.notify : null;
  if (!found) return null;
  const node = add(card('When this page is closed'), make('p', '', NOTIFY_SAYS));
  if (found.can) {
    add(node, add(make('div', 'setting'),
      make('p', 'row-title', 'Tell me when no page is open'),
      segmented('Tell me when no page is open', ['Off', 'On'], found.on ? 1 : 0, setNotify,
        'notify')));
    if (found.problem) add(node, make('p', 'fix', found.problem));
  } else {
    add(node, state('off', found.on ? 'Turned on, but this computer cannot do it now.'
      : 'This computer cannot do this.'),
    make('p', 'fix', found.problem || 'It has no way to show a notification of its own.'));
  }
  const problem = alertLine('notify-problem');
  say(problem, view.unnotified);
  return add(node, problem, make('p', 'quiet', NOTIFY_DIFFERS));
}
// --- Presentation Studio and its skills --------------------------------------------------------
// What the runner found when it last looked at its links, the companion skills and the
// releases. It puts back by itself only what the installer placed. A companion is brought
// only once the person says yes in the sheet, and a newer release is only ever said.

function upkeepOf() {
  return view.setup ? view.setup.upkeep || null : null;
}

function wantedCompanions(found) {
  return list(found && found.companions).filter((one) => ['missing', 'older']
    .includes(one.state));
}

function updating(found) {
  return Boolean(found && found.update && found.update.state === 'running');
}

// What the update in hand is doing, or how the last one went. None before there was one.
function updateLine(found) {
  const update = (found && found.update) || {};
  if (!update.state) return null;
  const node = add(make('p', ''), state(update.state === 'running' ? 'current'
    : update.state === 'done' ? 'done' : 'late', update.says || ''));
  if (update.state === 'running' && !Number.isNaN(Date.parse(update.since))) {
    add(node, ' Started ', when(update.since), '.');
  }
  return node;
}

// The way to the sheet that asks before the companions are brought.
function updateBar(found) {
  if (!found || !found.update || !found.update.offered) return null;
  return add(make('div', 'bar'), capsule('Update the skills', '', openSheet('companions',
    'update-skills'), 'update-skills'));
}

// --- versions: what is installed, the newest, and upgrading Presentation Studio -----------------
// The runner works out every row; the page only says it. Presentation Studio is upgraded only
// once the person says yes in the sheet, and restarted only when they press Restart.

function versionsOf() {
  const found = upkeepOf();
  return found && found.versions ? found.versions : null;
}

function upgradeOf(found) {
  return (found && found.upgrade) || {};
}

// The brand skill's install: what it would install, from where, and how the last one went.
function brandOf(found) {
  return (found && found.brand) || {};
}

// Whether Home tells of the versions: an upgrade or a brand install in hand or how it went,
// an upgrade waiting for a restart, or something newer or missing, until it is dismissed.
function versionsNotice() {
  const found = versionsOf();
  if (!found) return false;
  if (['running', 'restart', 'restarting', 'failed'].includes(upgradeOf(found).state)) return true;
  if (['running', 'failed', 'changed'].includes(brandOf(found).state)) return true;
  return Boolean(found.key && !found.dismissed);
}

function wantedRows(found) {
  return list(found && found.rows).filter((row) => ['update', 'missing'].includes(row.state));
}

// The companions among what is wanted: what comes with a newer Presentation Studio.
function wantedCompanionRows(found) {
  return wantedRows(found).filter((row) => row.name !== OWN_NAME && row.kind !== 'brand');
}

// One row's versions in a few words: from what is here to what it would be.
function versionStep(row) {
  if (row.state === 'missing') {
    return row.name + (row.target ? ' ' + row.target : '') + ', which is missing';
  }
  return row.name + ' ' + row.installed + ' → ' + row.target;
}

// What the upgrade in hand is doing, or how it went, with Restart once it is installed.
function upgradeParts(found) {
  const upgrade = upgradeOf(found);
  if (!upgrade.state) return [];
  const shape = { running: 'current', restart: 'done', restarting: 'current' }[upgrade.state]
    || 'late';
  const parts = [add(make('p', ''), state(shape, upgrade.says || ''))];
  if (upgrade.state === 'restart' && upgrade.restart) {
    const go = capsule('Restart', 'quiet', () => restartNow(go), 'restart');
    parts.push(add(make('div', 'bar'), go));
  }
  return parts;
}

// What the brand skill's install in hand is doing, or how it went.
function brandParts(found) {
  const brand = brandOf(found);
  if (!brand.state) return [];
  const shape = { running: 'current', done: 'done' }[brand.state] || 'late';
  const node = add(make('p', ''), state(shape, brand.says || ''));
  if (brand.state === 'running' && !Number.isNaN(Date.parse(brand.since))) {
    add(node, ' Started ', when(brand.since), '.');
  }
  return [node];
}

// The ways on from the versions: upgrade, the companions' own update, the brand skill's
// install, or the command a checkout is upgraded with.
function versionsBar(found, dismiss) {
  const upkeep = upkeepOf();
  const upgrade = upgradeOf(found);
  const buttons = [];
  if (upgrade.offered) {
    const companions = wantedCompanionRows(found).length > 0;
    buttons.push(capsule(companions ? 'Upgrade everything' : 'Upgrade', '',
      openSheet('upgrade', 'upgrade'), 'upgrade'));
  } else if (!upgrade.state && upkeep && upkeep.update && upkeep.update.offered) {
    buttons.push(capsule('Update the skills', '', openSheet('companions', 'update-skills'),
      'update-skills'));
  }
  const brand = brandOf(found);
  if (brand.offered && brand.state !== 'running') {
    buttons.push(capsule(brand.action + ' the brand skill', '', openSheet('brand', 'brand'),
      'brand'));
  }
  if (dismiss && found.key && !upgrade.state) {
    buttons.push(capsule('Dismiss', 'quiet', () => dismissVersions(found.key), 'dismiss'));
  }
  const parts = buttons.length ? [add(make('div', 'bar'), ...buttons)] : [];
  if (found.checkout && found.command && wantedRows(found).length) {
    parts.unshift(make('p', 'sentence', found.command));
    parts.push(add(make('div', 'bar'), copyButton('Copy the command', 'Command copied',
      found.command, 'copy-update')));
  }
  return parts;
}

// Home: said only when something is newer or missing, or an upgrade is in hand.
function updatesCard() {
  const upkeep = upkeepOf();
  if (!upkeep) return null;
  const found = versionsOf();
  if (!versionsNotice() && !updating(upkeep)) return null;
  const node = card('Updates');
  if (found && versionsNotice()) {
    const wanted = wantedRows(found);
    if (wanted.length && !['restart', 'restarting'].includes(upgradeOf(found).state)) {
      add(node, make('p', '', 'Newer versions are ready for this computer:'),
        bullets(wanted.map(versionStep)));
      for (const row of wanted) add(node, add(make('p', ''), state('review', row.says)));
    }
    add(node, ...upgradeParts(found), ...brandParts(found));
  }
  if (updating(upkeep)) add(node, updateLine(upkeep));
  else if (found && versionsNotice()) add(node, ...versionsBar(found, true));
  return node;
}

// Status: a row for Presentation Studio, each companion and the brand skill, with everything
// that was said of each.
function versionsCard() {
  const found = versionsOf();
  if (!found) return null;
  const node = card('Versions');
  node.id = 'versions';
  const table = make('table', 'table');
  const head = make('tr');
  for (const title of ['Skill', 'Installed', 'Newest', 'Pinned to', 'State']) {
    const top = make('th', '', title);
    top.scope = 'col';
    head.append(top);
  }
  const body = make('tbody');
  for (const row of list(found.rows)) {
    const name = make('th', '', row.name);
    name.scope = 'row';
    const [shape, words] = VERSION_STATES[row.state] || VERSION_STATES.unknown;
    const pinned = row.pinned ? row.pinned + (row.next && row.next !== row.pinned
      ? ', ' + row.next + ' with the newest Presentation Studio' : '') : '—';
    body.append(add(make('tr'), name, cell('Installed', row.installed || 'not installed'),
      cell('Newest', row.newest || 'not known'), cell('Pinned to', pinned),
      cell('State', state(shape, words))));
  }
  add(node, add(table, add(make('thead'), head), body));
  const facts = make('ul', 'facts');
  for (const row of list(found.rows)) {
    for (const said of [row.says, row.beyond, row.reports]) {
      if (said) facts.append(add(make('li', 'fact'), bead(said === row.says
        ? (VERSION_STATES[row.state] || VERSION_STATES.unknown)[0] : 'none'),
      make('span', '', said)));
    }
  }
  add(node, facts, ...upgradeParts(found), ...brandParts(found), ...versionsBar(found, false));
  const releases = (upkeepOf() || {}).releases || {};
  const known = (list(found.rows)[0] || {}).known_at;
  add(node, releasesLine(upkeepOf()));
  if (releases.problem && known && !Number.isNaN(Date.parse(known))) {
    add(node, add(make('p', 'quiet'), 'What is shown was last known ', when(known), '.'));
  }
  return node;
}

// The sheet that asks before Presentation Studio is upgraded: what, from where, and what next.
function upgradeSheet() {
  const found = versionsOf();
  const upgrade = upgradeOf(found);
  const cancel = capsule('Cancel', 'quiet', closeSheet, 'cancel');
  if (!upgrade.offered) {
    return [sheetTitle('Upgrade Presentation Studio?'), make('p', '', upgrade.says
      || 'There is nothing to upgrade now.'), add(make('div', 'bar'), cancel)];
  }
  const own = list(found.rows)[0] || {};
  const companions = wantedCompanionRows(found);
  const problem = problemLine();
  const confirm = capsule('Upgrade now', 'filled', () => settleUpgrade(problem, confirm),
    'send');
  const parts = [sheetTitle('Upgrade Presentation Studio to ' + upgrade.version + '?'),
    make('h3', 'sheet-part', 'What happens'),
    bullets(['Presentation Studio ' + upgrade.version + ' is fetched from '
      + (upgrade.from === 'tag' ? 'its release' : 'the newest version on ' + upgrade.from)
      + ' in Presentation Studio’s own repository, and its own installer checks it.',
    'It is installed beside ' + (own.installed || 'this version') + '. ' + UPGRADE_KEEPS,
    'Then you restart Presentation Studio to use it. This page comes back by itself.'])];
  if (companions.length) {
    parts.push(make('h3', 'sheet-part', 'Then the skills'),
      make('p', '', 'After the restart, Home offers the companion skills Presentation Studio '
        + upgrade.version + ' is made with, to bring with one more yes:'),
      bullets(companions.map(versionStep)));
  }
  return [...parts, make('p', 'quiet', UPGRADE_WAITS), problem,
    add(make('div', 'bar'), confirm, cancel)];
}

async function settleUpgrade(problem, pressed) {
  if (view.busy) return;
  const turn = view.turn;
  view.busy = true;
  pressed.disabled = true;
  let answered;
  try {
    answered = await send('upgrade', { version: upgradeOf(versionsOf()).version });
  } catch (failure) {
    view.busy = false;
    if (turn !== view.turn) return;
    say(problem, failure.message + ' Nothing was changed.');
    pressed.disabled = false;
    pressed.focus();
    return;
  }
  view.busy = false;
  if (turn !== view.turn) return;
  if (view.setup && answered) view.setup = { ...view.setup, upkeep: answered.upkeep };
  closeSheet();
  toast('Upgrading Presentation Studio. Home and the Status screen say how it goes.');
  draw(false);
}

// The sheet that asks before the brand skill is installed: the repository, the release and
// its revision, and what happens. Nothing is fetched or run before the yes.
function brandSheet() {
  const brand = brandOf(versionsOf());
  const cancel = capsule('Cancel', 'quiet', closeSheet, 'cancel');
  if (!brand.offered) {
    return [sheetTitle('Install the brand skill?'), make('p', '', brand.says
      || 'There is nothing to install now.'), add(make('div', 'bar'), cancel)];
  }
  const problem = problemLine();
  const confirm = capsule(brand.action + ' it now', 'filled', () => settleBrandInstall(problem,
    confirm), 'send');
  return [sheetTitle(brand.action === 'Upgrade'
    ? 'Upgrade the brand skill from ' + brand.installed + ' to ' + brand.version + '?'
    : 'Install the brand skill ' + brand.version + '?'),
  make('h3', 'sheet-part', 'What is installed'),
  bullets(['Release ' + brand.release + ', at revision ' + brand.commit + '.',
    'From ' + brand.repository + '.']),
  make('h3', 'sheet-part', 'What happens'), bullets(BRAND_STEPS),
  make('p', '', BRAND_TRUST), make('p', 'quiet', BRAND_WAITS), problem,
  add(make('div', 'bar'), confirm, cancel)];
}

async function settleBrandInstall(problem, pressed) {
  if (view.busy) return;
  const turn = view.turn;
  view.busy = true;
  pressed.disabled = true;
  let answered;
  try {
    answered = await send('brand/install', { release: brandOf(versionsOf()).release });
  } catch (failure) {
    view.busy = false;
    if (turn !== view.turn) return;
    say(problem, failure.message + ' Nothing was changed.');
    pressed.disabled = false;
    pressed.focus();
    return;
  }
  view.busy = false;
  if (turn !== view.turn) return;
  if (view.setup && answered) view.setup = { ...view.setup, upkeep: answered.upkeep };
  closeSheet();
  toast('Installing the brand skill. Home and the Status screen say how it goes.');
  draw(false);
}

async function dismissVersions(key) {
  try {
    const answered = await send('versions', { dismiss: key });
    if (view.setup && answered) view.setup = { ...view.setup, upkeep: answered.upkeep };
  } catch (failure) {
    toast(failure.message);
    return;
  }
  toast('Dismissed. Home says so again when a newer version is out.');
  setTitle();
  draw(false);
}

// Restart: the runner stops and opens its newer version, on the same address and with the
// same key, so this page waits for it and then loads the newer page.
async function restartNow(pressed) {
  if (view.restarting) return;
  const version = upgradeOf(versionsOf()).version;
  pressed.disabled = true;
  let answered;
  try {
    answered = await send('restart', {});
  } catch (failure) {
    pressed.disabled = false;
    toast(failure.message);
    return;
  }
  if (view.setup && answered) view.setup = { ...view.setup, upkeep: answered.upkeep };
  view.restarting = true;
  view.comingBack = { version, tries: 0 };
  toast('Restarting Presentation Studio. This page comes back by itself.');
  draw(false);
  window.setTimeout(comeBack, 1000);
}

// Asked once a second: whether the newer version answers yet. Once it does, its page is
// loaded. If it never does, the person is told to open it again.
async function comeBack() {
  const waiting = view.comingBack;
  if (!waiting) return;
  try {
    const found = await ask('capabilities');
    if (found && found.version === waiting.version) {
      window.location.reload();
      return;
    }
  } catch (failure) {
    // Not there yet, while it stops and starts again.
  }
  waiting.tries += 1;
  if (waiting.tries < COME_BACK_TRIES) {
    window.setTimeout(comeBack, 1000);
    return;
  }
  view.restarting = false;
  view.comingBack = null;
  notify('Presentation Studio did not come back by itself. Open it again with its command or '
    + 'its launcher.');
}

// What set-up says, and a browser notification once for each newer version Home tells of.
function tookSetup(found) {
  view.setup = found;
  view.setupAt = Date.now();
  const versions = versionsOf();
  const key = versions && versions.key && !versions.dismissed ? versions.key : null;
  const before = view.versionsTold;
  view.versionsTold = key;
  if (before === undefined || !key || key === before || alerts() !== 'granted') return;
  try {
    const note = new Notification('Presentation Studio can be upgraded',
      { body: wantedRows(versions).map(versionStep).join('; '), tag: 'versions' });
    note.onclick = () => {
      window.focus();
      note.close();
      show('home');
    };
  } catch (failure) {
    // A browser that will not show one still has the count in the tab title.
  }
}

function linkWords(link) {
  if (link.state === 'ok') return ['done', link.assistant + ': Presentation Studio is linked.'];
  if (link.state === 'repaired') return ['done', link.says];
  return [link.state === 'missing' ? 'late' : 'none', link.says];
}

const COMPANION_BEADS = { ok: 'done', missing: 'late', older: 'late', unread: 'none' };

function releasesLine(found) {
  const releases = (found && found.releases) || {};
  if (releases.on === false) {
    return make('p', 'quiet', 'Looking online for newer releases is turned off, in Settings.');
  }
  if (releases.problem) return make('p', 'fix', releases.problem);
  if (!releases.at || Number.isNaN(Date.parse(releases.at))) {
    return make('p', 'quiet', 'Newer releases have not been looked for yet.');
  }
  return add(make('p', 'quiet'), 'Newer releases were last looked for ', when(releases.at),
    list(releases.newer).length ? '.' : '. Nothing newer was found.');
}

// Status: everything that was found, what was put back, and the update.
function skillsCard() {
  const found = upkeepOf();
  if (!found) return null;
  const node = card('Presentation Studio and its skills');
  add(node, make('p', '', 'Presentation Studio ' + found.version + '.'
    + (found.guidance && found.guidance.says ? ' ' + found.guidance.says : '')));
  if (found.checking) {
    return add(node, make('p', 'quiet', 'Looking at the skills on this computer.'));
  }
  if (found.problem) add(node, make('p', 'fix', found.problem));
  const facts = make('ul', 'facts');
  for (const link of list(found.links)) {
    const [shape, words] = linkWords(link);
    facts.append(add(make('li', 'fact'), bead(shape), make('span', '', words)));
  }
  for (const one of list(found.companions)) {
    facts.append(add(make('li', 'fact'), bead(COMPANION_BEADS[one.state] || 'none'),
      make('span', '', one.says)));
  }
  add(node, facts);
  for (const said of list(found.repaired)) {
    if (!list(found.links).some((link) => link.says === said)) {
      add(node, add(make('p', ''), state('done', said)));
    }
  }
  return add(node, updateLine(found), updating(found) ? null : updateBar(found));
}

// The sheet that asks before the companions are brought: what, from where, and how.
function updateSheet() {
  const wanted = wantedCompanions(upkeepOf());
  const head = sheetTitle('Update the companion skills?');
  const cancel = capsule('Cancel', 'quiet', closeSheet, 'cancel');
  if (!wanted.length) {
    return [head, make('p', '', 'Every companion skill is already as new as this Presentation '
      + 'Studio was made with.'), add(make('div', 'bar'), cancel)];
  }
  const problem = problemLine();
  const confirm = capsule('Update them now', 'filled', () => settleUpdate(problem, confirm),
    'send');
  return [head, make('h3', 'sheet-part', 'What is brought'),
    bullets(wanted.map((one) => one.name + ' ' + one.wanted + ', from ' + one.repository
      + ' at revision ' + one.commit + '.')),
    make('p', '', UPDATE_SAYS),
    ...wanted.filter((one) => one.note).map((one) => make('p', '', one.note)),
    make('p', 'quiet', UPDATE_WAITS), problem,
    add(make('div', 'bar'), confirm, cancel)];
}

async function settleUpdate(problem, pressed) {
  if (view.busy) return;
  const turn = view.turn;
  view.busy = true;
  pressed.disabled = true;
  let answered;
  try {
    answered = await send('companions', {});
  } catch (failure) {
    view.busy = false;
    if (turn !== view.turn) return;
    say(problem, failure.message + ' Nothing was changed.');
    pressed.disabled = false;
    pressed.focus();
    return;
  }
  view.busy = false;
  if (turn !== view.turn) return;
  if (view.setup && answered) view.setup = { ...view.setup, upkeep: answered.upkeep };
  closeSheet();
  toast('Updating the skills. The Status screen says how it goes.');
  draw(false);
}

async function setLook(index, node) {
  if (view.turningLook) return;
  view.turningLook = true;
  view.lookRefused = '';
  slide(node, index);
  try {
    tookSetup(await send('setup', { look_for_updates: Boolean(index) }));
    toast(index ? 'On. Presentation Studio looks for newer releases once a day.'
      : 'Off. Presentation Studio no longer looks online for newer releases.');
  } catch (failure) {
    slide(node, index ? 0 : 1);
    view.lookRefused = failure.message + ' Nothing was changed.';
  }
  view.turningLook = false;
  if (view.screen === 'settings') draw(false);
}

// Settings, with the runner: whether it looks online for newer releases.
function lookCard() {
  const found = view.setup ? view.setup.updates : null;
  if (!found) return null;
  const node = add(card('Updates'), make('p', '', LOOK_SAYS),
    add(make('div', 'setting'), make('p', 'row-title', 'Look for updates once a day'),
      segmented('Look for updates once a day', ['Off', 'On'], found.look ? 1 : 0, setLook,
        'look')));
  const problem = alertLine('look-problem');
  say(problem, view.lookRefused);
  return add(node, problem, add(make('div', 'bar'),
    capsule('See the versions', 'quiet', () => show('status'), 'see-versions')));
}

// Settings, with the runner: where the brand skill is installed from. What is typed is kept
// while the screen is drawn again, and is checked by the runner before it is saved.
function brandSourceCard() {
  const found = view.setup ? view.setup.brand : null;
  if (!found) return null;
  if (!view.brandForm) {
    view.brandForm = { repository: found.repository || '', release: found.release || '',
      seen: 'shared' in view.setup ? view.setup.shared : null };
  }
  const form = view.brandForm;
  const node = add(card('Brand skill'), make('p', '', BRAND_SAYS),
    field('brand-repository', 'Its repository', form, 'repository',
      { hint: 'An https or ssh address, as git clones it. Git reaches it as you, without '
        + 'asking for anything.' }),
    field('brand-release', 'Which release', form, 'release',
      { short: true, hint: 'Empty for the newest, or a release’s tag, such as v1.4.0.' }));
  if (found.repository) {
    add(node, make('p', 'quiet', 'Installed from ' + found.repository + ', '
      + (found.release ? 'release ' + found.release : 'the newest release') + '.'));
  }
  const problem = alertLine('brand-problem');
  say(problem, view.brandRefused);
  const save = capsule(view.savingBrand ? 'Checking…' : 'Check and save', '',
    () => saveBrand(save), 'brand-save');
  save.disabled = view.savingBrand;
  return add(node, problem, add(make('div', 'bar'), save,
    capsule('See the versions', 'quiet', () => show('status'), 'brand-versions')));
}

async function saveBrand(pressed) {
  if (view.savingBrand) return;
  const form = view.brandForm;
  const repository = form.repository.trim();
  view.savingBrand = true;
  view.brandRefused = '';
  pressed.disabled = true;
  try {
    const body = { repository, release: form.release.trim() };
    if (form.seen) body.shared_seen = form.again ? view.setup.shared || {} : form.seen;
    tookSetup(await send('brand', body));
    view.brandForm = null;
    toast(repository ? 'Saved. The Status screen shows which release can be installed.'
      : 'Forgotten. A brand skill already installed is still used.');
  } catch (failure) {
    view.brandRefused = failure.message + ' Nothing was changed.';
    // What is typed here is the person's own: saved again, it is meant over what the page
    // has read by then.
    form.again = true;
  }
  view.savingBrand = false;
  if (view.screen === 'settings') draw(false);
}

// --- with a team: what is published ------------------------------------------------------

// --- with a team: what is published ------------------------------------------------------
// Each deck the workspace has published, at its latest revision.

function publishedRow(found) {
  const title = found.title || 'Untitled';
  const facts = add(make('p', ''), 'Revision ' + found.revision + ', published ',
    when(found.at), found.by ? ' by ' + found.by : '', '.');
  const go = capsule('Open', 'quiet', () => show('deck', { path: found.path }),
    'published ' + found.path);
  go.setAttribute('aria-label', 'Open ' + title);
  // The deck that opens is as it stands on this computer now. Where it has changed since
  // the revision, that is not what was published, and is said.
  const moved = found.current === false ? make('p', 'fix', 'It has changed on this computer '
    + 'since revision ' + found.revision + ' was published, so what opens is the deck as it '
    + 'stands now, not as it was published. Publish it again to make that the next '
    + 'revision.') : null;
  return add(make('li', 'row'), add(make('div', 'row-text'),
    make('h3', 'row-title', title), facts,
    found.ready ? state('done', 'Delivered when it was published')
      : state('late', 'Not delivered yet when it was published'), moved), go);
}

function paintPublished(fresh) {
  const found = view.shelf;
  if (!found.length) {
    place({ title: 'Published', back: true }, [add(make('section', 'card shine invite'),
      make('h2', 'invite-title', 'Nothing is published yet'),
      make('p', '', 'A finished deck is published from its own screen: open it, and choose '
        + '“Publish”. It is then listed here.'),
      add(make('div', 'bar'), capsule('See your decks', 'filled', () => show('decks'),
        'home')))], fresh);
    return;
  }
  const items = make('ul', 'rows');
  for (const entry of found) items.append(publishedRow(entry));
  place({ title: 'Published', back: true },
    [make('p', 'intro lede', count(found.length, 'deck is', 'decks are')
      + ' published in this workspace, each shown at its latest revision. A revision is '
      + 'never moved once it is published.'),
    add(card('Published decks'), items)], fresh);
}

async function drawPublished(fresh) {
  const turn = view.turn;
  if (fresh) {
    view.shelf = null;
    place({ title: 'Published', back: true },
      [make('p', 'quiet', 'Reading what is published.')], true);
  }
  try {
    const found = list((await ask('published')).published);
    if (turn !== view.turn) return;
    const mark = JSON.stringify(found);
    if (view.shelf && mark === view.drawn) return;
    const first = !view.shelf;
    view.shelf = found;
    view.drawn = mark;
    paintPublished(first);
  } catch (failure) {
    if (turn !== view.turn) return;
    if (!view.shelf) view.drawn = 'unread';
    unopened(failure, view.shelf, true, { title: 'What is published cannot be read',
      said: 'Nothing was changed. Whatever is published is as it was.',
      back: 'Back to your decks', to: () => show('decks') });
  }
}

// --- staying up to date --------------------------------------------------------------

function waitingKey(brief) {
  return brief.path + '\n' + brief.sentence;
}

// Tell the person, once, about each new thing that needs them. A notification that is
// clicked opens the deck it was about.
function took(found) {
  view.decks = { needs: list(found.needs), working: list(found.working),
    finished: list(found.finished), elsewhere: list(found.elsewhere) };
  const waiting = view.decks.needs;
  view.needs = waiting.length;
  // What the runner says about who has a deck is told once when it is new: that one was
  // taken from this computer, or was changed on two at once.
  const noticed = {};
  for (const brief of every()) {
    if (!brief.notice) continue;
    noticed[brief.path] = brief.notice;
    if (view.known && view.noticed[brief.path] !== brief.notice) {
      toast((brief.title || 'Untitled') + ': ' + brief.notice);
    }
  }
  view.noticed = noticed;
  const keys = waiting.map(waitingKey);
  for (const brief of view.known ? waiting : []) {
    if (view.known.includes(waitingKey(brief))) continue;
    const said = (brief.title || 'Untitled') + ': ' + brief.sentence;
    toast(said);
    if (alerts() !== 'granted') continue;
    try {
      const note = new Notification('Presentation Studio needs you',
        { body: said, tag: waitingKey(brief) });
      note.onclick = () => {
        window.focus();
        note.close();
        show('deck', { path: brief.path });
      };
    } catch (failure) {
      // A browser that will not show one still has the count in the tab title.
    }
  }
  view.known = keys;
}

// Someone is in the middle of writing in a box: the list is left as it is until they are done.
function typing() {
  const active = document.activeElement;
  return Boolean(active && (active.tagName === 'TEXTAREA' || active.tagName === 'INPUT')
    && active.value && main().contains(active) && active.id !== 'decks-search');
}

// A deck that is working is read more often, while its own screen is open.
function pace() {
  if (document.hidden) return POLL_HIDDEN;
  return view.screen === 'deck' && view.run && view.run.state === 'working' ? POLL_RUN
    : POLL_SHOWN;
}

function later() {
  window.clearTimeout(view.timer);
  view.timer = window.setTimeout(refresh, pace());
}

// One refresh at a time, so an older answer never lands after a newer one. One asked for
// while another is in hand is done once that one is, and once however often it was asked.
async function refresh() {
  window.clearTimeout(view.timer);
  if (view.refreshing) {
    view.again = true;
    return view.refreshing;
  }
  view.refreshing = (async () => {
    do {
      view.again = false;
      await catchUp();
    } while (view.again);
  })();
  try {
    await view.refreshing;
  } finally {
    view.refreshing = null;
  }
  later();
  return undefined;
}

// Read what has changed and draw it. A tab nobody is looking at reads only the list, for the
// count in its title and what to tell; the rest is read when it is looked at again.
async function catchUp() {
  // While the runner opens its newer version, it is not there to be asked.
  if (view.restarting) return;
  try {
    if (document.hidden && view.decks) {
      // Set-up is read now and then too, for a newer version to be told of.
      const setup = Date.now() - view.setupAt > SETUP_HIDDEN;
      const [found, listing] = await Promise.all([setup ? ask('setup') : null,
        ask('decks')]);
      if (setup) tookSetup(found);
      took(listing);
      notify('');
      setTitle();
      return;
    }
    // Set-up is read where it is shown, and once to begin with.
    const setup = !view.setup || SET_UP_SHOWN.includes(view.screen);
    const [found, listing] = await Promise.all([setup ? ask('setup') : null, ask('decks')]);
    if (setup) tookSetup(found);
    took(listing);
    await Promise.all([
      view.computer === undefined
        ? ask('computer').then((seen) => { view.computer = seen.computer; }) : null,
      view.screen === 'status' ? readStatus() : null]);
    notify('');
    setTitle();
    for (const node of document.querySelectorAll('time')) {
      const then = Date.parse(node.dateTime);
      if (!Number.isNaN(then)) node.textContent = ago(then);
    }
    frame();
    if (unset() && view.screen !== 'setup') {
      show('setup', null, true);
    } else if (['deck', 'published'].includes(view.screen)) {
      await draw(false);
    } else if (view.screen === 'setup' || view.screen === 'new') {
      // A form is drawn once and never again under the person filling it in.
      if (!view.drawn) draw(true);
    } else if (!view.busy && !view.checking && !view.notifying && !view.turningLook
        && !view.savingBrand && !typing()
        && view.drawn !== signature()) {
      draw(!view.drawn);
    }
  } catch (failure) {
    // Reading the list needs nothing but the key, so a refusal here is about the link.
    notify(failure.kind === 'refused' ? NOTICES.refused : failure.message);
  }
}

// A highlight on glass that follows the pointer. Not when the person asked for less motion.
function followPointer() {
  if (calm()) return;
  document.addEventListener('pointermove', (event) => {
    const lit = event.target && event.target.closest ? event.target.closest('.shine') : null;
    if (!lit) return;
    const box = lit.getBoundingClientRect();
    lit.style.setProperty('--mx', (event.clientX - box.left) + 'px');
    lit.style.setProperty('--my', (event.clientY - box.top) + 'px');
  }, { passive: true });
}

function linkToken() {
  const found = /(?:^#|&)token=([A-Za-z0-9_-]+)/.exec(window.location.hash);
  return found ? found[1] : '';
}

function begin() {
  view.token = linkToken();
  // A new link pasted into a tab that is already open changes only the fragment.
  window.addEventListener('hashchange', () => {
    const next = linkToken();
    if (next && next !== view.token) {
      view.token = next;
      refresh();
    }
  });
  for (const [id, screen, drawing] of NAV) {
    const item = byId(id);
    item.prepend(icon(drawing));
    item.addEventListener('click', () => show(screen));
  }
  window.addEventListener('popstate', (event) => {
    view.pushed = Math.max(0, view.pushed - 1);
    open(event.state || { screen: 'home' });
  });
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) refresh();
  });
  // Escape puts the sheet away.
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !byId('sheet').hidden && !view.busy) closeSheet();
  });
  // The arrow keys turn the slides, from the slides themselves or from the head of the
  // screen. They are left alone in a sheet, in a box, and with a modifier held, which is how
  // a browser goes back.
  document.addEventListener('keydown', (event) => {
    const by = { ArrowLeft: -1, ArrowRight: 1 }[event.key];
    if (!by || !view.viewer || !byId('sheet').hidden) return;
    if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    const active = document.activeElement;
    const slides = byId('slides');
    if (active && ![document.body, byId('title'), main()].includes(active)
        && !(slides && slides.contains(active))) return;
    view.viewer.move(by);
  });
  // The link's fragment holds the key, so the skip link must not replace it.
  document.querySelector('.skip').addEventListener('click', (event) => {
    event.preventDefault();
    main().focus();
  });
  followPointer();
  if (!view.token) {
    place({ title: 'This page needs its link' }, [], true);
    notify(NOTICES.refused);
    return;
  }
  open(window.history.state || { screen: 'home' });
  refresh();
}

begin();
