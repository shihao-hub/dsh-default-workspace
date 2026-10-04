const fs = require('fs');
const s = fs.readFileSync(process.argv[2], 'utf8');
const i = s.indexOf('(function(){return[');
console.log('i =', i);
console.log('charCode before i (i-3..i+3):', JSON.stringify(s.slice(i - 3, i + 5)));
console.log('codes:', [...s.slice(i - 3, i + 5)].map(c => c.charCodeAt(0)).join(','));
console.log('slice(0,120):', JSON.stringify(s.slice(0, 120)));
console.log('slice(i, i+80):', JSON.stringify(s.slice(i, i + 80)));

const slice = s.slice(i, i + 80);
// Does the first 40 chars parse as part of an array after 'return'?
for (const n of [30, 40, 50, 60, 70, 80]) {
  try { new Function('return ' + slice.slice(0, n)); console.log(n, 'parse OK'); }
  catch (e) { console.log(n, 'FAIL:', e.message); }
}
