// AUTO-MIGRATED: This public API compatibility surface was generated from
// `types/stylelint/index.d.ts` and requires human review before sign-off.

use std::collections::{BTreeMap, BTreeSet};
use std::future::Future;
use std::pin::Pin;
use std::sync::Arc;

use crate::options::{
    Config,
    FormatterType,
    LinterOptions,
    PluginReference,
    PostcssPluginOptions,
    ResolveConfigOptions,
    RuleSettings,
    Severity,
};
use crate::results::{
    DisableOptionsReport,
    EditInfo,
    LintResult,
    LinterResult,
    ProblemLocation,
    ProblemReport,
    RuleMeta,
    Warning,
};

pub type BoxFuture<'a, T> = Pin<Box<dyn Future<Output = T> + Send + 'a>>;
pub type Formatter = Arc<dyn Fn(&[LintResult], &LinterResult) -> String + Send + Sync>;

#[derive(Clone)]
pub struct LazyFormatter {
    loader: Arc<dyn Fn() -> BoxFuture<'static, Formatter> + Send + Sync>,
}

impl LazyFormatter {
    pub fn new<F>(loader: F) -> Self
    where
        F: Fn() -> BoxFuture<'static, Formatter> + Send + Sync + 'static,
    {
        Self {
            loader: Arc::new(loader),
        }
    }

    pub fn load(&self) -> BoxFuture<'static, Formatter> {
        (self.loader)()
    }
}

#[derive(Clone)]
pub struct Formatters {
    pub compact: LazyFormatter,
    pub json: LazyFormatter,
    pub string: LazyFormatter,
    pub tap: LazyFormatter,
    pub unix: LazyFormatter,
    pub verbose: LazyFormatter,
}

impl Formatters {
    pub fn builtin() -> Self {
        fn make_formatter(name: &'static str) -> LazyFormatter {
            LazyFormatter::new(move || {
                Box::pin(async move {
                    let label = name.to_string();
                    Arc::new(move |_results, return_value| {
                        format!("{label}: {}", return_value.report)
                    })
                })
            })
        }

        Self {
            compact: make_formatter("compact"),
            json: make_formatter("json"),
            string: make_formatter("string"),
            tap: make_formatter("tap"),
            unix: make_formatter("unix"),
            verbose: make_formatter("verbose"),
        }
    }
}

#[derive(Clone, Default)]
pub struct RuleMessages {
    fixed: BTreeMap<String, String>,
    dynamic: BTreeMap<String, Arc<dyn Fn(&[String]) -> String + Send + Sync>>,
}

impl RuleMessages {
    pub fn insert_static(
        &mut self,
        key: impl Into<String>,
        value: impl Into<String>,
    ) {
        self.fixed.insert(key.into(), value.into());
    }

    pub fn insert_dynamic<F>(&mut self, key: impl Into<String>, callback: F)
    where
        F: Fn(&[String]) -> String + Send + Sync + 'static,
    {
        self.dynamic.insert(key.into(), Arc::new(callback));
    }

    pub fn static_message(&self, key: &str) -> Option<&str> {
        self.fixed.get(key).map(String::as_str)
    }

    pub fn render(&self, key: &str, args: &[String]) -> Option<String> {
        if let Some(message) = self.fixed.get(key) {
            return Some(message.clone());
        }

        self.dynamic.get(key).map(|callback| callback(args))
    }
}

#[derive(Clone, Default)]
pub struct RuleDefinition {
    pub rule_name: String,
    pub messages: RuleMessages,
    pub primary_option_array: bool,
    pub meta: Option<RuleMeta>,
}

#[derive(Clone)]
pub struct LazyRule {
    loader: Arc<dyn Fn() -> BoxFuture<'static, RuleDefinition> + Send + Sync>,
}

impl LazyRule {
    pub fn new<F>(loader: F) -> Self
    where
        F: Fn() -> BoxFuture<'static, RuleDefinition> + Send + Sync + 'static,
    {
        Self {
            loader: Arc::new(loader),
        }
    }

    pub fn load(&self) -> BoxFuture<'static, RuleDefinition> {
        (self.loader)()
    }
}

#[derive(Clone, Default)]
pub struct RulesRegistry {
    entries: BTreeMap<String, LazyRule>,
}

