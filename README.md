<p align="center">
  <img src="docs/icon.png" width="96" alt="">
</p>

<h1 align="center">Jellyport</h1>

<p align="center">
  <b>The playlist manager for Plex and Jellyfin.</b><br>
  Copy, sync and build playlists across both servers, and find any title in your
  libraries. Free, open source and runs on Windows. No command line needed.
</p>

<p align="center">
  <a href="https://github.com/BintChar247/jellyport/releases"><img alt="Downloads" src="https://img.shields.io/github/downloads/BintChar247/jellyport/total?label=downloads&color=2ea44f"></a>
  <a href="https://github.com/BintChar247/jellyport/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/BintChar247/jellyport"></a>
  <a href="https://github.com/BintChar247/jellyport/stargazers"><img alt="Stars" src="https://img.shields.io/github/stars/BintChar247/jellyport?style=flat"></a>
</p>

<p align="center">
  <a href="https://github.com/BintChar247/jellyport/releases/latest"><b>⬇ Download for Windows</b></a> ·
  <a href="https://BintChar247.github.io/jellyport/">Website</a> ·
  <a href="https://github.com/BintChar247/jellyport/issues">Report a problem</a>
</p>

![Jellyport screenshot](docs/screenshot.png)

---

Running Plex and Jellyfin, or moving from one to the other? Your movies come across
easily, but your playlists don't. Jellyport shows both servers side by side, so you can
drag playlists across, keep them in sync in either direction, and build new ones from
anything in your libraries.

## Features

### Copy playlists with drag and drop
- **See both sides at once.** Plex playlists and movie libraries are on the left, and
  Jellyfin playlists are on the right.
- **Drag and drop** single movies, a selection, or whole playlists.
- **Preview before anything changes.** New items show in green and missing items show
  in red. Nothing is written until you click **Copy to Jellyfin**.

### ⇄ Sync playlists in either direction
- Compare same-named playlists on both servers and copy the missing entries
  **Jellyfin → Plex**, **Plex → Jellyfin**, or **both ways**.
- Playlists that exist on only one side are created on the other.
- Sync only adds entries; it never removes anything, so it's safe to run again.

### 🔎 Title Finder
- **Search all your libraries** on Plex or Jellyfin: **Starts with**, **Contains**,
  **Does not contain**, **Ends with**, **Regex**, or **Code (ABC-123)** for titles that
  start with a letter code and a number.
- **Two filters at once**, joined by **AND** or **OR**, each on the title or the file name.
- **Group by prefix** lists every first-N-letter prefix with a count.
- **＋ Create playlist** from the titles you select, on Plex, Jellyfin or both, or add
  them to an existing playlist.
- **📂 Open folder** shows a title's file in File Explorer, and **Copy paths** copies
  Windows-ready network paths (`\\server\Share\…`).
- **Date added** column (sortable), plus **Export CSV** (opens in Excel) and **Copy titles**.

### 🎨 A dark skin
- Jellyport has its own dark look with purple and amber accents and dark Windows
  title bars. Prefer the standard Windows style? Pick **Classic Windows** under
  **Settings → Appearance**.

### Built to be safe
- **Smart matching.** Items are matched across servers by file path, IMDb, TMDb or TVDb
  ID, or title and year. This works even when one server runs in Docker and sees your
  NAS folders under different paths.
- **No duplicates and no deletions.** Items already in a playlist are skipped, and
  Jellyport never removes anything from your playlists.
- **Your data stays on your network.** Jellyport talks only to your own servers. It
  has no accounts and no tracking.
- **A command-line version is included** for copying everything in one go or running
  it on a schedule.

## Install

