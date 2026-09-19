Desktop-sing 1.0 Privacy Statement
(Last updated: 2026-09-18)

We understand how important your personal information is to you. Desktop-sing is a local
utility. This statement explains what information it accesses, how that information is used,
and what it does **not** do. Installing or using this software means you have read and accepted
this statement.

1. What we collect: nothing
   This software has no accounts, no analytics, no telemetry and no advertising SDK, and it does
   not upload any of your data to our servers (we do not operate any servers).

2. What the software reads and writes locally (it stays on your computer)
   1. Settings and position memory: theme, font size, window position and so on, stored in
      %APPDATA%\Desktop-sing\config.json;
   2. Lyric cache and font library: lyrics retrieved by the app and fonts you download from the
      settings panel, stored under %APPDATA%\Desktop-sing\;
   3. System media information: the title, artist and playback position of the current track,
      read through the Windows System Media Transport Controls (SMTC). This is a local system
      capability provided by Windows. The software only reads information about media that is
      currently playing; it does not read your music files.

3. What network requests the software makes (download only, never upload)
   1. Lyric retrieval: queries the **public lyric endpoints** of QQ Music, NetEase Cloud Music,
      Kugou Music and LRCLIB. The request content is limited to the song title and artist name,
      and is used to fetch the matching lyrics;
   2. Font downloads: when you choose to download a font from the font library, the font file is
      fetched from that font's official distribution address or a mirror;
   3. There is no other network activity of any kind: no device information is collected, no usage
      habits are uploaded, and no data is sent back during update checks.

3a. About request headers (disclosed in full)
   Some music platforms' public endpoints only return results for common client types, so when
   requesting those endpoints the software sends a generic browser-type identifier together with a
   compatibility field marked as "PC client, client version 2.9.7". For LRCLIB and the update
   manifest endpoints the software identifies itself by its own name, Desktop-sing/1.0. These
   identifiers exist only to let the endpoints return lyric data normally. They **do not and cannot
   contain any of your personal information**, are not linked to your device or account, and are not
   used for identification or tracking. Lyrics and artwork come from the public endpoints of the
   platforms listed above, and this software has no affiliation, agency or partnership relationship
   with those platforms.

4. Third-party content
   Copyright in lyric content belongs to the respective rights holders; this software displays it
   for presentation purposes only. The availability of lyric endpoints is determined by the
   platforms concerned, and this software is not responsible for the accuracy or lawfulness of
   third-party content.

5. Deleting your data
   Uninstalling the software removes its installation directory. To erase all local data, delete the
   %APPDATA%\Desktop-sing\ folder: everything is deleted with that folder, it cannot be recovered,
   and we hold no copy of it.

6. Protection of minors
   This software does not collect any information from minors and contains no social or payment
   features.

7. Changes to this statement
   If this statement changes materially, the updated version and its date will be published in the
   new release's installer wizard and in the About window.

-- If you disagree with any part of this statement, please stop installing or using this software.
