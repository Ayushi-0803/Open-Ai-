use std::collections::BTreeMap;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Severity {
    Warning,
    Error,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FixMode {
    Lax,
    Strict,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FormatterType {
    Compact,
    Json,
    String,
    Tap,
    Unix,
    Verbose,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FormatterSelector {
    Named(FormatterType),
    Inline(String),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CustomSyntax(pub String);

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct GlobbyOptions {
    pub cwd: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RuleValue {
    Bool(bool),
    Number(i64),
    String(String),
    StringList(Vec<String>),
    Object(BTreeMap<String, RuleValue>),
}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct RuleSettings {
    pub primary: Option<RuleValue>,
    pub secondary: BTreeMap<String, RuleValue>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PluginReference {
    Named(String),
    Inline(String),
}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct LanguageSyntaxOptions {
    pub at_rules: BTreeMap<String, String>,
    pub properties: BTreeMap<String, String>,
    pub types: BTreeMap<String, String>,
    pub units: BTreeMap<String, Vec<String>>,
}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct DirectionalityOptions {
    pub block: Option<String>,
    pub inline: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct LanguageOptions {
    pub syntax: Option<LanguageSyntaxOptions>,
    pub directionality: Option<DirectionalityOptions>,
}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct ConfigOverride {
    pub files: Vec<String>,
    pub name: Option<String>,
    pub custom_syntax: Option<CustomSyntax>,
    pub rules: BTreeMap<String, RuleSettings>,
}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct Config {
    pub extends: Vec<String>,
    pub plugins: Vec<PluginReference>,
    pub ignore_files: Vec<String>,
    pub rules: BTreeMap<String, RuleSettings>,
    pub quiet: Option<bool>,
    pub formatter: Option<FormatterSelector>,
    pub default_severity: Option<Severity>,
    pub ignore_disables: Option<bool>,
    pub report_needless_disables: Option<bool>,
    pub report_invalid_scope_disables: Option<bool>,
    pub report_descriptionless_disables: Option<bool>,
    pub report_unscoped_disables: Option<bool>,
    pub max_warnings: Option<u32>,
    pub configuration_comment: Option<String>,
    pub overrides: Vec<ConfigOverride>,
    pub custom_syntax: Option<CustomSyntax>,
    pub reference_files: Vec<String>,
    pub language_options: Option<LanguageOptions>,
    pub allow_empty_input: Option<bool>,
    pub cache: Option<bool>,
    pub fix: Option<bool>,
    pub validate: Option<bool>,
}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct LinterOptions {
    pub files: Vec<String>,
    pub globby_options: Option<GlobbyOptions>,
    pub cache: Option<bool>,
    pub cache_location: Option<String>,
    pub cache_strategy: Option<String>,
    pub code: Option<String>,
    pub code_filename: Option<String>,
    pub config: Option<Config>,
    pub config_file: Option<String>,
    pub config_basedir: Option<String>,
    pub cwd: Option<String>,
    pub ignore_disables: Option<bool>,
    pub ignore_path: Vec<String>,
    pub ignore_pattern: Vec<String>,
    pub report_descriptionless_disables: Option<bool>,
    pub report_needless_disables: Option<bool>,
    pub report_invalid_scope_disables: Option<bool>,
    pub report_unscoped_disables: Option<bool>,
    pub max_warnings: Option<u32>,
    pub custom_syntax: Option<CustomSyntax>,
    pub formatter: Option<FormatterSelector>,
    pub disable_default_ignores: Option<bool>,
    pub fix: Option<FixModeOrBool>,
    pub compute_edit_info: Option<bool>,
    pub allow_empty_input: Option<bool>,
    pub quiet: Option<bool>,
    pub quiet_deprecation_warnings: Option<bool>,
    pub validate: Option<bool>,
    pub suppress_all: Option<bool>,
    pub suppress_location: Option<String>,
    pub suppress_rule: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FixModeOrBool {
    Bool(bool),
    Mode(FixMode),
}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct ResolveConfigOptions {
    pub config: Option<Config>,
    pub config_basedir: Option<String>,
    pub config_file: Option<String>,
    pub cwd: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PostcssPluginOptions {
    LinterOptions(LinterOptions),
    Config(Config),
}
