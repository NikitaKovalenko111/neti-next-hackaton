const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { test } = require('node:test');

function fixture(t, scenario) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'frontend-ci-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));

  const scripts = path.join(root, '.github/scripts');
  const frontend = path.join(root, 'frontend');
  const bin = path.join(root, 'bin');
  for (const directory of [scripts, frontend, bin]) {
    fs.mkdirSync(directory, { recursive: true });
  }

  const script = path.join(scripts, 'frontend-ci.cjs');
  fs.copyFileSync(path.join(__dirname, 'frontend-ci.cjs'), script);
  const manifest = JSON.stringify({ scripts: { lint: 'eslint .', build: 'vite build' } });
  const lock = JSON.stringify({ lockfileVersion: 3 });
  fs.writeFileSync(path.join(frontend, 'package.json'), manifest);
  fs.writeFileSync(path.join(frontend, 'package-lock.json'), lock);

  fs.writeFileSync(path.join(bin, 'npm'), `#!/usr/bin/env node
const fs = require('node:fs');
const args = process.argv.slice(2);
fs.appendFileSync(process.env.COMMAND_LOG, JSON.stringify(args) + '\\n');
if (args[0] === 'ci' && process.env.SCENARIO !== 'valid') {
  fs.writeSync(2, process.env.SCENARIO === 'network'
    ? 'npm error code ENOTFOUND\\n'
    : 'npm error code EUSAGE\\nnpm error package.json and package-lock.json are not in sync\\nnpm error Missing: @emnapi/core@1.11.3 from lock file\\n');
  process.exit(1);
}
if (args[0] === 'install' && process.env.SCENARIO === 'install-failure') process.exit(3);
if (args[0] === 'run' && args[1] === 'lint' && process.env.SCENARIO === 'lint-failure') process.exit(2);
`, { mode: 0o755 });

  const log = path.join(root, 'commands');
  const summary = path.join(root, 'summary');
  const result = spawnSync(process.execPath, [script], {
    encoding: 'utf8',
    env: {
      ...process.env,
      PATH: `${bin}${path.delimiter}${process.env.PATH}`,
      COMMAND_LOG: log,
      GITHUB_STEP_SUMMARY: summary,
      SCENARIO: scenario,
    },
  });

  assert.equal(fs.readFileSync(path.join(frontend, 'package.json'), 'utf8'), manifest);
  assert.equal(fs.readFileSync(path.join(frontend, 'package-lock.json'), 'utf8'), lock);

  return {
    ...result,
    commands: fs.readFileSync(log, 'utf8').trim().split('\n').map(JSON.parse),
    summary: fs.existsSync(summary) ? fs.readFileSync(summary, 'utf8') : '',
  };
}

test('valid lockfile uses npm ci and runs checks', (t) => {
  const result = fixture(t, 'valid');
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.deepEqual(result.commands, [['ci'], ['run', 'lint'], ['run', 'build']]);
  assert.equal(result.summary, '');
});

test('lockfile mismatch reports a warning and installs without rewriting frontend files', (t) => {
  const result = fixture(t, 'mismatch');
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stdout, /::warning file=frontend\/package-lock.json/);
  assert.match(result.summary, /Frontend developer must regenerate/);
  assert.deepEqual(result.commands, [
    ['ci'],
    ['install', '--no-package-lock', '--no-save', '--no-audit', '--no-fund'],
    ['run', 'lint'],
    ['run', 'build'],
  ]);
});

test('network errors remain blocking', (t) => {
  const result = fixture(t, 'network');
  assert.equal(result.status, 1);
  assert.deepEqual(result.commands, [['ci']]);
});

test('fallback install errors remain blocking', (t) => {
  const result = fixture(t, 'install-failure');
  assert.equal(result.status, 3, result.stdout + result.stderr);
  assert.equal(result.commands.length, 2);
});

test('lint errors after fallback remain blocking', (t) => {
  const result = fixture(t, 'lint-failure');
  assert.equal(result.status, 2, result.stdout + result.stderr);
  assert.equal(result.commands.at(-1)[1], 'lint');
});
