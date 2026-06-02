import net from 'node:net';
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const projectRoot = join(__dirname, '..');
const host = process.env.VITE_DEV_HOST || 'localhost';
const defaultPorts = [5173, 3000, 3001, 3002, 3003, 3004, 3005];
const candidatePorts = (process.env.VITE_DEV_PORTS || defaultPorts.join(','))
  .split(',')
  .map((value) => Number(value.trim()))
  .filter((value) => Number.isInteger(value) && value > 0 && value < 65536);

if (candidatePorts.length === 0) {
  console.error('No valid dev ports configured. Set VITE_DEV_PORTS, for example: 5173,3000,3001');
  process.exit(1);
}

function canListen(port) {
  return new Promise((resolve) => {
    const server = net.createServer();

    server.once('error', (error) => {
      resolve({ ok: false, error });
    });

    server.once('listening', () => {
      server.close(() => resolve({ ok: true }));
    });

    server.listen(port, host);
  });
}

async function choosePort() {
  for (const port of candidatePorts) {
    const result = await canListen(port);
    if (result.ok) {
      return port;
    }

    const code = result.error?.code ?? 'UNKNOWN';
    console.log(`Port ${port} cannot be used (${code}); trying the next one...`);
  }

  console.error(`No available dev port found on ${host}. Tried: ${candidatePorts.join(', ')}`);
  process.exit(1);
}

const selectedPort = await choosePort();
const viteCli = join(projectRoot, 'node_modules', 'vite', 'bin', 'vite.js');

if (!existsSync(viteCli)) {
  console.error('Vite CLI was not found at node_modules/vite/bin/vite.js. Run npm install first.');
  process.exit(1);
}

const extraArgs = process.argv.slice(2);
console.log(`Starting Vite on http://${host}:${selectedPort}/`);

// On Windows, spawning node_modules/.bin/vite.cmd can fail with EINVAL in
// modern Node versions because .cmd/.bat files are not normal executables.
// Launching the Vite JavaScript CLI through the current Node executable avoids
// cmd.exe and keeps argument passing safe/cross-platform.
const child = spawn(
  process.execPath,
  [viteCli, '--host', host, '--port', String(selectedPort), ...extraArgs],
  {
    cwd: projectRoot,
    stdio: 'inherit',
    shell: false,
    windowsHide: false,
  },
);

child.on('error', (error) => {
  console.error(`Failed to start Vite: ${error.message}`);
  process.exit(1);
});

child.on('exit', (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});
