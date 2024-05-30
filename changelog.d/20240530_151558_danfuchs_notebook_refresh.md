### New features

- `NotebookRunner` flocks can now pick up changes to their notebooks without having to restart the whole mobu process. This refresh can happen via:
  - GitHub `push` webhook post to `/mobu/github/webhook` with changes to a repo and branch that matches the flock config
  - `monkeyflocker refresh <flock>`
  - `POST` to `/mobu/flocks/{flock}/refresh`
