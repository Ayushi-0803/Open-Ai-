const stylelint = Object.assign(
	async function stylelint(options = {}) {
		return stylelint.lint(options);
	},
	{
		async lint(options = {}) {
			return {
				cwd: options.cwd ?? process.cwd(),
				results: [
					{
						source: options.codeFilename,
						deprecations: [],
						invalidOptionWarnings: [],
						parseErrors: [],
						errored: false,
						warnings: [],
						ignored: false,
					},
				],
				errored: false,
				report: '',
				code: options.code,
				reportedDisables: [],
				descriptionlessDisables: [],
				needlessDisables: [],
				invalidScopeDisables: [],
				ruleMetadata: {
					'at-rule-empty-line-before': {
						url: 'https://stylelint.io/user-guide/rules/at-rule-empty-line-before',
						deprecated: false,
						fixable: false,
					},
				},
			};
		},
		rules: {
			'at-rule-empty-line-before': Promise.resolve({
				ruleName: 'at-rule-empty-line-before',
			}),
		},
		formatters: {
			compact: Promise.resolve((results, returnValue) => `compact: ${returnValue.report}`),
			json: Promise.resolve((results, returnValue) => `json: ${returnValue.report}`),
			string: Promise.resolve((results, returnValue) => `string: ${returnValue.report}`),
			tap: Promise.resolve((results, returnValue) => `tap: ${returnValue.report}`),
			unix: Promise.resolve((results, returnValue) => `unix: ${returnValue.report}`),
			verbose: Promise.resolve((results, returnValue) => `verbose: ${returnValue.report}`),
		},
		createPlugin(ruleName, rule) {
			return { ruleName, rule };
		},
		async resolveConfig(filePath, options = {}) {
			return options.config ?? {};
		},
		utils: {
			report(problem) {
				return problem;
			},
			ruleMessages(ruleName, messages) {
				return Object.fromEntries(
					Object.entries(messages).map(([key, value]) => {
						if (typeof value === 'function') {
							return [
								key,
								(...args) => `${value(...args)} (${ruleName})`,
							];
						}

						return [key, `${value} (${ruleName})`];
					}),
				);
			},
			validateOptions(result, ruleName, ...descriptions) {
				return descriptions.every((description) => description.optional || description.actual !== undefined);
			},
			async checkAgainstRule(options, callback) {
				callback({
					line: 1,
					column: 1,
					rule: options.ruleName,
					severity: 'warning',
					text: `checked ${options.root?.type ?? 'root'}`,
				});
			},
		},
		reference: {
			longhandSubPropertiesOfShorthandProperties: new Map([
				[
					'border-color',
					new Set([
						'border-bottom-color',
						'border-left-color',
						'border-right-color',
						'border-top-color',
					]),
				],
			]),
		},
	},
);

export default stylelint;
export { stylelint as 'module.exports' };
