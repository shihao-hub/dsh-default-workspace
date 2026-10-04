// Deobfuscate fetchv.net loader bundles: reconstruct the obfuscator's decoded-string
// table by evaluating the bundle prefix in a VM, then dumping every decoded string.
// Read-only w.r.t. inputs; writes a .deob.js (decoder calls replaced) + .strings.json.
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const file = process.argv[2];
const src = fs.readFileSync(file, 'utf8');

// 1. find the base64 string-array IIFE: (function(){return[ ... ]}())
const arrRe = /\(function\(\)\{return\[/g;
let m, arrStart = -1, arrEnd = -1;
const candidates = [];
while ((m = arrRe.exec(src)) !== null) candidates.push(m.index);
if (candidates.length === 0) { console.error('no string array found'); process.exit(1); }
// choose the LAST candidate before the decoder region (first occurrence is the real one)
arrStart = candidates[0];
// the inner array literal ends with `];` right before `}())`; take through the trailing `()`
const tail = src.indexOf('];', arrStart);
if (tail < 0) { console.error('array tail not found'); process.exit(1); }
const arrSrc = src.slice(arrStart, tail + 1) + '})()'; // -> "(function(){return[...]})()"
if (!/^\(function\(\)\{return\[/.test(arrSrc)) { console.error('array extraction failed: ' + arrSrc.slice(0, 60)); process.exit(1); }
console.error('array src tail = ' + JSON.stringify(arrSrc.slice(-8)));

// 2. instantiate it to obtain the array reference
const arrCtx = {};
vm.createContext(arrCtx);
let arr;
try {
  arr = vm.runInContext(arrSrc, arrCtx);
} catch (e) { console.error('array eval failed: ' + e.message); process.exit(1); }
console.error('array length = ' + arr.length + ', arr[0] = ' + JSON.stringify(arr[0]));

// 3. find decoder name = name of the function whose first param indexes an array
const fnRe = /function (_0x[0-9a-f]+)\((_0x[0-9a-f]+),(_0x[0-9a-f]+)\)/g;
const decoders = [];
while ((m = fnRe.exec(src)) !== null) {
  // heuristic: decoder body contains "String['fromCharCode']" or "fromCharCode"
  const body = src.slice(m.index, m.index + 4000);
  if (/fromCharCode/.test(body)) decoders.push({ name: m[1], idx: m.index });
}
if (decoders.length === 0) { console.error('no decoder found'); process.exit(1); }
console.error('decoder candidates: ' + decoders.map(d => d.name).join(', '));

// take the largest-index (last) decoder: the self-defending one declared right after the array
const dec = decoders[decoders.length - 1];
// extract its full source by brace matching
function extractFn(s, start) {
  let i = s.indexOf('{', start), depth = 0;
  for (let j = i; j < s.length; j++) {
    if (s[j] === '{') depth++;
    else if (s[j] === '}') { depth--; if (depth === 0) return s.slice(start, j + 1); }
  }
  return null;
}
const decSrc = extractFn(src, dec.idx);
if (!decSrc) { console.error('decoder extraction failed'); process.exit(1); }
console.error('decoder source length = ' + decSrc.length);

const ctx = {};
vm.createContext(ctx);
vm.runInContext('const __arr = ' + JSON.stringify(arr) + ';', ctx);
// the decoder calls _0x537c() to fetch the array; provide it
const arrFnName = (decSrc.match(/_0x[0-9a-f]+\(\)/) || [])[0];
if (arrFnName) {
  vm.runInContext('function ' + arrFnName.replace('()', '') + '(){ return __arr; }', ctx);
}
try {
  vm.runInContext(decSrc + '\nglobalThis.__dec = ' + dec.name + ';', ctx);
} catch (e) { console.error('decoder eval failed: ' + e.message); process.exit(1); }

// 4. enumerate decoded strings
const key = arr[0];
const map = {};
let ok = 0;
for (let i = 0; i < 0x4000; i++) {
  try {
    const v = ctx.__dec(i, key);
    if (typeof v === 'string' && v.length && !/^_0x/.test(v)) { map[i] = v; ok++; }
  } catch (e) { /* out of range */ }
}
console.error('decoded strings = ' + ok);

// 5. rewrite the bundle: replace decoder calls with literal strings
let out = src;
let replaced = 0;
out = out.replace(new RegExp('\\b' + dec.name + '\\((0x[0-9a-f]+),\\s*([\'"])((?:\\\\.|(?!\\2).)*)\\2\\)', 'gi'), (full, hex, q, star) => {
  const i = parseInt(hex, 16);
  if (map[i] === undefined) return full;
  replaced++;
  return JSON.stringify(map[i]);
});
console.error('replaced calls = ' + replaced);

const dir = path.dirname(file);
const base = path.basename(file, '.js');
fs.writeFileSync(path.join(dir, base + '.deob.js'), out);
fs.writeFileSync(path.join(dir, base + '.strings.json'), JSON.stringify(map, null, 1));
console.log('wrote ' + path.join(dir, base + '.deob.js') + ' and .strings.json');
