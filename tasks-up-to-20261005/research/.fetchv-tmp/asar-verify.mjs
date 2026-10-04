import { readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'

const asar = 'D:\\Users\\29580\\AppData\\Local\\Programs\\DeepSeek Harness\\resources\\app.asar'
const buf = readFileSync(asar)

// asar = 16-byte pickle header + JSON directory + concatenated file payloads
const headerPickleSize = buf.readUInt32LE(4)
const headerStringSize = buf.readUInt32LE(12)
const headerJson = buf.subarray(16, 16 + headerStringSize).toString('utf8')
const header = JSON.parse(headerJson)
const dataStart = 8 + headerPickleSize

function walk(node, prefix) {
  const out = []
  for (const [name, child] of Object.entries(node.files ?? {})) {
    const p = prefix ? `${prefix}/${name}` : name
    if (child.files) out.push(...walk(child, p))
    else if (child.unpacked) out.push({ path: p, unpacked: true })
    else out.push({ path: p, offset: Number(child.offset), size: child.size })
  }
  return out
}

const entries = walk(header, '')
console.log('total entries in asar:', entries.length)

const targets = entries.filter((e) => e.path.includes('@deepseek-ai/dsh-tool-web') || e.path.includes('@deepseek-ai/dsh-web-search-deepseek') || e.path.includes('@deepseek-ai/dsh-web/lib') || e.path.includes('@deepseek-ai/dsh-web-fetch-http/lib'))

const mirrorRoot = 'C:\\Users\\29580\\AppData\\Local\\Temp\\dsh-asar-src\\'
const sha = (b) => createHash('sha256').update(b).digest('hex')

for (const e of targets) {
  if (e.unpacked) { console.log('UNPACKED  ', e.path); continue }
  const fromAsar = buf.subarray(dataStart + e.offset, dataStart + e.offset + e.size)
  const mirrorPath = mirrorRoot + e.path.replaceAll('/', '\\')
  let mirror
  try { mirror = readFileSync(mirrorPath) } catch { console.log('MISSING   ', e.path); continue }
  const same = sha(fromAsar) === sha(mirror)
  console.log(`${same ? 'IDENTICAL ' : 'DIFFERENT '} ${e.path}  asar=${e.size}B mirror=${mirror.length}B`)
}
