const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const dec = process.argv[3];
// find every alias: `const NAME = DECODER;` or `NAME = DECODER;` or `const{..}=...`
const aliases = new Set([dec]);
const re = new RegExp('([A-Za-z_$][\\w$]*)\\s*=\\s*' + dec + '\\b', 'g');
let m;
while ((m = re.exec(src)) !== null) aliases.add(m[1]);
// also `const A=DECODER,B=A` chains — iterate a few times
for (let pass = 0; pass < 4; pass++) {
  for (const a of [...aliases]) {
    const r2 = new RegExp('([A-Za-z_$][\\w$]*)\\s*=\\s*' + a + '\\b', 'g');
    let m2;
    while ((m2 = r2.exec(src)) !== null) aliases.add(m2[1]);
  }
}
console.log('aliases (' + aliases.size + '):', [...aliases].join(', '));
let total = 0;
for (const a of aliases) {
  const r = new RegExp(a.replace(/\$/g, '\\$') + "\\(0x[0-9a-fA-F]+\\s*,\\s*'[^']*'\\)", 'g');
  const hits = src.match(r);
  if (hits && hits.length) { console.log('  ' + a + ' -> ' + hits.length + ' calls, e.g. ' + hits[0]); total += hits.length; }
}
console.log('total call sites =', total);
