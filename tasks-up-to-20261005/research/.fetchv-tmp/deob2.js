// Step 1: recover the obfuscator's decoded-string table for a fetchv.net loader bundle.
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const file = process.argv[2];
const src = fs.readFileSync(file, 'utf8');

const i = src.indexOf('(function(){return[');
const j = src.indexOf('}())', i);
if (i < 0 || j < 0) { console.error('array not found'); process.exit(1); }
// slice EXCLUDING the trailing ';' inside the IIFE body
const arrSrc = src.slice(i, j) + '}())';
console.error('arrSrc len=' + arrSrc.length + ' tail=' + JSON.stringify(arrSrc.slice(-12)));

const ctx = {};
vm.createContext(ctx);
let arr;
try { arr = vm.runInContext(arrSrc, ctx); }
catch (e) { console.error('array eval failed: ' + e.message); process.exit(1); }
console.error('array len = ' + arr.length);

// locate decoder: function whose body contains fromCharCode
const fnRe = /function (_0x[0-9a-f]+)\((_0x[0-9a-f]+),(_0x[0-9a-f]+)\)\{/g;
let m, dec = null;
while ((m = fnRe.exec(src)) !== null) {
  const body = src.slice(m.index, m.index + 5000);
  if (body.includes('fromCharCode')) { dec = { name: m[1], idx: m.index }; break; }
}
if (!dec) { console.error('decoder not found'); process.exit(1); }
console.error('decoder = ' + dec.name);

// brace-match the decoder source
function extractFn(s, start) {
  const open = s.indexOf('{', start);
  let depth = 0;
  for (let k = open; k < s.length; k++) {
    if (s[k] === '{') depth++;
    else if (s[k] === '}') { depth--; if (depth === 0) return s.slice(start, k + 1); }
  }
  return null;
}
const decSrc = extractFn(src, dec.idx);
if (!decSrc) { console.error('decoder extract failed'); process.exit(1); }

const ctx2 = {};
vm.createContext(ctx2);
vm.runInContext('const __arr = ' + JSON.stringify(arr) + ';', ctx2);
// the decoder calls the array function; give it the same name
const arrFnName = (decSrc.match(/=\s*(_0x[0-9a-f]+)\(\)/) || [])[1];
console.error('array fn name = ' + arrFnName);
vm.runInContext('function ' + arrFnName + '(){ return __arr; }', ctx2);
vm.runInContext(decSrc + '\nthis.__dec = ' + dec.name + ';', ctx2);
const decFn = ctx2.__dec;
console.error('decoder ready');

const key = arr[0];
const map = {};
let ok = 0;
for (let k = 0; k < 0x8000; k++) {
  try {
    const v = decFn(k, key);
    if (typeof v === 'string' && v.length && !/^_0x[0-9a-f]+$/.test(v)) { map[k] = v; ok++; }
  } catch (e) { /* out of range */ }
}
console.error('decoded = ' + ok);

const dir = path.dirname(file);
const base = path.basename(file, '.js');
fs.writeFileSync(path.join(dir, base + '.strings.json'), JSON.stringify(map, null, 1));

// rewrite: replace decoder(0xNNN, 'star') -> literal
let out = src;
let hits = 0;
const callRe = new RegExp(dec.name.replace('_', '_') + "\\((0x[0-9a-fA-F]+)\\s*,\\s*'([^']*)'\\)", 'g');
out = out.replace(callRe, (full, hex, star) => {
  const k = parseInt(hex, 16);
  if (map[k] === undefined) return full;
  hits++;
  return JSON.stringify(map[k]);
});
console.error('rewritten calls = ' + hits);
fs.writeFileSync(path.join(dir, base + '.deob.js'), out);
console.log('OK ' + base + ': strings=' + ok + ' rewrites=' + hits);
