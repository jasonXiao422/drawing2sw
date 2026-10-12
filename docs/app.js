'use strict';

const EN = {
  skip: 'Skip to content',
  'nav.how': 'How it works', 'nav.parts': 'What it builds', 'nav.trust': 'Limits', 'nav.install': 'Install',
  'hero.kicker': 'Open-source agent skill · MIT',
  'hero.title': 'Give an AI your part drawing.<br>Get back a model you can <em>check</em>.',
  'hero.lede': 'The model reads the drawing. Deterministic code does the geometry. Every feature traces back to a dimension on the sheet, and every check says what it covered and what it didn’t.',
  'hero.start': 'Get started', 'hero.source': 'View source', 'hero.img': 'Images',
  'agents.label': 'For agents that can run local commands', 'agents.other': 'Cursor · other agents',
  'how.title': 'Only one step is left to the model',
  'how.sub': 'Ask a model to go straight from drawing to CAD code and you can’t tell where it went wrong. Drawing2SW splits the job up, with a file you can inspect at every handoff.',
  'flow.1.t': 'Extract evidence', 'flow.1.d': 'Native dimension entities from DWG/DXF, positioned text from PDF, automatic view splitting for images, optional OCR. All bound to the source file hash.',
  'flow.2.t': 'Model reads the drawing', 'flow.2.d': 'Confirms units and projection, links the views, decides which dimension belongs to which feature. Asks instead of guessing.',
  'flow.3.t': 'Validate', 'flow.3.d': 'JSON Schema, evidence references and engineering rules. Tangent and intersection points are computed, so the model only writes dimensions that are on the drawing.',
  'flow.4.t': 'Preview and review', 'flow.4.d': 'CadQuery writes a STEP and projects it into four wireframe views to overlay on the drawing.',
  'flow.5.t': 'Build in SolidWorks', 'flow.5.d': 'Feature by feature over COM. Each step is compared with CadQuery for volume and position, so a failure points to a feature.',
  'demo.caption': 'feature table excerpt',
  'demo.t': 'Every feature can name its source',
  'demo.p1': '<code>evidence_refs</code> point to specific annotations in the evidence file, which is bound to the drawing’s SHA-256. Swap the drawing or edit the file and validation fails.',
  'demo.p2': 'The table is CAD-neutral. The same file produces a STEP and drives SolidWorks, and the two results check each other.',
  'parts.title': 'What it can build',
  'parts.sub': 'All three are generated straight from feature tables in the repository. You can reproduce them.',
  'g.flange': 'Revolved flange', 'g.bracket': 'Mounting plate', 'g.plate': 'Two-hole plate (synthetic test)',
  'cap.rev': 'Revolved parts', 'cap.rev.d': 'Shafts, flanges, sleeves, discs; boss or cut revolved about any axis',
  'cap.pri': 'Prismatic parts', 'cap.pri.d': 'Plates, brackets, bases; extrudes, cuts, line-and-arc profiles, tangent arc loops',
  'cap.hole': 'Holes', 'cap.hole.d': 'Plain, tap drill, counterbore, countersink, drill point, bolt circles',
  'cap.detail': 'Details', 'cap.detail.d': 'Chamfers, fillets, inclined planes, cut up to a curved face, involute spur teeth',
  'cap.setup': 'Drawing setup', 'cap.setup.d': 'mm / inch, first / third angle projection, scale, dual units',
  'cap.no': 'Not yet', 'cap.no.d': 'Sheet metal, assemblies, sweep and loft, shell, general patterns. The agent says so instead of faking it.',
  'trust.title': 'What “passed” actually means',
  'trust.sub': 'A matching volume doesn’t mean the drawing was read correctly. These are errors the checks can’t catch, and Drawing2SW doesn’t pretend otherwise.',
  't1.t': 'Mirrored parts', 't1.d': 'Get the projection method backwards and volume, area and bounding box all still match. A person has to confirm the projection.',
  't2.t': 'Shifted holes', 't2.d': 'Move a hole 2 mm and the volume stays the same. Catch it with a projection overlay or a boolean comparison against a reference model.',
  't3.t': 'Both backends wrong together', 't3.d': 'CadQuery and SolidWorks execute the same feature table. If the table is wrong, they agree on the wrong answer.',
  'trust.foot': 'That’s why <code>drawing_verified</code> in <code>verify_model.py</code> is always <code>false</code>. At hand-off, the agent lists which checks passed, which weren’t run, and what it assumed.',
  'install.title': 'Up and running in five minutes',
  'install.sub': 'Needs Python 3.11 or 3.12. STEP preview works without SolidWorks, on macOS and Linux too.',
  'tab.other': 'Other agents', copy: 'Copy',
  's1.t': 'Run an example first', 's1.d': 'No AI needed. Make sure the environment works:',
  's2.t': 'Hand it to the agent', 's2.d': 'Just ask in plain language:',
  's2.c': 'Use drawing2sw to model D:\\drawings\\bracket.pdf as a SolidWorks part',
  's3.t': 'Answer its questions', 's3.d': 'Units, projection method, hole and keyway orientation, dimensions missing from the drawing. The agent stops and asks. These need a human.',
  'faq.title': 'FAQ',
  q1: 'Can I use it without SolidWorks?', a1: 'Yes. CadQuery writes STEP files that any CAD tool opens. Only .SLDPRT output needs Windows and SolidWorks; the student edition works.',
  q2: 'Which model works best?', a2: 'There’s no controlled blind comparison yet, so no claim. The model needs to see images and run local commands. The repo includes blind-run packaging; comparisons are welcome.',
  q3: 'Are my drawings uploaded?', a3: 'Preprocessing, modeling and checks all run locally. Only the reading step sends images to whichever AI model you use.',
  q4: 'What if it misreads the drawing?', a4: 'Tell it what’s wrong; it edits the feature table and rebuilds. If it’s a general reading mistake, please open an issue with a drawing you can share.',
  'foot.notices': 'Third-party notices', 'foot.issues': 'Report an issue'
};

