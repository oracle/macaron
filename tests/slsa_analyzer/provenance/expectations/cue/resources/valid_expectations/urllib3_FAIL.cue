{
    target: "",
    predicate: {
        invocation: {
            configSource: {
                uri: =~"^git\\+https://github.com/urllib3/urllib3@refs/tags/[0-9]+.[0-9]+.[0-9a-z]+$"
                entryPoint: ".github/workflows/invalid.yml"
            }
        }
    }
}
