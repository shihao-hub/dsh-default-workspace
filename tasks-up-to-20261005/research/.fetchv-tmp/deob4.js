// Recover + rotate the javascript-obfuscator string array for a fetchv.net loader bundle,
// then decode every call site and emit a deobfuscated copy.
const fs = require('fs');
const vm = require('vm');

const E = (s) => JSON.stringify(s);

function extractArrayFn(src) {
  const retIdx = src.indexOf('return[', src.indexOf('(function(){'));
  if (retIdx < 0) return null;
  const iifeStart = retIdx - '(function(){'.length;
  const fnStart = src.lastIndexOf('function', iifeStart);
  if (fnStart < 0) return null;
  let depth = 0, fnEndIdx = -1;
  for (let k = src.indexOf('{', fnStart); k < src.length; k++) {
    if (src[k] === '{') depth++;
    else if (src[k] === '}') { depth--; if (depth === 0) { fnEndIdx = k; break; } }
  }
  if (fnEndIdx < 0) return null;
  const body = src.slice(fnStart, fnEndIdx + 1);
  const name = body.match(/^function\s+(_0x[0-9a-f]+)/)[1];
  return { name, body };
}

function extractFn(src, start) {
  let depth = 0;
  for (let k = src.indexOf('{', start); k < src.length; k++) {
    if (src[k] === '{') depth++;
    else if (src[k] === '}') { depth--; if (depth === 0) return src.slice(start, k + 1); }
  }
  return null;
}

const file = process.argv[2];
const outPrefix = process.argv[3] || file.replace(/\.js$/, '');
const src = fs.readFileSync(file, 'utf8');

const tag = src.match(/var\s+(_0xod[A-Za-z0-9]+)\s*=\s*'([^']*)'/);
if (!tag) { console.error('FATAL: tag not found'); process.exit(1); }

const af = extractArrayFn(src);
if (!af) { console.error('FATAL: array function not found'); process.exit(1); }

// Run the array function by itself, with a big stack (the literal is deeply nested).
const runner = new vm.Script('var ' + tag[1] + ' = ' + E(tag[2]) + ';\n'
  + af.body + '\n__out = ' + af.name + '();');
const rc = { __out: null };
vm.createContext(rc);
runner.runInContext(rc, { timeout: 60000 });
const arr = rc.__out;
console.error('array fn = ' + af.name + ', array length = ' + arr.length);

// decoder function: the one containing fromCharCode
const fnRe = /function (_0x[0-9a-f]+)\((_0x[0-9a-f]+),(_0x[0-9a-f]+)\)\{/g;
let m, dec = null;
while ((m = fnRe.exec(src)) !== null) {
  if (src.slice(m.index, m.index + 6000).includes('fromCharCode')) { dec = { name: m[1], idx: m.index }; break; }
}
if (!dec) { console.error('FATAL: decoder not found'); process.exit(1); }
const decSrc = extractFn(src, dec.idx);
const dc = { __arr: arr, __arrayFn: af.name };
vm.createContext(dc);
vm.runInContext('function ' + af.name + '(){ return __arr; }', dc);
vm.runInContext(decSrc + '\n__dec = ' + dec.name + ';', dc);
console.error('decoder = ' + dec.name);

// The obfuscator aliases the decoder into many local names; collect them all.
const aliases = new Set([dec.name]);
for (let pass = 0; pass < 5; pass++) {
  for (const a of [...aliases]) {
    const r = new RegExp('([A-Za-z_$][\\w$]*)\\s*=\\s*' + a.replace(/\$/g, '\\$') + '\\b', 'g');
    let mm;
    while ((mm = r.exec(src)) !== null) aliases.add(mm[1]);
  }
}
console.error('decoder aliases = ' + aliases.size);

// decode every call site (each carries its own RC4 salt)
const map = {};
const reList = [...aliases].map(a => new RegExp(
  a.replace(/\$/g, '\\$') + "\\((0x[0-9a-fA-F]+)\\s*,\\s*'((?:[^'\\\\]|\\\\.)*)'\\)", 'g'));
for (const re of reList) {
  let mm;
  while ((mm = re.exec(src)) !== null) {
    const k = parseInt(mm[1], 16);
    if (map[k] !== undefined) continue;
    try {
      const v = dc.__dec(k, mm[2]);
      if (typeof v === 'string' && v.length) map[k] = v;
    } catch (e) {}
  }
}
console.error('call sites decoded = ' + Object.keys(map).length);
fs.writeFileSync(outPrefix + '.strings.json', JSON.stringify(map, null, 1));

let hits = 0, misses = 0;
let out = src;
for (const re of reList.map(r => new RegExp(r.source, 'g'))) {
  out = out.replace(re, (full, hex, salt) => {
    const k = parseInt(hex, 16);
    if (map[k] !== undefined) { hits++; return E(map[k]); }
    misses++;
    return full;
  });
}
console.error('rewritten = ' + hits + ', misses = ' + misses);
fs.writeFileSync(outPrefix + '.deob.js', out);
console.log('OK strings=' + Object.keys(map).length + ' rewrites=' + hits + ' misses=' + misses);
