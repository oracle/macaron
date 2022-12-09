# Contributing to Macaron

Oracle welcomes contributions to this repository from anyone.

If you want to submit a pull request to fix a bug or enhance an existing feature, please first open an issue and link to that issue when you submit your pull request.

If you have any questions about a possible submission, feel free to open an issue too.

## Opening issues

For bugs or enhancement requests, please file a GitHub issue unless it's security related. When filing a bug remember that the better written the bug is, the more likely it is to be fixed. If you think you've found a security vulnerability, do not raise a GitHub issue and follow the instructions in our [security policy](./SECURITY.md).

## Pull requests (PRs)

We welcome your code contributions. Before submitting code via a pull request, you will need to have signed the [Oracle Contributor Agreement][OCA] (OCA) and your commits need to include the following line using the name and e-mail address you used to sign the OCA:

```text
Signed-off-by: Your Name <you@example.org>
```

This can be automatically added to pull requests by committing with `--sign-off`
or `-s`, e.g.

```text
git commit --signoff
```

Only pull requests from committers that can be verified as having signed the OCA
can be accepted.

### Pull request process

1. Ensure there is an issue created to track and discuss the fix or enhancement
   you intend to submit.
2. Fork this repository.
3. Create a branch in your fork to implement the changes. We recommend using the issue number as part of your branch name, e.g. `1234-fixes`.
4. The name of the PR should follow the convention of [commit messages](#commit-messages).
5. Ensure that any documentation is updated with the changes that are required by your change.
6. Ensure that any samples are updated if the base image has been changed.
7. Submit the pull request. *Do not leave the pull request blank*. Explain exactly what your changes are meant to do and provide simple steps on how to validate. your changes. Ensure that you reference the issue you created as well.
8. We will assign the pull request to 2-3 people for review before it is merged.

### Commit messages

- Commit messages should follow the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) convention.
- Note that the commit types `fix`, `feat`, and `refactor` should only be used for commits appearing in the next release of the project as a package.
  - The project uses [`commitizen`](https://github.com/commitizen-tools/commitizen) on the commit history to automatically create the `CHANGELOG.md` file. `commitizen` takes into account commits typed with `fix`, `feat` and `refactor`.
  - For small commits to fix a PR during code review, the commit type should be `chore` (instead of `fix` or `refactor`).

### Code review

- A PR must be reviewed and approved by at least one maintainer of the project.
- During code review, fixes to the PR should be new commits (no rebasing).
- Each commit should be kept small for easy review.
- As mentioned in the [commit messages](#commit-messages) section, the type of these commits should be `chore`.

### CI tests

- Each new feature or change PR should provide meaningful CI tests.
- All the tests and security scanning checks in CI should pass and achieve the expected coverage.

### Merging PRs

- Before a PR is merged, all commits in the PR should be rebased into meaningful commits.
  - Its commit message should be the same as the PR title if there only one commit.
- PRs should be merged using the fast-forward only strategy.
  - This ensures a linear commit history for the project.
  - If the fast-forward merge does not work due to new commits on `main` (in this case the two branches diverge and the PR branch cannot be fast-forwarded), the PR branch should be rebased onto `main` first.

## Branching model

* The `main` branch is only used for releases and the `staging` branch is used for development. We only merge to `main` when we want to create a new release for Macaron.

## Code of conduct

Follow the [Golden Rule](https://en.wikipedia.org/wiki/Golden_Rule). If you'd like more specific guidelines, see the [Contributor Covenant Code of Conduct][COC].

[OCA]: https://oca.opensource.oracle.com
[COC]: https://www.contributor-covenant.org/version/1/4/code-of-conduct/