const AGENTS = {
  claude: {
    cmd: 'git clone https://github.com/jasonXiao422/drawing2sw.git "$env:USERPROFILE\\.claude\\skills\\drawing2sw"\ncd "$env:USERPROFILE\\.claude\\skills\\drawing2sw"\npowershell -ExecutionPolicy Bypass -File install.ps1',
    zh: '装好后在 Claude Code 里输入 /drawing2sw，或者直接说"按这张图建模"。只在某个项目里用的话，放到项目的 .claude/skills/drawing2sw/。',
    en: 'Then type /drawing2sw in Claude Code, or just ask it to model a drawing. For one project only, use the project’s .claude/skills/drawing2sw/ instead.'
  },
  codex: {
    cmd: 'cd <你的项目>\ngit clone https://github.com/jasonXiao422/drawing2sw.git .agents\\skills\\drawing2sw\ncd .agents\\skills\\drawing2sw\npowershell -ExecutionPolicy Bypass -File install.ps1',
    cmdEn: 'cd <your-project>\ngit clone https://github.com/jasonXiao422/drawing2sw.git .agents\\skills\\drawing2sw\ncd .agents\\skills\\drawing2sw\npowershell -ExecutionPolicy Bypass -File install.ps1',
    zh: '在 Codex 里用 $drawing2sw 调用。skill 目录以 Codex 当前版本的文档为准。',
    en: 'Invoke it with $drawing2sw. Check the current Codex docs for the skill folder location.'
  },
  other: {
    cmd: 'git clone https://github.com/jasonXiao422/drawing2sw.git\ncd drawing2sw\npowershell -ExecutionPolicy Bypass -File install.ps1',
    zh: '放在 AI 能访问的目录里，然后告诉它："先读 drawing2sw/SKILL.md，按里面的步骤做。"需要 AI 能运行本地 Python。',
    en: 'Put it somewhere the agent can read, then tell it: “Read drawing2sw/SKILL.md first and follow it.” The agent must be able to run local Python.'
  }
};

const zh = {};
let lang = 'zh';
let agent = 'claude';
try { if (new URLSearchParams(location.search).get('lang') === 'en' || localStorage.getItem('d2sw-lang') === 'en') lang = 'en'; } catch (e) {}

document.querySelectorAll('[data-i18n]').forEach(el => { zh[el.dataset.i18n] = el.innerHTML; });
document.querySelectorAll('[data-i18n-html]').forEach(el => { zh[el.dataset.i18nHtml] = el.innerHTML; });

function render() {
  const dict = lang === 'en' ? EN : zh;
  document.documentElement.lang = lang === 'en' ? 'en' : 'zh-CN';
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const v = dict[el.dataset.i18n];
    if (v === undefined) return;
    el.innerHTML = v;  // 两种语言的文字都写在本文件和 index.html 里，不来自用户输入
  });
  document.querySelectorAll('[data-i18n-html]').forEach(el => {
    const v = dict[el.dataset.i18nHtml]; if (v !== undefined) el.innerHTML = v;
  });
  document.getElementById('lang').textContent = lang === 'en' ? '中文' : 'EN';
  document.title = lang === 'en' ? 'Drawing2SW · Part drawings to SolidWorks' : 'Drawing2SW · 从零件图到 SolidWorks';
  renderAgent();
}

function renderAgent() {
  const a = AGENTS[agent];
  document.getElementById('cmd').textContent = (lang === 'en' && a.cmdEn) ? a.cmdEn : a.cmd;
  document.getElementById('agent-note').textContent = a[lang];
  document.querySelectorAll('[data-agent]').forEach(b => b.setAttribute('aria-selected', String(b.dataset.agent === agent)));
}

document.getElementById('lang').addEventListener('click', () => {
  lang = lang === 'en' ? 'zh' : 'en';
  try { localStorage.setItem('d2sw-lang', lang); } catch (e) {}
  const url = new URL(location.href);
  if (lang === 'en') url.searchParams.set('lang', 'en'); else url.searchParams.delete('lang');
  history.replaceState(null, '', url);
  render();
});

document.querySelectorAll('[data-agent]').forEach(b => b.addEventListener('click', () => { agent = b.dataset.agent; renderAgent(); }));

document.getElementById('copy').addEventListener('click', async e => {
  const btn = e.currentTarget;
  try {
    await navigator.clipboard.writeText(document.getElementById('cmd').textContent);
    btn.textContent = lang === 'en' ? 'Copied' : '已复制';
  } catch (err) {
    btn.textContent = lang === 'en' ? 'Select to copy' : '请手动选中';
  }
  setTimeout(() => { btn.textContent = lang === 'en' ? EN.copy : zh.copy; }, 1600);
});

render();
