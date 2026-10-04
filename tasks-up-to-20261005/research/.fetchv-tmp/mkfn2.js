const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const retIdx = src.indexOf('return[', src.indexOf('(function(){'));
const iifeStart = retIdx - '(function(){'.length;
const fnStart = src.lastIndexOf('function', iifeStart);
let depth = 0, k0 = src.indexOf('{', fnStart), fnEndIdx = -1;
for (let k = k0; k < src.length; k++) {
  if (src[k] === '{') depth++;
  else if (src[k] === '}') { depth--; if (depth === 0) { fnEndIdx = k; break; } }
}
const fnBody = src.slice(fnStart, fnEndIdx + 1);
const fnName = fnBody.match(/^function\s+(_0x[0-9a-f]+)/)[1];
const tag = src.match(/var\s+(_0xod[A-Za-z0-9]+)\s*=\s*'([^']*)'/);
const out = 'var ' + tag[1] + ' = ' + JSON.stringify(tag[2]) + ';\n'
  + fnBody + '\n'
  + 'try { const A = ' + fnName + '(); console.log("OK len", A.length, "A[0]", JSON.stringify(A[0])); '
  + 'require("fs").writeFileSync(process.argv[2], JSON.stringify(A)); } '
  + 'catch (e) { console.log("ERR", e.constructor.name, e.message); console.log(e.stack.split("\\n").slice(0,6).join("\\n")); }';
fs.writeFileSync(process.argv[3], out);
console.log('built', process.argv[3], 'fn', fnName, 'bodyLen', fnBody.length);
