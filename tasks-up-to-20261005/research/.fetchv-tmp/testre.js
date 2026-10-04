const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const dec = process.argv[3] || '_0x5597';
const idx = src.indexOf(dec + '(');
console.log('first occurrence at', idx);
console.log('context:', JSON.stringify(src.slice(Math.max(0, idx - 60), idx + 60)));
const re1 = new RegExp(dec + "\\((0x[0-9a-fA-F]+)\\s*,\\s*'((?:[^'\\\\]|\\\\.)*)'\\)", 'g');
console.log('regex source:', re1.source);
const all = src.match(re1);
console.log('matches:', all ? all.length : 0);
if (all) console.log('first:', all[0]);
// fallback simple pattern
const re2 = new RegExp(dec.replace('_', '_') + '\\(' + '0x[0-9a-fA-F]+' + ",'[^']*'\\)", 'g');
const all2 = src.match(re2);
console.log('simple-pattern matches:', all2 ? all2.length : 0);
if (all2) console.log('first:', all2[0]);
