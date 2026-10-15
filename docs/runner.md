# The runner

The runner is the program behind the page. It keeps your workspace, runs each deck's steps with your own assistant, and waits for you at every decision. This page will say more about it; for now it describes the values every studio shares.

## Shared values

Presentation Studio, Training Studio and Blog Studio keep the values they share in one file, `~/.config/studios-config.json` (`STUDIOS_CONFIG` names another place), and nowhere else. Change one of these values in any studio and all three use it from their next read.

| Key | In Presentation Studio | Saved from |
| --- | --- | --- |
| `team.repository` | The team repository. Set-up offers it where this computer has joined none, and Status and Settings say when it is not the one this computer's workspace is a copy of. | Set-up, when it joins another team repository |
| `team.branch` | The branch, for a new workspace in that repository. A workspace your team has set up already keeps the branch its `hub.json` names. | Set-up, with a new team repository, where the file names no branch for it |
| `share` | `"decision"` shares after each decision, `"asked"` only when you ask. Any other value is `"decision"`. Used only for a team repository. | Set-up, for a team repository |
| `person.name` | Your name, as your teammates see who runs a deck and who decided what. | Set-up and Settings |
| `assistant.agent`, `.model`, `.effort` | The default assistant, its model and its reasoning level. A value Presentation Studio would refuse is its built-in default: Claude Code, with the model and level left to it. | Set-up and Settings |
| `brand.repository`, `.release` | Where the brand skill is installed and upgraded from. An address that carries a password or token is refused, and a release needs a repository. | Settings, "Brand skill" |
| `brand.brand`, `.variant` | The brand and variant a new deck is offered first, when the brand skill on this computer has them. | Set-up and Settings |
| `output` | `"google"` makes a new deck Google Slides, `"pptx"` PowerPoint. | Set-up and Settings |

- **Saving writes only what changed.** Only the members you changed are written, and only where the file says otherwise. Everything else in the file, including what other studios keep there, stays as it was, byte for byte. The file is replaced whole or not at all. A folder on this computer is not a team repository, so it never writes `team` or `share`.
- **What stays here.** The limits, how slide previews are made, how many decks run at once, which brand skill to use when there are several, notifications and looking for updates belong to Presentation Studio on this computer alone, in its own settings.
- **When the file cannot be read.** Presentation Studio carries on with its built-in defaults, says so in one sentence on set-up and Status, and refuses to save a shared value until the file can be read. It never writes over the file.
- **When the team repository changes elsewhere.** The workspace you joined is a copy of a repository, kept in Presentation Studio's own data folder. If another studio changes `team.repository`, Presentation Studio carries on in the copy it has and never moves by itself. Status and Settings say that your studios now share another repository, with "Join it", which opens set-up filled in with it. Joining writes the repository, and its branch, into the shared file.
- **From an earlier version.** Earlier versions kept some of these values on this computer. When the runner starts, it writes each of them into the shared file where the file has none, with the team repository and branch this computer joined, and then removes them from its own settings. A value the file already has is left as it is, and Status and Settings say once which ones those were, until you choose "Got it". While the file cannot be read nothing moves, and it is tried again at the next start.
