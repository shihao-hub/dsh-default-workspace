// Minimal ASAR reader: list or extract, no dependencies.
const fs = require('node:fs');
const path = require('node:path');

function readHeader(archivePath) {
  const fd = fs.openSync(archivePath, 'r');
  const sizeBuf = Buffer.alloc(16);
  if (fs.readSync(fd, sizeBuf, 0, 16, null) !== 16) throw new Error('bad header size');
  const pickleSize = sizeBuf.readUInt32LE(4);
  const jsonLen = sizeBuf.readUInt32LE(12);
  const jsonBuf = Buffer.alloc(jsonLen);
  if (fs.readSync(fd, jsonBuf, 0, jsonLen, 16) !== jsonLen) throw new Error('bad header');
  const json = jsonBuf.toString('utf8');
  const dataStart = 8 + pickleSize;
  fs.closeSync(fd);
  return { header: JSON.parse(json), dataStart };
}

function walk(node, prefix, out) {
  if (node.files) {
    for (const [name, child] of Object.entries(node.files)) walk(child, prefix ? prefix + '/' + name : name, out);
  } else {
    out.push({ file: prefix, size: node.size, offset: node.offset, unpacked: !!node.unpacked });
  }
}

const [cmd, archive, target, dest] = process.argv.slice(2);
const { header, dataStart } = readHeader(archive);

if (cmd === 'list') {
  const out = [];
  walk(header, '', out);
  const re = target ? new RegExp(target) : null;
  for (const e of out) {
    if (!re || re.test(e.file)) console.log(`${e.unpacked ? 'U' : ' '} ${e.size}\t${e.file}`);
  }
} else if (cmd === 'extract') {
  const out = [];
  walk(header, '', out);
  const re = new RegExp(target);
  const fd = fs.openSync(archive, 'r');
  let n = 0;
  for (const e of out) {
    if (!re.test(e.file) || e.unpacked) continue;
    const buf = Buffer.alloc(e.size);
    fs.readSync(fd, buf, 0, e.size, dataStart + Number(e.offset));
    const outPath = path.join(dest, e.file);
    fs.mkdirSync(path.dirname(outPath), { recursive: true });
    fs.writeFileSync(outPath, buf);
    n++;
  }
  console.log(`extracted ${n} files to ${dest}`);
} else {
  console.error('usage: node asar.mjs list <archive> [regex] | extract <archive> <regex> <dest>');
  process.exit(2);
}
