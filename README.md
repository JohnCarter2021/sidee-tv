<p align="center"><img src="assets/sidee-logo.png" width="180" alt="Sidee"></p>

# Sidee

**Your TV, your freedom.**

Sidee is a free, open-source tool that helps people make more of the TVs they already own. Its simple browser dashboard lets you connect to a compatible TV and manage additional web-app launcher tiles, without coding, command-line setup, or specialist knowledge.

Sidee is built around three principles:

- **Freedom and control:** Give people more choice over how they use their own devices.
- **Accessibility:** Make the process straightforward, even for first-time users.
- **Privacy and security:** Keep TV discovery and pairing on the local network, with authorization through the PIN shown on the TV.

Please read the scope notes below before installing: in v1 Sidee pairs with **one TV at a time** (use "Forget this TV" in the dashboard to pair another), the **native-install mode is not part of the v1 grid**, and the grid is a **catalogue of tiles** — it is not a guarantee that any particular web app will run well on any particular TV.

## TV front-end (`/tv/`, prototype)

Sidee can also serve a remote-friendly front-end on the same dashboard server, for TVs whose remote only scrolls on desktop websites. Start Sidee as usual, then open `http://<this-computer's-LAN-IP>:8787/tv/?key=<key-from-your-dashboard-URL>` in the TV browser (or add that address as a custom tile). Arrows move a visible focus box, OK opens, Back returns.

Zero-touch option: once a TV is paired, launching Sidee installs a **Sidee TV** tile on that TV automatically (and refreshes it if its address ever changes) — no URL to type, nothing to reinstall by hand. The tile just opens the `/tv/` menu. The dashboard address itself is now stable across restarts too: the access key and last-used port are saved in Sidee's state folder and reused, so an installed tile keeps working — on Android as well as desktop, since the app no longer pins a random port. The tile shows no icon (tile icons must be HTTPS; the dashboard serves plain HTTP on the LAN). The dashboard's status area reports the tile state (on your TV, waiting for pairing, TV not answering), and the tile is only installed when the TV actually answers its app list, so a slow TV never ends up with duplicates. If a stream fails, the player says so on screen and OK retries instead of sitting on black.

What it does today: browse AnimeX (home, catalog, schedule, show pages) with links rewritten to stay inside `/tv/`, and play episodes in a native `<video>` player (OK play/pause, left/right seek 10s, up/down volume). Sidee resolves each episode's stream server-side and proxies playlists and segments, attaching the Referer the stream host requires. Scope: AnimeX only, subtitles, default provider; no search yet. Not in any release yet — run from source to try it.

## Requirements

- Windows 10/11, macOS 15+ (Apple Silicon or Intel), Linux (Ubuntu LTS is the primary tested distro; the AppImage may work elsewhere), or Android 7.0+ for the phone APK (sideload only in v1)
- A compatible VIDAA TV and a computer or phone on the same home Wi-Fi/Ethernet network
- Internet access for the initial setup and any online experiences you choose to open on the TV

Compatibility varies by TV model and firmware. The primary tested firmware is U09.60 / V0000.09.60A.Q0707. Support for some other models is experimental; see the [compatibility notes](docs/toshiba-compatibility.md).

## Get started

