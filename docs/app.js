'use strict';

const EN = {
  skip: 'Skip to content',
  'nav.how': 'How it works', 'nav.parts': 'What it builds', 'nav.trust': 'Limits', 'nav.install': 'Install',
  'hero.kicker': 'Open-source agent skill · MIT',
  'hero.title': 'Reads your engineering drawings,<br>then models the part in <em>SolidWorks</em>.',
  'hero.lede': 'Works with DWG, DXF, PDF and images. The AI reads the drawing, scripts build the model. Every feature records which dimension it came from, and the result is checked against the answer.',
  'hero.source': 'View source', 'hero.img': 'Images',
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
  'parts.sub': 'All three are public practice drawings modelled from a blind read, with no answer model, checked by projecting back and comparing with the sheet. The third is a Chinese GB textbook drawing. All three pass every SolidWorks step check.',
  'g.frame': 'Bearing frame', 'g.frame.d': 'GB textbook drawing: barrel, side walls, rib, counterbored base, tapped end holes · 21 steps', 'g.pivot': 'S-shaped pivot arm', 'g.pivot.d': 'R75 / R35 reverse arcs, R55 centreline · 9 features',
  'g.crank': 'V-twin crank case', 'g.crank.d': 'Bores and tapped holes on two 30° faces · 14 features',
  'hero.tag.views': 'Views projected from the model',
  'hero.credit': 'Exercise 17 from Curtis Waguespack’s <a href="https://inventortrenches.blogspot.com/">Inventor practice drawings</a>. The original sheet is copyrighted and not reproduced; the left side is projected back from the finished model.',
  'cap.rev': 'Revolved parts', 'cap.rev.d': 'Shafts, flanges, sleeves, discs; boss or cut revolved about any axis',
  'cap.pri': 'Prismatic parts', 'cap.pri.d': 'Plates, brackets, bases; extrudes, cuts, line-and-arc profiles, tangent arc loops',
  'cap.hole': 'Holes', 'cap.hole.d': 'Plain, tap drill, counterbore, countersink, drill point, bolt circles',
  'cap.detail': 'Details', 'cap.detail.d': 'Chamfers, fillets, inclined planes, cut up to a curved face, linear and circular patterns, mirror, shell, involute spur teeth',
  'cap.setup': 'Drawing setup', 'cap.setup.d': 'mm / inch, first / third angle projection, scale, dual units',
  'cap.no': 'Not yet', 'cap.no.d': 'Sheet metal, assemblies, sweep and loft, multi-thickness shell. The agent says so instead of faking it.',
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
  'ai.t': 'Easiest: let your AI install it',
  'ai.d': 'Copy these install instructions and paste them to Claude Code, Codex or any agent that can run commands. It shows you what it will install and asks before every step.',
  'ai.btn': 'Copy install prompt', 'ai.show': 'See what the prompt says',
  'ai.hint': 'If the agent says its safety settings block downloading third-party code, that is a normal safeguard. Run the commands below yourself; it takes the same time.',
  'manual.t': 'Or install it yourself in a terminal',
  'hero.zip': 'Download ZIP',
  'zip.t': 'Or download the package',
  'zip.1': 'Unzip into your agent’s skills folder. For Claude Code that is <code>%USERPROFILE%\\.claude\\skills\\</code>, so you end up with <code>skills\\drawing2sw\\SKILL.md</code>.',
  'zip.2': 'Open a terminal in the <code>drawing2sw</code> folder and run <code>powershell -ExecutionPolicy Bypass -File install.ps1</code>.',
  'zip.3': 'Then ask your agent: “Use drawing2sw to model this drawing.”',
  'zip.btn': 'Download drawing2sw.zip',
  'hero.start': 'Install',
  'faq.title': 'FAQ',
  q1: 'Can I use it without SolidWorks?', a1: 'Yes. CadQuery writes STEP files that any CAD tool opens. Only .SLDPRT output needs Windows and SolidWorks; the student edition works.',
  q2: 'Which model works best?', a2: 'There’s no controlled blind comparison yet, so no claim. The model needs to see images and run local commands. The repo includes blind-run packaging; comparisons are welcome.',
  q3: 'Are my drawings uploaded?', a3: 'Preprocessing, modeling and checks all run locally. Only the reading step sends images to whichever AI model you use.',
  q4: 'What if it misreads the drawing?', a4: 'Tell it what’s wrong; it edits the feature table and rebuilds. If it’s a general reading mistake, please open an issue with a drawing you can share.',
  'foot.notices': 'Third-party notices', 'foot.issues': 'Report an issue'
};

