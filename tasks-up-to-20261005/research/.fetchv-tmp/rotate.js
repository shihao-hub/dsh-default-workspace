// Reproduce the obfuscator's array-rotation IIFE on a reconstructed string array.
const vm = require('vm');

/** src = bundle source; arr = reconstructed array; returns the rotated array. */
function rotate(src, arr) {
  // find the rotation IIFE: the first `(function(_0x...,_0x...` after the array definition
  const start = src.indexOf('(function(_0x', src.indexOf('}())'));
  if (start < 0) { console.error('rotation IIFE not found'); return arr; }
  // brace/paren match the whole IIFE call, then append `(ARGS)` copied from the bundle
  let depth = 0, inStr = null, esc = false, end = -1;
  for (let k = start; k < src.length; k++) {
    const c = src[k];
    if (inStr) {
      if (esc) { esc = false; continue; }
      if (c === '\\') { esc = true; continue; }
      if (c === inStr) inStr = null;
      continue;
    }
    if (c === "'" || c === '"' || c === '`') { inStr = c; continue; }
    if (c === '(') depth++;
    else if (c === ')') { depth--; if (depth === 0) { end = k; break; } }
  }
  if (end < 0) { console.error('rotation IIFE unbalanced'); return arr; }
  const iife = src.slice(start, end + 1);          // (function(a,b,c,d,e,f,g){...})
  const callArgs = src.slice(end + 1, src.indexOf(';', end));   // (0x..., ..., _0x537c, 0xc6)
  const code = 'var __array = __ARR__;\n' + iife + callArgs + ';\n__array';
  const ctx = { __ARR__: arr };
  vm.createContext(ctx);
  try {
    const out = vm.runInContext(code, ctx);
    return out;
  } catch (e) {
    console.error('rotation failed: ' + e.message);
    return arr;
  }
}

module.exports = { rotate };
