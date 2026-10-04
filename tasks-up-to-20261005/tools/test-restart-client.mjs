// Mock-run the client half: factory(require) + apply(ctx) with stub services,
// asserting the slot registration this plugin is supposed to perform.
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const source = fs.readFileSync(
  path.resolve(import.meta.dirname, '../dsh-local-plugins/app-restart/client.js'),
  'utf8'
);

const registrations = [];
const effects = [];

globalThis.window = {
  __ModuleLoader__: {
    load(def) {
      globalThis.__loaded = def;
    }
  }
};

const React = {
  createElement(type, props, ...children) {
    return { type, props, children };
  },
  useState(initial) {
    const ref = { value: typeof initial === 'function' ? initial() : initial };
    return [ref.value, (next) => { ref.value = typeof next === 'function' ? next(ref.value) : next; }];
  },
  useEffect(fn) { effects.push(fn); return undefined; },
  useCallback(fn) { return fn; },
  useRef(value) { return { current: value }; }
};

const ctx = {
  effect(fn, label) {
    const dispose = fn();
    effects.push({ label, dispose });
    return dispose;
  },
  locale: {
    register(ns, dicts) {
      registrations.push({ kind: 'locale', ns, keys: Object.keys(dicts.zh) });
      return () => {};
    },
    bind(ns) {
      return (key) => ns + ':' + key;
    },
    getLocale() { return { active: 'zh' }; }
  },
  slots: {
    inject(slotKey, factory) {
      registrations.push({ kind: 'inject', slotKey });
      factory();
    },
    register(options, component) {
      registrations.push({ kind: 'register', options, componentName: component?.name ?? 'anonymous', component });
      return () => {};
    }
  }
};

const requireShim = (specifier) => {
  if (specifier === 'react') return React;
  throw new Error('unexpected require: ' + specifier);
};

new Function('window', 'require', source)(globalThis.window, requireShim);

const def = globalThis.__loaded;
console.log('module id:', def?.id);
const face = def.factory(requireShim);
console.log('inject face:', face.inject);
face.apply(ctx);

console.log('registrations:');
for (const r of registrations) console.log(' -', JSON.stringify(r).slice(0, 220));

const injects = registrations.filter((r) => r.kind === 'inject');
const regs = registrations.filter((r) => r.kind === 'register');
const locales = registrations.filter((r) => r.kind === 'locale');
const footer = regs.find((r) => r.options?.name === 'sidebar.footer.action');

const checks = {
  'module id': def.id === '@local/app-restart',
  'injects slots+locale': face.inject.includes('slots') && face.inject.includes('locale'),
  'registers into sidebar.footer.action': Boolean(footer),
  'footer entry id': footer?.options?.id === 'app-restart',
  'footer carries locale ns': footer?.options?.locale === 'app-restart',
  'component is named AppControlButtons': footer?.componentName === 'AppControlButtons',
  'locale dictionary registered': locales.length === 1 && locales[0].keys.length === Object.keys(locales[0].keys).length,
  'stylesheet effect ran': effects.some((e) => e?.label === 'app-restart: stylesheet')
};

let ok = true;
for (const [name, pass] of Object.entries(checks)) {
  console.log((pass ? 'PASS' : 'FAIL') + ' ' + name);
  if (!pass) ok = false;
}

// render smoke: the occupant renders two FlowButtons (restart + quit).
// Mock createElement keeps function components as elements; expand them.
function expand(node) {
  if (node === null || typeof node !== 'object') return [];
  const out = [node];
  if (typeof node.type === 'function') {
    out.push(...expand(node.type({ ...node.props, children: node.children })));
  }
  for (const child of Array.isArray(node.children) ? node.children : []) out.push(...expand(child));
  return out;
}

if (footer) {
  const t = (key) => 't:' + key;
  const tree = footer.component.call(null, { t });
  console.log('render root type:', tree.type, 'children:', tree.children.length);
  const flat = expand(tree);
  const wrapDivs = flat.filter((n) => n.type === 'div' && n.props?.className === 'rsr_wrap');
  console.log('flow buttons:', wrapDivs.length);
  for (const d of wrapDivs) {
    console.log('  button label:', d.children[0].props['aria-label']);
  }
  if (wrapDivs.length !== 2) ok = false;
}

process.exit(ok ? 0 : 1);
