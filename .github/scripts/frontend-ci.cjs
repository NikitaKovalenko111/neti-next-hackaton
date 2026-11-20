const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const directory = path.resolve(__dirname, '../../frontend');
const manifestPath = path.join(directory, 'package.json');

if (!fs.existsSync(manifestPath)) {
  console.log('Frontend checks skipped: frontend/package.json is absent.');
  process.exit(0);
}

const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
const exists = (filename) => fs.existsSync(path.join(directory, filename));
const lockfiles = [
  ['npm', 'package-lock.json'],
  ['npm', 'npm-shrinkwrap.json'],
  ['pnpm', 'pnpm-lock.yaml'],
  ['yarn', 'yarn.lock'],
].filter(([, filename]) => exists(filename));

if (lockfiles.length !== 1) {
  throw new Error('Frontend must have exactly one npm, pnpm or Yarn lockfile.');
}

const [manager] = lockfiles[0];
const declared = manifest.packageManager;
const [declaredManager, declaredVersion] = (declared || '').split('@');

if (declared && declaredManager !== manager) {
  throw new Error(`packageManager ${declared} does not match the ${manager} lockfile.`);
}

// Use the declared package-manager version when present. npm uses setup-node's npm.
const version = declaredVersion?.split('+')[0];
let executable = 'npm';
let prefix = [];
let install = ['ci'];

if (manager === 'pnpm') {
  executable = 'npx';
  prefix = ['--yes', '--package', `pnpm@${version || '10'}`, '--', 'pnpm'];
  install = ['install', '--frozen-lockfile'];
}

if (manager === 'yarn') {
  const classic = fs.readFileSync(path.join(directory, 'yarn.lock'), 'utf8')
    .includes('# yarn lockfile v1');
  executable = 'npx';
  prefix = ['--yes', '--package', classic
    ? `yarn@${version || '1.22.22'}`
    : `@yarnpkg/cli-dist@${version || '4'}`, '--', 'yarn'];
  install = ['install', classic ? '--frozen-lockfile' : '--immutable'];
}

function run(args, { capture = false, allowFailure = false } = {}) {
  console.log(`\n> ${executable} ${[...prefix, ...args].join(' ')}`);
  const result = spawnSync(executable, [...prefix, ...args], {
    cwd: directory,
    env: { ...process.env, CI: 'true' },
    stdio: capture ? ['inherit', 'pipe', 'pipe'] : 'inherit',
    encoding: 'utf8',
    maxBuffer: 16 * 1024 * 1024,
  });

  if (result.error) throw result.error;
  if (capture) {
    if (result.stdout) fs.writeSync(1, result.stdout);
    if (result.stderr) fs.writeSync(2, result.stderr);
  }
  if (result.status !== 0 && !allowFailure) process.exit(result.status || 1);

  return result;
}

if (manager === 'npm') {
  const result = run(install, { capture: true, allowFailure: true });

  if (result.status !== 0) {
    const output = `${result.stdout || ''}\n${result.stderr || ''}`;
    const lockMismatch = /\bEUSAGE\b/.test(output) &&
      /in sync|Missing: .+ from lock file|Invalid: lock file/.test(output);

    if (!lockMismatch || lockfiles[0][1] !== 'package-lock.json') {
      process.exit(result.status || 1);
    }

    const warning = 'package-lock.json is out of sync. Frontend developer must regenerate it. ' +
      'CI will install from package.json without changing the committed lockfile.';
    console.log(`::warning file=frontend/package-lock.json,title=Frontend lockfile mismatch::${warning}`);

    if (process.env.GITHUB_STEP_SUMMARY) {
      fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY,
        `\n### Frontend lockfile needs repair\n\n${warning}\n\n` +
        'Lint, tests and build will run using dependencies resolved from package.json.\n');
    }

    run(['install', '--no-package-lock', '--no-save', '--no-audit', '--no-fund']);
  }
} else {
  run(install);
}

const scripts = manifest.scripts || {};
const checks = [
  'lint',
  'format:check',
  scripts.typecheck ? 'typecheck' : 'type-check',
  scripts['test:ci'] ? 'test:ci' : 'test',
  'build',
];

for (const script of checks) {
  if (typeof scripts[script] !== 'string' || scripts[script].trim() === '') {
    console.log(`Check skipped: package.json has no ${script} script.`);
    continue;
  }

  run(['run', script]);
}
