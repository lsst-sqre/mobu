<!-- Delete the sections that don't apply -->

### Backwards-incompatible changes

- The existing refresh functionality is now a GitHub app integration (from a simple webhook integration). This requires new Phalanx secrets to be sync'd, and a new GitHub app to be added to repos that want the functionality. Special care has been taken to not leave these checks in a forever-in-progress state, even in the case of (graceful) mobu shutdown/restart

### New features

- A GitHub app integration to generate GitHub actions checks for commits pushed to notebook repo branches that are part of active PRs. These checks trigger and report on a solitary Mobu run of the changed notebooks in the commit.

### Other changes

- Python 3.12.3 -> 3.12.4
