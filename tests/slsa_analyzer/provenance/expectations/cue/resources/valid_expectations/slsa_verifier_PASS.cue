{
    target: "pkg:github.com/slsa-framework/slsa-verifier",
    predicate: {
        invocation: {
            configSource: {
                uri: =~"^git\\+https://github.com/slsa-framework/slsa-verifier@refs/tags/v[0-9]+.[0-9]+.[0-9a-z]+$"
                entryPoint: ".github/workflows/release.yml"
            }
        }
    }
}
