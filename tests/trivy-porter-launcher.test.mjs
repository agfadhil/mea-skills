import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { test } from 'node:test';
import { findPython, runTrivyPorter } from '../scripts/trivy-porter.mjs';

const python3 = () => ({ status: 0, stdout: '3\n' });

test('runtime selection skips missing executables and Python 2', () => {
  const attempts = [];
  const selected = findPython({ platform: 'win32', probe: (command, argv, options) => {
    attempts.push([command, argv]);
    assert.equal(options.shell, false);
    if (command === 'py') return { error: new Error('ENOENT'), status: null };
    return { status: 0, stdout: command === 'python3' ? '2\n' : '3\n' };
  } });
  assert.deepEqual(selected, { command: 'python', args: [] });
  assert.deepEqual(attempts.map(([command, args]) => [command, args.slice(0, -2)]), [
    ['py', ['-3']], ['python3', []], ['python', []],
  ]);
});

test('launcher forwards literal arguments, working directory, inherited stdio, and exit status', async () => {
  const argv = ['continue', '--project', '/project with spaces/$(unsafe)', '--session', 'session-123'];
  const signals = new EventEmitter();
  const status = await runTrivyPorter({
    argv, cwd: '/working directory', platform: 'linux', probe: python3, signalSource: signals,
    spawnProcess: (command, childArgs, options) => {
      assert.equal(command, 'python3');
      assert.match(childArgs[0], /[\\/]trivy-porter[\\/]scripts[\\/]trivy_porter\.py$/);
      assert.deepEqual(childArgs.slice(1), argv);
      assert.deepEqual(options, { cwd: '/working directory', stdio: 'inherit', shell: false });
      const child = new EventEmitter();
      queueMicrotask(() => child.emit('exit', 43, null));
      return child;
    },
  });
  assert.equal(status, 43);
  assert.equal(signals.listenerCount('SIGINT'), 0);
  assert.equal(signals.listenerCount('SIGTERM'), 0);
});

test('interrupt is forwarded to Python and returns its signal exit status', async () => {
  const signals = new EventEmitter();
  const received = [];
  const status = await runTrivyPorter({
    platform: 'win32', probe: python3, signalSource: signals,
    spawnProcess: (command, argv) => {
      assert.equal(command, 'py');
      assert.equal(argv[0], '-3');
      const child = Object.assign(new EventEmitter(), {
        exitCode: null, signalCode: null,
        kill(signal) {
          received.push(signal);
          queueMicrotask(() => child.emit('exit', null, signal));
        },
      });
      queueMicrotask(() => signals.emit('SIGINT'));
      return child;
    },
  });
  assert.equal(status, 130);
  assert.deepEqual(received, ['SIGINT']);
  assert.equal(signals.listenerCount('SIGINT'), 0);
});

test('unavailable Python reports prerequisite and never launches a child', async () => {
  let error = '';
  const status = await runTrivyPorter({
    platform: 'linux', probe: () => ({ status: 1, stdout: '' }),
    errorOutput: { write: (message) => { error += message; } },
    spawnProcess: () => { assert.fail('Must not launch without Python 3'); },
  });
  assert.equal(status, 1);
  assert.match(error, /Python 3 tidak ditemukan/);
});
