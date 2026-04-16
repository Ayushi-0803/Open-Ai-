import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';

const fixturePath = path.resolve(
	import.meta.dirname,
	'../fixtures/lib/utils/index.js',
);

const contents = await fs.readFile(fixturePath, 'utf8');

assert.equal(contents, '');
