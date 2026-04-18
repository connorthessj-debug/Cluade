import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import Ajv from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..', '..');

const schema = JSON.parse(fs.readFileSync(path.join(ROOT, 'schemas/content.schema.json'), 'utf8'));
const content = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/content.json'), 'utf8'));

const ajv = new Ajv({ allErrors: true, strict: false });
addFormats(ajv);
const validate = ajv.compile(schema);

describe('content.json matches schema', () => {
  it('validates the live content file', () => {
    const ok = validate(content);
    if (!ok) console.error(validate.errors);
    expect(ok).toBe(true);
  });

  it('rejects a negative price', () => {
    const bad = structuredClone(content);
    bad.menu.classics[0].price = -1;
    expect(validate(bad)).toBe(false);
  });

  it('rejects an invalid email in site.email', () => {
    const bad = structuredClone(content);
    bad.site.email = 'not-an-email';
    expect(validate(bad)).toBe(false);
  });

  it('rejects a rating above 5', () => {
    const bad = structuredClone(content);
    bad.menu.classics[0].rating = 6;
    expect(validate(bad)).toBe(false);
  });

  it('rejects an item missing required id', () => {
    const bad = structuredClone(content);
    delete bad.menu.classics[0].id;
    expect(validate(bad)).toBe(false);
  });
});