impl RulesRegistry {
    pub fn insert(&mut self, name: impl Into<String>, rule: LazyRule) {
        self.entries.insert(name.into(), rule);
    }

    pub fn get(&self, name: &str) -> Option<&LazyRule> {
        self.entries.get(name)
    }

    pub fn names(&self) -> impl Iterator<Item = &str> {
        self.entries.keys().map(String::as_str)
    }
}

#[derive(Clone)]
pub struct Plugin {
    pub rule_name: String,
    pub rule: RuleDefinition,
}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct InternalApi {
    pub options: LinterOptions,
    pub cwd: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct CheckAgainstRuleOptions {
    pub rule_name: String,
    pub rule_settings: Option<RuleSettings>,
    pub root_description: String,
    pub result_source: Option<String>,
    pub fix: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RuleOptionDescription {
    pub actual: Option<String>,
    pub optional: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct ReferenceData {
    pub longhand_sub_properties_of_shorthand_properties: BTreeMap<String, BTreeSet<String>>,
}

impl ReferenceData {
    pub fn builtin() -> Self {
        let mut mapping = BTreeMap::new();
        mapping.insert(
            "border-color".to_string(),
            BTreeSet::from([
                "border-bottom-color".to_string(),
                "border-left-color".to_string(),
                "border-right-color".to_string(),
                "border-top-color".to_string(),
            ]),
        );

        Self {
            longhand_sub_properties_of_shorthand_properties: mapping,
        }
    }
}

#[derive(Debug, Clone, Default)]
pub struct Utils;

impl Utils {
    pub fn report(&self, result: &mut LintResult, problem: ProblemReport) {
        let (line, column, end_line, end_column) = match problem.location {
            ProblemLocation::Span { start, end } => {
                (start.line, start.column, Some(end.line), Some(end.column))
            }
            ProblemLocation::Index { .. } => (1, 1, None, None),
            ProblemLocation::Word { .. } => (1, 1, None, None),
            ProblemLocation::None => (1, 1, None, None),
        };

        result.warnings.push(Warning {
            line,
            column,
            end_line,
            end_column,
            fix: problem.fix,
            rule: problem.rule_name,
            severity: problem.severity,
            text: problem.message,
            url: None,
            stylelint_type: None,
        });
    }

    pub fn rule_messages(&self, rule_name: &str, messages: RuleMessages) -> RuleMessages {
        let mut wrapped = RuleMessages::default();

        for (key, value) in messages.fixed {
            wrapped.insert_static(key, format!("{value} ({rule_name})"));
        }

        for (key, callback) in messages.dynamic {
            let scoped_rule_name = rule_name.to_string();
            wrapped.insert_dynamic(key, move |args| {
                format!("{} ({scoped_rule_name})", callback(args))
            });
        }

        wrapped
    }

    pub fn validate_options(
        &self,
        _rule_name: &str,
        option_descriptions: &[RuleOptionDescription],
    ) -> bool {
        option_descriptions
            .iter()
            .all(|description| description.optional || description.actual.is_some())
    }

    pub fn check_against_rule<F>(
        &self,
        options: CheckAgainstRuleOptions,
        mut callback: F,
    ) -> BoxFuture<'static, ()>
    where
        F: FnMut(Warning) + Send + 'static,
    {
        Box::pin(async move {
            callback(Warning {
                line: 1,
                column: 1,
                end_line: None,
                end_column: None,
                fix: if options.fix {
                    Some(EditInfo {
                        range: (0, 0),
                        text: String::new(),
                    })
                } else {
                    None
                },
                rule: options.rule_name,
                severity: Severity::Warning,
                text: format!("checked {}", options.root_description),
                url: None,
                stylelint_type: None,
            });
        })
    }
}

#[derive(Clone)]
pub struct PublicApiFacade {
    lint_fn: Arc<dyn Fn(LinterOptions) -> BoxFuture<'static, LinterResult> + Send + Sync>,
    resolve_config_fn:
        Arc<dyn Fn(String, Option<ResolveConfigOptions>) -> BoxFuture<'static, Option<Config>> + Send + Sync>,
    create_linter_fn: Arc<dyn Fn(LinterOptions) -> InternalApi + Send + Sync>,
    pub rules: RulesRegistry,
    pub formatters: Formatters,
    pub utils: Utils,
    pub reference: ReferenceData,
}

impl PublicApiFacade {
    pub fn lint(&self, options: LinterOptions) -> BoxFuture<'static, LinterResult> {
        (self.lint_fn)(options)
    }

    pub fn resolve_config(
        &self,
        file_path: impl Into<String>,
        options: Option<ResolveConfigOptions>,
    ) -> BoxFuture<'static, Option<Config>> {
        (self.resolve_config_fn)(file_path.into(), options)
    }

    pub fn create_plugin(&self, rule_name: impl Into<String>, rule: RuleDefinition) -> Plugin {
        Plugin {
            rule_name: rule_name.into(),
            rule,
        }
    }

    pub fn create_linter(&self, options: LinterOptions) -> InternalApi {
        (self.create_linter_fn)(options)
    }

    pub fn postcss_plugin(&self, options: PostcssPluginOptions) -> InternalApi {
        match options {
            PostcssPluginOptions::LinterOptions(options) => self.create_linter(options),
            PostcssPluginOptions::Config(config) => self.create_linter(LinterOptions {
                config: Some(config),
                ..LinterOptions::default()
            }),
        }
    }
}

pub fn default_public_api() -> PublicApiFacade {
    let mut rules = RulesRegistry::default();
    rules.insert(
        "at-rule-empty-line-before",
        LazyRule::new(|| {
            Box::pin(async move {
                let mut messages = RuleMessages::default();
                messages.insert_dynamic("warning", |args| {
                    let reason = args.first().cloned().unwrap_or_else(|| "unknown".to_string());
                    format!("This is not allowed because {reason}")
                });

                RuleDefinition {
                    rule_name: "at-rule-empty-line-before".to_string(),
                    messages,
                    primary_option_array: false,
                    meta: Some(RuleMeta {
                        url: "https://stylelint.io/user-guide/rules/at-rule-empty-line-before".to_string(),
                        deprecated: false,
                        fixable: false,
                    }),
                }
            })
        }),
    );

    let lint_fn = Arc::new(|options: LinterOptions| {
        Box::pin(async move {
            let cwd = options.cwd.unwrap_or_else(|| ".".to_string());
            let code = options.code.clone();
            let result = LintResult {
                source: options.code_filename.clone(),
                deprecations: Vec::new(),
                invalid_option_warnings: Vec::new(),
                parse_errors: Vec::new(),
                errored: Some(false),
                warnings: Vec::new(),
                ignored: Some(false),
            };
            let mut rule_metadata = BTreeMap::new();
            rule_metadata.insert(
                "at-rule-empty-line-before".to_string(),
                RuleMeta {
                    url: "https://stylelint.io/user-guide/rules/at-rule-empty-line-before".to_string(),
                    deprecated: false,
                    fixable: false,
                },
            );

            LinterResult {
                cwd,
                results: vec![result],
                errored: false,
                report: String::new(),
                code,
                max_warnings_exceeded: None,
                reported_disables: DisableOptionsReport::default(),
                descriptionless_disables: DisableOptionsReport::default(),
                needless_disables: DisableOptionsReport::default(),
                invalid_scope_disables: DisableOptionsReport::default(),
                rule_metadata,
            }
        })
    });

    let resolve_config_fn = Arc::new(|_file_path: String, options: Option<ResolveConfigOptions>| {
        Box::pin(async move {
            if let Some(options) = options {
                if let Some(config) = options.config {
                    return Some(config);
                }
            }

            Some(Config::default())
        })
    });

    let create_linter_fn = Arc::new(|options: LinterOptions| InternalApi {
        cwd: options.cwd.clone().unwrap_or_else(|| ".".to_string()),
        options,
    });

    PublicApiFacade {
        lint_fn,
        resolve_config_fn,
        create_linter_fn,
        rules,
        formatters: Formatters::builtin(),
        utils: Utils,
        reference: ReferenceData::builtin(),
    }
}

pub fn plugin_reference(name: impl Into<String>) -> PluginReference {
    PluginReference::Named(name.into())
}

pub fn formatter_type_name(formatter: &FormatterType) -> &'static str {
    match formatter {
        FormatterType::Compact => "compact",
        FormatterType::Json => "json",
        FormatterType::String => "string",
        FormatterType::Tap => "tap",
        FormatterType::Unix => "unix",
        FormatterType::Verbose => "verbose",
    }
}
