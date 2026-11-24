import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {readFileSync, writeFileSync} from 'node:fs';

const repository = 'https://github.com/AnthonyZZH/xiaoqian-weixin';
const sourcePath = 'vendor/library-adapter/core.mjs';
const copy = new URL('./src/core.mjs', import.meta.url);
const lock = new URL('./core-source.json', import.meta.url);
const digest = bytes => createHash('sha256').update(bytes).digest('hex');

function sourceAt(checkout, commit) {
  if (!/^[0-9a-f]{40}$/.test(commit)) throw new Error('Expected a full Git commit hash');
  return execFileSync('git', ['-C', checkout, 'cat-file', 'blob', `${commit}:${sourcePath}`], {
    env: {...process.env, GIT_NO_LAZY_FETCH: '1'},
  });
}

const [command, checkout, revision, ...extra] = process.argv.slice(2);
if (command === '--update' && checkout && revision && !extra.length) {
  const bytes = sourceAt(checkout, revision);
  const pin = {repository, commit: revision, path: sourcePath, sha256: digest(bytes)};
  writeFileSync(copy, bytes);
  writeFileSync(lock, JSON.stringify(pin, null, 2) + '\n');
} else if (command === '--check' && !revision && !extra.length) {
  const pin = JSON.parse(readFileSync(lock, 'utf8'));
  const bytes = readFileSync(copy);
  if (pin.repository !== repository || pin.path !== sourcePath || !/^[0-9a-f]{40}$/.test(pin.commit) ||
      pin.sha256 !== digest(bytes) || (checkout && !bytes.equals(sourceAt(checkout, pin.commit)))) {
    throw new Error('The bundled core differs from its source pin');
  }
  console.log(`Verified ${sourcePath} at ${pin.commit}`);
} else {
  throw new Error('Usage: node sync-core.mjs --check [checkout] | --update <checkout> <full-commit>');
}
