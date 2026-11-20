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

function run(args) {
  console.log(`\n> ${executable} ${[...prefix, ...args].join(' ')}`);
  const result = spawnSync(executable, [...prefix, ...args], {
    cwd: directory,
    env: { ...process.env, CI: 'true' },
    stdio: 'inherit',
  });

  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status || 1);
}

run(install);

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
