import assert from 'node:assert/strict';

import stylelint from '../../bindings/node/index.mjs';

const dynamicModule = await import('../../bindings/node/index.mjs');

assert.equal(typeof stylelint, 'function');
assert.equal(dynamicModule.default, stylelint);
assert.equal(typeof stylelint.lint, 'function');
assert.equal(typeof stylelint.resolveConfig, 'function');
assert.equal(typeof stylelint.createPlugin, 'function');
assert.ok(stylelint.rules['at-rule-empty-line-before']);
assert.ok(stylelint.formatters.json);

const config = await stylelint.resolveConfig('path', {
	config: {
		quiet: true,
	},
	configBasedir: 'path',
	configFile: 'path',
	cwd: 'path',
});
const result = await stylelint.lint({
	config,
	code: '',
	codeFilename: 'inline.css',
	cwd: 'path',
});

assert.equal(result.cwd, 'path');
assert.equal(result.results.length, 1);
assert.equal(result.code, '');

const messages = stylelint.utils.ruleMessages('sample-rule', {
	problem: 'This a rule problem message',
	warning: (reason) => `This is not allowed because ${reason}`,
	withNarrowedParam: (mixinName) => `Mixin not allowed: ${mixinName}`,
});
assert.equal(messages.problem, 'This a rule problem message (sample-rule)');
assert.equal(messages.warning('reason'), 'This is not allowed because reason (sample-rule)');
assert.equal(
	messages.withNarrowedParam('mixin'),
	'Mixin not allowed: mixin (sample-rule)',
);

const plugin = stylelint.createPlugin('sample-rule', {
	ruleName: 'sample-rule',
});
assert.equal(plugin.ruleName, 'sample-rule');

assert.ok(
	stylelint.reference.longhandSubPropertiesOfShorthandProperties
		.get('border-color')
		.has('border-top-color'),
);
