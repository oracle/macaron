## Configuration
Macaron allows the user to provide configurations for the analysis by using a yaml file. The schema for the config file can be seen at [target_config_schema.yaml](./target_config_schema.yaml).

Let's go through the configurations that the user can use. The example below is the configuration for running Macaron against the [apache/maven](https://github.com/apache/maven) repository.

```
target:
  id: "apache/maven"
  branch: ""
  digest: ""
  path: "https://github.com/apache/maven.git"

dependencies:
  - id: "junit-jupiter-engine"
    branch: ""
    digest: ""
    path: "https://github.com/junit-team/junit5.git"

  ...
```

We can provide values for 2 fields:
- `target`: indicate the main repository of the analysis. In `target`, we can specify these fields:
  - `target`: Specify the target repository we want to analyze.
  - `branch`: The name of the branch for Macaron to checkout and run the analysis on. (optional)
  - `digest`: The hash of the commit (in full form) to checkout in the current branch. (optional).
  - `path`: The path of the target repository.
- `dependencies`: a list of repositories for each dependency of the main repository that you want to analyze. Each of the member of this list has the same fields as the main repository `target`. The `dependencies` list is optional for the analysis.


**Note**: optional fields can be removed from the configuration if not specified.