Download the **0.2.0.1 release** from the [release page](https://github.com/JohnCarter2021/Sidee/releases/tag/v0.2.0.1). See the limits below and in the release notes before installing.

Release assets (SHA-256 checksums in `SHA256SUMS.txt` on the same page):

| Platform | Asset | What you get |
| --- | --- | --- |
| Windows | `Sidee-Windows-Exe.zip` | Portable exe (no installer) |
| Windows | `sidee-windows.zip` | Source ZIP (runs with `start-windows.bat`; downloads a pinned Python runtime on first launch) |
| macOS Apple Silicon | `Sidee-macOS-arm64.app.zip` + `.dmg` | App + DMG |
| macOS Intel | `Sidee-macOS-x64.app.zip` + `.dmg` | App + DMG |
| Linux x86_64 | `Sidee-Linux-x86_64.AppImage` | AppImage |
| Android | `app-debug.apk` | Sideload APK (debug build) |

### Windows

1. Download the `Sidee-Windows-Exe.zip` release asset and extract it.
2. Run the exe. Keep its window open while using the dashboard.
3. Follow the on-screen steps in the dashboard.

**SmartScreen note (unsigned beta):** the Windows build is not code-signed, so Windows may warn that it is from an unknown publisher. If you trust the downloaded artifact, you can click through the warning. Never disable SmartScreen or your antivirus to run Sidee. Signing is a separate, budgeted decision before a general release.

**Portable note:** there is no installer. Your pairing lives in your user profile (`~/.sidee/session.json`), not in the app folder, so moving or deleting the app folder does not by itself forget your TV — use "Forget this TV" in the dashboard for that.

If the browser does not open automatically, use the full dashboard link shown by the app, including its access key. If Windows requests network access, allow it on your trusted home network.

### macOS

1. Download the `Sidee-macOS-arm64` (Apple Silicon) or `Sidee-macOS-x64` (Intel) release asset.
2. Open the DMG, drag Sidee.app to Applications, and launch it.
3. Use **Open dashboard** in Sidee's control window.

**Important:** The current macOS builds are not signed or notarized. macOS may prevent them from opening automatically. If you trust the downloaded package, follow [Apple's instructions](https://support.apple.com/en-us/102445) for opening an unverified app. If prompted, grant local network access so Sidee can discover your TV. The builds are checked in CI but still require broader testing on physical Macs.

Sidee's control window must remain open while you use the dashboard; **Quit Sidee** stops the local dashboard service.

### Linux

1. Download the `Sidee-Linux-x86_64.AppImage` release asset.
2. Make it executable (`chmod +x Sidee-Linux-x86_64.AppImage`) and run it.
3. Follow the on-screen steps in the dashboard.

Ubuntu LTS is the primary tested distro. Other distros are not promised in v1; if the AppImage does not start on yours, please report the distro and version (see Beta below).

### Android (beta, sideload)

1. Download the `app-debug.apk` release asset on your phone.
2. Allow installing from this source when Android asks ("unknown apps" prompt — expected for a sideloaded beta, not a defect), then install the APK.
3. Open Sidee. The dashboard runs inside the app, on the phone only.

**Honest beta limit:** on the emulator, the app starts and its loopback dashboard starts cleanly (proven in CI). **Pairing a TV from the phone, and installing a tile from the phone, are not yet proven** — they need a TV or simulated TV test, which is still open. Until that test passes, treat phone-side pairing as experimental and keep the desktop dashboard as the proven path.

## Connect your TV

1. **Find TV:** Turn on your TV, put it on the same network as your computer, and select **Find TV**. Sidee uses the discovered address rather than assuming a fixed TV IP. If discovery fails, you can enter the address shown in the TV's network settings.
2. **Request code:** Select **Request code** and enter the four-digit PIN displayed on your TV, then choose **Confirm code**. Pairing requires this confirmation.
3. **Manage launcher tiles:** Choose an app in the grid and follow the confirmation steps. The grid lists built-in apps (Nuvio, Stremio, Jellyfin) plus your own custom apps; it does not currently accept arbitrary web-app URLs as built-ins.
4. **Forget this TV:** when paired, the dashboard shows a "Forget this TV" button. It deletes only the saved pairing on this device; tiles already on the TV stay there, and you can pair another TV afterwards.

Registered tiles remain in the TV launcher across restarts, even when Sidee is no longer running. The availability of the web experiences opened by those tiles depends on their own network requirements.

**Want to use your phone?** The desktop dashboard provides a locally generated QR code so you can open its controls on a phone connected to the same home network. Keep Sidee running on the computer and keep dashboard access links private.

## Updates

The dashboard footer has a **Check for updates** button. It asks GitHub Releases for the latest stable release and tells you if a newer version exists, with a download link. It never downloads or installs an update by itself. Beta (pre-release) builds are never offered by this check; see Beta below.

## Beta channel

Beta builds ship as **GitHub pre-releases**, not as public releases. A public release follows only after a beta soak, never directly from CI artifacts. Beta builds are marked as pre-releases on the release page; the in-app update check offers stable releases only.

If you hit a problem on a beta build, please report it with the [beta report template](.github/ISSUE_TEMPLATE/beta-report.md): TV model, firmware, platform and build, and the redacted diagnostic log from the dashboard's "Check my setup" step. Never include pairing tokens, PINs, or dashboard access keys in a report.

## How Sidee works

Sidee uses the TV's local control interface for network discovery, PIN-authorized pairing, and launcher management. The connection uses MQTT/TLS on port 36669. Sidee does not require an account or cloud service for discovery, pairing, or TV control.

Sidee is designed to use functions available to an authorized, paired TV client. It does not install native system software or modify the TV's operating system.

## Privacy and security

- **No Sidee telemetry:** TV discovery and control take place locally; Sidee does not require an account.
- **Consent-based pairing:** You must confirm the PIN shown on your TV.
- **Local credentials:** Saved pairing tokens remain in your user profile at `~/.sidee/session.json` (mode 600 on Unix; inherited user-profile permissions on Windows).
- **Protected dashboard access:** Treat dashboard links and saved pairing tokens as private. Only share access with people you trust on your home network.
- **Limited operations:** Sidee manages web launcher tiles through the TV's authorized control interface; it does not make system-level changes.

Web experiences opened from the TV launcher may make their own network connections independently of Sidee.

## Trademarks and app icons

Nuvio, Stremio, and Jellyfin are projects of their respective owners. Sidee uses their names and icons only to identify the tiles that install those apps; it is not affiliated with, or endorsed by, those projects. The Jellyfin tile uses an official-branded tile image; the Stremio card icon is bundled from the community VIDAA build's own icon; the Nuvio card uses its wordmark. If any project asks for a change, the icon or name will be changed.

Check recorded 2026-10-30: names and icons reviewed for nominative use (identifying the app a tile installs, no endorsement claim, no altered logos). A formal legal review before wide, signed distribution is still open and is required before Phase 5 — this note is not legal advice.

## Troubleshooting

If **Find TV** cannot locate your TV, check that both devices share the same network and that a VPN, guest Wi-Fi, or firewall is not blocking local discovery. The manual IP option checks that the destination responds as a compatible TV and that port 36669 is reachable; it never bypasses PIN authorization.

Some TVs advertise themselves rather than replying directly to discovery. In that case, keep the TV on and retry **Find TV**. For known firmware-specific pairing limitations, see the [compatibility notes](docs/toshiba-compatibility.md).

On macOS, check **System Settings → Privacy & Security → Local Network** and, if needed, the firewall permissions for Sidee. Diagnostic logs are stored at `~/Library/Logs/Sidee/sidee.log`. Keep logs containing private access data confidential.

## Development

With Python 3.9+ already installed, the dashboard can also be started from a source checkout:

```bash
python -m pip install -r requirements.txt
python sidee.py
```

Optional command-line interface:

```bash
python sidee.py discover
python sidee.py pair TV_IP
python sidee.py install PRESET_ID
python sidee.py list
python sidee.py launch PRESET_ID
python sidee.py refresh
```

Replace `TV_IP` with your TV's LAN address and `PRESET_ID` with an available built-in option. Pairing always requires the TV's authorization.

Run Python tests with `python -m unittest discover -s tests` and dashboard interaction tests with `node --test tests/test_dashboard_selection.js`.

Packaging information is in the [macOS build notes](docs/macos-build.md). Automated builds are available through [GitHub Actions](https://github.com/JohnCarter2021/Sidee/actions/workflows/build.yml). Android build notes are in [android/README.md](android/README.md).

## Why Sidee exists

Sidee began with a simple idea: people should have more freedom to use technology they already own. After a lot of experimentation, that idea became a small tool designed to make everyday tasks easier and more approachable. If it helps you, please consider supporting continued development.

☕ [Support Sidee on Ko-fi](https://ko-fi.com/sidee)

## License

MIT — see [LICENSE](LICENSE). Sidee is an independent project and is not affiliated with TV manufacturers. Use it only with devices you own or are authorized to manage.
