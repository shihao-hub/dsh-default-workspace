// Standalone exercise for the restart helper: victim = a disposable cmd that
// spawns a child ping. Targeted-kill mode must kill only the given PID;
// tree-kill mode must take the child too; both must "relaunch" the exe.
import { spawn, execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { __test } from '../dsh-local-plugins/app-restart/index.js';

const helper = path.join(os.tmpdir(), 'dsh-app-restart-helper.test.ps1');
fs.writeFileSync(helper, __test.HELPER_SOURCE, 'utf8');
console.log('helper written:', helper);

const victimExe = 'C:\\Windows\\System32\\cmd.exe';

function runHelper(args) {
	// Fire and forget: the helper kills and relaunches asynchronously.
	const child = spawn(
		'powershell.exe',
		['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', helper, ...args],
		{ stdio: 'ignore', windowsHide: true }
	);
	child.unref();
}

function pidsOf(name) {
	const out = execFileSync(
		'powershell.exe',
		['-NoProfile', '-NonInteractive', '-Command',
			`(Get-Process -Name '${name}' -ErrorAction SilentlyContinue).Id -join ' '`],
		{ encoding: 'utf8' }
	).trim();
	return out === '' ? [] : out.split(/\s+/).map(Number);
}

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

const mode = process.argv[2] === 'tree' ? 'tree' : 'targeted';
console.log('mode:', mode);

const before = new Set(pidsOf('cmd'));
console.log('cmd pids before:', [...before]);

// Victim tree: cmd (holds a ping child for 60s)
const victim = spawn(victimExe, ['/d', '/c', 'ping -n 60 127.0.0.1 > nul'], { stdio: 'ignore', windowsHide: true });
await sleep(1200);
const victimChildBefore = pidsOf('PING');
console.log('victim pid:', victim.pid, 'ping children:', victimChildBefore);

const args = [
	'-ExePath', victimExe,
	'-MainPid', String(victim.pid),
	'-HostPid', '0',
	'-DelayMs', '400'
];
if (mode === 'tree') args.push('-TreeKill');
runHelper(args);

await sleep(6000);

const after = new Set(pidsOf('cmd'));
const newOnes = [...after].filter((p) => !before.has(p));
const pingAfter = pidsOf('PING');
console.log('new cmd pids (relaunched):', newOnes);
console.log('ping children after:', pingAfter);

const log = fs.readFileSync(path.join(os.tmpdir(), 'dsh-app-restart.log'), 'utf8').trim().split(/\r?\n/).slice(-8);
console.log('--- log tail ---');
console.log(log.join('\n'));

if (mode === 'tree') {
	if (newOnes.length >= 1 && pingAfter.length === 0) {
		console.log('RESULT tree: PASS (relaunched, child tree gone)');
	} else {
		console.log('RESULT tree: FAIL', { newOnes: newOnes.length, pingAfter: pingAfter.length });
	}
} else {
	if (newOnes.length >= 1 && pingAfter.length >= 1) {
		console.log('RESULT targeted: PASS (relaunched, child ping untouched)');
	} else {
		console.log('RESULT targeted: FAIL', { newOnes: newOnes.length, pingAfter: pingAfter.length });
	}
}
