{
    target: "pkg:github/ossf/scorecard",
    predicate: {
        invocation: {
            configSource: {
                uri: =~"^git\\+https://github.com/ossf/scorecard@refs/tags/v[0-9]+.[0-9]+.[0-9a-z]+$"
                entryPoint: ".github/workflows/goreleaser.yaml"
            }
        }
    }
}
