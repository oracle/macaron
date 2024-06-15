{
    target: "pkg:maven/io.github.behnazh-w.demo/example-maven-app",
    predicate: {
        buildDefinition: {
            externalParameters: {
                workflow: {
                    ref: "refs/heads/main",
                    repository: "https://github.com/behnazh-w/example-maven-app",
                    path: ".github/workflows/main.yaml"
                }
            }
        }
    }
}