1. Download **`Jellyport-Setup-x.y.z.exe`** from the
   [latest release](https://github.com/BintChar247/jellyport/releases/latest).
2. Run it. The installer doesn't need admin rights.

> **Windows SmartScreen** may warn about an "unrecognized app", because the installer
> isn't code-signed. Click **More info → Run anyway**. You can always build it
> yourself from source (see below).

Prefer Python? Jellyport uses only the standard library, so this works on Windows,
macOS and Linux:

```bash
python jellyport.py
```

## Setup

On first launch, the **Settings** window opens.

| Setting | Where to find it |
|---|---|
| **Plex URL** | `http://<server-ip>:32400` |
| **Plex token** | In Plex Web, open any movie, then choose **⋯ → Get Info → View XML**. Copy the value after `X-Plex-Token=` in the address bar. |
| **Jellyfin URL** | The address you use to open Jellyfin, e.g. `http://<server-ip>:8096` |
| **Jellyfin API key** | **Dashboard → API Keys → +** |
| **Jellyfin user** | The user who should own the playlists |
| **Path mappings** | Optional. See below. |
| **Open files on this PC** | Optional. How Title Finder's **Open folder** and **Copy paths** reach your files, e.g. `/volume1/Data => Z:\`. Leave it empty on Synology to use `\\server\Share\…` automatically. |

### Path mappings (Docker / NAS users)

If Plex and Jellyfin see the same files under different paths, add a mapping so the
file-path match works. This is common when one of them runs in Docker. For example:

```
/volume1/video/Movies  =>  /media/movies
```

To find the paths:
- **Plex:** **Settings → Libraries → Edit → Add folders**
- **Jellyfin:** **Dashboard → Libraries**

Without a mapping, Jellyport still matches movies by IMDb or TMDb ID, or by title
and year.

## How to use

1. Click **Connect**. Your playlists load on both sides.
2. Expand a Plex playlist or library, then select movies. Use Ctrl-click or Shift-click
   to pick several.
3. **Drag** them onto a Jellyfin playlist:
   - Drop onto an existing playlist to add the movies to it.
   - Drop a whole Plex playlist onto empty space to create a Jellyfin playlist with
     the same name.
   - Use **＋ New playlist…** to start an empty playlist.
4. Check the green (pending) and red (not found) rows, then click **Copy to Jellyfin**.

### Sync playlists

1. Click **⇄ Sync playlists…** in the toolbar. The first comparison reads your Plex
   library, which can take a few seconds.
2. Choose **Jellyfin → Plex**, **Plex → Jellyfin** or **Both ways**.
3. Each playlist pair shows how many entries are on each side, how many will be added,
   and how many can't be matched. Double-click a row to see the unmatched entries.
4. Playlists that need changes are ticked. Click a row to untick it, then click
   **Sync ticked playlists**.

Plex *smart* playlists can be read but not added to, so they're skipped as a target.
Running sync again only adds what's new.

### Title Finder

1. Click **🔎 Title Finder…** in the toolbar.
2. Pick a server and a library (or **All libraries**). Titles load automatically.
3. Type in **Find** and choose **Starts with**, **Code (ABC-123)**, **Contains**,
   **Does not contain**, **Ends with** or **Regex**. You can search the title or the
   file name.
   - To narrow it down, fill in the second row too and pick **AND** (both must match)
     or **OR** (either can match). Each row can search a different field. Leave the
     second box empty to use one filter, and use **Clear filters** to start again.
4. Use **Group by prefix** to see every prefix with its count, and click one to list its
   titles. Click a column header, such as **Date added**, to sort.
5. Select titles (Ctrl-click or Shift-click), then:
   - **＋ Create playlist…** to create a playlist on **Plex**, **Jellyfin** or **Both**,
     or pick an existing playlist to add to. Titles already in it are skipped, and TV
     shows are left out because playlists hold episodes. Titles from one server are
     matched on the other automatically.
   - **📂 Open folder**, or double-click a title, to show its file in File Explorer.
   - **Copy paths** to copy the files' Windows paths, one per line.
   - **Copy titles** or **Export CSV…**. With nothing selected, these use every title
     in the list.

Title Finder only changes your servers when you click **Create** in Create playlist.

## Command line

```bash
python jellyport_cli.py --list
```

```bash
python jellyport_cli.py --dry-run
```

```bash
python jellyport_cli.py -p "Date Night"
```

```bash
python jellyport_cli.py
```

| Option | What it does |
|---|---|
| `--list` | Lists the Plex playlists and exits |
| `--dry-run` | Shows the matches and planned changes without changing anything |
| `-p NAME` | Copies only this playlist (you can repeat it) |
| `--replace` | Rebuilds Jellyfin playlists that already exist |
| `--include-smart` | Also copies Plex smart playlists, as a fixed snapshot |
| `--prefix TEXT` | Adds a prefix to the names of the created playlists |

The command-line version reads `config.json` from the current folder. Copy
`config.example.json` to start one.

## Where settings are stored

| | Location |
|---|---|
| Installed app | `%APPDATA%\Jellyport\config.json` |
| Running from source | `config.json` next to the script |

Your token and API key are stored only in that file on your PC.

## Building the installer

```bash
python -m pip install pyinstaller
```

```bash
winget install JRSoftware.InnoSetup
```

```bash
powershell -ExecutionPolicy Bypass -File installer\build.ps1
```

The installer is written to `dist\`.

## Limitations

- Video playlists only (movies and episodes). Music playlists aren't supported yet.
- The left side lists movie libraries. TV episodes that are already in a Plex playlist
  still copy.
- Plex smart playlists are copied as a snapshot. Jellyfin has no smart playlists.
- Sync adds entries but never removes them, so a movie removed from a playlist on one
  side stays on the other until you remove it there too.

## Contributing

Bug reports and pull requests are welcome. Please open an
[issue](https://github.com/BintChar247/jellyport/issues) first for larger changes.

## License

[MIT](LICENSE). Jellyport isn't affiliated with Plex Inc. or the Jellyfin project.
