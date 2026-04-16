use stylelint_types::{default_public_api, PublicApiFacade};

const BINDINGS_INDEX: &str = include_str!("../../../bindings/node/index.mjs");
const BINDINGS_PACKAGE_JSON: &str = include_str!("../../../bindings/node/package.json");

pub fn stylelint_facade() -> PublicApiFacade {
    default_public_api()
}

pub fn bindings_source() -> &'static str {
    BINDINGS_INDEX
}

pub fn bindings_package_json() -> &'static str {
    BINDINGS_PACKAGE_JSON
}

pub fn required_surface_members() -> &'static [&'static str] {
    &[
        "lint",
        "rules",
        "formatters",
        "createPlugin",
        "resolveConfig",
        "utils",
        "reference",
        "module.exports",
    ]
}
