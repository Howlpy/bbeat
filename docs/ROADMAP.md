# Roadmap

This is an honest, informal list. Nothing here is a promise or has a date.

## Done (recent highlights)

- Native Android app (Capacitor) with GitHub Releases (`bbeat-X.Y.Z.apk`), Android Auto, back button handling, native icon and splash screen.
- Offline mode: instant offline detection, same UI with non-downloaded tracks dimmed, playback continues with downloaded tracks of the current queue.
- Network resilience: GET retries and data reload on reconnect.
- Calm redesign: design tokens, bundled Manrope font, no gradients; simpler navigation with a Library hub.
- Weekly genre charts (last 7 days, server-wide, ranked by distinct listeners then plays, shows who listened).
- Wrapped as stories per period (week, month, year, all time) with a shareable 1080x1920 image.
- Import from Spotify, YouTube and SoundCloud plus local upload, showing who imported what.
- Playlist and album `.zip` export.
- Performance: immutable caching for hashed assets, WebP cover thumbnails, SQLite pragmas.
- Genre detection: voting cascade (Last.fm, Deezer, iTunes, Wikidata), per-artist consistency, optional provider-agnostic AI classifier with review queue and per-artist locking.
- Subsonic API compatibility, multi-user with admin approval, live "now playing".

## Next

- **Listening parties**: a shared, temporary queue where friends add and reorder songs, while the music plays on the host device.
- **Queue improvements**: reorder, play next, clear. Today the queue only supports removing items and is not persisted across restarts (a persistent queue is part of this).
- **Interface language switching (i18n)**: Spanish and English UI. The interface is currently Spanish only.
- **Genre classifier improvements**: better handling of obscure artists, easier bulk review in Admin, more evidence sources.
- **Audio-based classification (optional)**: classify genre from the audio itself for tracks the metadata sources cannot resolve.

## Ideas

- Bulk edit and move tracks.
- Import from Apple Music and Deezer.
- Rate limiting for instances exposed to the internet.
- A native iOS app (today iPhone users rely on Subsonic clients).
- Screenshots and a short demo in the README.

Suggestions are welcome: open an issue on GitHub.
