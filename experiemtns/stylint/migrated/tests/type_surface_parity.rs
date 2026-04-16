use std::future::Future;
use std::pin::Pin;
use std::sync::{Arc, Mutex};
use std::task::{Context, Poll, RawWaker, RawWakerVTable, Waker};

use stylelint_migrated::{
    bindings_package_json,
    bindings_source,
    required_surface_members,
    stylelint_facade,
    CheckAgainstRuleOptions,
    Config,
    FormatterSelector,
    FormatterType,
    LinterOptions,
    PluginReference,
    ProblemLocation,
    ProblemReport,
    ResolveConfigOptions,
    RuleMessages,
    RuleOptionDescription,
    Severity,
};

fn block_on<F: Future>(future: F) -> F::Output {
    let waker = noop_waker();
    let mut context = Context::from_waker(&waker);
    let mut future = Box::pin(future);

    loop {
        match Future::poll(Pin::as_mut(&mut future), &mut context) {
            Poll::Ready(value) => return value,
            Poll::Pending => std::thread::yield_now(),
        }
    }
}

fn noop_waker() -> Waker {
    // Safety: the no-op waker never dereferences the data pointer and only
    // uses it to satisfy the RawWaker API for immediately-ready futures.
    unsafe { Waker::from_raw(RawWaker::new(std::ptr::null(), &VTABLE)) }
}

unsafe fn clone_raw_waker(_: *const ()) -> RawWaker {
    RawWaker::new(std::ptr::null(), &VTABLE)
}

unsafe fn wake_raw_waker(_: *const ()) {}

unsafe fn wake_by_ref_raw_waker(_: *const ()) {}

unsafe fn drop_raw_waker(_: *const ()) {}

static VTABLE: RawWakerVTable = RawWakerVTable::new(
    clone_raw_waker,
    wake_raw_waker,
    wake_by_ref_raw_waker,
    drop_raw_waker,
);

#[test]
fn preserves_resolve_config_to_lint_chain() {
    let api = stylelint_facade();
    let config = block_on(api.resolve_config(
        "path",
        Some(ResolveConfigOptions {
            config: Some(Config {
                plugins: vec![PluginReference::Named("custom-plugin".to_string())],
                formatter: Some(FormatterSelector::Named(FormatterType::Json)),
                ..Config::default()
            }),
            config_basedir: Some("path".to_string()),
            config_file: Some("path".to_string()),
            cwd: Some("path".to_string()),
        }),
    ))
    .expect("resolve_config should preserve compatibility boundary");

    let result = block_on(api.lint(LinterOptions {
        config: Some(config),
        cwd: Some("path".to_string()),
        code: Some(String::new()),
        code_filename: Some("inline.css".to_string()),
        ..LinterOptions::default()
    }));

    assert_eq!(result.cwd, "path");
    assert_eq!(result.results.len(), 1);
    assert_eq!(result.code.as_deref(), Some(""));
    assert!(result.rule_metadata.contains_key("at-rule-empty-line-before"));
}

#[test]
fn preserves_utils_plugin_and_reference_surface() {
    let api = stylelint_facade();

    let mut messages = RuleMessages::default();
    messages.insert_static("problem", "This a rule problem message");
    messages.insert_dynamic("warning", |args| {
        format!(
            "This is not allowed because {}",
            args.first().cloned().unwrap_or_default()
        )
    });
    messages.insert_dynamic("withNarrowedParam", |args| {
        format!(
            "Mixin not allowed: {}",
            args.first().cloned().unwrap_or_default()
        )
    });

    let scoped_messages = api.utils.rule_messages("sample-rule", messages);
    assert_eq!(
        scoped_messages.static_message("problem"),
        Some("This a rule problem message (sample-rule)")
    );
    assert_eq!(
        scoped_messages.render("warning", &[String::from("reason")]),
        Some("This is not allowed because reason (sample-rule)".to_string())
    );
    assert_eq!(
        scoped_messages.render("withNarrowedParam", &[String::from("mixin")]),
        Some("Mixin not allowed: mixin (sample-rule)".to_string())
    );

    let rule = block_on(
        api.rules
            .get("at-rule-empty-line-before")
            .expect("rule should exist in registry")
            .load(),
    );
    let plugin = api.create_plugin("sample-rule", rule.clone());
    assert_eq!(plugin.rule_name, "sample-rule");
    assert_eq!(plugin.rule.rule_name, "at-rule-empty-line-before");

    let mut lint_result = stylelint_migrated::LintResult::default();
    api.utils.report(
        &mut lint_result,
        ProblemReport {
            rule_name: "sample-rule".to_string(),
            message: "Reported warning".to_string(),
            node_description: "root".to_string(),
            location: ProblemLocation::Word {
                word: "foo".to_string(),
            },
            severity: Severity::Warning,
            fix: None,
        },
    );
    assert_eq!(lint_result.warnings.len(), 1);

    let seen_warning = Arc::new(Mutex::new(None));
    let seen_warning_ref = Arc::clone(&seen_warning);
    block_on(api.utils.check_against_rule(
        CheckAgainstRuleOptions {
            rule_name: "at-rule-empty-line-before".to_string(),
            rule_settings: None,
            root_description: "root".to_string(),
            result_source: None,
            fix: true,
        },
        |warning| {
            let mut slot = seen_warning_ref
                .lock()
                .expect("warning capture mutex should not be poisoned");
            *slot = Some(warning);
        },
    ));
    let warning = seen_warning
        .lock()
        .expect("warning capture mutex should not be poisoned")
        .clone()
        .expect("checkAgainstRule should emit a warning");
    assert_eq!(warning.rule, "at-rule-empty-line-before");
    assert!(warning.fix.is_some());

    let shorthand = api
        .reference
        .longhand_sub_properties_of_shorthand_properties
        .get("border-color")
        .expect("reference data should preserve shorthand mapping");
    assert!(shorthand.contains("border-top-color"));
}

#[test]
fn preserves_formatter_and_node_surface_contract() {
    let api = stylelint_facade();
    let formatter = block_on(api.formatters.json.load());
    let formatted = formatter(
        &[],
        &stylelint_migrated::LinterResult {
            report: "report body".to_string(),
            ..stylelint_migrated::LinterResult::default()
        },
    );
    assert_eq!(formatted, "json: report body");

    let source = bindings_source();
    let package_json = bindings_package_json();

    for member in required_surface_members() {
        assert!(
            source.contains(member) || package_json.contains(member),
            "compatibility shim should mention {member}",
        );
    }

    assert!(source.contains("export default stylelint;"));
    assert!(source.contains("export { stylelint as 'module.exports' };"));
    assert!(package_json.contains("\"type\": \"module\""));
}

#[test]
fn preserves_validation_semantics_for_required_options() {
    let api = stylelint_facade();
    assert!(api.utils.validate_options(
        "sample-rule",
        &[RuleOptionDescription {
            actual: Some("configured".to_string()),
            optional: false,
        }],
    ));
    assert!(!api.utils.validate_options(
        "sample-rule",
        &[RuleOptionDescription {
            actual: None,
            optional: false,
        }],
    ));
}