const PROMPT = {
  zh: `请帮我安装 Drawing2SW 这个 skill。它用来读取工程图（DWG、DXF、PDF、图片），然后在 SolidWorks 里建模。

来源：官方 GitHub 仓库 https://github.com/jasonXiao422/drawing2sw （MIT 开源）。只从这个地址下载，不要用其他镜像或第三方页面。

每一步运行命令之前先告诉我要做什么，等我同意再执行。

1. 检查环境：运行 \`git --version\` 和 \`py -3.12 --version\`（没有 3.12 就试 \`py -3.11 --version\`）。缺 git 或 Python 3.11/3.12 时，告诉我怎么装，不要替我安装。
2. 下载到你读取 skill 的目录。Claude Code 是 \`%USERPROFILE%\\.claude\\skills\\drawing2sw\`；其他 AI 请用你自己的个人 skill 目录，不确定就问我。命令：
   git clone --depth 1 https://github.com/jasonXiao422/drawing2sw.git <上面的目录>
   如果目录已经存在，进去运行 \`git pull\` 更新。
3. 下载完先给我看 SKILL.md 开头 20 行，并说明 install.ps1 会做什么（在 skill 目录里建一个 .venv，从 PyPI 装 requirements.txt 里的依赖，默认源失败时换清华镜像，最后跑环境自检）。等我确认。
4. 在 skill 目录里运行：powershell -ExecutionPolicy Bypass -File install.ps1 （CadQuery 比较大，要几分钟）。如果某个包几分钟没有下载进展，停掉，先设 $env:PIP_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple" 再重新运行同一条命令，不要自己改装别的版本。
5. 运行 \`.venv\\Scripts\\python.exe scripts\\check_env.py\` 并把结果告诉我。我装了 SolidWorks 的话，再加 \`--sw\` 检查一次。
6. 告诉我装好了，以后怎么用。比如我说"用 drawing2sw 把 D:\\图纸\\支架.pdf 建成 SolidWorks 零件"。

如果你的安全设置不允许下载或运行这些命令，直接告诉我，我自己在终端里运行。`,
  en: `Please install the Drawing2SW skill for me. It reads engineering drawings (DWG, DXF, PDF, images) and models the part in SolidWorks.

Source: the official GitHub repository https://github.com/jasonXiao422/drawing2sw (MIT). Download only from this address, not from mirrors or third-party pages.

Before running each command, tell me what it does and wait for my OK.

1. Check the environment: run \`git --version\` and \`py -3.12 --version\` (or \`py -3.11 --version\`). If git or Python 3.11/3.12 is missing, tell me how to install it; don't install it for me.
2. Download into your skills folder. For Claude Code that is \`%USERPROFILE%\\.claude\\skills\\drawing2sw\`; other agents should use their own personal skills folder, ask me if unsure:
   git clone --depth 1 https://github.com/jasonXiao422/drawing2sw.git <that folder>
   If the folder already exists, run \`git pull\` inside it instead.
3. Show me the first 20 lines of SKILL.md and explain what install.ps1 does (creates a .venv inside the skill folder, installs requirements.txt from PyPI, falls back to a mirror if that fails, then runs an environment check). Wait for my OK.
4. In the skill folder run: powershell -ExecutionPolicy Bypass -File install.ps1 (CadQuery is large, this takes a few minutes). It downloads from the official PyPI. Only if I am in mainland China and a package makes no download progress for several minutes: stop, set $env:PIP_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple" and rerun the same command. Do not install other versions yourself.
5. Run \`.venv\\Scripts\\python.exe scripts\\check_env.py\` and tell me the result. If I have SolidWorks, run it again with \`--sw\`.
6. Tell me it's ready and how to use it, for example: "Use drawing2sw to model D:\\drawings\\bracket.pdf in SolidWorks".

If your safety settings don't allow downloading or running these commands, just say so and I'll run them myself in a terminal.`
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
  document.title = lang === 'en' ? 'Drawing2SW · Engineering drawings to SolidWorks' : 'Drawing2SW · 读工程图，在 SolidWorks 里建模';
  renderAgent();
  renderPrompt();
}

function renderPrompt() {
  document.getElementById('prompt-text').textContent = PROMPT[lang];
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

document.getElementById('copy-prompt').addEventListener('click', async e => {
  const btn = e.currentTarget;
  const idle = lang === 'en' ? EN['ai.btn'] : zh['ai.btn'];
  try {
    await navigator.clipboard.writeText(PROMPT[lang]);
    btn.textContent = lang === 'en' ? 'Copied. Paste it to your AI' : '已复制，粘贴给你的 AI';
  } catch (err) {
    document.querySelector('.ai-prompt').open = true;
    btn.textContent = lang === 'en' ? 'Select the text below to copy' : '请选中下面的文字复制';
  }
  setTimeout(() => { btn.innerHTML = idle; }, 2400);
});

render();
