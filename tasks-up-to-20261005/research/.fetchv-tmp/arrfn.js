// Extract and run the javascript-obfuscator "string array" wrapper.
// Returns the FINAL array that the decoder closes over (after the rotation IIFE).
const vm = require('vm');

function balanceSlice(src, from, open, close) {
  let depth = 0, inStr = null, esc = false;
  for (let k = from; k < src.length; k++) {
    const c = src[k];
    if (inStr) {
      if (esc) { esc = false; continue; }
      if (c === '\\') { esc = true; continue; }
      if (c === inStr) inStr = null;
      continue;
    }
    if (c === "'" || c === '"' || c === '`') { inStr = c; continue; }
    if (c === open) depth++;
    else if (c === close) { depth--; if (depth === 0) return src.slice(from, k + 1); }
  }
  return null;
}

/** Recover the rotated string array + the tag variable name it belongs to. */
function extractRotatedArray(src) {
  const tagM = src.match(/var\s+(_0xod[A-Za-z0-9]+)\s*=\s*'([^']*)'/);
  if (!tagM) throw new Error('tag var not found');
  const tag = tagM[1], tagValue = tagM[2];

  // the string-array function: `function _0xNNN(){const X=(function(){return[ ... ];}());<rotation>;return X;}`
  // locate by finding "return[" preceded by "(function(){"
  const retIdx = src.indexOf('return[', src.indexOf('(function(){'));
  // walk forward: array literal, then optional .concat(...) chain
  let cursor = retIdx;
  let expr = '';
  for (;;) {
    const arr = balanceSlice(src, cursor, '[', ']');
    if (arr === null) throw new Error('array literal unbalanced');
    expr += arr;
    const after = cursor + arr.length;
    if (src.startsWith('.concat(', after)) {
      const call = balanceSlice(src, after + 7, '(', ')');
      if (call === null) throw new Error('concat unbalanced');
      expr += '.concat' + call;
      cursor = after + 7 + call.length;
      if (src.startsWith('.concat(', cursor)) continue;
      break;
    }
    break;
  }
  // after the expression comes `;}())` — the `)` closes the IIFE call; then `;`
  // the enclosing function name is what follows the closing of that function
  const fnEnd = expr.length + cursor;                 // absolute end of the array expression
  const rest = src.slice(fnEnd, fnEnd + 400);
  // inside the string-array function, `X` names the array: `const X=(function(){...}())`
  const before = src.slice(Math.max(0, retIdx - 400), retIdx);
  const constM = before.match(/const\s+(_0x[0-9a-f]+)\s*=\s*\(function\(\)\{\s*$/);
  if (!constM) throw new Error('array const name not found; tail=' + JSON.stringify(before.slice(-80)));

  // the array IIFE body: from '(function(){' through the '}())' that closes it
  const iifeStart = retIdx - '(function(){'.length;
  const iifeExpr = src.slice(iifeStart, fnEnd) + '}())';

  // the outer string-array function name: `function NAME(){`
  const hdr = src.slice(Math.max(0, iifeStart - 200), iifeStart);
  const nameM = hdr.match(/function\s+(_0x[0-9a-f]+)\s*\(\)\s*\{\s*const\s+/);
  if (!nameM) throw new Error('string-array function name not found');
  const arrayFn = nameM[1];

  // body of the string-array function: from its '{' to its matching '}'
  const fnStart = src.lastIndexOf('function', iifeStart);
  let depth = 0, k0 = src.indexOf('{', fnStart), fnEndIdx = -1;
  for (let k = k0; k < src.length; k++) {
    if (src[k] === '{') depth++;
    else if (src[k] === '}') { depth--; if (depth === 0) { fnEndIdx = k; break; } }
  }
  const fnBody = src.slice(fnStart, fnEndIdx + 1);

  const ctx = { [tag]: tagValue };
  vm.createContext(ctx);
  const finalArr = vm.runInContext('(' + fnBody + ')()', ctx);
  // prove the array function is self-consistent
  const viaFn = vm.runInContext(arrayFn + '()', ctx);
  return { array: finalArr, arrayFn, tag, tagValue, viaFnLen: viaFn.length, exprLen: expr.length };
}

module.exports = { extractRotatedArray, balanceSlice };
