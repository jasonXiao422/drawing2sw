'use strict';
let language = new URLSearchParams(location.search).get('lang') === 'en' ? 'en' : 'zh';
let agent = 'codex';
const agents = {
  codex: { path: ['项目/.agents/skills/drawing2sw/', 'project/.agents/skills/drawing2sw/'], note: ['在项目中加载后，用 $drawing2sw 调用。', 'Load in your project, then invoke $drawing2sw.'] },
  claude: { path: ['项目/.claude/skills/drawing2sw/', 'project/.claude/skills/drawing2sw/'], note: ['在 Claude Code 中用 /drawing2sw 调用。', 'Invoke /drawing2sw in Claude Code.'] },
  other: { path: ['你授权访问的目录/drawing2sw/', 'your-authorized-folder/drawing2sw/'], note: ['让 Agent 读取该目录中的 SKILL.md，并确认它能运行本地 Python。', 'Ask the agent to read SKILL.md and verify that it can execute local Python.'] }
};
function updateAgent() {
  const i = language === 'en' ? 1 : 0;
  document.getElementById('agent-path').textContent = agents[agent].path[i];
  document.getElementById('agent-note').textContent = agents[agent].note[i];
}
function translate() {
  document.documentElement.lang = language === 'en' ? 'en' : 'zh-CN';
  document.querySelectorAll('[data-zh][data-en]').forEach(el => { el.textContent = el.dataset[language]; });
  document.getElementById('language').textContent = language === 'en' ? '中文 ↗' : 'EN ↗';
  document.getElementById('language').setAttribute('aria-label', language === 'en' ? '切换到中文' : 'Switch to English');
  document.title = language === 'en' ? 'Drawing2SW — Mechanical drawing to CAD' : 'Drawing2SW — 从工程图到三维';
  updateAgent();
}
document.getElementById('language').addEventListener('click', () => {
  language = language === 'zh' ? 'en' : 'zh'; translate();
  const url = new URL(location.href); url.searchParams.set('lang', language); history.replaceState(null, '', url);
});
const models = { bracket: ['51,240.708', 'BRACKET / 01'], flange: ['158,682.892', 'FLANGE / 02'], plate: ['23,660.708', 'PLATE / 03'] };
document.querySelectorAll('[data-model]').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('[data-model]').forEach(b => { b.classList.remove('active'); b.setAttribute('aria-pressed', 'false'); });
  button.classList.add('active'); button.setAttribute('aria-pressed', 'true');
  const model = button.dataset.model;
  document.getElementById('model-image').src = `assets/${model}.svg`;
  document.getElementById('model-image').alt = `CadQuery projection: ${model}`;
  document.getElementById('model-id').textContent = models[model][1];
  document.getElementById('volume').replaceChildren(document.createTextNode(models[model][0] + ' '));
  const unit = document.createElement('small'); unit.textContent = 'mm³'; document.getElementById('volume').append(unit);
}));
document.querySelectorAll('[data-agent]').forEach(button => button.addEventListener('click', () => {
  agent = button.dataset.agent;
  document.querySelectorAll('[data-agent]').forEach(b => { b.classList.remove('active'); b.setAttribute('aria-pressed', 'false'); });
  button.classList.add('active'); button.setAttribute('aria-pressed', 'true'); updateAgent();
}));
document.getElementById('copy').addEventListener('click', async () => {
  const status = document.getElementById('copy-status');
  try { await navigator.clipboard.writeText(document.getElementById('commands').textContent); status.textContent = language === 'en' ? 'Commands copied.' : '命令已复制。'; }
  catch { status.textContent = language === 'en' ? 'Select and copy the commands manually.' : '请选中命令后手动复制。'; }
});
translate();
