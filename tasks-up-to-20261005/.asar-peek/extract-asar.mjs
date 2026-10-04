// Read-only ASAR extractor for research. Extracts selected paths so they can be read with normal tools.
import fs from 'node:fs';
import path from 'node:path';

const [, , asarPath, outDir, ...patterns] = process.argv;
const listOnly = process.env.LIST_ONLY === '1';
if (!asarPath || !outDir || patterns.length === 0) {
  console.error('usage: node extract-asar.mjs <app.asar> <outDir> <pattern...>');
  process.exit(2);
}

const fd = fs.openSync(asarPath, 'r');
const sizeBuf = Buffer.alloc(8);
fs.readSync(fd, sizeBuf, 0, 8, 0);
const headerSize = sizeBuf.readUInt32LE(4);
const headerBuf = Buffer.alloc(headerSize);
fs.readSync(fd, headerBuf, 0, headerSize, 8);
const jsonLen = headerBuf.readUInt32LE(4);
const header = JSON.parse(headerBuf.toString('utf8', 8, 8 + jsonLen));
const dataBase = 8 + headerSize;
console.log(`asar: header ${headerSize} bytes, JSON ${jsonLen} bytes, data at ${dataBase}`);

const all = [];
(function walk(node, prefix) {
  if (!node.files) return;
  for (const [name, child] of Object.entries(node.files)) {
    const p = prefix ? `${prefix}/${name}` : name;
    if (child.files) walk(child, p);
    else all.push({ p, size: child.size, offset: Number(child.offset), unpacked: !!child.unpacked });
  }
})(header, '');
console.log(`archive contains ${all.length} files`);

const toRe = (g) => new RegExp('^' + g.split('*').map((s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('.*') + '$');
const res = patterns.map(toRe);
const hits = all.filter((f) => res.some((r) => r.test(f.p)));
console.log(`matched ${hits.length} files`);

if (listOnly) {
  for (const h of hits.sort((a, b) => a.p.localeCompare(b.p))) console.log(`${String(h.size).padStart(9)}  ${h.p}`);
  process.exit(0);
}

let bytes = 0;
for (const h of hits) {
  if (h.unpacked) { console.log(`skip (unpacked): ${h.p}`); continue; }
  const dest = path.join(outDir, ...h.p.split('/'));
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  const buf = Buffer.alloc(h.size);
  let read = 0;
  while (read < h.size) {
    const n = fs.readSync(fd, buf, read, h.size - read, dataBase + h.offset + read);
    if (n <= 0) throw new Error(`short read on ${h.p}`);
    read += n;
  }
  fs.writeFileSync(dest, buf);
  bytes += h.size;
}
fs.closeSync(fd);
console.log(`extracted ${hits.length} files, ${(bytes / 1024).toFixed(1)} KB -> ${outDir}`);
