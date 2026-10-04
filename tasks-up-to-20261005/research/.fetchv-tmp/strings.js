const fs = require('fs');
const file = process.argv[2];
const filter = process.argv[3] ? new RegExp(process.argv[3], 'i') : null;
const s = fs.readFileSync(file, 'utf8');
const out = new Set();
for (const m of s.matchAll(/'([^'\\]{2,120})'|"([^"\\]{2,120})"/g)) {
  const v = m[1] !== undefined ? m[1] : m[2];
  if (!v) continue;
  if (/^_0x/.test(v)) continue;
  if (filter && !filter.test(v)) continue;
  out.add(v);
}
console.log([...out].sort().join('\n'));
console.log('--- total ' + out.size);
