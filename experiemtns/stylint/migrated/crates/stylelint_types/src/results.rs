use std::collections::BTreeMap;

use crate::options::Severity;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum StylelintWarningType {
    Deprecation,
    InvalidOption,
    ParseError,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EditInfo {
    pub range: (usize, usize),
    pub text: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Warning {
    pub line: u32,
    pub column: u32,
    pub end_line: Option<u32>,
    pub end_column: Option<u32>,
    pub fix: Option<EditInfo>,
    pub rule: String,
    pub severity: Severity,
    pub text: String,
    pub url: Option<String>,
    pub stylelint_type: Option<StylelintWarningType>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Deprecation {
    pub text: String,
    pub reference: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct InvalidOptionWarning {
    pub text: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ParseError {
    pub line: u32,
    pub column: u32,
    pub text: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct LintResult {
    pub source: Option<String>,
    pub deprecations: Vec<Deprecation>,
    pub invalid_option_warnings: Vec<InvalidOptionWarning>,
    pub parse_errors: Vec<ParseError>,
    pub errored: Option<bool>,
    pub warnings: Vec<Warning>,
    pub ignored: Option<bool>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DisableReportRange {
    pub rule: String,
    pub start: usize,
    pub end: Option<usize>,
}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct DisableReportEntry {
    pub source: Option<String>,
    pub ranges: Vec<DisableReportRange>,
}

pub type DisableOptionsReport = Vec<DisableReportEntry>;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MaxWarningsExceeded {
    pub max_warnings: u32,
    pub found_warnings: u32,
}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct RuleMeta {
    pub url: String,
    pub deprecated: bool,
    pub fixable: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct LinterResult {
    pub cwd: String,
    pub results: Vec<LintResult>,
    pub errored: bool,
    pub report: String,
    pub code: Option<String>,
    pub max_warnings_exceeded: Option<MaxWarningsExceeded>,
    pub reported_disables: DisableOptionsReport,
    pub descriptionless_disables: DisableOptionsReport,
    pub needless_disables: DisableOptionsReport,
    pub invalid_scope_disables: DisableOptionsReport,
    pub rule_metadata: BTreeMap<String, RuleMeta>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Position {
    pub line: u32,
    pub column: u32,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ProblemLocation {
    Span {
        start: Position,
        end: Position,
    },
    Index {
        index: usize,
        end_index: usize,
    },
    Word {
        word: String,
    },
    None,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProblemReport {
    pub rule_name: String,
    pub message: String,
    pub node_description: String,
    pub location: ProblemLocation,
    pub severity: Severity,
    pub fix: Option<EditInfo>,
}
