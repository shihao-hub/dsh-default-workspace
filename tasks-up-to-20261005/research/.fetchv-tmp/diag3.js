const fs = require('fs');
const s = fs.readFileSync(process.argv[2], 'utf8');
const start = s.indexOf('(function(){return[');
const src = s.slice(start);
// scan the array-literal region character by character
let inStr = null, esc = false, depthBracket = 0, depthBrace = 0, depthParen = 0;
let line = 1, col = 0, problems = [];
for (let k = 0; k < src.length; k++) {
  const c = src[k];
  col++;
  if (c === '\n') { line++; col = 0; }
  if (inStr) {
    if (esc) { esc = false; continue; }
    if (c === '\\') { esc = true; continue; }
    if (c === inStr) { inStr = null; continue; }
    continue;
  }
  if (c === "'" || c === '"' || c === '`') { inStr = c; continue; }
  if (c === '[') depthBracket++;
  else if (c === ']') { depthBracket--; if (depthBracket === 0 && depthBrace === 1 && depthParen === 1) { console.log('array literal closes at offset', k, 'of', src.length); console.log('trailing:', JSON.stringify(src.slice(k, k + 12))); break; } }
  else if (c === '{') depthBrace++;
  else if (c === '}') depthBrace--;
  else if (c === '(') depthParen++;
  else if (c === ')') depthParen--;
}
console.log('final state: inStr =', inStr, 'bracket =', depthBracket, 'brace =', depthBrace, 'paren =', depthParen);
