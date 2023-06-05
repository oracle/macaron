{
    target: "micronaut-projects/micronaut-core",
    predicate: {
        invocation: {
            configSource: {
                uri: =~"^git\\+https://github.com/micronaut-projects/micronaut-core@refs/tags/v[0-9]+.[0-9]+.[0-9]+$"
                entryPoint: ".github/workflows/release.yml"
            }
        }
    }
}
