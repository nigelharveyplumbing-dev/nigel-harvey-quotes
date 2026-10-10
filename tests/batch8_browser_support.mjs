export class BrowserOperationTimeout extends Error {
  constructor(phase, milliseconds) {
    super(`${phase} exceeded ${milliseconds}ms`);
    this.name = 'BrowserOperationTimeout';
    this.phase = phase;
    this.milliseconds = milliseconds;
  }
}

// A host-side deadline also covers browser evaluate promises, which can remain
// pending even when Playwright's navigation/action defaults are configured.
export async function bounded(phase, operation, milliseconds = 15000, progress = () => {}) {
  const started = Date.now();
  progress({ phase, state: 'start' });
  let timer;
  try {
    const result = await Promise.race([
      Promise.resolve().then(operation),
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(new BrowserOperationTimeout(phase, milliseconds)), milliseconds);
      }),
    ]);
    progress({ phase, state: 'done', milliseconds: Date.now() - started });
    return result;
  } catch (error) {
    // Never include page text, request bodies, credentials or an assertion's
    // actual/expected values in public progress diagnostics.
    progress({ phase, state: 'failed', errorType: error.name, milliseconds: Date.now() - started });
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

async function exited(child, milliseconds) {
  if (child.exitCode !== null || child.signalCode !== null) return true;
  let timer;
  let listener;
  try {
    return await Promise.race([
      new Promise(resolve => { listener = () => resolve(true); child.once('exit', listener); }),
      new Promise(resolve => { timer = setTimeout(() => resolve(false), milliseconds); }),
    ]);
  } finally {
    clearTimeout(timer);
    if (listener) child.removeListener('exit', listener);
  }
}

export async function stopServer(child, milliseconds = 3000) {
  if (child.exitCode !== null || child.signalCode !== null) return { terminated: true, forced: false };
  const signal = value => {
    try {
      // Signal a retained child handle, never a PID found by scanning the host.
      child.kill(value);
    } catch (error) { if (error.code !== 'ESRCH') throw error; }
  };
  signal('SIGTERM');
  if (await exited(child, milliseconds)) return { terminated: true, forced: false };
  signal('SIGKILL');
  if (!await exited(child, milliseconds)) throw new Error('Disposable server did not terminate');
  return { terminated: true, forced: true };
}

