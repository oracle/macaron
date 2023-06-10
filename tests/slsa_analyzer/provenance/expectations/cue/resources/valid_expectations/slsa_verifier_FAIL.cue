{
    target: "slsa-framework/slsa-verifier",
    predicate: {
        invocation: {
            configSource: {
                uri: =~"^git\\+https://github.com/fail/slsa-verifier@refs/tags/v[0-9]+.[0-9]+.[0-9a-z]+$"
                entryPoint: ".github/workflows/release.yml"
            }
        }
    }
}
